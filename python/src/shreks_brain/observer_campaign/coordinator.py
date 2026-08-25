from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3


class ObserverCampaignCoordinatorError(ValueError):
    """Raised when a multi-token paper campaign cannot proceed without guessing."""


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignSelectionPolicy:
    recent_lookback_ms: int
    max_entry_candidates: int

    def __post_init__(self) -> None:
        _require_positive_int("recent_lookback_ms", self.recent_lookback_ms)
        _require_positive_int("max_entry_candidates", self.max_entry_candidates)


@dataclass(frozen=True, slots=True)
class ObserverCampaignCandidate:
    candidate_id: int
    mint: str
    latest_market_observed_at_unix_ms: int

    def __post_init__(self) -> None:
        _require_positive_int("candidate_id", self.candidate_id)
        _require_non_empty_string("mint", self.mint)
        _require_non_negative_int(
            "latest_market_observed_at_unix_ms",
            self.latest_market_observed_at_unix_ms,
        )


_REQUIRED_COLUMNS = {
    "token_candidates": frozenset(
        {
            "id",
            "mint",
            "discovered_at_unix_ms",
        }
    ),
    "market_snapshots": frozenset(
        {
            "id",
            "candidate_id",
            "observed_at_unix_ms",
        }
    ),
}


class ObserverCampaignCandidateStore:
    """Read-only point-in-time candidate enumeration for paper coordination."""

    def __init__(self, database_path: str | os.PathLike[str]) -> None:
        try:
            path = Path(database_path).expanduser()
            if not path.exists() or not path.is_file():
                raise ObserverCampaignCoordinatorError(
                    "observer campaign database not found"
                )
            self._database_path = path.resolve(strict=True)
        except ObserverCampaignCoordinatorError:
            raise
        except (TypeError, ValueError, OSError) as error:
            raise ObserverCampaignCoordinatorError(
                "invalid observer campaign database path"
            ) from error

        connection = self._connect()
        try:
            self._validate_schema(connection)
        finally:
            connection.close()

    def recent_candidates(
        self,
        *,
        as_of_unix_ms: int,
        policy: ObserverPaperCampaignSelectionPolicy,
    ) -> tuple[ObserverCampaignCandidate, ...]:
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)
        if type(policy) is not ObserverPaperCampaignSelectionPolicy:
            raise ObserverCampaignCoordinatorError(
                "policy must be an exact ObserverPaperCampaignSelectionPolicy"
            )
        cutoff = max(0, as_of_unix_ms - policy.recent_lookback_ms)

        connection = self._connect()
        try:
            rows = connection.execute(
                """SELECT
                       candidate.id,
                       candidate.mint,
                       MAX(snapshot.observed_at_unix_ms) AS latest_market_observed_at
                    FROM token_candidates AS candidate
                    JOIN market_snapshots AS snapshot
                      ON snapshot.candidate_id = candidate.id
                    WHERE candidate.discovered_at_unix_ms <= ?
                      AND snapshot.observed_at_unix_ms BETWEEN ? AND ?
                    GROUP BY candidate.id, candidate.mint
                    ORDER BY latest_market_observed_at DESC, candidate.id ASC""",
                (as_of_unix_ms, cutoff, as_of_unix_ms),
            ).fetchall()
            candidates = tuple(_candidate_from_row(row) for row in rows)
            _reject_ambiguous_mints(candidates)
            return candidates[: policy.max_entry_candidates]
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign recent-candidate read failed: {error}"
            ) from error
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign recent-candidate evidence is invalid: {error}"
            ) from error
        finally:
            connection.close()

    def resolve_required_mints(
        self,
        mints: tuple[str, ...],
        *,
        as_of_unix_ms: int,
    ) -> tuple[ObserverCampaignCandidate, ...]:
        if not isinstance(mints, tuple):
            raise ObserverCampaignCoordinatorError("mints must be a tuple")
        for mint in mints:
            _require_non_empty_string("mint", mint)
        _require_non_negative_int("as_of_unix_ms", as_of_unix_ms)

        ordered_mints = tuple(dict.fromkeys(mints))
        connection = self._connect()
        try:
            resolved: list[ObserverCampaignCandidate] = []
            for mint in ordered_mints:
                rows = connection.execute(
                    """SELECT
                           candidate.id,
                           candidate.mint,
                           MAX(snapshot.observed_at_unix_ms) AS latest_market_observed_at
                        FROM token_candidates AS candidate
                        LEFT JOIN market_snapshots AS snapshot
                          ON snapshot.candidate_id = candidate.id
                         AND snapshot.observed_at_unix_ms <= ?
                        WHERE candidate.mint = ?
                          AND candidate.discovered_at_unix_ms <= ?
                        GROUP BY candidate.id, candidate.mint
                        ORDER BY candidate.id ASC""",
                    (as_of_unix_ms, mint, as_of_unix_ms),
                ).fetchall()
                if not rows:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' not found at point in time"
                    )
                if len(rows) != 1:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' is ambiguous"
                    )
                row = rows[0]
                if row[2] is None:
                    raise ObserverCampaignCoordinatorError(
                        f"required observer candidate mint '{mint}' has no point-in-time market evidence"
                    )
                resolved.append(_candidate_from_row(row))
            return tuple(resolved)
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"required observer candidate read failed: {error}"
            ) from error
        except (TypeError, ValueError) as error:
            raise ObserverCampaignCoordinatorError(
                f"required observer candidate evidence is invalid: {error}"
            ) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                f"file:{self._database_path}?mode=ro",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign database open failed: {error}"
            ) from error

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        try:
            for table, required in _REQUIRED_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
                columns = frozenset(str(row[1]) for row in rows)
                missing = required - columns
                if missing:
                    raise ObserverCampaignCoordinatorError(
                        f"observer campaign database missing {table} columns: "
                        + ", ".join(sorted(missing))
                    )
        except ObserverCampaignCoordinatorError:
            raise
        except sqlite3.Error as error:
            raise ObserverCampaignCoordinatorError(
                f"observer campaign schema validation failed: {error}"
            ) from error


def _candidate_from_row(row: tuple[object, ...]) -> ObserverCampaignCandidate:
    if len(row) != 3:
        raise ObserverCampaignCoordinatorError("observer campaign candidate row is malformed")
    candidate_id, mint, latest_market = row
    try:
        return ObserverCampaignCandidate(
            candidate_id=candidate_id,  # type: ignore[arg-type]
            mint=mint,  # type: ignore[arg-type]
            latest_market_observed_at_unix_ms=latest_market,  # type: ignore[arg-type]
        )
    except ValueError as error:
        raise ObserverCampaignCoordinatorError(str(error)) from error


def _reject_ambiguous_mints(
    candidates: tuple[ObserverCampaignCandidate, ...],
) -> None:
    by_mint: dict[str, int] = {}
    for candidate in candidates:
        existing = by_mint.get(candidate.mint)
        if existing is not None and existing != candidate.candidate_id:
            raise ObserverCampaignCoordinatorError(
                f"recent observer candidate mint '{candidate.mint}' is ambiguous"
            )
        by_mint[candidate.mint] = candidate.candidate_id


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")
