CREATE TABLE paper_quote_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('entry', 'exit')),
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
        purpose,
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

CREATE INDEX idx_paper_quote_snapshots_candidate_purpose_time
    ON paper_quote_snapshots (
        candidate_id,
        purpose,
        quoted_at_unix_ms DESC,
        provider,
        probe_policy_version
    );
