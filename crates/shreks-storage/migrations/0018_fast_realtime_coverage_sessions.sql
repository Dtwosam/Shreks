CREATE TABLE fast_realtime_coverage_sessions (
    session_id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    process_session_sequence INTEGER NOT NULL CHECK (process_session_sequence > 0),
    first_notification_observed_at_unix_ms INTEGER NOT NULL
        CHECK (first_notification_observed_at_unix_ms >= 0),
    last_notification_observed_at_unix_ms INTEGER NOT NULL
        CHECK (
            last_notification_observed_at_unix_ms
            >= first_notification_observed_at_unix_ms
        ),
    first_notification_slot TEXT NOT NULL
        CHECK (length(trim(first_notification_slot)) > 0),
    last_notification_slot TEXT NOT NULL
        CHECK (length(trim(last_notification_slot)) > 0),
    first_notification_signature TEXT NOT NULL
        CHECK (length(trim(first_notification_signature)) > 0),
    last_notification_signature TEXT NOT NULL
        CHECK (length(trim(last_notification_signature)) > 0),
    notification_count INTEGER NOT NULL CHECK (notification_count > 0)
);

CREATE INDEX idx_fast_realtime_coverage_sessions_time
    ON fast_realtime_coverage_sessions (
        first_notification_observed_at_unix_ms,
        last_notification_observed_at_unix_ms
    );
