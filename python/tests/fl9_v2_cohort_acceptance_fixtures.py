from __future__ import annotations

from pathlib import Path
import sqlite3

from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptancePolicy,
)


_SOURCE_SCHEMA = """
CREATE TABLE fast_realtime_coverage_sessions (
    session_id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    process_session_sequence INTEGER NOT NULL,
    first_notification_observed_at_unix_ms INTEGER NOT NULL,
    last_notification_observed_at_unix_ms INTEGER NOT NULL,
    notification_count INTEGER NOT NULL
);

CREATE TABLE fast_events (
    sequence INTEGER PRIMARY KEY,
    signature TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    provider TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    mint TEXT NOT NULL,
    quote_mint TEXT NOT NULL,
    venue TEXT NOT NULL,
    actor TEXT
);
"""


def source_database(
    tmp_path: Path,
    *,
    include_session_123: bool = True,
    latest_session_id: int = 123,
    drift_session_id: int | None = None,
    reverse_events: bool = False,
) -> Path:
    path = tmp_path / "observer.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_SOURCE_SCHEMA)
        policy = Fl9V2CohortAcceptancePolicy()

        for session in policy.source_sessions:
            provider = session.provider
            if drift_session_id == session.session_id:
                provider = "drifted-provider"
            connection.execute(
                """
                INSERT INTO fast_realtime_coverage_sessions (
                    session_id,
                    provider,
                    process_session_sequence,
                    first_notification_observed_at_unix_ms,
                    last_notification_observed_at_unix_ms,
                    notification_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    provider,
                    session.process_session_sequence,
                    session.first_notification_observed_at_unix_ms,
                    session.last_notification_observed_at_unix_ms,
                    session.notification_count,
                ),
            )

        if include_session_123:
            connection.execute(
                """
                INSERT INTO fast_realtime_coverage_sessions (
                    session_id,
                    provider,
                    process_session_sequence,
                    first_notification_observed_at_unix_ms,
                    last_notification_observed_at_unix_ms,
                    notification_count
                ) VALUES (?, 'solana_public', 1, ?, ?, 1)
                """,
                (
                    latest_session_id,
                    policy.test_end_unix_ms + 1,
                    policy.test_end_unix_ms + 2,
                ),
            )

        events = []
        sequence = 1
        for session in policy.source_sessions:
            events.append(
                (
                    sequence,
                    f"sig-{session.session_id}",
                    0,
                    "solana_public",
                    session.first_notification_observed_at_unix_ms + 1,
                    f"mint-{session.session_id}",
                    "quote-sol",
                    "pump_swap",
                    None if session.session_id == 118 else f"actor-{session.session_id}",
                )
            )
            sequence += 1

        # This row is inside the broad 115..122 timestamp range but not inside
        # any exact source-session window. It must never be selected.
        events.append(
            (
                sequence,
                "gap-signature",
                0,
                "solana_public",
                1_788_893_000_000,
                "gap-mint",
                "quote-sol",
                "pump_swap",
                "gap-actor",
            )
        )
        sequence += 1

        # Wrong venue inside a valid session must be excluded.
        events.append(
            (
                sequence,
                "bonding-signature",
                0,
                "solana_public",
                policy.source_sessions[0].first_notification_observed_at_unix_ms + 2,
                "bonding-mint",
                "quote-sol",
                "pump_fun_bonding_curve",
                "bonding-actor",
            )
        )

        if reverse_events:
            events = list(reversed(events))

        connection.executemany(
            """
            INSERT INTO fast_events (
                sequence,
                signature,
                ordinal,
                provider,
                observed_at_unix_ms,
                mint,
                quote_mint,
                venue,
                actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            events,
        )
        connection.commit()
    finally:
        connection.close()
    return path
