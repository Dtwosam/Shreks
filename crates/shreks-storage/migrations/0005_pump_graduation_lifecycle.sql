CREATE TABLE pump_migration_signals (
    signature TEXT PRIMARY KEY,
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= 0),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'verified', 'rejected')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at_unix_ms INTEGER,
    last_error TEXT
);

CREATE INDEX idx_pump_migration_signals_pending
    ON pump_migration_signals (status, observed_at_unix_ms ASC, signature ASC);

CREATE TABLE token_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    mint TEXT NOT NULL,
    quote_mint TEXT NOT NULL,
    from_venue TEXT NOT NULL,
    to_venue TEXT NOT NULL,
    pool_address TEXT NOT NULL,
    signature TEXT NOT NULL,
    slot TEXT NOT NULL,
    detected_at_unix_ms INTEGER NOT NULL CHECK (detected_at_unix_ms >= 0),
    occurred_at_unix_ms INTEGER,
    UNIQUE (event_type, signature, mint, pool_address),
    FOREIGN KEY (signature) REFERENCES pump_migration_signals (signature) ON DELETE RESTRICT
);

CREATE INDEX idx_token_lifecycle_events_mint_detected
    ON token_lifecycle_events (mint, detected_at_unix_ms ASC, signature ASC, pool_address ASC);

CREATE INDEX idx_token_lifecycle_events_type_detected
    ON token_lifecycle_events (event_type, detected_at_unix_ms ASC, signature ASC);
