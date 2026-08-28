CREATE TABLE fast_events (
    sequence INTEGER PRIMARY KEY CHECK (sequence > 0),
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    slot TEXT NOT NULL CHECK (length(trim(slot)) > 0),
    source_observed_at_unix_ms INTEGER NOT NULL CHECK (source_observed_at_unix_ms >= 0),
    occurred_at_unix_ms INTEGER NOT NULL CHECK (occurred_at_unix_ms >= 0),
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= source_observed_at_unix_ms),
    mint TEXT NOT NULL CHECK (length(trim(mint)) > 0),
    quote_mint TEXT NOT NULL CHECK (length(trim(quote_mint)) > 0),
    venue TEXT NOT NULL CHECK (length(trim(venue)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('buy', 'sell')),
    actor TEXT,
    base_quantity REAL NOT NULL CHECK (base_quantity > 0),
    quote_quantity REAL NOT NULL CHECK (quote_quantity > 0),
    price_quote REAL NOT NULL CHECK (price_quote > 0),
    base_decimals INTEGER NOT NULL CHECK (base_decimals >= 0 AND base_decimals <= 255),
    quote_decimals INTEGER NOT NULL CHECK (quote_decimals >= 0 AND quote_decimals <= 255),
    UNIQUE (signature, ordinal),
    FOREIGN KEY (signature, ordinal)
        REFERENCES pump_trade_evidence (signature, ordinal)
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_fast_events_contiguous_sequence
BEFORE INSERT ON fast_events
FOR EACH ROW
WHEN NOT EXISTS (
         SELECT 1
         FROM fast_events
         WHERE signature = NEW.signature AND ordinal = NEW.ordinal
     )
     AND NEW.sequence != (
         SELECT COALESCE(MAX(sequence), 0) + 1
         FROM fast_events
     )
BEGIN
    SELECT RAISE(ABORT, 'fast_events sequence must append contiguously');
END;

CREATE INDEX idx_fast_events_market_sequence
    ON fast_events (mint, quote_mint, venue, sequence);

CREATE INDEX idx_fast_events_observed_sequence
    ON fast_events (observed_at_unix_ms, sequence);
