CREATE TABLE pump_trade_evidence_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0 AND ordinal <= 4294967295),
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    slot TEXT NOT NULL CHECK (length(trim(slot)) > 0),
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= 0),
    mint TEXT NOT NULL CHECK (length(trim(mint)) > 0),
    quote_mint TEXT NOT NULL CHECK (length(trim(quote_mint)) > 0),
    user TEXT NOT NULL CHECK (length(trim(user)) > 0),
    is_buy INTEGER NOT NULL CHECK (is_buy IN (0, 1)),
    token_amount_raw TEXT NOT NULL CHECK (length(token_amount_raw) > 0),
    sol_amount_raw TEXT NOT NULL CHECK (length(sol_amount_raw) > 0),
    quote_amount_raw TEXT NOT NULL CHECK (length(quote_amount_raw) > 0),
    timestamp_unix_seconds INTEGER NOT NULL CHECK (timestamp_unix_seconds >= 0),
    virtual_sol_reserves_raw TEXT NOT NULL CHECK (length(virtual_sol_reserves_raw) > 0),
    virtual_token_reserves_raw TEXT NOT NULL CHECK (length(virtual_token_reserves_raw) > 0),
    real_sol_reserves_raw TEXT NOT NULL CHECK (length(real_sol_reserves_raw) > 0),
    real_token_reserves_raw TEXT NOT NULL CHECK (length(real_token_reserves_raw) > 0),
    virtual_quote_reserves_raw TEXT NOT NULL CHECK (length(virtual_quote_reserves_raw) > 0),
    real_quote_reserves_raw TEXT NOT NULL CHECK (length(real_quote_reserves_raw) > 0),
    ix_name TEXT NOT NULL CHECK (length(trim(ix_name)) > 0),
    FOREIGN KEY (signature, ordinal)
        REFERENCES pump_trade_evidence(signature, ordinal)
        ON DELETE RESTRICT,
    UNIQUE (
        signature, ordinal, provider, slot,
        mint, quote_mint, user, is_buy,
        token_amount_raw, sol_amount_raw, quote_amount_raw,
        timestamp_unix_seconds,
        virtual_sol_reserves_raw, virtual_token_reserves_raw,
        real_sol_reserves_raw, real_token_reserves_raw,
        virtual_quote_reserves_raw, real_quote_reserves_raw,
        ix_name
    )
);

CREATE INDEX idx_pump_trade_evidence_conflicts_identity
    ON pump_trade_evidence_conflicts (signature, ordinal);
CREATE INDEX idx_pump_trade_evidence_conflicts_observed
    ON pump_trade_evidence_conflicts (observed_at_unix_ms, signature, ordinal);

CREATE TABLE pump_swap_trade_evidence_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 2147483648 AND ordinal <= 4294967295),
    log_index INTEGER NOT NULL CHECK (log_index >= 0 AND log_index < 2147483648),
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    slot TEXT NOT NULL CHECK (length(trim(slot)) > 0),
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= 0),
    pool TEXT NOT NULL CHECK (length(trim(pool)) > 0),
    user TEXT NOT NULL CHECK (length(trim(user)) > 0),
    is_buy INTEGER NOT NULL CHECK (is_buy IN (0, 1)),
    base_amount_raw TEXT NOT NULL CHECK (length(base_amount_raw) > 0),
    quote_amount_raw TEXT NOT NULL CHECK (length(quote_amount_raw) > 0),
    user_quote_amount_raw TEXT NOT NULL CHECK (length(user_quote_amount_raw) > 0),
    timestamp_unix_seconds INTEGER NOT NULL CHECK (timestamp_unix_seconds >= 0),
    pool_base_reserves_raw TEXT NOT NULL CHECK (length(pool_base_reserves_raw) > 0),
    pool_quote_reserves_raw TEXT NOT NULL CHECK (length(pool_quote_reserves_raw) > 0),
    FOREIGN KEY (signature, ordinal)
        REFERENCES pump_swap_trade_evidence(signature, ordinal)
        ON DELETE RESTRICT,
    UNIQUE (
        signature, ordinal, log_index, provider, slot,
        pool, user, is_buy,
        base_amount_raw, quote_amount_raw, user_quote_amount_raw,
        timestamp_unix_seconds, pool_base_reserves_raw, pool_quote_reserves_raw
    )
);

CREATE INDEX idx_pump_swap_trade_evidence_conflicts_identity
    ON pump_swap_trade_evidence_conflicts (signature, ordinal);
CREATE INDEX idx_pump_swap_trade_evidence_conflicts_observed
    ON pump_swap_trade_evidence_conflicts (observed_at_unix_ms, signature, ordinal);
