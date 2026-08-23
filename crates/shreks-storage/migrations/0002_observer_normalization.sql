ALTER TABLE token_candidates ADD COLUMN venue TEXT;

CREATE TABLE provider_health_v2 (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'rate_limited', 'unavailable')),
    observed_at_unix_ms INTEGER NOT NULL,
    latency_ms INTEGER,
    detail TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0)
);

INSERT INTO provider_health_v2 (
    provider,
    status,
    observed_at_unix_ms,
    latency_ms,
    detail,
    consecutive_failures
)
SELECT
    provider,
    status,
    observed_at_unix_ms,
    latency_ms,
    detail,
    consecutive_failures
FROM provider_health;

DROP TABLE provider_health;
ALTER TABLE provider_health_v2 RENAME TO provider_health;

CREATE TABLE market_snapshots_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_observed_at_unix_ms INTEGER,
    venue TEXT NOT NULL DEFAULT 'other_solana',
    pair_address TEXT NOT NULL DEFAULT '',
    dex_id TEXT NOT NULL DEFAULT '',
    base_mint TEXT NOT NULL DEFAULT '',
    quote_mint TEXT NOT NULL DEFAULT '',
    price_native TEXT,
    price_usd REAL,
    market_cap_usd REAL,
    fdv_usd REAL,
    liquidity_usd REAL,
    volume_m5_usd REAL,
    volume_h1_usd REAL,
    volume_h6_usd REAL,
    volume_h24_usd REAL,
    buys_m5 INTEGER CHECK (buys_m5 IS NULL OR buys_m5 >= 0),
    sells_m5 INTEGER CHECK (sells_m5 IS NULL OR sells_m5 >= 0),
    buys_h1 INTEGER CHECK (buys_h1 IS NULL OR buys_h1 >= 0),
    sells_h1 INTEGER CHECK (sells_h1 IS NULL OR sells_h1 >= 0),
    price_change_m5_pct REAL,
    price_change_h1_pct REAL,
    pair_created_at_unix_ms INTEGER,
    raw_ref TEXT,
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE CASCADE,
    UNIQUE (candidate_id, observed_at_unix_ms, source, pair_address)
);

INSERT INTO market_snapshots_v2 (
    id,
    candidate_id,
    observed_at_unix_ms,
    source,
    source_observed_at_unix_ms,
    price_usd,
    market_cap_usd,
    fdv_usd,
    liquidity_usd,
    volume_m5_usd,
    volume_h1_usd,
    volume_h6_usd,
    volume_h24_usd,
    buys_m5,
    sells_m5,
    buys_h1,
    sells_h1,
    price_change_m5_pct,
    price_change_h1_pct,
    pair_created_at_unix_ms,
    raw_ref
)
SELECT
    id,
    candidate_id,
    observed_at_unix_ms,
    source,
    source_observed_at_unix_ms,
    price_usd,
    market_cap_usd,
    fdv_usd,
    liquidity_usd,
    volume_m5_usd,
    volume_h1_usd,
    volume_h6_usd,
    volume_h24_usd,
    buys_m5,
    sells_m5,
    buys_h1,
    sells_h1,
    price_change_m5_pct,
    price_change_h1_pct,
    pair_created_at_unix_ms,
    raw_ref
FROM market_snapshots;

DROP TABLE market_snapshots;
ALTER TABLE market_snapshots_v2 RENAME TO market_snapshots;

CREATE INDEX idx_market_snapshots_candidate_time
    ON market_snapshots (candidate_id, observed_at_unix_ms DESC);
CREATE INDEX idx_market_snapshots_source_time
    ON market_snapshots (source, observed_at_unix_ms DESC);
CREATE INDEX idx_market_snapshots_venue_time
    ON market_snapshots (venue, observed_at_unix_ms DESC);
CREATE INDEX idx_market_snapshots_pair_time
    ON market_snapshots (pair_address, observed_at_unix_ms DESC);

CREATE TABLE token_mint_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    owner_program TEXT NOT NULL,
    supply TEXT NOT NULL,
    decimals INTEGER NOT NULL CHECK (decimals >= 0 AND decimals <= 255),
    mint_authority TEXT,
    freeze_authority TEXT,
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE CASCADE,
    UNIQUE (candidate_id, provider, slot)
);

CREATE INDEX idx_token_mint_states_candidate_time
    ON token_mint_states (candidate_id, observed_at_unix_ms DESC);
CREATE INDEX idx_token_mint_states_provider_time
    ON token_mint_states (provider, observed_at_unix_ms DESC);
