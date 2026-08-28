CREATE TABLE pump_trade_evidence (
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
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
    PRIMARY KEY (signature, ordinal)
);

CREATE INDEX idx_pump_trade_evidence_mint_time
    ON pump_trade_evidence (
        mint,
        timestamp_unix_seconds,
        signature,
        ordinal
    );

CREATE INDEX idx_pump_trade_evidence_observed
    ON pump_trade_evidence (
        observed_at_unix_ms,
        signature,
        ordinal
    );
