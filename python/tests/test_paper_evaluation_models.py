from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.paper_evaluation.models import (
    PAPER_EVALUATION_SCHEMA_VERSION,
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationCapture,
    PaperEvaluationLedger,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _entry(**overrides: object) -> PaperEntryProvenance:
    values: dict[str, object] = {
        "paper_run_id": "run-1",
        "candidate_version": "candidate-v1",
        "candidate_fingerprint_sha256": _SHA_A,
        "strategy_version": "strategy-v1",
        "intent_idempotency_key": "entry-1",
        "mint": "mint-a",
        "decision_as_of_unix_ms": 1_000,
        "setup_name": "fresh_launch",
        "market_regime": MarketRegime.HOT,
        "score_policy_version": "score-v1",
        "decision_policy_version": "decision-v1",
        "paper_execution_policy_version": "paper-v1",
    }
    values.update(overrides)
    return PaperEntryProvenance(**values)  # type: ignore[arg-type]


def _execution(**overrides: object) -> PaperPositionExecutionEvidence:
    values: dict[str, object] = {
        "paper_run_id": "run-1",
        "candidate_version": "candidate-v1",
        "candidate_fingerprint_sha256": _SHA_A,
        "strategy_version": "strategy-v1",
        "position_id": "position-1",
        "ledger_sequence": 1,
        "intent_idempotency_key": "entry-1",
        "mint": "mint-a",
        "side": TradeSide.BUY,
        "execution_state": PaperExecutionState.FILLED,
        "ledger_reason_code": PaperLedgerReasonCode.POSITION_OPENED,
        "booked_at_unix_ms": 1_100,
        "evaluated_at_unix_ms": 1_100,
        "requested_notional_usd": 100.0,
        "explicit_cost_usd": 1.0,
        "filled_notional_usd": 100.0,
        "filled_quantity": 10.0,
        "reference_price_usd": 9.9,
        "execution_price_usd": 10.0,
        "signed_slippage_usd": 1.0,
        "quote_provider": "fixture",
        "executed_at_unix_ms": 1_100,
    }
    values.update(overrides)
    return PaperPositionExecutionEvidence(**values)  # type: ignore[arg-type]


def _closure(**overrides: object) -> PaperClosedPositionEvidence:
    values: dict[str, object] = {
        "paper_run_id": "run-1",
        "candidate_version": "candidate-v1",
        "candidate_fingerprint_sha256": _SHA_A,
        "strategy_version": "strategy-v1",
        "position_id": "position-1",
        "mint": "mint-a",
        "opened_at_unix_ms": 1_100,
        "closed_at_unix_ms": 2_000,
        "realized_pnl_usd": 20.0,
        "accumulated_costs_usd": 2.0,
        "buy_fill_count": 1,
        "sell_fill_count": 1,
        "closing_ledger_sequence": 2,
    }
    values.update(overrides)
    return PaperClosedPositionEvidence(**values)  # type: ignore[arg-type]


def _orphan(**overrides: object) -> PaperOrphanCostEvidence:
    values: dict[str, object] = {
        "paper_run_id": "run-1",
        "candidate_version": "candidate-v1",
        "candidate_fingerprint_sha256": _SHA_A,
        "strategy_version": "strategy-v1",
        "intent_idempotency_key": "failed-entry-1",
        "mint": "mint-b",
        "explicit_cost_usd": 0.25,
        "evaluated_at_unix_ms": 1_500,
    }
    values.update(overrides)
    return PaperOrphanCostEvidence(**values)  # type: ignore[arg-type]


def test_schema_and_valid_contracts_are_immutable() -> None:
    assert PAPER_EVALUATION_SCHEMA_VERSION == "e11-paper-evaluation-v1"
    entry = _entry()
    execution = _execution()
    closure = _closure()
    orphan = _orphan()

    assert entry.market_regime is MarketRegime.HOT
    assert execution.side is TradeSide.BUY
    assert closure.closing_ledger_sequence == 2
    assert orphan.explicit_cost_usd == pytest.approx(0.25)

    with pytest.raises(AttributeError):
        entry.setup_name = "changed"  # type: ignore[misc]


def test_entry_provenance_rejects_invalid_identity_and_enum_values() -> None:
    for field, value in (
        ("paper_run_id", ""),
        ("candidate_version", " "),
        ("strategy_version", ""),
        ("intent_idempotency_key", ""),
        ("mint", ""),
        ("setup_name", ""),
        ("score_policy_version", ""),
        ("decision_policy_version", ""),
        ("paper_execution_policy_version", ""),
        ("candidate_fingerprint_sha256", "x" * 64),
        ("decision_as_of_unix_ms", -1),
        ("market_regime", "HOT"),
    ):
        with pytest.raises(ValueError):
            _entry(**{field: value})


def test_execution_fill_fields_are_all_or_none() -> None:
    with pytest.raises(ValueError):
        _execution(reference_price_usd=None)

    failed = _execution(
        execution_state=PaperExecutionState.FAILED,
        ledger_reason_code=PaperLedgerReasonCode.FAILED_EXECUTION_BOOKED,
        explicit_cost_usd=0.25,
        filled_notional_usd=None,
        filled_quantity=None,
        reference_price_usd=None,
        execution_price_usd=None,
        signed_slippage_usd=None,
        quote_provider=None,
        executed_at_unix_ms=None,
    )
    assert failed.execution_state is PaperExecutionState.FAILED

    with pytest.raises(ValueError):
        replace(failed, filled_notional_usd=1.0)


def test_execution_rejects_invalid_numbers_enums_and_success_without_fill() -> None:
    for field, value in (
        ("ledger_sequence", 0),
        ("requested_notional_usd", 0.0),
        ("explicit_cost_usd", -0.1),
        ("filled_notional_usd", 0.0),
        ("filled_quantity", 0.0),
        ("reference_price_usd", 0.0),
        ("execution_price_usd", float("nan")),
        ("signed_slippage_usd", float("inf")),
        ("side", "BUY"),
        ("execution_state", "FILLED"),
        ("ledger_reason_code", "POSITION_OPENED"),
    ):
        with pytest.raises(ValueError):
            _execution(**{field: value})


def test_closure_requires_consistent_terminal_accounting_shape() -> None:
    for field, value in (
        ("opened_at_unix_ms", -1),
        ("closed_at_unix_ms", 1_000),
        ("realized_pnl_usd", float("nan")),
        ("accumulated_costs_usd", -1.0),
        ("buy_fill_count", 0),
        ("sell_fill_count", 0),
        ("closing_ledger_sequence", 0),
    ):
        with pytest.raises(ValueError):
            _closure(**{field: value})


def test_orphan_cost_requires_strictly_positive_cost() -> None:
    for value in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            _orphan(explicit_cost_usd=value)


def test_capture_requires_one_attribution_and_unique_identities() -> None:
    capture = PaperEvaluationCapture(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=_SHA_A,
        strategy_version="strategy-v1",
        entry_provenance=(_entry(),),
        executions=(_execution(),),
        closures=(_closure(),),
        orphan_costs=(),
    )
    assert capture.executions[0].ledger_sequence == 1

    with pytest.raises(ValueError):
        replace(capture, entry_provenance=(_entry(), _entry()))
    with pytest.raises(ValueError):
        replace(capture, executions=(_execution(), _execution()))
    with pytest.raises(ValueError):
        replace(capture, closures=(_closure(), _closure()))
    with pytest.raises(ValueError):
        replace(capture, entry_provenance=(_entry(candidate_fingerprint_sha256=_SHA_B),))


def test_capture_allows_empty_cycle_but_keeps_candidate_attribution() -> None:
    capture = PaperEvaluationCapture(
        paper_run_id="run-1",
        candidate_version="candidate-v1",
        candidate_fingerprint_sha256=_SHA_A,
        strategy_version="strategy-v1",
        entry_provenance=(),
        executions=(),
        closures=(),
        orphan_costs=(),
    )
    assert capture.paper_run_id == "run-1"


def test_ledger_requires_canonical_order_unique_identities_and_valid_digest() -> None:
    entry_1 = _entry(intent_idempotency_key="entry-1", decision_as_of_unix_ms=1_000)
    entry_2 = _entry(intent_idempotency_key="entry-2", decision_as_of_unix_ms=1_001)
    execution_1 = _execution(ledger_sequence=1, intent_idempotency_key="entry-1")
    execution_2 = _execution(
        position_id="position-2",
        ledger_sequence=2,
        intent_idempotency_key="entry-2",
        mint="mint-b",
    )
    ledger = PaperEvaluationLedger(
        schema_version=PAPER_EVALUATION_SCHEMA_VERSION,
        entry_provenance=(entry_1, entry_2),
        executions=(execution_1, execution_2),
        closures=(),
        orphan_costs=(),
        document_fingerprint_sha256=_SHA_C,
    )
    assert ledger.document_fingerprint_sha256 == _SHA_C

    with pytest.raises(ValueError):
        replace(ledger, entry_provenance=(entry_2, entry_1))
    with pytest.raises(ValueError):
        replace(ledger, executions=(execution_2, execution_1))
    with pytest.raises(ValueError):
        replace(ledger, document_fingerprint_sha256="not-a-sha")


def test_ledger_rejects_duplicate_run_sequence_even_across_positions() -> None:
    first = _execution(position_id="position-1", ledger_sequence=1)
    second = _execution(
        position_id="position-2",
        ledger_sequence=1,
        intent_idempotency_key="entry-2",
        mint="mint-b",
    )
    with pytest.raises(ValueError):
        PaperEvaluationLedger(
            schema_version=PAPER_EVALUATION_SCHEMA_VERSION,
            entry_provenance=(),
            executions=(first, second),
            closures=(),
            orphan_costs=(),
            document_fingerprint_sha256=_SHA_C,
        )
