from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from shreks_brain.features.models import (
    ANCHOR_1M_MAX_AGE_MS,
    ANCHOR_1M_MIN_AGE_MS,
    ANCHOR_5M_MAX_AGE_MS,
    ANCHOR_5M_MIN_AGE_MS,
    ANCHOR_15M_MAX_AGE_MS,
    ANCHOR_15M_MIN_AGE_MS,
    MarketFeaturePoint,
)

from .models import (
    OBSERVER_MARKET_SCHEMA_VERSION,
    ObservedMarketWindow,
    ObserverCandidateIdentity,
    ObserverMarketReadPolicy,
    ObserverMarketSnapshot,
)


_REQUIRED_COLUMNS = {
    "token_candidates": frozenset(
        {
            "id",
            "mint",
            "pair_address",
            "discovery_source",
            "discovered_at_unix_ms",
            "venue",
        }
    ),
    "market_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "observed_at_unix_ms",
            "source",
            "source_observed_at_unix_ms",
            "venue",
            "pair_address",
            "price_usd",
            "liquidity_usd",
            "volume_m5_usd",
            "volume_h1_usd",
            "buys_m5",
            "sells_m5",
            "buys_h1",
            "sells_h1",
            "pair_created_at_unix_ms",
        }
    ),
}

_MARKET_SELECT = """SELECT
    id, candidate_id, observed_at_unix_ms, source,
    source_observed_at_unix_ms, venue, pair_address,
    price_usd, liquidity_usd, volume_m5_usd, volume_h1_usd,
    buys_m5, sells_m5, buys_h1, sells_h1, pair_created_at_unix_ms
FROM market_snapshots"""


class ObserverMarketReadError(ValueError):
    """Raised when observer market evidence cannot be read safely."""


class ObserverMarketStore:
    """Read-only access to the normalized Rust observer market database."""

    def __init__(self, database_path: str | os.PathLike[str]) -> None:
        try:
            self._database_path = Path(database_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ObserverMarketReadError("invalid observer database path") from error

        connection = self._connect()
        try:
            self._validate_schema(connection)
        finally:
            connection.close()

    def resolve_candidate(
        self,
        mint: str,
        *,
        pair_address: str | None = None,
        discovery_source: str | None = None,
    ) -> ObserverCandidateIdentity:
        _require_non_empty_string("mint", mint)
        _require_optional_string("pair_address", pair_address)
        _require_optional_non_empty_string("discovery_source", discovery_source)

        clauses = ["mint = ?"]
        parameters: list[object] = [mint]
        if pair_address is not None:
            clauses.append("pair_address = ?")
            parameters.append(pair_address)
        if discovery_source is not None:
            clauses.append("discovery_source = ?")
            parameters.append(discovery_source)

        query = f"""SELECT
                        id, mint, pair_address, discovery_source,
                        discovered_at_unix_ms, venue
                    FROM token_candidates
                    WHERE {' AND '.join(clauses)}
                    ORDER BY id ASC
                    LIMIT 2"""

        connection = self._connect()
        try:
            rows = connection.execute(query, parameters).fetchall()
        except sqlite3.Error as error:
            raise ObserverMarketReadError(
                f"observer candidate read failed: {error}"
            ) from error
        finally:
            connection.close()

        if not rows:
            raise ObserverMarketReadError("observer candidate not found")
        if len(rows) != 1:
            raise ObserverMarketReadError("observer candidate identity is ambiguous")
        return _candidate_from_row(rows[0])

    def load_window(
        self,
        candidate_id: int,
        as_of_unix_ms: int,
        policy: ObserverMarketReadPolicy,
    ) -> ObservedMarketWindow:
        _require_positive_int("candidate_id", candidate_id)
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        if type(policy) is not ObserverMarketReadPolicy:
            raise ValueError("policy must be an ObserverMarketReadPolicy")

        connection = self._connect()
        try:
            candidate = self._candidate_by_id(connection, candidate_id)
            current = self._select_current(connection, candidate_id, as_of_unix_ms, policy)
            selected_source = current.source
            selected_pair_address = current.pair_address

            history_start = max(
                0,
                as_of_unix_ms
                - max(ANCHOR_15M_MAX_AGE_MS, policy.local_range_lookback_ms),
            )
            rows = connection.execute(
                f"""{_MARKET_SELECT}
                    WHERE candidate_id = ?
                      AND source = ?
                      AND pair_address = ?
                      AND observed_at_unix_ms BETWEEN ? AND ?
                    ORDER BY observed_at_unix_ms DESC, id ASC""",
                (
                    candidate_id,
                    selected_source,
                    selected_pair_address,
                    history_start,
                    as_of_unix_ms,
                ),
            ).fetchall()
            snapshots = tuple(_snapshot_from_row(row) for row in rows)

            one_minute_ago = _select_anchor(
                snapshots,
                as_of_unix_ms=as_of_unix_ms,
                target_age_ms=ANCHOR_1M_MIN_AGE_MS,
                min_age_ms=ANCHOR_1M_MIN_AGE_MS,
                max_age_ms=ANCHOR_1M_MAX_AGE_MS,
            )
            five_minutes_ago = _select_anchor(
                snapshots,
                as_of_unix_ms=as_of_unix_ms,
                target_age_ms=ANCHOR_5M_MIN_AGE_MS,
                min_age_ms=ANCHOR_5M_MIN_AGE_MS,
                max_age_ms=ANCHOR_5M_MAX_AGE_MS,
            )
            fifteen_minutes_ago = _select_anchor(
                snapshots,
                as_of_unix_ms=as_of_unix_ms,
                target_age_ms=ANCHOR_15M_MIN_AGE_MS,
                min_age_ms=ANCHOR_15M_MIN_AGE_MS,
                max_age_ms=ANCHOR_15M_MAX_AGE_MS,
            )

            local_start = max(0, as_of_unix_ms - policy.local_range_lookback_ms)
            local_prices = tuple(
                snapshot.price_usd
                for snapshot in snapshots
                if snapshot.observed_at_unix_ms >= local_start
                and snapshot.price_usd is not None
                and snapshot.price_usd > 0
            )
            local_high = max(local_prices) if local_prices else None
            local_low = min(local_prices) if local_prices else None

            pair_created_at = current.pair_created_at_unix_ms
            if pair_created_at is None:
                fallback_row = connection.execute(
                    f"""{_MARKET_SELECT}
                        WHERE candidate_id = ?
                          AND source = ?
                          AND pair_address = ?
                          AND observed_at_unix_ms <= ?
                          AND pair_created_at_unix_ms IS NOT NULL
                        ORDER BY observed_at_unix_ms DESC, id ASC
                        LIMIT 1""",
                    (
                        candidate_id,
                        selected_source,
                        selected_pair_address,
                        as_of_unix_ms,
                    ),
                ).fetchone()
                if fallback_row is not None:
                    pair_created_at = _snapshot_from_row(
                        fallback_row
                    ).pair_created_at_unix_ms

            return ObservedMarketWindow(
                schema_version=OBSERVER_MARKET_SCHEMA_VERSION,
                policy_version=policy.version,
                candidate=candidate,
                as_of_unix_ms=as_of_unix_ms,
                selected_source=selected_source,
                selected_pair_address=selected_pair_address,
                current=current,
                one_minute_ago=one_minute_ago,
                five_minutes_ago=five_minutes_ago,
                fifteen_minutes_ago=fifteen_minutes_ago,
                pair_created_at_unix_ms=pair_created_at,
                local_high_price_usd=local_high,
                local_low_price_usd=local_low,
            )
        except ObserverMarketReadError:
            raise
        except sqlite3.Error as error:
            raise ObserverMarketReadError(
                f"observer market replay read failed: {error}"
            ) from error
        except (TypeError, ValueError) as error:
            raise ObserverMarketReadError(
                f"observer market evidence is invalid: {error}"
            ) from error
        finally:
            connection.close()

    @staticmethod
    def _candidate_by_id(
        connection: sqlite3.Connection, candidate_id: int
    ) -> ObserverCandidateIdentity:
        row = connection.execute(
            """SELECT
                   id, mint, pair_address, discovery_source,
                   discovered_at_unix_ms, venue
               FROM token_candidates
               WHERE id = ?
               LIMIT 1""",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ObserverMarketReadError("observer candidate not found")
        return _candidate_from_row(row)

    @staticmethod
    def _select_current(
        connection: sqlite3.Connection,
        candidate_id: int,
        as_of_unix_ms: int,
        policy: ObserverMarketReadPolicy,
    ) -> ObserverMarketSnapshot:
        minimum_observed_at = max(0, as_of_unix_ms - policy.max_current_age_ms)
        for source in policy.source_priority:
            row = connection.execute(
                f"""{_MARKET_SELECT}
                    WHERE candidate_id = ?
                      AND source = ?
                      AND observed_at_unix_ms BETWEEN ? AND ?
                    ORDER BY observed_at_unix_ms DESC, id ASC
                    LIMIT 1""",
                (candidate_id, source, minimum_observed_at, as_of_unix_ms),
            ).fetchone()
            if row is not None:
                return _snapshot_from_row(row)
        raise ObserverMarketReadError(
            "no fresh observer market snapshot matches caller source priority"
        )

    def _connect(self) -> sqlite3.Connection:
        database_uri = f"{self._database_path.as_uri()}?mode=ro"
        try:
            connection = sqlite3.connect(database_uri, uri=True)
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error as error:
            raise ObserverMarketReadError(
                f"unable to open observer database read-only: {error}"
            ) from error

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table_name, required_columns in _REQUIRED_COLUMNS.items():
                if table_name not in tables:
                    raise ObserverMarketReadError(
                        f"observer database missing required table {table_name}"
                    )
                columns = {
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA table_info({table_name})"
                    ).fetchall()
                }
                missing = required_columns - columns
                if missing:
                    missing_text = ", ".join(sorted(missing))
                    raise ObserverMarketReadError(
                        f"observer database table {table_name} missing required columns: "
                        f"{missing_text}"
                    )
        except ObserverMarketReadError:
            raise
        except sqlite3.Error as error:
            raise ObserverMarketReadError(
                f"observer database schema read failed: {error}"
            ) from error


def build_market_feature_points(
    window: ObservedMarketWindow,
) -> tuple[
    MarketFeaturePoint,
    MarketFeaturePoint | None,
    MarketFeaturePoint | None,
    MarketFeaturePoint | None,
]:
    if type(window) is not ObservedMarketWindow:
        raise ValueError("window must be an ObservedMarketWindow")
    return (
        _to_market_feature_point(window.current),
        _to_optional_market_feature_point(window.one_minute_ago),
        _to_optional_market_feature_point(window.five_minutes_ago),
        _to_optional_market_feature_point(window.fifteen_minutes_ago),
    )


def _candidate_from_row(row: sqlite3.Row) -> ObserverCandidateIdentity:
    try:
        return ObserverCandidateIdentity(
            candidate_id=row["id"],
            mint=row["mint"],
            pair_address=row["pair_address"],
            discovery_source=row["discovery_source"],
            discovered_at_unix_ms=row["discovered_at_unix_ms"],
            venue=row["venue"],
        )
    except (TypeError, ValueError) as error:
        raise ObserverMarketReadError(
            f"observer candidate row is invalid: {error}"
        ) from error


def _snapshot_from_row(row: sqlite3.Row) -> ObserverMarketSnapshot:
    try:
        return ObserverMarketSnapshot(
            row_id=row["id"],
            candidate_id=row["candidate_id"],
            observed_at_unix_ms=row["observed_at_unix_ms"],
            source=row["source"],
            source_observed_at_unix_ms=row["source_observed_at_unix_ms"],
            venue=row["venue"],
            pair_address=row["pair_address"],
            price_usd=row["price_usd"],
            liquidity_usd=row["liquidity_usd"],
            volume_m5_usd=row["volume_m5_usd"],
            volume_h1_usd=row["volume_h1_usd"],
            buys_m5=row["buys_m5"],
            sells_m5=row["sells_m5"],
            buys_h1=row["buys_h1"],
            sells_h1=row["sells_h1"],
            pair_created_at_unix_ms=row["pair_created_at_unix_ms"],
        )
    except (TypeError, ValueError) as error:
        raise ObserverMarketReadError(
            f"observer market snapshot row is invalid: {error}"
        ) from error


def _select_anchor(
    snapshots: tuple[ObserverMarketSnapshot, ...],
    *,
    as_of_unix_ms: int,
    target_age_ms: int,
    min_age_ms: int,
    max_age_ms: int,
) -> ObserverMarketSnapshot | None:
    eligible = tuple(
        snapshot
        for snapshot in snapshots
        if min_age_ms
        <= as_of_unix_ms - snapshot.observed_at_unix_ms
        <= max_age_ms
    )
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda snapshot: (
            abs(
                (as_of_unix_ms - snapshot.observed_at_unix_ms)
                - target_age_ms
            ),
            -snapshot.observed_at_unix_ms,
            snapshot.row_id,
        ),
    )


def _to_market_feature_point(snapshot: ObserverMarketSnapshot) -> MarketFeaturePoint:
    return MarketFeaturePoint(
        observed_at_unix_ms=snapshot.observed_at_unix_ms,
        price_usd=snapshot.price_usd,
        liquidity_usd=snapshot.liquidity_usd,
        volume_m5_usd=snapshot.volume_m5_usd,
        volume_h1_usd=snapshot.volume_h1_usd,
        buys_m5=snapshot.buys_m5,
        sells_m5=snapshot.sells_m5,
        buys_h1=snapshot.buys_h1,
        sells_h1=snapshot.sells_h1,
    )


def _to_optional_market_feature_point(
    snapshot: ObserverMarketSnapshot | None,
) -> MarketFeaturePoint | None:
    if snapshot is None:
        return None
    return _to_market_feature_point(snapshot)


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_string(name: str, value: str | None) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string or None")


def _require_optional_non_empty_string(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_empty_string(name, value)


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
