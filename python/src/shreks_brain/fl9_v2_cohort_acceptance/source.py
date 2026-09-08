from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Protocol

from .models import (
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CoverageSessionCheckpoint,
)


@dataclass(frozen=True, slots=True)
class Fl9V2SourceDecision:
    sequence: int
    signature: str
    ordinal: int
    provider: str
    observed_at_unix_ms: int
    mint: str
    quote_mint: str
    venue: str
    actor: str | None

    def __post_init__(self) -> None:
        _non_negative_int("sequence", self.sequence)
        _non_empty("signature", self.signature)
        _non_negative_int("ordinal", self.ordinal)
        _non_empty("provider", self.provider)
        _non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _non_empty("mint", self.mint)
        _non_empty("quote_mint", self.quote_mint)
        _non_empty("venue", self.venue)
        if self.actor is not None:
            _non_empty("actor", self.actor)

    @property
    def decision_identity(self) -> tuple[object, ...]:
        return (
            self.signature,
            self.ordinal,
            self.sequence,
            self.mint,
            self.quote_mint,
            self.venue,
            self.observed_at_unix_ms,
        )

    @property
    def canonical_key(self) -> tuple[str, int]:
        return (self.signature, self.ordinal)


@dataclass(frozen=True, slots=True)
class Fl9V2SourceSnapshot:
    latest_session_id: int
    source_sessions: tuple[Fl9V2CoverageSessionCheckpoint, ...]
    raw_decisions: tuple[Fl9V2SourceDecision, ...]
    cross_session_duplicate_count: int
    raw_unique_mint_count: int

    def __post_init__(self) -> None:
        _non_negative_int("latest_session_id", self.latest_session_id)
        if not isinstance(self.source_sessions, tuple) or not self.source_sessions:
            raise ValueError("source_sessions must be a non-empty tuple")
        if not all(
            type(value) is Fl9V2CoverageSessionCheckpoint
            for value in self.source_sessions
        ):
            raise ValueError(
                "source_sessions must contain exact checkpoint values"
            )
        if not isinstance(self.raw_decisions, tuple):
            raise ValueError("raw_decisions must be a tuple")
        if not all(
            type(value) is Fl9V2SourceDecision
            for value in self.raw_decisions
        ):
            raise ValueError(
                "raw_decisions must contain exact source decision values"
            )
        expected = tuple(sorted(self.raw_decisions, key=_decision_sort_key))
        if self.raw_decisions != expected:
            raise ValueError("raw_decisions must be in canonical order")
        keys = tuple(value.canonical_key for value in self.raw_decisions)
        if len(keys) != len(set(keys)):
            raise ValueError("raw_decisions contain duplicate canonical identities")
        _non_negative_int(
            "cross_session_duplicate_count",
            self.cross_session_duplicate_count,
        )
        _non_negative_int("raw_unique_mint_count", self.raw_unique_mint_count)
        if len({value.mint for value in self.raw_decisions}) != (
            self.raw_unique_mint_count
        ):
            raise ValueError("raw_unique_mint_count does not reconcile")


class Fl9V2CohortSource(Protocol):
    def load_source_snapshot(
        self,
        policy: Fl9V2CohortAcceptancePolicy,
    ) -> Fl9V2SourceSnapshot:
        ...


class SqliteFl9V2CohortSource:
    def __init__(self, database_path: str | Path) -> None:
        path = Path(database_path).expanduser().resolve()
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                "FL9 V2 cohort source database must be an existing regular file"
            )
        self._database_path = path

    def load_source_snapshot(
        self,
        policy: Fl9V2CohortAcceptancePolicy,
    ) -> Fl9V2SourceSnapshot:
        if type(policy) is not Fl9V2CohortAcceptancePolicy:
            raise ValueError(
                "policy must be exact Fl9V2CohortAcceptancePolicy"
            )

        connection = self._connect()
        try:
            latest_row = connection.execute(
                "SELECT MAX(session_id) FROM fast_realtime_coverage_sessions"
            ).fetchone()
            latest_session_id = latest_row[0] if latest_row is not None else None
            if (
                isinstance(latest_session_id, bool)
                or not isinstance(latest_session_id, int)
                or latest_session_id < policy.required_latest_session_id
            ):
                raise ValueError(
                    "FL9 V2 cohort source sessions are not yet immutable: "
                    "latest session is below required boundary"
                )

            placeholders = ",".join("?" for _ in policy.source_session_ids)
            rows = connection.execute(
                f"""
                SELECT
                    session_id,
                    provider,
                    process_session_sequence,
                    first_notification_observed_at_unix_ms,
                    last_notification_observed_at_unix_ms,
                    notification_count
                FROM fast_realtime_coverage_sessions
                WHERE session_id IN ({placeholders})
                ORDER BY session_id
                """,
                policy.source_session_ids,
            ).fetchall()
            actual_sessions = tuple(
                Fl9V2CoverageSessionCheckpoint(
                    session_id=row["session_id"],
                    provider=row["provider"],
                    process_session_sequence=row[
                        "process_session_sequence"
                    ],
                    first_notification_observed_at_unix_ms=row[
                        "first_notification_observed_at_unix_ms"
                    ],
                    last_notification_observed_at_unix_ms=row[
                        "last_notification_observed_at_unix_ms"
                    ],
                    notification_count=row["notification_count"],
                )
                for row in rows
            )
            if actual_sessions != policy.source_sessions:
                raise ValueError(
                    "FL9 V2 cohort source session metadata contradicts "
                    "the frozen checkpoint"
                )

            window_rows: list[tuple[int, Fl9V2SourceDecision]] = []
            for session in policy.source_sessions:
                decision_rows = connection.execute(
                    """
                    SELECT
                        sequence,
                        signature,
                        ordinal,
                        provider,
                        observed_at_unix_ms,
                        mint,
                        quote_mint,
                        venue,
                        actor
                    FROM fast_events
                    WHERE venue = 'pump_swap'
                      AND observed_at_unix_ms >= ?
                      AND observed_at_unix_ms <= ?
                    ORDER BY
                        observed_at_unix_ms,
                        sequence,
                        signature,
                        ordinal
                    """,
                    (
                        session.first_notification_observed_at_unix_ms,
                        session.last_notification_observed_at_unix_ms,
                    ),
                ).fetchall()
                for row in decision_rows:
                    window_rows.append(
                        (
                            session.session_id,
                            Fl9V2SourceDecision(
                                sequence=row["sequence"],
                                signature=row["signature"],
                                ordinal=row["ordinal"],
                                provider=row["provider"],
                                observed_at_unix_ms=row[
                                    "observed_at_unix_ms"
                                ],
                                mint=row["mint"],
                                quote_mint=row["quote_mint"],
                                venue=row["venue"],
                                actor=row["actor"],
                            ),
                        )
                    )
        except sqlite3.Error as exc:
            raise ValueError(
                f"FL9 V2 cohort source read failed: {exc}"
            ) from exc
        finally:
            connection.close()

        raw_decisions, duplicate_count = _canonicalize_window_rows(
            tuple(window_rows)
        )
        return Fl9V2SourceSnapshot(
            latest_session_id=latest_session_id,
            source_sessions=actual_sessions,
            raw_decisions=raw_decisions,
            cross_session_duplicate_count=duplicate_count,
            raw_unique_mint_count=len(
                {value.mint for value in raw_decisions}
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self._database_path.as_uri()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return connection
        except sqlite3.Error as exc:
            raise ValueError(
                f"unable to open FL9 V2 cohort database read-only: {exc}"
            ) from exc


def _canonicalize_window_rows(
    rows: tuple[tuple[int, Fl9V2SourceDecision], ...],
) -> tuple[tuple[Fl9V2SourceDecision, ...], int]:
    canonical: dict[tuple[str, int], Fl9V2SourceDecision] = {}
    duplicate_count = 0
    for session_id, row in rows:
        _non_negative_int("session_id", session_id)
        if type(row) is not Fl9V2SourceDecision:
            raise ValueError(
                "window rows must contain exact Fl9V2SourceDecision values"
            )
        existing = canonical.get(row.canonical_key)
        if existing is None:
            canonical[row.canonical_key] = row
            continue
        if existing != row:
            raise ValueError(
                "contradictory canonical FL9 V2 source decision identity"
            )
        duplicate_count += 1

    return (
        tuple(sorted(canonical.values(), key=_decision_sort_key)),
        duplicate_count,
    )


def _decision_sort_key(
    value: Fl9V2SourceDecision,
) -> tuple[object, ...]:
    return (
        value.observed_at_unix_ms,
        value.sequence,
        value.signature,
        value.ordinal,
    )


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
