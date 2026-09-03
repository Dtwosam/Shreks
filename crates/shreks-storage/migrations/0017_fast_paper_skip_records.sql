CREATE TABLE fast_paper_skip_records (
    record_id TEXT PRIMARY KEY CHECK (length(record_id) = 64),
    record_version TEXT NOT NULL CHECK (length(trim(record_version)) > 0),
    assessment_version TEXT NOT NULL CHECK (length(trim(assessment_version)) > 0),
    source_event_id TEXT NOT NULL CHECK (length(trim(source_event_id)) > 0),
    market_key TEXT NOT NULL CHECK (length(trim(market_key)) > 0),
    source_sequence INTEGER NOT NULL CHECK (source_sequence > 0),
    as_of_unix_ms INTEGER NOT NULL CHECK (as_of_unix_ms >= 0),
    strategy_family TEXT NOT NULL CHECK (length(trim(strategy_family)) > 0),
    strategy_version TEXT NOT NULL CHECK (length(trim(strategy_version)) > 0),
    reasons_json TEXT NOT NULL CHECK (length(trim(reasons_json)) > 0),
    decision_signature TEXT NOT NULL CHECK (length(trim(decision_signature)) > 0),
    decision_ordinal INTEGER NOT NULL CHECK (decision_ordinal >= 0),
    decision_mint TEXT NOT NULL CHECK (length(trim(decision_mint)) > 0),
    decision_quote_mint TEXT NOT NULL CHECK (length(trim(decision_quote_mint)) > 0),
    decision_venue TEXT NOT NULL CHECK (length(trim(decision_venue)) > 0),
    future_path_label_version INTEGER NOT NULL CHECK (future_path_label_version > 0),
    UNIQUE (source_event_id, strategy_family, strategy_version, assessment_version)
);

CREATE TRIGGER fast_paper_skip_records_canonical_source_guard
BEFORE INSERT ON fast_paper_skip_records
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1
    FROM fast_events
    WHERE signature = NEW.decision_signature
      AND ordinal = NEW.decision_ordinal
      AND sequence = NEW.source_sequence
      AND mint = NEW.decision_mint
      AND quote_mint = NEW.decision_quote_mint
      AND venue = NEW.decision_venue
      AND observed_at_unix_ms = NEW.as_of_unix_ms
)
BEGIN
    SELECT RAISE(ABORT, 'fast PAPER SKIP decision must match canonical FastEvent');
END;

CREATE TRIGGER fast_paper_skip_records_restrict_canonical_delete
BEFORE DELETE ON fast_events
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM fast_paper_skip_records
    WHERE decision_signature = OLD.signature
      AND decision_ordinal = OLD.ordinal
)
BEGIN
    SELECT RAISE(ABORT, 'FastEvent is referenced by Fast PAPER SKIP audit');
END;

CREATE INDEX idx_fast_paper_skip_records_future_labels
    ON fast_paper_skip_records (
        decision_signature, decision_ordinal, future_path_label_version
    );

CREATE INDEX idx_fast_paper_skip_records_market_time
    ON fast_paper_skip_records (
        decision_mint, decision_quote_mint, decision_venue, as_of_unix_ms
    );
