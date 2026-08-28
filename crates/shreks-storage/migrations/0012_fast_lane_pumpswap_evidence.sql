CREATE TABLE pump_swap_trade_evidence (
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
    PRIMARY KEY (signature, ordinal),
    UNIQUE (signature, log_index)
);

CREATE INDEX idx_pump_swap_trade_evidence_pool_time
    ON pump_swap_trade_evidence (
        pool,
        timestamp_unix_seconds,
        signature,
        log_index
    );

CREATE INDEX idx_pump_swap_trade_evidence_observed
    ON pump_swap_trade_evidence (
        observed_at_unix_ms,
        signature,
        ordinal
    );

-- Migration 11 linked every canonical row directly to the bonding-curve raw
-- table. PumpSwap is a distinct evidence source, so rebuild the append-only
-- journal without a single-table FK and enforce venue-aware source integrity
-- with triggers below. Existing sequences and rows are copied unchanged.
CREATE TABLE fast_events_v12 (
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
    UNIQUE (signature, ordinal)
);

INSERT INTO fast_events_v12 (
    sequence, signature, ordinal, provider, slot,
    source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
    mint, quote_mint, venue, kind, actor,
    base_quantity, quote_quantity, price_quote,
    base_decimals, quote_decimals
)
SELECT
    sequence, signature, ordinal, provider, slot,
    source_observed_at_unix_ms, occurred_at_unix_ms, observed_at_unix_ms,
    mint, quote_mint, venue, kind, actor,
    base_quantity, quote_quantity, price_quote,
    base_decimals, quote_decimals
FROM fast_events;

DROP TABLE fast_events;
ALTER TABLE fast_events_v12 RENAME TO fast_events;

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
    SELECT RAISE(IGNORE);
END;

CREATE TRIGGER trg_fast_events_pump_source
BEFORE INSERT ON fast_events
FOR EACH ROW
WHEN NEW.venue = 'pump_fun_bonding_curve'
     AND NOT EXISTS (
         SELECT 1
         FROM pump_trade_evidence
         WHERE signature = NEW.signature AND ordinal = NEW.ordinal
     )
BEGIN
    SELECT RAISE(ABORT, 'missing Pump bonding-curve source evidence');
END;

CREATE TRIGGER trg_fast_events_pumpswap_source
BEFORE INSERT ON fast_events
FOR EACH ROW
WHEN NEW.venue = 'pump_swap'
     AND NOT EXISTS (
         SELECT 1
         FROM pump_swap_trade_evidence
         WHERE signature = NEW.signature AND ordinal = NEW.ordinal
     )
BEGIN
    SELECT RAISE(ABORT, 'missing PumpSwap source evidence');
END;

CREATE TRIGGER trg_pump_trade_evidence_restrict_canonical_delete
BEFORE DELETE ON pump_trade_evidence
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM fast_events
    WHERE signature = OLD.signature
      AND ordinal = OLD.ordinal
      AND venue = 'pump_fun_bonding_curve'
)
BEGIN
    SELECT RAISE(ABORT, 'Pump bonding-curve evidence is referenced by FastEvent');
END;

CREATE TRIGGER trg_pump_swap_trade_evidence_restrict_canonical_delete
BEFORE DELETE ON pump_swap_trade_evidence
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM fast_events
    WHERE signature = OLD.signature
      AND ordinal = OLD.ordinal
      AND venue = 'pump_swap'
)
BEGIN
    SELECT RAISE(ABORT, 'PumpSwap evidence is referenced by FastEvent');
END;

CREATE INDEX idx_fast_events_market_sequence
    ON fast_events (mint, quote_mint, venue, sequence);

CREATE INDEX idx_fast_events_observed_sequence
    ON fast_events (observed_at_unix_ms, sequence);
