from __future__ import annotations

from pathlib import Path

import pytest

from fl9_v2_cohort_acceptance_fixtures import source_database
from shreks_brain.fl9_v2_cohort_acceptance import (
    Fl9V2CohortAcceptancePolicy,
)
from shreks_brain.fl9_v2_cohort_acceptance.source import (
    Fl9V2SourceDecision,
    SqliteFl9V2CohortSource,
    _canonicalize_window_rows,
)


def test_source_reads_union_of_exact_session_windows_not_broad_range(tmp_path) -> None:
    db = source_database(tmp_path)
    snapshot = SqliteFl9V2CohortSource(db).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )

    signatures = {row.signature for row in snapshot.raw_decisions}
    assert "gap-signature" not in signatures
    assert "bonding-signature" not in signatures
    assert signatures == {f"sig-{value}" for value in range(115, 123)}
    assert snapshot.cross_session_duplicate_count == 0
    assert snapshot.raw_unique_mint_count == 8


def test_source_requires_session_122_to_be_immutable(tmp_path) -> None:
    db = source_database(tmp_path, include_session_123=False)

    with pytest.raises(ValueError, match="immutable|latest session"):
        SqliteFl9V2CohortSource(db).load_source_snapshot(
            Fl9V2CohortAcceptancePolicy()
        )


def test_source_accepts_later_current_session_without_semantic_change(tmp_path) -> None:
    first = source_database(tmp_path / "a", latest_session_id=123)
    second = source_database(tmp_path / "b", latest_session_id=124)

    one = SqliteFl9V2CohortSource(first).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )
    two = SqliteFl9V2CohortSource(second).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )

    assert one.raw_decisions == two.raw_decisions
    assert one.source_sessions == two.source_sessions
    assert one.cross_session_duplicate_count == two.cross_session_duplicate_count


def test_source_session_metadata_drift_fails_closed(tmp_path) -> None:
    db = source_database(tmp_path, drift_session_id=119)

    with pytest.raises(ValueError, match="session.*119|metadata|checkpoint"):
        SqliteFl9V2CohortSource(db).load_source_snapshot(
            Fl9V2CohortAcceptancePolicy()
        )


def test_source_row_order_is_canonical_independent_of_insertion_order(tmp_path) -> None:
    first = source_database(tmp_path / "a", reverse_events=False)
    second = source_database(tmp_path / "b", reverse_events=True)

    one = SqliteFl9V2CohortSource(first).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )
    two = SqliteFl9V2CohortSource(second).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )

    assert one.raw_decisions == two.raw_decisions
    assert tuple(row.sequence for row in one.raw_decisions) == tuple(range(1, 9))


def test_null_actor_is_retained_as_input_evidence(tmp_path) -> None:
    db = source_database(tmp_path)
    snapshot = SqliteFl9V2CohortSource(db).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )

    row = next(value for value in snapshot.raw_decisions if value.signature == "sig-118")
    assert row.actor is None


def _decision(*, mint: str = "mint") -> Fl9V2SourceDecision:
    return Fl9V2SourceDecision(
        sequence=1,
        signature="sig",
        ordinal=0,
        provider="solana_public",
        observed_at_unix_ms=1_000,
        mint=mint,
        quote_mint="quote",
        venue="pump_swap",
        actor="actor",
    )


def test_identical_cross_window_duplicate_deduplicates() -> None:
    row = _decision()
    rows, duplicate_count = _canonicalize_window_rows(
        ((115, row), (116, row))
    )
    assert rows == (row,)
    assert duplicate_count == 1


def test_contradictory_cross_window_duplicate_fails_closed() -> None:
    with pytest.raises(ValueError, match="contradictory|canonical"):
        _canonicalize_window_rows(
            ((115, _decision()), (116, _decision(mint="other")))
        )


def test_source_uses_read_only_query_only_sqlite_contract() -> None:
    source_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "shreks_brain"
        / "fl9_v2_cohort_acceptance"
        / "source.py"
    )
    text = source_path.read_text(encoding="utf-8")
    assert "?mode=ro" in text
    assert "PRAGMA query_only = ON" in text
    assert "INSERT " not in text
    assert "UPDATE " not in text
    assert "DELETE " not in text
