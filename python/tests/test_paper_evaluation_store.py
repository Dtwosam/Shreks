from __future__ import annotations

from dataclasses import replace
import json

import pytest

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.paper_evaluation.models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationCapture,
    PaperPositionExecutionEvidence,
)
from shreks_brain.paper_evaluation.store import PaperEvaluationEvidenceStore
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide


RUN = "run-1"
CANDIDATE = "candidate-v1"
SHA = "a" * 64
STRATEGY = "fresh-v1"


def _entry(**overrides: object) -> PaperEntryProvenance:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        intent_idempotency_key="buy-1",
        mint="MintA",
        decision_as_of_unix_ms=1_000,
        setup_name="fresh_launch_continuation",
        market_regime=MarketRegime.NORMAL,
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        paper_execution_policy_version="paper-v1",
    )
    values.update(overrides)
    return PaperEntryProvenance(**values)  # type: ignore[arg-type]


def _execution(*, sequence: int, side: TradeSide, **overrides: object) -> PaperPositionExecutionEvidence:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        position_id="position-a",
        ledger_sequence=sequence,
        intent_idempotency_key="buy-1" if side is TradeSide.BUY else "sell-1",
        mint="MintA",
        side=side,
        execution_state=PaperExecutionState.FILLED,
        ledger_reason_code=(
            PaperLedgerReasonCode.POSITION_OPENED
            if side is TradeSide.BUY
            else PaperLedgerReasonCode.POSITION_CLOSED
        ),
        booked_at_unix_ms=1_000 + sequence,
        evaluated_at_unix_ms=1_000 + sequence,
        requested_notional_usd=100.0 if side is TradeSide.BUY else 110.0,
        explicit_cost_usd=1.0,
        filled_notional_usd=100.0 if side is TradeSide.BUY else 110.0,
        filled_quantity=100.0,
        reference_price_usd=1.0 if side is TradeSide.BUY else 1.1,
        execution_price_usd=1.0 if side is TradeSide.BUY else 1.1,
        signed_slippage_usd=0.0,
        quote_provider="paper-test",
        executed_at_unix_ms=1_000 + sequence,
    )
    values.update(overrides)
    return PaperPositionExecutionEvidence(**values)  # type: ignore[arg-type]


def _closure(**overrides: object) -> PaperClosedPositionEvidence:
    values: dict[str, object] = dict(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        position_id="position-a",
        mint="MintA",
        opened_at_unix_ms=1_001,
        closed_at_unix_ms=2_000,
        realized_pnl_usd=8.0,
        accumulated_costs_usd=2.0,
        buy_fill_count=1,
        sell_fill_count=1,
        closing_ledger_sequence=2,
    )
    values.update(overrides)
    return PaperClosedPositionEvidence(**values)  # type: ignore[arg-type]


def _capture(*, complete: bool = True) -> PaperEvaluationCapture:
    executions = (_execution(sequence=1, side=TradeSide.BUY),)
    closures = ()
    if complete:
        executions += (_execution(sequence=2, side=TradeSide.SELL),)
        closures = (_closure(),)
    return PaperEvaluationCapture(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        entry_provenance=(_entry(),),
        executions=executions,
        closures=closures,
        orphan_costs=(),
    )


def test_missing_store_loads_empty_sealed_ledger_without_creating_file(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    ledger = store.load()
    assert ledger.entry_provenance == ()
    assert ledger.executions == ()
    assert ledger.closures == ()
    assert ledger.orphan_costs == ()
    assert ledger.document_fingerprint_sha256 != "0" * 64
    assert not path.exists()


def test_record_capture_round_trips_and_uses_atomic_canonical_file(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    written = store.record_capture(_capture())
    assert store.load() == written
    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")
    assert json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False) == raw[:-1]
    assert not path.with_name(path.name + ".tmp").exists()


def test_identical_capture_is_byte_for_byte_idempotent(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    first = store.record_capture(_capture())
    before = path.read_bytes()
    second = store.record_capture(_capture())
    after = path.read_bytes()
    assert second == first
    assert after == before


def test_later_capture_unions_new_evidence_without_rewriting_identity(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    first = _capture(complete=False)
    store.record_capture(first)
    second = PaperEvaluationCapture(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        entry_provenance=(),
        executions=(_execution(sequence=2, side=TradeSide.SELL),),
        closures=(_closure(),),
        orphan_costs=(),
    )
    ledger = store.record_capture(second)
    assert len(ledger.entry_provenance) == 1
    assert tuple(value.ledger_sequence for value in ledger.executions) == (1, 2)
    assert len(ledger.closures) == 1


def test_same_identity_with_different_content_fails_closed(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    store.record_capture(_capture(complete=False))
    conflict = PaperEvaluationCapture(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA,
        strategy_version=STRATEGY,
        entry_provenance=(),
        executions=(
            replace(
                _execution(sequence=1, side=TradeSide.BUY),
                explicit_cost_usd=1.5,
            ),
        ),
        closures=(),
        orphan_costs=(),
    )
    with pytest.raises(ValueError, match="different content"):
        store.record_capture(conflict)


def test_evaluated_trades_reconstruct_after_restart(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    PaperEvaluationEvidenceStore(path).record_capture(_capture())
    trades = PaperEvaluationEvidenceStore(path).evaluated_trades(RUN, CANDIDATE)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.position_id == "position-a"
    assert trade.net_pnl_usd == pytest.approx(8.0)
    assert trade.explicit_cost_usd == pytest.approx(2.0)
    assert trade.gross_pnl_usd == pytest.approx(10.0)


def test_record_cycle_calls_extractor_then_persists(monkeypatch, tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    capture = _capture(complete=False)
    observed = {}

    def fake_extract(paper_run_id, candidate, cycle):
        observed["args"] = (paper_run_id, candidate, cycle)
        return capture

    monkeypatch.setattr(
        "shreks_brain.paper_evaluation.store.extract_paper_evaluation_evidence",
        fake_extract,
    )
    candidate = object()
    cycle = object()
    ledger = store.record_cycle(RUN, candidate, cycle)
    assert observed["args"] == (RUN, candidate, cycle)
    assert ledger == store.load()
    assert ledger.entry_provenance == capture.entry_provenance


def test_load_rejects_malformed_json_unknown_fields_and_tampering(tmp_path) -> None:
    path = tmp_path / "paper-evidence.json"
    store = PaperEvaluationEvidenceStore(path)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        store.load()

    store.record_capture(_capture()) if not path.exists() else None
    path.unlink(missing_ok=True)
    store.record_capture(_capture())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["unknown"] = 1
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        store.load()

    path.unlink(missing_ok=True)
    store.record_capture(_capture())
    document = json.loads(path.read_text(encoding="utf-8"))
    document["entry_provenance"][0]["setup_name"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        store.load()


def test_store_exposes_only_append_only_evidence_operations() -> None:
    public = {
        name
        for name in dir(PaperEvaluationEvidenceStore)
        if not name.startswith("_")
    }
    assert public == {"load", "record_capture", "record_cycle", "evaluated_trades"}
