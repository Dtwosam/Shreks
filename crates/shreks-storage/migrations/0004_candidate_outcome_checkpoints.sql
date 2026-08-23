CREATE TABLE candidate_outcome_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    horizon_seconds INTEGER NOT NULL CHECK (
        horizon_seconds IN (60, 300, 900, 1800, 3600, 14400, 86400)
    ),
    due_at_unix_ms INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    baseline_snapshot_id INTEGER,
    checkpoint_snapshot_id INTEGER,
    completed_at_unix_ms INTEGER,
    return_pct REAL,
    mfe_pct REAL,
    mae_pct REAL,
    liquidity_change_pct REAL,
    volume_m5_change_pct REAL,
    buys_m5_change INTEGER,
    sells_m5_change INTEGER,
    rug_or_dead_pool INTEGER CHECK (rug_or_dead_pool IS NULL OR rug_or_dead_pool IN (0, 1)),
    exitability TEXT CHECK (exitability IS NULL OR exitability IN ('exitable', 'not_exitable')),
    FOREIGN KEY (candidate_id) REFERENCES token_candidates (id) ON DELETE CASCADE,
    FOREIGN KEY (baseline_snapshot_id) REFERENCES market_snapshots (id) ON DELETE RESTRICT,
    FOREIGN KEY (checkpoint_snapshot_id) REFERENCES market_snapshots (id) ON DELETE RESTRICT,
    UNIQUE (candidate_id, horizon_seconds),
    CHECK (
        (status = 'pending'
            AND baseline_snapshot_id IS NULL
            AND checkpoint_snapshot_id IS NULL
            AND completed_at_unix_ms IS NULL)
        OR
        (status = 'completed'
            AND baseline_snapshot_id IS NOT NULL
            AND checkpoint_snapshot_id IS NOT NULL
            AND completed_at_unix_ms IS NOT NULL)
    )
);

CREATE INDEX idx_candidate_outcomes_pending_due
    ON candidate_outcome_checkpoints (status, due_at_unix_ms, candidate_id);
CREATE INDEX idx_candidate_outcomes_candidate_horizon
    ON candidate_outcome_checkpoints (candidate_id, horizon_seconds);
