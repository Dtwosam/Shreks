CREATE TABLE fast_future_path_labels (
    decision_signature TEXT NOT NULL CHECK (length(trim(decision_signature)) > 0),
    decision_ordinal INTEGER NOT NULL CHECK (decision_ordinal >= 0),
    decision_sequence INTEGER NOT NULL CHECK (decision_sequence > 0),
    decision_mint TEXT NOT NULL CHECK (length(trim(decision_mint)) > 0),
    decision_quote_mint TEXT NOT NULL CHECK (length(trim(decision_quote_mint)) > 0),
    decision_venue TEXT NOT NULL CHECK (length(trim(decision_venue)) > 0),
    decision_observed_at_unix_ms INTEGER NOT NULL CHECK (decision_observed_at_unix_ms >= 0),
    decision_entry_price_quote REAL NOT NULL CHECK (decision_entry_price_quote > 0),
    decision_entry_total_quote REAL CHECK (decision_entry_total_quote IS NULL OR decision_entry_total_quote > 0),
    coverage_complete_through_unix_ms INTEGER NOT NULL CHECK (coverage_complete_through_unix_ms >= 0),
    coverage_contiguous INTEGER NOT NULL CHECK (coverage_contiguous IN (0, 1)),
    horizon_ms INTEGER NOT NULL CHECK (horizon_ms > 0),
    label_version INTEGER NOT NULL CHECK (label_version > 0),
    completeness TEXT NOT NULL CHECK (completeness IN ('complete', 'incomplete')),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    no_trade_events INTEGER NOT NULL CHECK (no_trade_events IN (0, 1)),
    endpoint_signature TEXT,
    endpoint_ordinal INTEGER CHECK (endpoint_ordinal IS NULL OR endpoint_ordinal >= 0),
    endpoint_observed_at_unix_ms INTEGER CHECK (endpoint_observed_at_unix_ms IS NULL OR endpoint_observed_at_unix_ms >= 0),
    endpoint_price_quote REAL CHECK (endpoint_price_quote IS NULL OR endpoint_price_quote > 0),
    endpoint_return_bps REAL,
    mfe_bps REAL,
    mae_bps REAL,
    time_to_peak_ms INTEGER CHECK (time_to_peak_ms IS NULL OR time_to_peak_ms >= 0),
    time_to_trough_ms INTEGER CHECK (time_to_trough_ms IS NULL OR time_to_trough_ms >= 0),
    reversal_occurred INTEGER CHECK (reversal_occurred IS NULL OR reversal_occurred IN (0, 1)),
    first_reversal_after_ms INTEGER CHECK (first_reversal_after_ms IS NULL OR first_reversal_after_ms >= 0),
    min_exit_capacity_base REAL CHECK (min_exit_capacity_base IS NULL OR min_exit_capacity_base >= 0),
    endpoint_exit_capacity_base REAL CHECK (endpoint_exit_capacity_base IS NULL OR endpoint_exit_capacity_base >= 0),
    route_unavailability_observed INTEGER CHECK (route_unavailability_observed IS NULL OR route_unavailability_observed IN (0, 1)),
    best_cost_adjusted_return_bps REAL,
    endpoint_cost_adjusted_return_bps REAL,
    PRIMARY KEY (decision_signature, decision_ordinal, horizon_ms, label_version),
    FOREIGN KEY (decision_signature, decision_ordinal)
        REFERENCES fast_events (signature, ordinal)
        ON DELETE RESTRICT,
    FOREIGN KEY (endpoint_signature, endpoint_ordinal)
        REFERENCES fast_events (signature, ordinal)
        ON DELETE RESTRICT,
    CHECK ((endpoint_signature IS NULL) = (endpoint_ordinal IS NULL)),
    CHECK (
        (completeness = 'incomplete' AND event_count = 0 AND no_trade_events = 0)
        OR
        (completeness = 'complete' AND event_count = 0 AND no_trade_events = 1)
        OR
        (completeness = 'complete' AND event_count > 0 AND no_trade_events = 0)
    ),
    CHECK (
        event_count > 0
        OR (
            endpoint_signature IS NULL
            AND endpoint_ordinal IS NULL
            AND endpoint_observed_at_unix_ms IS NULL
            AND endpoint_price_quote IS NULL
            AND endpoint_return_bps IS NULL
            AND mfe_bps IS NULL
            AND mae_bps IS NULL
            AND time_to_peak_ms IS NULL
            AND time_to_trough_ms IS NULL
            AND reversal_occurred IS NULL
            AND first_reversal_after_ms IS NULL
            AND min_exit_capacity_base IS NULL
            AND endpoint_exit_capacity_base IS NULL
            AND route_unavailability_observed IS NULL
            AND best_cost_adjusted_return_bps IS NULL
            AND endpoint_cost_adjusted_return_bps IS NULL
        )
    )
);

CREATE TRIGGER fast_future_path_labels_decision_price_source_guard
BEFORE INSERT ON fast_future_path_labels
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1
    FROM fast_events
    WHERE signature = NEW.decision_signature
      AND ordinal = NEW.decision_ordinal
      AND price_quote = NEW.decision_entry_price_quote
)
BEGIN
    SELECT RAISE(ABORT, 'future-path decision price must match canonical FastEvent');
END;

CREATE INDEX idx_fast_future_path_labels_decision_sequence
    ON fast_future_path_labels (decision_sequence, horizon_ms, label_version);

CREATE INDEX idx_fast_future_path_labels_market_horizon
    ON fast_future_path_labels (decision_mint, decision_quote_mint, decision_venue, horizon_ms, label_version);
