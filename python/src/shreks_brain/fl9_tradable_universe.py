from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from shreks_brain.observer_market import (
    ObserverMarketReadError,
    ObserverMarketStore,
)


FL9_TRADABLE_UNIVERSE_POLICY_VERSION = "fl9-tradable-universe-v1"
FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME = (
    "shreks.fl9_tradable_universe_assessment"
)
FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION = 1

_REQUIRED_VENUE = "pump_swap"
_REQUIRED_FROM_VENUE = "pump_fun_bonding_curve"
_REQUIRED_TO_VENUE = "pump_swap"
_REQUIRED_EVENT_TYPE = "pump_graduation"
_REQUIRED_SNAPSHOT_SOURCE = "dexscreener"
_MAX_SNAPSHOT_AGE_MS = 60_000
_MIN_LIQUIDITY_USD = 3_000.0
_MIN_VOLUME_H24_USD = 1_000.0


@dataclass(frozen=True, slots=True)
class Fl9TradableUniversePolicy:
    version: str = FL9_TRADABLE_UNIVERSE_POLICY_VERSION
    required_venue: str = _REQUIRED_VENUE
    required_from_venue: str = _REQUIRED_FROM_VENUE
    required_to_venue: str = _REQUIRED_TO_VENUE
    required_event_type: str = _REQUIRED_EVENT_TYPE
    required_snapshot_source: str = _REQUIRED_SNAPSHOT_SOURCE
    maximum_snapshot_age_ms: int = _MAX_SNAPSHOT_AGE_MS
    minimum_liquidity_usd: float = _MIN_LIQUIDITY_USD
    minimum_volume_h24_usd: float = _MIN_VOLUME_H24_USD

    def __post_init__(self) -> None:
        expected = (
            FL9_TRADABLE_UNIVERSE_POLICY_VERSION,
            _REQUIRED_VENUE,
            _REQUIRED_FROM_VENUE,
            _REQUIRED_TO_VENUE,
            _REQUIRED_EVENT_TYPE,
            _REQUIRED_SNAPSHOT_SOURCE,
            _MAX_SNAPSHOT_AGE_MS,
            _MIN_LIQUIDITY_USD,
            _MIN_VOLUME_H24_USD,
        )
        actual = (
            self.version,
            self.required_venue,
            self.required_from_venue,
            self.required_to_venue,
            self.required_event_type,
            self.required_snapshot_source,
            self.maximum_snapshot_age_ms,
            self.minimum_liquidity_usd,
            self.minimum_volume_h24_usd,
        )
        if actual != expected:
            raise ValueError(
                "fl9-tradable-universe-v1 constants are immutable; "
                "threshold changes require a new policy version"
            )


@dataclass(frozen=True, slots=True)
class Fl9TradableUniverseAssessment:
    schema_name: str
    schema_version: int
    policy_version: str
    policy_fingerprint_sha256: str
    mint: str
    quote_mint: str
    decision_venue: str
    decision_observed_at_unix_ms: int
    eligible: bool
    reason: str
    graduation_detected_at_unix_ms: int | None
    candidate_id: int | None
    snapshot_row_id: int | None
    snapshot_observed_at_unix_ms: int | None
    snapshot_age_ms: int | None
    selected_pair_address: str | None
    liquidity_usd: float | None
    volume_h24_usd: float | None

    def __post_init__(self) -> None:
        if self.schema_name != FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME:
            raise ValueError("unsupported FL9 tradable-universe assessment schema")
        if self.schema_version != FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION:
            raise ValueError("unsupported FL9 tradable-universe assessment version")
        if self.policy_version != FL9_TRADABLE_UNIVERSE_POLICY_VERSION:
            raise ValueError("unsupported FL9 tradable-universe policy")
        _require_sha256(
            "policy_fingerprint_sha256",
            self.policy_fingerprint_sha256,
        )
        _require_non_empty("mint", self.mint)
        _require_non_empty("quote_mint", self.quote_mint)
        _require_non_empty("decision_venue", self.decision_venue)
        _require_non_negative_int(
            "decision_observed_at_unix_ms",
            self.decision_observed_at_unix_ms,
        )
        _require_non_empty("reason", self.reason)
        _optional_non_negative_int(
            "graduation_detected_at_unix_ms",
            self.graduation_detected_at_unix_ms,
        )
        _optional_positive_int("candidate_id", self.candidate_id)
        _optional_positive_int("snapshot_row_id", self.snapshot_row_id)
        _optional_non_negative_int(
            "snapshot_observed_at_unix_ms",
            self.snapshot_observed_at_unix_ms,
        )
        _optional_non_negative_int("snapshot_age_ms", self.snapshot_age_ms)
        if self.selected_pair_address is not None and not isinstance(
            self.selected_pair_address, str
        ):
            raise ValueError("selected_pair_address must be a string or None")
        _optional_non_negative_finite("liquidity_usd", self.liquidity_usd)
        _optional_non_negative_finite(
            "volume_h24_usd",
            self.volume_h24_usd,
        )
        if self.eligible and self.reason != "eligible":
            raise ValueError("eligible FL9 assessment must use reason='eligible'")
        if not self.eligible and self.reason == "eligible":
            raise ValueError("ineligible FL9 assessment cannot use reason='eligible'")


def fl9_tradable_universe_policy_fingerprint_sha256(
    policy: Fl9TradableUniversePolicy,
) -> str:
    if type(policy) is not Fl9TradableUniversePolicy:
        raise ValueError("policy must be exact Fl9TradableUniversePolicy")
    return _sha256_canonical(asdict(policy))


class Fl9TradableUniverseStore:
    """Read-only point-in-time FL9 BUY-universe assessment."""

    def __init__(self, database_path: str | Path) -> None:
        try:
            self._database_path = Path(database_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ValueError("invalid FL9 observer database path") from error
        self._market = ObserverMarketStore(self._database_path)
        connection = self._connect()
        try:
            self._validate_lifecycle_schema(connection)
        finally:
            connection.close()

    def assess(
        self,
        *,
        mint: str,
        quote_mint: str,
        decision_venue: str,
        decision_observed_at_unix_ms: int,
        policy: Fl9TradableUniversePolicy,
    ) -> Fl9TradableUniverseAssessment:
        _require_non_empty("mint", mint)
        _require_non_empty("quote_mint", quote_mint)
        _require_non_empty("decision_venue", decision_venue)
        _require_non_negative_int(
            "decision_observed_at_unix_ms",
            decision_observed_at_unix_ms,
        )
        if type(policy) is not Fl9TradableUniversePolicy:
            raise ValueError("policy must be exact Fl9TradableUniversePolicy")

        policy_fingerprint = (
            fl9_tradable_universe_policy_fingerprint_sha256(policy)
        )
        if decision_venue != policy.required_venue:
            return self._assessment(
                policy=policy,
                policy_fingerprint=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=decision_observed_at_unix_ms,
                reason="wrong_decision_venue",
            )

        migration = self._verified_migration_at_or_before(
            mint=mint,
            quote_mint=quote_mint,
            as_of_unix_ms=decision_observed_at_unix_ms,
            policy=policy,
        )
        if migration is None:
            return self._assessment(
                policy=policy,
                policy_fingerprint=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=decision_observed_at_unix_ms,
                reason="missing_verified_migration",
            )
        migration_detected_at, contradictory = migration
        if contradictory:
            return self._assessment(
                policy=policy,
                policy_fingerprint=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=decision_observed_at_unix_ms,
                reason="contradictory_verified_migration",
                graduation_detected_at_unix_ms=migration_detected_at,
            )

        try:
            candidate = self._market.resolve_candidate_at(
                mint,
                decision_observed_at_unix_ms,
                preferred_discovery_source=policy.required_snapshot_source,
            )
        except ObserverMarketReadError:
            return self._assessment(
                policy=policy,
                policy_fingerprint=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=decision_observed_at_unix_ms,
                reason="candidate_identity_unavailable",
                graduation_detected_at_unix_ms=migration_detected_at,
            )

        try:
            snapshot = self._market.load_current_exact_market(
                candidate.candidate_id,
                decision_observed_at_unix_ms,
                source=policy.required_snapshot_source,
                venue=policy.required_venue,
                base_mint=mint,
                quote_mint=quote_mint,
                max_age_ms=policy.maximum_snapshot_age_ms,
            )
        except ObserverMarketReadError:
            return self._assessment(
                policy=policy,
                policy_fingerprint=policy_fingerprint,
                mint=mint,
                quote_mint=quote_mint,
                decision_venue=decision_venue,
                decision_observed_at_unix_ms=decision_observed_at_unix_ms,
                reason="missing_fresh_exact_market_snapshot",
                graduation_detected_at_unix_ms=migration_detected_at,
                candidate_id=candidate.candidate_id,
            )

        age = (
            decision_observed_at_unix_ms
            - snapshot.observed_at_unix_ms
        )
        if age < 0 or age > policy.maximum_snapshot_age_ms:
            raise ValueError(
                "authenticated exact-market reader violated FL9 snapshot chronology"
            )

        common = dict(
            policy=policy,
            policy_fingerprint=policy_fingerprint,
            mint=mint,
            quote_mint=quote_mint,
            decision_venue=decision_venue,
            decision_observed_at_unix_ms=decision_observed_at_unix_ms,
            graduation_detected_at_unix_ms=migration_detected_at,
            candidate_id=candidate.candidate_id,
            snapshot_row_id=snapshot.row_id,
            snapshot_observed_at_unix_ms=snapshot.observed_at_unix_ms,
            snapshot_age_ms=age,
            selected_pair_address=snapshot.pair_address,
            liquidity_usd=snapshot.liquidity_usd,
            volume_h24_usd=snapshot.volume_h24_usd,
        )

        if snapshot.liquidity_usd is None:
            return self._assessment(
                **common,
                reason="missing_liquidity_usd",
            )
        if snapshot.volume_h24_usd is None:
            return self._assessment(
                **common,
                reason="missing_volume_h24_usd",
            )
        if snapshot.liquidity_usd < policy.minimum_liquidity_usd:
            return self._assessment(
                **common,
                reason="below_minimum_liquidity_usd",
            )
        if snapshot.volume_h24_usd < policy.minimum_volume_h24_usd:
            return self._assessment(
                **common,
                reason="below_minimum_volume_h24_usd",
            )

        return self._assessment(
            **common,
            reason="eligible",
            eligible=True,
        )

    def _verified_migration_at_or_before(
        self,
        *,
        mint: str,
        quote_mint: str,
        as_of_unix_ms: int,
        policy: Fl9TradableUniversePolicy,
    ) -> tuple[int, bool] | None:
        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT
                       e.pool_address,
                       e.detected_at_unix_ms
                   FROM token_lifecycle_events AS e
                   JOIN pump_migration_signals AS s
                     ON s.signature = e.signature
                   WHERE s.status = 'verified'
                     AND e.event_type = ?
                     AND e.from_venue = ?
                     AND e.to_venue = ?
                     AND e.mint = ?
                     AND e.quote_mint = ?
                     AND e.detected_at_unix_ms <= ?
                   ORDER BY
                       e.detected_at_unix_ms ASC,
                       e.signature ASC,
                       e.pool_address ASC""",
                (
                    policy.required_event_type,
                    policy.required_from_venue,
                    policy.required_to_venue,
                    mint,
                    quote_mint,
                    as_of_unix_ms,
                ),
            ).fetchall()
        except sqlite3.Error as error:
            raise ValueError(
                f"FL9 lifecycle evidence read failed: {error}"
            ) from error
        finally:
            connection.close()

        if not rows:
            return None
        pools = {row["pool_address"] for row in rows}
        if any(not isinstance(pool, str) or not pool.strip() for pool in pools):
            raise ValueError("FL9 lifecycle evidence contains blank pool address")
        return min(row["detected_at_unix_ms"] for row in rows), len(pools) != 1

    def _assessment(
        self,
        *,
        policy: Fl9TradableUniversePolicy,
        policy_fingerprint: str,
        mint: str,
        quote_mint: str,
        decision_venue: str,
        decision_observed_at_unix_ms: int,
        reason: str,
        eligible: bool = False,
        graduation_detected_at_unix_ms: int | None = None,
        candidate_id: int | None = None,
        snapshot_row_id: int | None = None,
        snapshot_observed_at_unix_ms: int | None = None,
        snapshot_age_ms: int | None = None,
        selected_pair_address: str | None = None,
        liquidity_usd: float | None = None,
        volume_h24_usd: float | None = None,
    ) -> Fl9TradableUniverseAssessment:
        if policy.version != FL9_TRADABLE_UNIVERSE_POLICY_VERSION:
            raise ValueError("unsupported FL9 tradable-universe policy")
        return Fl9TradableUniverseAssessment(
            schema_name=FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_NAME,
            schema_version=FL9_TRADABLE_UNIVERSE_ASSESSMENT_SCHEMA_VERSION,
            policy_version=policy.version,
            policy_fingerprint_sha256=policy_fingerprint,
            mint=mint,
            quote_mint=quote_mint,
            decision_venue=decision_venue,
            decision_observed_at_unix_ms=decision_observed_at_unix_ms,
            eligible=eligible,
            reason=reason,
            graduation_detected_at_unix_ms=graduation_detected_at_unix_ms,
            candidate_id=candidate_id,
            snapshot_row_id=snapshot_row_id,
            snapshot_observed_at_unix_ms=snapshot_observed_at_unix_ms,
            snapshot_age_ms=snapshot_age_ms,
            selected_pair_address=selected_pair_address,
            liquidity_usd=liquidity_usd,
            volume_h24_usd=volume_h24_usd,
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self._database_path.as_uri()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as error:
            raise ValueError(
                f"unable to open FL9 observer database read-only: {error}"
            ) from error

    @staticmethod
    def _validate_lifecycle_schema(connection: sqlite3.Connection) -> None:
        required = {
            "pump_migration_signals": {
                "signature",
                "status",
            },
            "token_lifecycle_events": {
                "signature",
                "event_type",
                "from_venue",
                "to_venue",
                "mint",
                "quote_mint",
                "pool_address",
                "detected_at_unix_ms",
            },
        }
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table, columns in required.items():
                if table not in tables:
                    raise ValueError(
                        f"FL9 observer database missing required table {table}"
                    )
                actual = {
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    )
                }
                missing = columns - actual
                if missing:
                    raise ValueError(
                        f"FL9 observer database table {table} missing columns: "
                        + ", ".join(sorted(missing))
                    )
        except sqlite3.Error as error:
            raise ValueError(
                f"FL9 observer database schema read failed: {error}"
            ) from error


def _sha256_canonical(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _optional_non_negative_int(name: str, value: object) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _optional_positive_int(name: str, value: object) -> None:
    if value is None:
        return
    if _require_non_negative_int(name, value) == 0:
        raise ValueError(f"{name} must be positive")


def _optional_non_negative_finite(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value
