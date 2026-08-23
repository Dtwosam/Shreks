CREATE TABLE pump_launch_signals (
    signature TEXT PRIMARY KEY,
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'verified', 'rejected')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at_unix_ms INTEGER,
    candidate_id INTEGER,
    last_error TEXT,
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE SET NULL
);

CREATE INDEX idx_pump_launch_signals_pending
    ON pump_launch_signals (status, observed_at_unix_ms ASC, signature ASC);
