CREATE TABLE paper_loop_checkpoints (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    checkpoint_schema_version TEXT NOT NULL,
    state_as_of_unix_ms INTEGER NOT NULL CHECK (state_as_of_unix_ms >= 0),
    created_at_unix_ms INTEGER NOT NULL CHECK (created_at_unix_ms >= 0),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE INDEX idx_paper_loop_checkpoints_run_latest
    ON paper_loop_checkpoints (run_id, sequence DESC);
