from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from shreks_brain.evaluation.codec import build_evidence
from shreks_brain.evaluation.models import TradingEvaluationPolicy
from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.paper_evaluation.codec import build_paper_evaluation_ledger
from shreks_brain.paper_evaluation.engine import build_evaluated_trades
from shreks_brain.paper_evaluation.models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)
from shreks_brain.proof.engine import evaluate_candidate_proof
from shreks_brain.proof.models import (
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateStatus,
    PaperProofPolicy,
)
from shreks_brain.promotion.models import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionDecision,
    PromotionGateCode,
    PromotionGateResult,
    PromotionGateStatus,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.registry import RegistryStatus, build_registry_candidate
from shreks_brain.registry.codec import (
    build_registry,
    compute_event_fingerprint,
)
from shreks_brain.registry.models import RegistryStatusEvent
from shreks_brain.risk import TradeSide


RUN = "paper-run-1"
CANDIDATE = "candidate-v1"
STRATEGY = "strategy-v1"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _paper_policy() -> TradingEvaluationPolicy:
    return TradingEvaluationPolicy(
        version="paper-eval-v1",
        starting_equity_usd=1_000.0,
        calibration_bucket_count=2,
    )


def _proof_policy(**overrides: object) -> PaperProofPolicy:
    values: dict[str, object] = dict(
        version="proof-v1",
        min_trade_count=3,
        min_distinct_mint_count=3,
        min_evaluation_span_ms=5_000,
        min_net_expectancy_pct=0.0,
        min_profit_factor=1.0,
        max_drawdown_pct=100.0,
        max_cost_burden_pct=100.0,
        max_single_winner_share_of_positive_pnl=0.7,
    )
    values.update(overrides)
    return PaperProofPolicy(**values)  # type: ignore[arg-type]


def _entry(index: int, *, mint: str) -> PaperEntryProvenance:
    return PaperEntryProvenance(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA_A,
        strategy_version=STRATEGY,
        intent_idempotency_key=f"buy-{index}",
        mint=mint,
        decision_as_of_unix_ms=900 + index * 2_000,
        setup_name="fresh_launch_continuation",
        market_regime=MarketRegime.NORMAL,
        score_policy_version="score-v1",
        decision_policy_version="decision-v1",
        paper_execution_policy_version="paper-v1",
    )


def _execution(
    index: int,
    *,
    sequence: int,
    side: TradeSide,
    mint: str,
    position_id: str,
    notional: float,
    timestamp: int,
) -> PaperPositionExecutionEvidence:
    return PaperPositionExecutionEvidence(
        paper_run_id=RUN,
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=SHA_A,
        strategy_version=STRATEGY,
        position_id=position_id,
        ledger_sequence=sequence,
        intent_idempotency_key=(f"buy-{index}" if side is TradeSide.BUY else f"sell-{index}"),
        mint=mint,
        side=side,
        execution_state=PaperExecutionState.FILLED,
        ledger_reason_code=(
            PaperLedgerReasonCode.POSITION_OPENED
            if side is TradeSide.BUY
            else PaperLedgerReasonCode.POSITION_CLOSED
        ),
        booked_at_unix_ms=timestamp,
        evaluated_at_unix_ms=timestamp,
        requested_notional_usd=notional,
        explicit_cost_usd=1.0,
        filled_notional_usd=notional,
        filled_quantity=notional,
        reference_price_usd=1.0,
        execution_price_usd=1.0,
        signed_slippage_usd=1.0 if side is TradeSide.BUY else 0.0,
        quote_provider="paper-test",
        executed_at_unix_ms=timestamp,
    )


def _ledger(
    nets: tuple[float, ...] = (10.0, 5.0, -4.0),
    *,
    same_mint: bool = False,
    orphan_cost: bool = False,
):
    entries = []
    executions = []
    closures = []
    for index, net in enumerate(nets):
        mint = "MintA" if same_mint else f"Mint{index}"
        position_id = f"position-{index}"
        opened = 1_000 + index * 2_000
        closed = 2_000 + index * 2_000
        buy_sequence = index * 2 + 1
        sell_sequence = buy_sequence + 1
        entries.append(_entry(index, mint=mint))
        executions.extend(
            (
                _execution(
                    index,
                    sequence=buy_sequence,
                    side=TradeSide.BUY,
                    mint=mint,
                    position_id=position_id,
                    notional=100.0,
                    timestamp=opened,
                ),
                _execution(
                    index,
                    sequence=sell_sequence,
                    side=TradeSide.SELL,
                    mint=mint,
                    position_id=position_id,
                    notional=100.0 + net + 2.0,
                    timestamp=closed,
                ),
            )
        )
        closures.append(
            PaperClosedPositionEvidence(
                paper_run_id=RUN,
                candidate_version=CANDIDATE,
                candidate_fingerprint_sha256=SHA_A,
                strategy_version=STRATEGY,
                position_id=position_id,
                mint=mint,
                opened_at_unix_ms=opened,
                closed_at_unix_ms=closed,
                realized_pnl_usd=net,
                accumulated_costs_usd=2.0,
                buy_fill_count=1,
                sell_fill_count=1,
                closing_ledger_sequence=sell_sequence,
            )
        )
    orphans = ()
    if orphan_cost:
        orphans = (
            PaperOrphanCostEvidence(
                paper_run_id=RUN,
                candidate_version=CANDIDATE,
                candidate_fingerprint_sha256=SHA_A,
                strategy_version=STRATEGY,
                intent_idempotency_key="failed-entry",
                mint="MintFailed",
                explicit_cost_usd=0.01,
                evaluated_at_unix_ms=500,
            ),
        )
    return build_paper_evaluation_ledger(
        tuple(entries), tuple(executions), tuple(closures), orphans
    )


def _paper_evaluation(ledger):
    trades = build_evaluated_trades(
        RUN,
        CANDIDATE,
        ledger.entry_provenance,
        ledger.executions,
        ledger.closures,
        ledger.orphan_costs,
    )
    return build_evidence(CANDIDATE, trades, (), _paper_policy())


def _registry(paper_evaluation):
    candidate = build_registry_candidate(
        candidate_version=CANDIDATE,
        strategy_version=STRATEGY,
        feature_schema_version="d6-research-v1",
        feature_columns=("market_liquidity_usd",),
        evaluation_report=paper_evaluation.report,
        registered_at_unix_ms=100,
        trained_model=None,
        validation_run=None,
    )
    return candidate, build_registry((candidate,), ())


def _e8_assessment(
    candidate,
    registry,
    *,
    decision: PromotionDecision = PromotionDecision.ELIGIBLE,
    evaluated_at_unix_ms: int = 500,
    candidate_fingerprint: str | None = None,
    registry_fingerprint: str | None = None,
) -> PromotionAssessment:
    statuses = {code: PromotionGateStatus.PASS for code in PromotionGateCode}
    if decision is PromotionDecision.INSUFFICIENT_EVIDENCE:
        statuses[PromotionGateCode.MIN_TRADE_COUNT] = PromotionGateStatus.INSUFFICIENT
    elif decision is PromotionDecision.INELIGIBLE:
        statuses[PromotionGateCode.MIN_NET_EXPECTANCY_PCT] = PromotionGateStatus.FAIL
    gates = tuple(
        PromotionGateResult(
            code=code,
            status=statuses[code],
            observed_value=1,
            threshold_value=1,
            message=f"{code.value} checked",
        )
        for code in sorted(PromotionGateCode, key=lambda value: value.value)
    )
    return PromotionAssessment(
        schema_version=PROMOTION_SCHEMA_VERSION,
        policy_version="promotion-v1",
        candidate_version=CANDIDATE,
        candidate_fingerprint_sha256=(
            candidate.candidate_fingerprint_sha256
            if candidate_fingerprint is None
            else candidate_fingerprint
        ),
        registry_fingerprint_sha256=(
            registry.registry_fingerprint_sha256
            if registry_fingerprint is None
            else registry_fingerprint
        ),
        evaluation_fingerprint_sha256=paper_evaluation_placeholder(candidate),
        trade_evidence_fingerprint_sha256=SHA_B,
        shadow_ledger_fingerprint_sha256=SHA_C,
        baseline_evaluation_identities=(),
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        gates=gates,
        decision=decision,
        assessment_fingerprint_sha256=SHA_B,
    )


def paper_evaluation_placeholder(candidate) -> str:
    return candidate.evaluation.evaluation_fingerprint_sha256


def _fixture(
    nets: tuple[float, ...] = (10.0, 5.0, -4.0),
    *,
    same_mint: bool = False,
):
    ledger = _ledger(nets, same_mint=same_mint)
    paper_evaluation = _paper_evaluation(ledger)
    candidate, registry = _registry(paper_evaluation)
    e8 = _e8_assessment(candidate, registry)
    return ledger, paper_evaluation, candidate, registry, e8


def _gate(result, code: PaperProofGateCode):
    return next(value for value in result.gates if value.code is code)


def _evaluate(
    ledger,
    paper_evaluation,
    registry,
    e8,
    *,
    policy: PaperProofPolicy | None = None,
    evaluated_at_unix_ms: int = 10_000,
):
    return evaluate_candidate_proof(
        registry,
        CANDIDATE,
        e8,
        RUN,
        ledger,
        paper_evaluation,
        _proof_policy() if policy is None else policy,
        evaluated_at_unix_ms,
    )


def test_complete_paper_proof_is_sufficient_and_deterministic() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    first = _evaluate(ledger, evidence, registry, e8)
    second = _evaluate(ledger, evidence, registry, e8)
    assert first == second
    assert first.decision is PaperProofDecision.SUFFICIENT
    assert all(gate.status is PaperProofGateStatus.PASS for gate in first.gates)
    assert len(first.assessment_fingerprint_sha256) == 64
    assert len(first.paper_trade_evidence_fingerprint_sha256) == 64


@pytest.mark.parametrize(
    ("e8_decision", "expected_status", "expected_decision"),
    (
        (
            PromotionDecision.INSUFFICIENT_EVIDENCE,
            PaperProofGateStatus.INSUFFICIENT,
            PaperProofDecision.INSUFFICIENT_EVIDENCE,
        ),
        (
            PromotionDecision.INELIGIBLE,
            PaperProofGateStatus.FAIL,
            PaperProofDecision.FAILED,
        ),
    ),
)
def test_e8_decision_maps_to_proof_gate(
    e8_decision: PromotionDecision,
    expected_status: PaperProofGateStatus,
    expected_decision: PaperProofDecision,
) -> None:
    ledger, evidence, candidate, registry, _e8 = _fixture()
    e8 = _e8_assessment(candidate, registry, decision=e8_decision)
    result = _evaluate(ledger, evidence, registry, e8)
    assert _gate(result, PaperProofGateCode.E8_ASSESSMENT_ELIGIBLE).status is expected_status
    assert result.decision is expected_decision


def test_missing_candidate_raises() -> None:
    ledger, evidence, _candidate, _registry, e8 = _fixture()
    with pytest.raises(ValueError, match="not registered"):
        _evaluate(ledger, evidence, build_registry((), ()), e8)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("candidate_fingerprint", SHA_C),
        ("registry_fingerprint", SHA_C),
    ),
)
def test_e8_registry_provenance_mismatch_is_failed(field: str, value: str) -> None:
    ledger, evidence, candidate, registry, _e8 = _fixture()
    kwargs = {field: value}
    e8 = _e8_assessment(candidate, registry, **kwargs)
    result = _evaluate(ledger, evidence, registry, e8)
    assert _gate(result, PaperProofGateCode.E8_REGISTRY_PROVENANCE).status is PaperProofGateStatus.FAIL
    assert result.decision is PaperProofDecision.FAILED


def test_candidate_must_still_be_current_challenger() -> None:
    ledger, evidence, candidate, registry, _e8 = _fixture()
    draft = RegistryStatusEvent(
        candidate_version=CANDIDATE,
        from_status=RegistryStatus.CHALLENGER,
        to_status=RegistryStatus.RETIRED,
        decision_reference="retire-for-test",
        decided_at_unix_ms=700,
        reason="retired",
        event_fingerprint_sha256="0" * 64,
    )
    event = replace(
        draft,
        event_fingerprint_sha256=compute_event_fingerprint(draft),
    )
    retired = build_registry((candidate,), (event,))
    e8 = _e8_assessment(candidate, retired)
    result = _evaluate(ledger, evidence, retired, e8)
    assert _gate(result, PaperProofGateCode.E8_REGISTRY_PROVENANCE).status is PaperProofGateStatus.FAIL


def test_e10_trade_mismatch_fails_paper_provenance_and_metric_gates() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    changed = tuple(
        replace(
            trade,
            gross_pnl_usd=trade.gross_pnl_usd + (1.0 if index == 0 else 0.0),
            net_pnl_usd=trade.net_pnl_usd + (1.0 if index == 0 else 0.0),
        )
        for index, trade in enumerate(evidence.trades)
    )
    mismatched = build_evidence(CANDIDATE, changed, (), _paper_policy())
    result = _evaluate(ledger, mismatched, registry, e8)
    assert _gate(result, PaperProofGateCode.PAPER_EVIDENCE_PROVENANCE).status is PaperProofGateStatus.FAIL
    assert _gate(result, PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT).status is PaperProofGateStatus.FAIL
    assert result.decision is PaperProofDecision.FAILED


def test_e10_candidate_mismatch_fails_paper_provenance() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    other_trades = tuple(replace(trade, candidate_version="other-v1") for trade in evidence.trades)
    other = build_evidence("other-v1", other_trades, (), _paper_policy())
    result = _evaluate(ledger, other, registry, e8)
    assert _gate(result, PaperProofGateCode.PAPER_EVIDENCE_PROVENANCE).status is PaperProofGateStatus.FAIL


def test_e11_orphan_cost_reconciliation_error_propagates() -> None:
    clean_ledger, evidence, _candidate, registry, e8 = _fixture()
    bad_ledger = _ledger(orphan_cost=True)
    assert clean_ledger != bad_ledger
    with pytest.raises(ValueError, match="orphan"):
        _evaluate(bad_ledger, evidence, registry, e8)


@pytest.mark.parametrize(
    ("policy", "code"),
    (
        (_proof_policy(min_trade_count=4), PaperProofGateCode.MIN_PAPER_TRADE_COUNT),
        (
            _proof_policy(min_distinct_mint_count=4),
            PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT,
        ),
        (
            _proof_policy(min_evaluation_span_ms=5_001),
            PaperProofGateCode.MIN_PAPER_EVALUATION_SPAN,
        ),
    ),
)
def test_small_paper_sample_is_insufficient(
    policy: PaperProofPolicy, code: PaperProofGateCode
) -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    result = _evaluate(ledger, evidence, registry, e8, policy=policy)
    assert _gate(result, code).status is PaperProofGateStatus.INSUFFICIENT
    assert result.decision is PaperProofDecision.INSUFFICIENT_EVIDENCE


def test_distinct_mint_gate_uses_actual_paper_mints() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture(same_mint=True)
    result = _evaluate(ledger, evidence, registry, e8)
    gate = _gate(result, PaperProofGateCode.MIN_PAPER_DISTINCT_MINT_COUNT)
    assert gate.observed_value == 1
    assert gate.status is PaperProofGateStatus.INSUFFICIENT


@pytest.mark.parametrize(
    ("policy", "code"),
    (
        (
            _proof_policy(min_net_expectancy_pct=10.0),
            PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT,
        ),
        (
            _proof_policy(min_profit_factor=10.0),
            PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR,
        ),
        (
            _proof_policy(max_drawdown_pct=0.1),
            PaperProofGateCode.MAX_PAPER_DRAWDOWN_PCT,
        ),
        (
            _proof_policy(max_cost_burden_pct=0.1),
            PaperProofGateCode.MAX_PAPER_COST_BURDEN_PCT,
        ),
        (
            _proof_policy(max_single_winner_share_of_positive_pnl=0.6),
            PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE,
        ),
    ),
)
def test_existing_paper_metric_outside_threshold_is_failure(
    policy: PaperProofPolicy, code: PaperProofGateCode
) -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    result = _evaluate(ledger, evidence, registry, e8, policy=policy)
    assert _gate(result, code).status is PaperProofGateStatus.FAIL
    assert result.decision is PaperProofDecision.FAILED


def test_empty_paper_run_has_insufficient_expectancy_profit_factor_and_winner_share() -> None:
    ledger = _ledger(())
    evidence = _paper_evaluation(ledger)
    candidate, registry = _registry(evidence)
    e8 = _e8_assessment(candidate, registry)
    result = _evaluate(ledger, evidence, registry, e8)
    for code in (
        PaperProofGateCode.MIN_PAPER_NET_EXPECTANCY_PCT,
        PaperProofGateCode.MIN_PAPER_PROFIT_FACTOR,
        PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE,
    ):
        assert _gate(result, code).status is PaperProofGateStatus.INSUFFICIENT
    assert result.decision is PaperProofDecision.INSUFFICIENT_EVIDENCE


def test_all_losing_run_has_insufficient_winner_concentration() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture((-5.0, -4.0, -3.0))
    result = _evaluate(
        ledger,
        evidence,
        registry,
        e8,
        policy=_proof_policy(min_net_expectancy_pct=-100.0, min_profit_factor=0.0),
    )
    assert _gate(result, PaperProofGateCode.MAX_PAPER_SINGLE_WINNER_SHARE).status is PaperProofGateStatus.INSUFFICIENT


def test_evaluation_timestamp_cannot_precede_referenced_evidence() -> None:
    ledger, evidence, candidate, registry, _e8 = _fixture()
    e8 = _e8_assessment(candidate, registry, evaluated_at_unix_ms=7_000)
    with pytest.raises(ValueError, match="cannot precede"):
        _evaluate(ledger, evidence, registry, e8, evaluated_at_unix_ms=6_999)


def test_gate_order_is_lexical_and_trade_fingerprint_is_source_sensitive() -> None:
    ledger, evidence, _candidate, registry, e8 = _fixture()
    result = _evaluate(ledger, evidence, registry, e8)
    assert tuple(gate.code.value for gate in result.gates) == tuple(
        sorted(code.value for code in PaperProofGateCode)
    )

    changed_ledger = _ledger((11.0, 5.0, -4.0))
    changed_evidence = _paper_evaluation(changed_ledger)
    changed_candidate, changed_registry = _registry(changed_evidence)
    changed_e8 = _e8_assessment(changed_candidate, changed_registry)
    changed = _evaluate(
        changed_ledger, changed_evidence, changed_registry, changed_e8
    )
    assert result.paper_trade_evidence_fingerprint_sha256 != changed.paper_trade_evidence_fingerprint_sha256
    assert result.assessment_fingerprint_sha256 != changed.assessment_fingerprint_sha256
