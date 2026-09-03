from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from shreks_brain.fast_paper import (
    FAST_PAPER_SKIP_AUDIT_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperSkipAuditError,
    FastPaperSkipAuditRecord,
    FastPaperSkipAuditView,
    FastPaperSkipFutureLabel,
    FastPaperSkipLabelLink,
    load_fast_paper_skip_with_future_labels,
    record_fast_paper_skip,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _REPO_ROOT / "crates" / "shreks-storage" / "migrations"


def _assessment() -> FastPaperActionAssessment:
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id="event-7",
        market_key="pump:mint-a:quote-a",
        source_sequence=7,
        as_of_unix_ms=1_000,
        strategy_family="impulse-scalp",
        strategy_version="1",
        action=FastPaperAction.SKIP,
        reasons=("insufficient_edge", "capacity_uncertain"),
    )


def _link(*, label_version: int = 1, venue: str = "pump") -> FastPaperSkipLabelLink:
    return FastPaperSkipLabelLink(
        decision_signature="sig-7",
        decision_ordinal=0,
        mint="mint-a",
        quote_mint="quote-a",
        venue=venue,
        future_path_label_version=label_version,
    )


def _database(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "shreks.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE fast_events (
                sequence INTEGER PRIMARY KEY,
                signature TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                mint TEXT NOT NULL,
                quote_mint TEXT NOT NULL,
                venue TEXT NOT NULL,
                observed_at_unix_ms INTEGER NOT NULL,
                price_quote REAL NOT NULL,
                UNIQUE (signature, ordinal)
            );
            """
        )
        connection.execute(
            """INSERT INTO fast_events (
                   sequence, signature, ordinal, mint, quote_mint, venue,
                   observed_at_unix_ms, price_quote
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (7, "sig-7", 0, "mint-a", "quote-a", "pump", 1_000, 1.0),
        )
        connection.executescript(
            (_MIGRATIONS / "0016_fast_future_path_labels.sql").read_text()
        )
        connection.executescript(
            (_MIGRATIONS / "0017_fast_paper_skip_records.sql").read_text()
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _insert_label(
    database_path: Path,
    *,
    horizon_ms: int,
    label_version: int = 1,
    endpoint_return_bps: float = 120.0,
    mfe_bps: float = 180.0,
    mae_bps: float = -45.0,
    reversal_occurred: bool = True,
    min_exit_capacity_base: float = 8.5,
    endpoint_exit_capacity_base: float = 9.0,
    route_unavailability_observed: bool = False,
    best_cost_adjusted_return_bps: float = 140.0,
    endpoint_cost_adjusted_return_bps: float = 95.0,
) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """INSERT INTO fast_future_path_labels (
                   decision_signature, decision_ordinal, decision_sequence,
                   decision_mint, decision_quote_mint, decision_venue,
                   decision_observed_at_unix_ms, decision_entry_price_quote,
                   decision_entry_total_quote,
                   coverage_complete_through_unix_ms, coverage_contiguous,
                   horizon_ms, label_version, completeness, event_count, no_trade_events,
                   endpoint_signature, endpoint_ordinal, endpoint_observed_at_unix_ms,
                   endpoint_price_quote, endpoint_return_bps, mfe_bps, mae_bps,
                   time_to_peak_ms, time_to_trough_ms, reversal_occurred,
                   first_reversal_after_ms, min_exit_capacity_base,
                   endpoint_exit_capacity_base, route_unavailability_observed,
                   best_cost_adjusted_return_bps, endpoint_cost_adjusted_return_bps
               ) VALUES (
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
               )""",
            (
                "sig-7",
                0,
                7,
                "mint-a",
                "quote-a",
                "pump",
                1_000,
                1.0,
                10.0,
                1_000 + horizon_ms,
                1,
                horizon_ms,
                label_version,
                "complete",
                1,
                0,
                None,
                None,
                1_000 + horizon_ms,
                1.0 + endpoint_return_bps / 10_000.0,
                endpoint_return_bps,
                mfe_bps,
                mae_bps,
                max(1, horizon_ms // 3),
                max(1, horizon_ms // 2),
                1 if reversal_occurred else 0,
                max(1, horizon_ms // 2) if reversal_occurred else None,
                min_exit_capacity_base,
                endpoint_exit_capacity_base,
                1 if route_unavailability_observed else 0,
                best_cost_adjusted_return_bps,
                endpoint_cost_adjusted_return_bps,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_skip_audit_public_version_is_stable() -> None:
    assert FAST_PAPER_SKIP_AUDIT_VERSION == "fl7.3-v1"


def test_only_skip_assessments_can_be_recorded(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    with pytest.raises(FastPaperSkipAuditError, match="SKIP"):
        record_fast_paper_skip(
            database_path,
            replace(_assessment(), action=FastPaperAction.BUY),
            _link(),
        )

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fast_paper_skip_records").fetchone()[0] == 0
    finally:
        connection.close()


def test_exact_skip_persistence_preserves_ordered_reasons_and_link(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    assessment = _assessment()
    link = _link()

    record = record_fast_paper_skip(database_path, assessment, link)

    assert isinstance(record, FastPaperSkipAuditRecord)
    assert record.version == FAST_PAPER_SKIP_AUDIT_VERSION
    assert len(record.record_id) == 64
    int(record.record_id, 16)
    assert record.assessment == assessment
    assert record.link == link

    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """SELECT reasons_json, source_sequence, as_of_unix_ms,
                      decision_signature, decision_ordinal,
                      decision_mint, decision_quote_mint, decision_venue,
                      future_path_label_version
               FROM fast_paper_skip_records"""
        ).fetchone()
    finally:
        connection.close()

    assert row == (
        '["insufficient_edge","capacity_uncertain"]',
        7,
        1_000,
        "sig-7",
        0,
        "mint-a",
        "quote-a",
        "pump",
        1,
    )


def test_exact_replay_is_idempotent_and_does_not_duplicate_rows(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    first = record_fast_paper_skip(database_path, _assessment(), _link())
    replay = record_fast_paper_skip(database_path, _assessment(), _link())

    assert replay == first
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fast_paper_skip_records").fetchone()[0] == 1
    finally:
        connection.close()


def test_conflicting_replay_for_same_logical_assessment_fails_closed(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    record_fast_paper_skip(database_path, _assessment(), _link())

    with pytest.raises(FastPaperSkipAuditError, match="conflict"):
        record_fast_paper_skip(
            database_path,
            replace(_assessment(), reasons=("different_reason",)),
            _link(),
        )


def test_canonical_fast_event_contradictions_fail_closed(tmp_path: Path) -> None:
    database_path = _database(tmp_path)

    with pytest.raises(FastPaperSkipAuditError, match="canonical FastEvent"):
        record_fast_paper_skip(
            database_path,
            replace(_assessment(), source_sequence=8),
            _link(),
        )

    with pytest.raises(FastPaperSkipAuditError, match="canonical FastEvent"):
        record_fast_paper_skip(
            database_path,
            replace(_assessment(), as_of_unix_ms=1_001),
            _link(),
        )

    with pytest.raises(FastPaperSkipAuditError, match="canonical FastEvent"):
        record_fast_paper_skip(database_path, _assessment(), _link(venue="pump_swap"))


def test_recording_skip_never_creates_future_labels(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    record_fast_paper_skip(database_path, _assessment(), _link())

    connection = sqlite3.connect(database_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM fast_future_path_labels").fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_future_labels_attach_later_without_mutating_skip_record(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    record = record_fast_paper_skip(database_path, _assessment(), _link())

    before = load_fast_paper_skip_with_future_labels(database_path, record.record_id)
    assert isinstance(before, FastPaperSkipAuditView)
    assert before.record == record
    assert before.future_labels == ()

    _insert_label(database_path, horizon_ms=3_000)
    _insert_label(database_path, horizon_ms=250)
    _insert_label(database_path, horizon_ms=500, label_version=2)

    after = load_fast_paper_skip_with_future_labels(database_path, record.record_id)
    assert after.record == record
    assert tuple(label.horizon_ms for label in after.future_labels) == (250, 3_000)
    assert all(label.label_version == 1 for label in after.future_labels)

    connection = sqlite3.connect(database_path)
    try:
        stored_record_id = connection.execute(
            "SELECT record_id FROM fast_paper_skip_records"
        ).fetchone()[0]
        assert stored_record_id == record.record_id
        assert connection.execute("SELECT COUNT(*) FROM fast_paper_skip_records").fetchone()[0] == 1
    finally:
        connection.close()


def test_future_label_fields_are_preserved_without_reinterpretation(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    record = record_fast_paper_skip(database_path, _assessment(), _link())
    _insert_label(
        database_path,
        horizon_ms=1_000,
        endpoint_return_bps=123.5,
        mfe_bps=222.25,
        mae_bps=-88.75,
        reversal_occurred=True,
        min_exit_capacity_base=7.25,
        endpoint_exit_capacity_base=8.75,
        route_unavailability_observed=True,
        best_cost_adjusted_return_bps=155.0,
        endpoint_cost_adjusted_return_bps=77.5,
    )

    view = load_fast_paper_skip_with_future_labels(database_path, record.record_id)
    assert len(view.future_labels) == 1
    label = view.future_labels[0]
    assert isinstance(label, FastPaperSkipFutureLabel)
    assert label.horizon_ms == 1_000
    assert label.label_version == 1
    assert label.completeness == "complete"
    assert label.coverage_complete_through_unix_ms == 2_000
    assert label.coverage_contiguous is True
    assert label.event_count == 1
    assert label.no_trade_events is False
    assert label.endpoint_observed_at_unix_ms == 2_000
    assert label.endpoint_return_bps == pytest.approx(123.5)
    assert label.mfe_bps == pytest.approx(222.25)
    assert label.mae_bps == pytest.approx(-88.75)
    assert label.reversal_occurred is True
    assert label.min_exit_capacity_base == pytest.approx(7.25)
    assert label.endpoint_exit_capacity_base == pytest.approx(8.75)
    assert label.route_unavailability_observed is True
    assert label.best_cost_adjusted_return_bps == pytest.approx(155.0)
    assert label.endpoint_cost_adjusted_return_bps == pytest.approx(77.5)


def test_record_id_is_deterministic_and_reason_order_is_semantic(tmp_path: Path) -> None:
    database_a = _database(tmp_path / "a")
    database_b = _database(tmp_path / "b")

    first = record_fast_paper_skip(database_a, _assessment(), _link())
    second = record_fast_paper_skip(database_b, _assessment(), _link())
    assert first.record_id == second.record_id

    reordered = replace(
        _assessment(), reasons=("capacity_uncertain", "insufficient_edge")
    )
    third_db = _database(tmp_path / "c")
    third = record_fast_paper_skip(third_db, reordered, _link())
    assert third.record_id != first.record_id


def test_missing_or_unmigrated_database_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(FastPaperSkipAuditError, match="does not exist"):
        record_fast_paper_skip(missing, _assessment(), _link())
    assert not missing.exists()

    unmigrated = tmp_path / "unmigrated.db"
    sqlite3.connect(unmigrated).close()
    with pytest.raises(FastPaperSkipAuditError, match="fast_paper_skip_records"):
        record_fast_paper_skip(unmigrated, _assessment(), _link())


def test_unknown_or_malformed_record_id_fails_closed(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    with pytest.raises(FastPaperSkipAuditError, match="record_id"):
        load_fast_paper_skip_with_future_labels(database_path, "not-a-hash")

    with pytest.raises(FastPaperSkipAuditError, match="not found"):
        load_fast_paper_skip_with_future_labels(database_path, "0" * 64)
