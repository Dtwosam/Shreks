from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.evaluation import (
    TradingEvaluationEvidence,
    TradingEvaluationPolicy,
    evaluate_trading_performance,
)
from shreks_brain.fast_campaign import (
    FastCampaignDecisionResults,
    fast_campaign_result_to_paper_assessment,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
    FastDeterministicLifecycleResults,
    fast_deterministic_lifecycle_to_paper_assessment,
)
from shreks_brain.fast_paper import (
    FAST_PAPER_BUY_VERSION,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperBuyApproval,
    FastPaperBuyOutcome,
    FastPaperBuyQuote,
    FastPaperMaterialUpdate,
    FastPaperPositionActionApproval,
    FastPaperPositionActionPolicy,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_loop_state,
    create_fast_paper_position_action_state,
    execute_fast_paper_buy,
    run_fast_paper_event,
)
from shreks_brain.fast_policy_proof import build_fast_policy_run_evidence
from shreks_brain.paper import (
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionState,
)
from shreks_brain.paper_evaluation import build_evaluated_trades
from shreks_brain.paper_evaluation.fast import (
    FAST_PAPER_EVALUATION_ADAPTER_VERSION,
    FastPaperEntryEvaluationContext,
    FastPaperEvaluationIdentity,
    FastPaperExecutionEvidenceInput,
    extract_fast_paper_evaluation_evidence,
)
from shreks_brain.risk import RiskPolicy

from .models import (
    FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
    FastCampaignPaperCandidateIdentity,
    FastCampaignPaperDecisionEvidence,
    FastCampaignPaperQuoteEvidence,
    FastCampaignPaperRunResult,
)


_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class _FastCampaignPaperDecision:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    action: str
    current_exposure_fraction: float
    target_exposure_fraction: float
    assessment: FastPaperActionAssessment


def run_fast_campaign_paper_candidate(
    *,
    identity: FastCampaignPaperCandidateIdentity,
    decisions: FastCampaignDecisionResults,
    evidence: tuple[FastCampaignPaperDecisionEvidence, ...],
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastCampaignPaperRunResult:
    if type(identity) is not FastCampaignPaperCandidateIdentity:
        raise ValueError(
            "identity must be exact FastCampaignPaperCandidateIdentity"
        )
    if type(decisions) is not FastCampaignDecisionResults:
        raise ValueError("decisions must be exact FastCampaignDecisionResults")

    common_decisions = tuple(
        _FastCampaignPaperDecision(
            source_event_id=decision.source_event_id,
            market_key=decision.market_key,
            source_sequence=decision.source_sequence,
            as_of_unix_ms=decision.as_of_unix_ms,
            action=decision.action,
            current_exposure_fraction=decision.current_exposure_fraction,
            target_exposure_fraction=decision.target_exposure_fraction,
            assessment=fast_campaign_result_to_paper_assessment(
                decision,
                assessment_version=identity.assessment_version,
                strategy_family=identity.strategy_family,
                strategy_version=identity.strategy_version,
            ),
        )
        for decision in decisions.decisions
    )
    return _run_fast_campaign_paper_decision_sequence(
        identity=identity,
        decisions=common_decisions,
        evidence=evidence,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
    )


def run_fast_deterministic_lifecycle_paper_candidate(
    *,
    manifest: FastDeterministicCandidateManifest,
    paper_run_id: str,
    assessment_version: str,
    decisions: FastDeterministicLifecycleResults,
    evidence: tuple[FastCampaignPaperDecisionEvidence, ...],
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastCampaignPaperRunResult:
    if type(manifest) is not FastDeterministicCandidateManifest:
        raise ValueError(
            "manifest must be exact FastDeterministicCandidateManifest"
        )
    if type(decisions) is not FastDeterministicLifecycleResults:
        raise ValueError(
            "decisions must be exact FastDeterministicLifecycleResults"
        )
    if decisions.policy != manifest.lifecycle_policy:
        raise ValueError(
            "deterministic lifecycle decision policy does not match candidate manifest"
        )

    identity = FastCampaignPaperCandidateIdentity(
        version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
        paper_run_id=paper_run_id,
        candidate_version=manifest.candidate_version,
        candidate_fingerprint_sha256=manifest.candidate_fingerprint_sha256,
        strategy_family=manifest.strategy_family,
        strategy_version=manifest.strategy_version,
        assessment_version=assessment_version,
    )
    common_decisions = tuple(
        _FastCampaignPaperDecision(
            source_event_id=decision.source_event_id,
            market_key=decision.market_key,
            source_sequence=decision.source_sequence,
            as_of_unix_ms=decision.as_of_unix_ms,
            action=decision.action,
            current_exposure_fraction=(
                0.0
                if decision.current_exposure_fraction is None
                else decision.current_exposure_fraction
            ),
            target_exposure_fraction=decision.target_exposure_fraction,
            assessment=fast_deterministic_lifecycle_to_paper_assessment(
                decision,
                assessment_version=identity.assessment_version,
                strategy_family=identity.strategy_family,
                strategy_version=identity.strategy_version,
            ),
        )
        for decision in decisions.decisions
    )
    return _run_fast_campaign_paper_decision_sequence(
        identity=identity,
        decisions=common_decisions,
        evidence=evidence,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
    )


def _run_fast_campaign_paper_decision_sequence(
    *,
    identity: FastCampaignPaperCandidateIdentity,
    decisions: tuple[_FastCampaignPaperDecision, ...],
    evidence: tuple[FastCampaignPaperDecisionEvidence, ...],
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastCampaignPaperRunResult:
    if type(identity) is not FastCampaignPaperCandidateIdentity:
        raise ValueError(
            "identity must be exact FastCampaignPaperCandidateIdentity"
        )
    if not isinstance(decisions, tuple) or not all(
        type(value) is _FastCampaignPaperDecision for value in decisions
    ):
        raise ValueError(
            "decisions must be a tuple of exact shared campaign PAPER decision values"
        )
    if not isinstance(evidence, tuple) or not all(
        type(value) is FastCampaignPaperDecisionEvidence for value in evidence
    ):
        raise ValueError(
            "evidence must be a tuple of exact FastCampaignPaperDecisionEvidence values"
        )
    if type(starting_ledger) is not PaperLedger:
        raise ValueError("starting_ledger must be exact PaperLedger")
    if type(fill_policy) is not PaperFillPolicy:
        raise ValueError("fill_policy must be exact PaperFillPolicy")
    if type(risk_policy) is not RiskPolicy:
        raise ValueError("risk_policy must be exact RiskPolicy")
    if type(position_policy) is not FastPaperPositionActionPolicy:
        raise ValueError(
            "position_policy must be exact FastPaperPositionActionPolicy"
        )
    if type(evaluation_policy) is not TradingEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact TradingEvaluationPolicy"
        )
    if not math.isclose(
        evaluation_policy.starting_equity_usd,
        starting_ledger.starting_cash_usd,
        rel_tol=_REL_TOL,
        abs_tol=_ABS_TOL,
    ):
        raise ValueError(
            "evaluation policy starting equity must equal starting PAPER cash"
        )
    if any(
        position.state is PaperPositionState.OPEN
        for position in starting_ledger.positions
    ):
        raise ValueError(
            "campaign PAPER executor requires a starting ledger with no OPEN positions"
        )
    if len(decisions) != len(evidence):
        raise ValueError(
            "campaign decision results and execution evidence lengths must match"
        )
    if not decisions:
        raise ValueError("campaign decision results cannot be empty")

    _validate_population_alignment(decisions, evidence)

    loop_state = create_fast_paper_loop_state()
    ledger = starting_ledger
    buy_results = []
    position_results = []
    execution_inputs: list[FastPaperExecutionEvidenceInput] = []
    entry_contexts: list[FastPaperEntryEvaluationContext] = []

    market_positions: dict[str, str] = {}
    position_states = {}
    market_exposures: dict[str, float] = {}
    decision_targets = {
        decision.source_event_id: decision.target_exposure_fraction
        for decision in decisions
    }

    for decision, point in zip(decisions, evidence):
        _validate_decision_shape(decision)
        assessment = decision.assessment
        event_result = run_fast_paper_event(
            loop_state,
            FastPaperMaterialUpdate(
                source_event_id=decision.source_event_id,
                market_key=decision.market_key,
                source_sequence=decision.source_sequence,
                as_of_unix_ms=decision.as_of_unix_ms,
                state_version=point.state_version,
                is_material=True,
                material_reason="campaign_decision",
            ),
            lambda _update, assessment=assessment: assessment,
        )
        loop_state = event_result.next_state

        tracked_position_id = market_positions.get(decision.market_key)
        tracked_exposure = market_exposures.get(decision.market_key)
        _validate_posture(
            decision,
            tracked_position_id=tracked_position_id,
            tracked_exposure=tracked_exposure,
        )
        _validate_evidence_for_action(decision, point)

        action = assessment.action
        if action is FastPaperAction.SKIP:
            continue

        if action is FastPaperAction.BUY:
            assert point.entry_authority is not None
            assert point.risk_context is not None
            assert point.quote is not None
            assert point.market_regime is not None
            if point.risk_context.as_of_unix_ms != point.evaluated_at_unix_ms:
                raise ValueError(
                    "BUY risk context timestamp must equal evidence evaluation time"
                )

            authority = point.entry_authority
            buy_result = execute_fast_paper_buy(
                ledger,
                FastPaperBuyApproval(
                    version=FAST_PAPER_BUY_VERSION,
                    assessment=assessment,
                    mint=authority.mint,
                    quote_mint=authority.quote_mint,
                    state_version=point.state_version,
                    intended_base_quantity=authority.intended_base_quantity,
                    decision_executable_entry_price_quote=(
                        authority.decision_executable_entry_price_quote
                    ),
                    maximum_acceptable_entry_price_quote=(
                        authority.maximum_acceptable_entry_price_quote
                    ),
                    expected_entry_variable_cost_bps=(
                        authority.expected_entry_variable_cost_bps
                    ),
                    expected_entry_fixed_cost_quote=(
                        authority.expected_entry_fixed_cost_quote
                    ),
                ),
                point.risk_context,
                risk_policy,
                fill_policy,
                evaluated_at_unix_ms=point.evaluated_at_unix_ms,
                quote=_buy_quote(point.quote),
            )
            buy_results.append(buy_result)
            ledger = buy_result.next_ledger
            _collect_buy_execution(
                assessment,
                buy_result,
                point,
                execution_inputs,
                entry_contexts,
            )

            if buy_result.outcome is FastPaperBuyOutcome.FILLED:
                update = buy_result.ledger_update
                if update is None or update.state is not PaperLedgerUpdateState.APPLIED:
                    raise ValueError(
                        "FILLED campaign BUY requires APPLIED authoritative ledger update"
                    )
                position_id = update.position_id
                if position_id is None:
                    raise ValueError(
                        "FILLED campaign BUY requires authoritative position_id"
                    )
                position = _require_open_position(ledger, position_id)
                if position.mint != authority.mint:
                    raise ValueError(
                        "opened PAPER position mint does not match BUY authority"
                    )
                market_positions[decision.market_key] = position_id
                market_exposures[decision.market_key] = (
                    decision.target_exposure_fraction
                )
                position_states[position_id] = (
                    create_fast_paper_position_action_state(
                        position_id, ledger.as_of_unix_ms
                    )
                )
            continue

        assert tracked_position_id is not None
        assert tracked_exposure is not None
        assert point.quote is not None
        state = position_states.get(tracked_position_id)
        if state is None:
            raise ValueError(
                "tracked OPEN position is missing Fast PAPER position-action state"
            )
        position = _require_open_position(ledger, tracked_position_id)
        target_base_quantity = _position_exit_quantity(
            decision, position, tracked_exposure
        )

        position_result = apply_fast_paper_position_action(
            state=state,
            approval=FastPaperPositionActionApproval(
                version=FAST_PAPER_POSITION_ACTION_VERSION,
                assessment=assessment,
                position_id=tracked_position_id,
                mint=position.mint,
                quote_mint=point.quote.quote_mint,
                state_version=point.state_version,
                target_base_quantity=target_base_quantity,
            ),
            ledger=ledger,
            quote=_position_quote(point.quote),
            fill_policy=fill_policy,
            policy=position_policy,
            evaluated_at_unix_ms=point.evaluated_at_unix_ms,
        )
        position_results.append(position_result)
        ledger = position_result.next_ledger
        position_states[tracked_position_id] = position_result.next_state

        _collect_position_execution(position_result, execution_inputs)

        if position_result.outcome is FastPaperPositionOutcome.SOLD:
            market_positions.pop(decision.market_key, None)
            market_exposures.pop(decision.market_key, None)
            position_states.pop(tracked_position_id, None)
        elif position_result.outcome is FastPaperPositionOutcome.REDUCED:
            active_exit = position_result.active_exit
            if active_exit is None:
                raise ValueError(
                    "REDUCED campaign position requires active exit authority"
                )
            target = decision_targets.get(active_exit.assessment.source_event_id)
            if target is None:
                raise ValueError(
                    "executed pending REDUCE cannot be linked to campaign decision"
                )
            market_exposures[decision.market_key] = target

    evaluation_identity = FastPaperEvaluationIdentity(
        version=FAST_PAPER_EVALUATION_ADAPTER_VERSION,
        paper_run_id=identity.paper_run_id,
        candidate_version=identity.candidate_version,
        candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
        strategy_version=identity.strategy_version,
        allowed_assessment_strategy_versions=(identity.strategy_version,),
    )
    capture = extract_fast_paper_evaluation_evidence(
        evaluation_identity,
        tuple(entry_contexts),
        tuple(execution_inputs),
    )
    trades = build_evaluated_trades(
        capture.paper_run_id,
        capture.candidate_version,
        capture.entry_provenance,
        capture.executions,
        capture.closures,
        capture.orphan_costs,
    )
    report = evaluate_trading_performance(
        trades,
        (),
        evaluation_policy,
        identity.candidate_version,
    )
    trading_evaluation = TradingEvaluationEvidence(
        candidate_version=identity.candidate_version,
        policy=evaluation_policy,
        trades=trades,
        probability_observations=(),
        report=report,
    )
    run_evidence = build_fast_policy_run_evidence(
        paper_run_id=identity.paper_run_id,
        candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
        strategy_version=identity.strategy_version,
        loop_state=loop_state,
        trading_evaluation=trading_evaluation,
    )

    return FastCampaignPaperRunResult(
        version=FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION,
        identity=identity,
        event_loop_state=loop_state,
        final_ledger=ledger,
        buy_results=tuple(buy_results),
        position_results=tuple(position_results),
        evaluation_capture=capture,
        trading_evaluation=trading_evaluation,
        run_evidence=run_evidence,
    )


def _validate_population_alignment(
    decisions: tuple[_FastCampaignPaperDecision, ...],
    evidence: tuple[FastCampaignPaperDecisionEvidence, ...],
) -> None:
    seen: set[str] = set()
    latest_by_market: dict[str, tuple[int, int]] = {}
    for decision, point in zip(decisions, evidence):
        if decision.source_event_id != point.source_event_id:
            raise ValueError(
                "campaign source_event_id does not match positional execution evidence"
            )
        if decision.source_event_id in seen:
            raise ValueError("campaign decision source_event_id values must be unique")
        seen.add(decision.source_event_id)
        if point.evaluated_at_unix_ms < decision.as_of_unix_ms:
            raise ValueError(
                "campaign execution evidence cannot be evaluated before decision"
            )
        if (
            point.quote is not None
            and point.quote.observed_at_unix_ms > point.evaluated_at_unix_ms
        ):
            raise ValueError("future quote cannot be campaign execution evidence")

        previous = latest_by_market.get(decision.market_key)
        if previous is not None:
            if decision.source_sequence <= previous[0]:
                raise ValueError(
                    "campaign per-market source sequence must strictly increase"
                )
            if decision.as_of_unix_ms < previous[1]:
                raise ValueError(
                    "campaign per-market decision time cannot move backward"
                )
        latest_by_market[decision.market_key] = (
            decision.source_sequence,
            decision.as_of_unix_ms,
        )


def _validate_decision_shape(decision: _FastCampaignPaperDecision) -> None:
    current = decision.current_exposure_fraction
    target = decision.target_exposure_fraction
    _require_exposure("current_exposure_fraction", current)
    _require_exposure("target_exposure_fraction", target)

    if decision.action == "SKIP":
        if not _close(current, 0.0) or not _close(target, 0.0):
            raise ValueError("SKIP requires flat current and target exposure")
    elif decision.action == "BUY":
        if not _close(current, 0.0) or target <= 0.0:
            raise ValueError("BUY requires flat current and positive target exposure")
    elif decision.action == "HOLD":
        if current <= 0.0 or not _close(target, current):
            raise ValueError("HOLD requires unchanged positive exposure")
    elif decision.action == "REDUCE":
        if current <= 0.0 or target <= 0.0 or target >= current:
            raise ValueError(
                "REDUCE target exposure must be positive and strictly below current exposure"
            )
    elif decision.action == "SELL":
        if current <= 0.0 or not _close(target, 0.0):
            raise ValueError("SELL target exposure must be zero from an OPEN posture")
    else:
        raise ValueError("campaign action is unsupported")


def _validate_posture(
    decision: _FastCampaignPaperDecision,
    *,
    tracked_position_id: str | None,
    tracked_exposure: float | None,
) -> None:
    flat_action = decision.action in {"SKIP", "BUY"}
    if flat_action:
        if tracked_position_id is not None or tracked_exposure is not None:
            raise ValueError(
                f"{decision.action} requires flat campaign posture without OPEN position"
            )
        return

    if tracked_position_id is None or tracked_exposure is None:
        raise ValueError(
            f"{decision.action} requires an authoritative tracked OPEN position"
        )
    if not _close(decision.current_exposure_fraction, tracked_exposure):
        raise ValueError(
            "campaign decision current exposure does not match tracked PAPER posture"
        )


def _validate_evidence_for_action(
    decision: _FastCampaignPaperDecision,
    point: FastCampaignPaperDecisionEvidence,
) -> None:
    if decision.action == "SKIP":
        if any(
            value is not None
            for value in (
                point.quote,
                point.risk_context,
                point.entry_authority,
                point.market_regime,
            )
        ):
            raise ValueError("SKIP must not carry unused execution evidence")
        return

    if point.quote is None:
        raise ValueError(
            f"{decision.action} requires explicit campaign quote evidence"
        )

    if decision.action == "BUY":
        if point.risk_context is None:
            raise ValueError("BUY requires explicit RiskContext evidence")
        if point.entry_authority is None:
            raise ValueError("BUY requires explicit entry authority")
        if point.market_regime is None:
            raise ValueError("BUY requires point-in-time MarketRegime")
        return

    if any(
        value is not None
        for value in (
            point.risk_context,
            point.entry_authority,
            point.market_regime,
        )
    ):
        raise ValueError(
            f"{decision.action} must not carry BUY-only risk/entry/regime evidence"
        )


def _position_exit_quantity(
    decision: _FastCampaignPaperDecision,
    position: PaperPosition,
    tracked_exposure: float,
) -> float | None:
    if decision.action == "HOLD":
        return None
    if decision.action == "SELL":
        return position.quantity
    if decision.action != "REDUCE":
        raise ValueError("position exit quantity requested for unsupported action")

    current = tracked_exposure
    target = decision.target_exposure_fraction
    if current <= 0.0 or target <= 0.0 or target >= current:
        raise ValueError(
            "REDUCE requires positive target exposure strictly below current exposure"
        )
    exit_fraction = 1.0 - target / current
    quantity = position.quantity * exit_fraction
    if (
        not math.isfinite(quantity)
        or quantity <= 0.0
        or quantity >= position.quantity
        or _close(quantity, position.quantity)
    ):
        raise ValueError("derived REDUCE base exit quantity is invalid")
    return quantity


def _collect_buy_execution(
    assessment,
    result,
    point: FastCampaignPaperDecisionEvidence,
    execution_inputs: list[FastPaperExecutionEvidenceInput],
    entry_contexts: list[FastPaperEntryEvaluationContext],
) -> None:
    execution = result.execution
    update = result.ledger_update
    if (
        execution is not None
        and update is not None
        and update.state is PaperLedgerUpdateState.APPLIED
    ):
        execution_inputs.append(
            FastPaperExecutionEvidenceInput(
                assessment=assessment,
                execution=execution,
                ledger_update=update,
            )
        )
    if result.outcome is FastPaperBuyOutcome.FILLED:
        if point.market_regime is None:
            raise ValueError("FILLED BUY requires point-in-time MarketRegime")
        entry_contexts.append(
            FastPaperEntryEvaluationContext(
                source_event_id=assessment.source_event_id,
                market_regime=point.market_regime,
            )
        )


def _collect_position_execution(
    result,
    execution_inputs: list[FastPaperExecutionEvidenceInput],
) -> None:
    execution = result.execution
    update = result.execution_ledger_update
    if (
        execution is None
        or update is None
        or update.state is not PaperLedgerUpdateState.APPLIED
    ):
        return
    active_exit = result.active_exit
    if active_exit is None:
        raise ValueError(
            "campaign position execution requires active exit assessment authority"
        )
    execution_inputs.append(
        FastPaperExecutionEvidenceInput(
            assessment=active_exit.assessment,
            execution=execution,
            ledger_update=update,
        )
    )


def _buy_quote(value: FastCampaignPaperQuoteEvidence) -> FastPaperBuyQuote:
    return FastPaperBuyQuote(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=value.state,
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=value.quote_to_usd_rate,
    )


def _position_quote(
    value: FastCampaignPaperQuoteEvidence,
) -> FastPaperPositionQuote:
    return FastPaperPositionQuote(
        provider=value.provider,
        mint=value.mint,
        quote_mint=value.quote_mint,
        observed_at_unix_ms=value.observed_at_unix_ms,
        state=value.state,
        reference_price_quote=value.reference_price_quote,
        execution_price_quote=value.execution_price_quote,
        quoted_base_quantity=value.quoted_base_quantity,
        available_base_quantity=value.available_base_quantity,
        quote_to_usd_rate=value.quote_to_usd_rate,
    )


def _require_open_position(ledger: PaperLedger, position_id: str) -> PaperPosition:
    matches = tuple(
        position
        for position in ledger.positions
        if position.position_id == position_id
    )
    if len(matches) != 1:
        raise ValueError("tracked PAPER position_id is missing or ambiguous")
    position = matches[0]
    if position.state is not PaperPositionState.OPEN:
        raise ValueError("tracked PAPER position must remain OPEN")
    return position


def _require_exposure(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite within [0, 1]")


def _close(left: float, right: float) -> bool:
    return math.isclose(
        left,
        right,
        rel_tol=_REL_TOL,
        abs_tol=_ABS_TOL,
    )
