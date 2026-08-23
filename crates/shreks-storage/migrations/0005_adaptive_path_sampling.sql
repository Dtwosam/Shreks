CREATE TABLE candidate_path_sampling (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES token_candidates(id) ON DELETE CASCADE,
    next_due_at_unix_ms INTEGER,
    last_sample_at_unix_ms INTEGER,
    sample_count INTEGER NOT NULL DEFAULT 0
        CHECK(sample_count >= 0),
    status TEXT NOT NULL
        CHECK(status IN ('active', 'completed')),
    cadence_version TEXT NOT NULL,
    CHECK(
        (status = 'active' AND next_due_at_unix_ms IS NOT NULL)
        OR
        (status = 'completed' AND next_due_at_unix_ms IS NULL)
    )
);

CREATE INDEX idx_candidate_path_sampling_due
ON candidate_path_sampling(status, next_due_at_unix_ms, candidate_id);
