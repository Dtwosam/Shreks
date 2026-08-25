from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from .models import (
    ObserverExitQuoteSafetyEvidence,
    ObserverHolderSafetyEvidence,
    ObserverMintSafetyEvidence,
    ObserverSafetyProbeIdentity,
)


_REQUIRED_COLUMNS = {
    "token_candidates": frozenset({"id", "mint"}),
    "token_mint_states": frozenset(
        {
            "id",
            "candidate_id",
            "provider",
            "mint_authority",
            "freeze_authority",
            "slot",
            "observed_at_unix_ms",
        }
    ),
    "token_holder_distributions": frozenset(
        {
            "id",
            "candidate_id",
            "provider",
            "mint",
            "last_indexed_slot",
            "observed_at_unix_ms",
            "complete",
            "top_holder_concentration_pct",
        }
    ),
    "exit_quote_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "provider",
            "probe_policy_version",
            "input_mint",
            "output_mint",
            "taker",
            "input_amount",
            "output_amount",
            "minimum_output_amount",
            "slippage_bps",
            "route_available",
            "price_impact_pct",
            "quoted_at_unix_ms",
        }
    ),
}


class ObserverSafetyReadError(ValueError):
    """Raised when persisted observer safety evidence cannot be read safely."""


class ObserverSafetyEvidenceStore:
    """Read-only point-in-time access to normalized observer safety evidence."""

    def __init__(self, database_path: str | os.PathLike[str]) -> None:
        try:
            self._database_path = Path(database_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ObserverSafetyReadError("invalid observer database path") from error

        connection = self._connect()
        try:
            self._validate_schema(connection)
        finally:
            connection.close()

    def latest_mint_state(
        self,
        candidate_id: int,
        mint: str,
        as_of_unix_ms: int,
    ) -> ObserverMintSafetyEvidence | None:
        _validate_lookup(candidate_id, mint, as_of_unix_ms)
        connection = self._connect()
        try:
            self._validate_candidate_identity(connection, candidate_id, mint)
            row = connection.execute(
                """SELECT
                       s.candidate_id, s.provider, c.mint,
                       s.mint_authority, s.freeze_authority,
                       s.slot, s.observed_at_unix_ms
                   FROM token_mint_states AS s
                   JOIN token_candidates AS c ON c.id = s.candidate_id
                   WHERE s.candidate_id = ?
                     AND c.mint = ?
                     AND s.provider = 'helius'
                     AND s.observed_at_unix_ms <= ?
                   ORDER BY s.observed_at_unix_ms DESC, s.id ASC
                   LIMIT 1""",
                (candidate_id, mint, as_of_unix_ms),
            ).fetchone()
            if row is None:
                return None
            return ObserverMintSafetyEvidence(
                candidate_id=_positive_int(row["candidate_id"], "mint candidate_id"),
                provider=_string(row["provider"], "mint provider"),
                mint=_string(row["mint"], "mint"),
                mint_authority=_optional_string(row["mint_authority"], "mint_authority"),
                freeze_authority=_optional_string(
                    row["freeze_authority"], "freeze_authority"
                ),
                slot=_canonical_u64(row["slot"], "mint slot"),
                observed_at_unix_ms=_non_negative_int(
                    row["observed_at_unix_ms"], "mint observed_at_unix_ms"
                ),
            )
        except ObserverSafetyReadError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise ObserverSafetyReadError(
                f"observer mint safety evidence read failed: {error}"
            ) from error
        finally:
            connection.close()

    def latest_holder_distribution(
        self,
        candidate_id: int,
        mint: str,
        as_of_unix_ms: int,
    ) -> ObserverHolderSafetyEvidence | None:
        _validate_lookup(candidate_id, mint, as_of_unix_ms)
        connection = self._connect()
        try:
            self._validate_candidate_identity(connection, candidate_id, mint)
            row = connection.execute(
                """SELECT
                       candidate_id, provider, mint, last_indexed_slot,
                       observed_at_unix_ms, complete, top_holder_concentration_pct
                   FROM token_holder_distributions
                   WHERE candidate_id = ?
                     AND mint = ?
                     AND provider = 'helius'
                     AND observed_at_unix_ms <= ?
                   ORDER BY observed_at_unix_ms DESC, id ASC
                   LIMIT 1""",
                (candidate_id, mint, as_of_unix_ms),
            ).fetchone()
            if row is None:
                return None
            complete = _sqlite_bool(row["complete"], "holder complete")
            concentration = (
                _optional_percentage(
                    row["top_holder_concentration_pct"],
                    "top_holder_concentration_pct",
                )
                if complete
                else None
            )
            return ObserverHolderSafetyEvidence(
                candidate_id=_positive_int(
                    row["candidate_id"], "holder candidate_id"
                ),
                provider=_string(row["provider"], "holder provider"),
                mint=_string(row["mint"], "holder mint"),
                last_indexed_slot=_canonical_u64(
                    row["last_indexed_slot"], "holder last_indexed_slot"
                ),
                observed_at_unix_ms=_non_negative_int(
                    row["observed_at_unix_ms"], "holder observed_at_unix_ms"
                ),
                complete=complete,
                top_holder_concentration_pct=concentration,
            )
        except ObserverSafetyReadError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise ObserverSafetyReadError(
                f"observer holder safety evidence read failed: {error}"
            ) from error
        finally:
            connection.close()

    def latest_exit_quote(
        self,
        candidate_id: int,
        mint: str,
        probe_identity: ObserverSafetyProbeIdentity,
        as_of_unix_ms: int,
    ) -> ObserverExitQuoteSafetyEvidence | None:
        _validate_lookup(candidate_id, mint, as_of_unix_ms)
        if type(probe_identity) is not ObserverSafetyProbeIdentity:
            raise ValueError("probe_identity must be an ObserverSafetyProbeIdentity")

        connection = self._connect()
        try:
            self._validate_candidate_identity(connection, candidate_id, mint)
            row = connection.execute(
                """SELECT
                       candidate_id, provider, probe_policy_version, input_mint,
                       output_mint, taker, input_amount, output_amount,
                       minimum_output_amount, slippage_bps, route_available,
                       price_impact_pct, quoted_at_unix_ms
                   FROM exit_quote_snapshots
                   WHERE candidate_id = ?
                     AND provider = 'jupiter'
                     AND probe_policy_version = ?
                     AND input_mint = ?
                     AND output_mint = ?
                     AND taker = ?
                     AND input_amount = ?
                     AND slippage_bps = ?
                     AND quoted_at_unix_ms <= ?
                   ORDER BY quoted_at_unix_ms DESC, id ASC
                   LIMIT 1""",
                (
                    candidate_id,
                    probe_identity.probe_policy_version,
                    mint,
                    probe_identity.output_mint,
                    probe_identity.taker,
                    str(probe_identity.input_amount),
                    probe_identity.slippage_bps,
                    as_of_unix_ms,
                ),
            ).fetchone()
            if row is None:
                return None
            return ObserverExitQuoteSafetyEvidence(
                candidate_id=_positive_int(row["candidate_id"], "quote candidate_id"),
                provider=_string(row["provider"], "quote provider"),
                probe_policy_version=_string(
                    row["probe_policy_version"], "probe_policy_version"
                ),
                input_mint=_string(row["input_mint"], "quote input_mint"),
                output_mint=_string(row["output_mint"], "quote output_mint"),
                taker=_string(row["taker"], "quote taker"),
                input_amount=_canonical_u64(row["input_amount"], "quote input_amount"),
                output_amount=_canonical_u64(row["output_amount"], "quote output_amount"),
                minimum_output_amount=_canonical_u64(
                    row["minimum_output_amount"], "quote minimum_output_amount"
                ),
                slippage_bps=_slippage_bps(row["slippage_bps"]),
                route_available=_sqlite_bool(
                    row["route_available"], "quote route_available"
                ),
                price_impact_pct=_optional_string(
                    row["price_impact_pct"], "quote price_impact_pct"
                ),
                quoted_at_unix_ms=_non_negative_int(
                    row["quoted_at_unix_ms"], "quote quoted_at_unix_ms"
                ),
            )
        except ObserverSafetyReadError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise ObserverSafetyReadError(
                f"observer exit-quote safety evidence read failed: {error}"
            ) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        database_uri = f"{self._database_path.as_uri()}?mode=ro"
        try:
            connection = sqlite3.connect(database_uri, uri=True)
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error as error:
            raise ObserverSafetyReadError(
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
                    raise ObserverSafetyReadError(
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
                    raise ObserverSafetyReadError(
                        f"observer database table {table_name} missing required columns: "
                        f"{missing_text}"
                    )
        except ObserverSafetyReadError:
            raise
        except sqlite3.Error as error:
            raise ObserverSafetyReadError(
                f"observer database schema read failed: {error}"
            ) from error

    @staticmethod
    def _validate_candidate_identity(
        connection: sqlite3.Connection,
        candidate_id: int,
        mint: str,
    ) -> None:
        row = connection.execute(
            "SELECT mint FROM token_candidates WHERE id = ? LIMIT 1",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ObserverSafetyReadError("observer safety candidate not found")
        stored_mint = _string(row["mint"], "candidate mint")
        if stored_mint != mint:
            raise ObserverSafetyReadError(
                "observer safety candidate id and mint attribution do not match"
            )


def _validate_lookup(candidate_id: int, mint: str, as_of_unix_ms: int) -> None:
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id <= 0:
        raise ValueError("candidate_id must be a positive integer")
    if not isinstance(mint, str) or not mint.strip():
        raise ValueError("mint must be a non-empty string")
    if (
        isinstance(as_of_unix_ms, bool)
        or not isinstance(as_of_unix_ms, int)
        or as_of_unix_ms < 0
    ):
        raise ValueError("as_of_unix_ms must be a non-negative integer")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObserverSafetyReadError(f"{field} is not a non-empty string")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ObserverSafetyReadError(f"{field} is not a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverSafetyReadError(f"{field} is not a non-negative integer")
    return value


def _canonical_u64(value: object, field: str) -> int:
    if not isinstance(value, str):
        raise ObserverSafetyReadError(f"{field} is not canonical u64 decimal text")
    try:
        parsed = int(value, 10)
    except ValueError as error:
        raise ObserverSafetyReadError(f"{field} is not u64 decimal text") from error
    if parsed < 0 or parsed > 2**64 - 1 or str(parsed) != value:
        raise ObserverSafetyReadError(f"{field} is not canonical u64 decimal text")
    return parsed


def _sqlite_bool(value: object, field: str) -> bool:
    if value == 0:
        return False
    if value == 1:
        return True
    raise ObserverSafetyReadError(f"{field} is not a canonical SQLite boolean")


def _optional_percentage(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObserverSafetyReadError(f"{field} is not numeric")
    parsed = float(value)
    if not 0.0 <= parsed <= 100.0:
        raise ObserverSafetyReadError(f"{field} is outside [0, 100]")
    return parsed


def _slippage_bps(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise ObserverSafetyReadError("quote slippage_bps is outside [0, 10000]")
    return value
