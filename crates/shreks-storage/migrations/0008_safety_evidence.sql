CREATE TABLE token_holder_distributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    mint TEXT NOT NULL,
    last_indexed_slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= 0),
    reported_total_accounts TEXT NOT NULL,
    accounts_scanned INTEGER NOT NULL CHECK (accounts_scanned >= 0),
    unique_owners INTEGER NOT NULL CHECK (unique_owners >= 0),
    pages_scanned INTEGER NOT NULL CHECK (pages_scanned > 0),
    complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
    total_balance_raw TEXT NOT NULL,
    largest_owner TEXT,
    largest_owner_balance_raw TEXT,
    top_holder_concentration_pct REAL CHECK (
        top_holder_concentration_pct IS NULL
        OR (top_holder_concentration_pct >= 0.0 AND top_holder_concentration_pct <= 100.0)
    ),
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE CASCADE,
    UNIQUE (candidate_id, provider, mint, last_indexed_slot, observed_at_unix_ms),
    CHECK ((largest_owner IS NULL) = (largest_owner_balance_raw IS NULL)),
    CHECK (complete = 1 OR top_holder_concentration_pct IS NULL)
);

CREATE INDEX idx_token_holder_distributions_candidate_time
    ON token_holder_distributions (
        candidate_id,
        observed_at_unix_ms DESC,
        provider,
        last_indexed_slot
    );

CREATE TABLE exit_quote_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    probe_policy_version TEXT NOT NULL CHECK (length(trim(probe_policy_version)) > 0),
    input_mint TEXT NOT NULL,
    output_mint TEXT NOT NULL,
    taker TEXT NOT NULL,
    input_amount TEXT NOT NULL,
    output_amount TEXT NOT NULL,
    minimum_output_amount TEXT NOT NULL,
    slippage_bps INTEGER NOT NULL CHECK (slippage_bps >= 0 AND slippage_bps <= 10000),
    route_available INTEGER NOT NULL CHECK (route_available IN (0, 1)),
    price_impact_pct TEXT,
    route_labels_json TEXT NOT NULL,
    quoted_at_unix_ms INTEGER NOT NULL CHECK (quoted_at_unix_ms >= 0),
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE CASCADE,
    UNIQUE (
        candidate_id,
        provider,
        probe_policy_version,
        input_mint,
        output_mint,
        taker,
        input_amount,
        slippage_bps,
        quoted_at_unix_ms
    )
);

CREATE INDEX idx_exit_quote_snapshots_candidate_time
    ON exit_quote_snapshots (
        candidate_id,
        quoted_at_unix_ms DESC,
        provider,
        probe_policy_version
    );
