from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from .models import (
    ObserverPaperQuoteEvidence,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)


_MAX_U64 = 2**64 - 1

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
    "token_mint_states": frozenset(
        {
            "id",
            "candidate_id",
            "provider",
            "decimals",
            "mint_authority",
            "freeze_authority",
            "slot",
            "observed_at_unix_ms",
        }
    ),
    "paper_quote_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "purpose",
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
            "route_labels_json",
            "quoted_at_unix_ms",
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


class ObserverCampaignReadError(ValueError):
    """Raised when observer campaign evidence cannot be read safely."""


class ObserverCampaignStore:
    """Read-only access to persisted E15 observer campaign evidence."""

    def __init__(self, database_path: str | os.PathLike[str]) -> None:
        try:
            self._database_path = Path(database_path).expanduser().resolve()
        except (TypeError, ValueError, OSError) as error:
            raise ObserverCampaignReadError("invalid observer database path") from error

        connection = self._connect()
        try:
            self._validate_schema(connection)
        finally:
            connection.close()

    def latest_paper_quote(
        self,
        identity: ObserverPaperQuoteIdentity,
        as_of_unix_ms: int,
    ) -> ObserverPaperQuoteEvidence | None:
        if type(identity) is not ObserverPaperQuoteIdentity:
            raise ValueError("identity must be an ObserverPaperQuoteIdentity")
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)

        connection = self._connect()
        try:
            candidate_mint = self._candidate_mint(connection, identity.candidate_id)
            expected_mint = (
                identity.output_mint
                if identity.purpose is ObserverPaperQuotePurpose.ENTRY
                else identity.input_mint
            )
            if candidate_mint != expected_mint:
                raise ObserverCampaignReadError(
                    "paper quote candidate mint attribution does not match observer candidate"
                )

            row = connection.execute(
                """SELECT
                       candidate_id, purpose, provider, probe_policy_version,
                       input_mint, output_mint, taker, input_amount,
                       output_amount, minimum_output_amount, slippage_bps,
                       route_available, price_impact_pct, route_labels_json,
                       quoted_at_unix_ms
                   FROM paper_quote_snapshots
                   WHERE candidate_id = ?
                     AND purpose = ?
                     AND provider = ?
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
                    identity.candidate_id,
                    identity.purpose.value,
                    identity.provider,
                    identity.probe_policy_version,
                    identity.input_mint,
                    identity.output_mint,
                    identity.taker,
                    str(identity.input_amount),
                    identity.slippage_bps,
                    as_of_unix_ms,
                ),
            ).fetchone()
            if row is None:
                return None
            return _paper_quote_from_row(row, expected_identity=identity)
        except ObserverCampaignReadError:
            raise
        except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ObserverCampaignReadError(
                f"observer paper quote read failed: {error}"
            ) from error
        finally:
            connection.close()

    def latest_token_decimals(
        self,
        candidate_id: int,
        mint: str,
        as_of_unix_ms: int,
    ) -> int | None:
        _require_positive_int("candidate_id", candidate_id)
        _require_non_empty_string("mint", mint)
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)

        connection = self._connect()
        try:
            candidate_mint = self._candidate_mint(connection, candidate_id)
            if candidate_mint != mint:
                raise ObserverCampaignReadError(
                    "token decimals candidate mint does not match observer candidate"
                )
            row = connection.execute(
                """SELECT decimals
                   FROM token_mint_states
                   WHERE candidate_id = ?
                     AND provider = 'helius'
                     AND observed_at_unix_ms <= ?
                   ORDER BY observed_at_unix_ms DESC, id ASC
                   LIMIT 1""",
                (candidate_id, as_of_unix_ms),
            ).fetchone()
            if row is None:
                return None
            return _decimals(row["decimals"])
        except ObserverCampaignReadError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise ObserverCampaignReadError(
                f"observer token decimals read failed: {error}"
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
            raise ObserverCampaignReadError(
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
                    raise ObserverCampaignReadError(
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
                    raise ObserverCampaignReadError(
                        f"observer database table {table_name} missing required columns: "
                        f"{missing_text}"
                    )
        except ObserverCampaignReadError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignReadError(
                f"observer database schema read failed: {error}"
            ) from error

    @staticmethod
    def _candidate_mint(connection: sqlite3.Connection, candidate_id: int) -> str:
        row = connection.execute(
            "SELECT mint FROM token_candidates WHERE id = ? LIMIT 1",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ObserverCampaignReadError("observer candidate not found")
        return _string(row["mint"], "candidate mint")


def _paper_quote_from_row(
    row: sqlite3.Row,
    *,
    expected_identity: ObserverPaperQuoteIdentity,
) -> ObserverPaperQuoteEvidence:
    purpose_raw = _string(row["purpose"], "quote purpose")
    try:
        purpose = ObserverPaperQuotePurpose(purpose_raw)
    except ValueError as error:
        raise ObserverCampaignReadError("stored paper quote purpose is invalid") from error

    identity = ObserverPaperQuoteIdentity(
        candidate_id=_positive_int(row["candidate_id"], "quote candidate_id"),
        purpose=purpose,
        provider=_string(row["provider"], "quote provider"),
        probe_policy_version=_string(
            row["probe_policy_version"], "quote probe_policy_version"
        ),
        input_mint=_string(row["input_mint"], "quote input_mint"),
        output_mint=_string(row["output_mint"], "quote output_mint"),
        taker=_string(row["taker"], "quote taker"),
        input_amount=_canonical_u64(row["input_amount"], "quote input_amount", positive=True),
        slippage_bps=_slippage_bps(row["slippage_bps"]),
    )
    if identity != expected_identity:
        raise ObserverCampaignReadError("stored paper quote identity is contradictory")

    labels_raw = _string(row["route_labels_json"], "quote route_labels_json", allow_empty=True)
    labels_value = json.loads(labels_raw)
    if not isinstance(labels_value, list) or not all(
        isinstance(label, str) and label.strip() for label in labels_value
    ):
        raise ObserverCampaignReadError("stored paper quote route labels are invalid")
    canonical_labels = json.dumps(labels_value, separators=(",", ":"), ensure_ascii=False)
    if canonical_labels != labels_raw:
        raise ObserverCampaignReadError("stored paper quote route labels are not canonical JSON")

    return ObserverPaperQuoteEvidence(
        identity=identity,
        output_amount=_canonical_u64(row["output_amount"], "quote output_amount"),
        minimum_output_amount=_canonical_u64(
            row["minimum_output_amount"], "quote minimum_output_amount"
        ),
        route_available=_sqlite_bool(row["route_available"], "quote route_available"),
        price_impact_pct=_optional_string(
            row["price_impact_pct"], "quote price_impact_pct"
        ),
        route_labels=tuple(labels_value),
        quoted_at_unix_ms=_non_negative_int(
            row["quoted_at_unix_ms"], "quote quoted_at_unix_ms"
        ),
    )


def _canonical_u64(value: object, name: str, *, positive: bool = False) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be canonical u64 text")
    if value != "0" and value.startswith("0"):
        raise ValueError(f"{name} must be canonical u64 text")
    if not value.isascii() or not value.isdigit():
        raise ValueError(f"{name} must be canonical u64 text")
    parsed = int(value)
    minimum = 1 if positive else 0
    if parsed < minimum or parsed > _MAX_U64 or str(parsed) != value:
        raise ValueError(f"{name} must be canonical u64 text")
    return parsed


def _string(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _sqlite_bool(value: object, name: str) -> bool:
    if type(value) is not int or value not in (0, 1):
        raise ValueError(f"{name} must be SQLite boolean 0 or 1")
    return bool(value)


def _slippage_bps(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 10_000:
        raise ValueError("quote slippage_bps must be within [0, 10000]")
    return value


def _decimals(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError("mint decimals must be within [0, 255]")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")
