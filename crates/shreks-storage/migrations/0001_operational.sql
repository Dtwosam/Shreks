CREATE TABLE provider_health (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'unavailable')),
    observed_at_unix_ms INTEGER NOT NULL,
    latency_ms INTEGER,
    detail TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0)
);

CREATE TABLE token_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mint TEXT NOT NULL,
    pair_address TEXT NOT NULL DEFAULT '',
    discovery_source TEXT NOT NULL,
    discovered_at_unix_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'observing',
    created_at_unix_ms INTEGER NOT NULL,
    UNIQUE (mint, pair_address, discovery_source)
);

CREATE INDEX idx_token_candidates_discovered_at
    ON token_candidates (discovered_at_unix_ms DESC);
CREATE INDEX idx_token_candidates_mint
    ON token_candidates (mint);

CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_observed_at_unix_ms INTEGER,
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
    UNIQUE (candidate_id, observed_at_unix_ms, source)
);

CREATE INDEX idx_market_snapshots_candidate_time
    ON market_snapshots (candidate_id, observed_at_unix_ms DESC);
CREATE INDEX idx_market_snapshots_source_time
    ON market_snapshots (source, observed_at_unix_ms DESC);

CREATE TABLE raw_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    external_id TEXT,
    observed_at_unix_ms INTEGER NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT,
    UNIQUE (provider, observation_type, payload_sha256)
);

CREATE INDEX idx_raw_observations_provider_time
    ON raw_observations (provider, observed_at_unix_ms DESC);

CREATE TABLE ingestion_checkpoints (
    provider TEXT NOT NULL,
    stream TEXT NOT NULL,
    cursor TEXT,
    updated_at_unix_ms INTEGER NOT NULL,
    PRIMARY KEY (provider, stream)
);
