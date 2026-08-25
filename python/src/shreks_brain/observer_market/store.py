from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from .models import ObserverCandidateIdentity


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

        row = rows[0]
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


def _require_non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_string(name: str, value: str | None) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be a string or None")


def _require_optional_non_empty_string(name: str, value: str | None) -> None:
    if value is not None:
        _require_non_empty_string(name, value)
