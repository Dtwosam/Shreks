from __future__ import annotations

from shreks_brain.decision import DecisionAction
from shreks_brain.exits import (
    ExitExecutionContext,
    ExitState,
    assess_exit,
    create_exit_state,
)
from shreks_brain.features import FeatureVector
from shreks_brain.paper import PaperPosition, PaperPositionState

from .engine import run_fast_paper_event
from .models import (
    FastPaperAction,
    FastPaperLoopState,
    FastPaperMaterialUpdate,
)
from .position_models import FastPaperPositionActionApproval
from .protective_models import (
    FAST_PAPER_PROTECTIVE_EXIT_VERSION,
    FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY,
    FastPaperPositionApprovalEvaluator,
    FastPaperProtectiveEventResult,
    FastPaperProtectiveExitError,
    FastPaperProtectiveExitPolicy,
)


def create_fast_paper_protective_exit_state(
    position: PaperPosition,
    policy: FastPaperProtectiveExitPolicy,
) -> ExitState:
    """Initialize FL7.6 protective state through the sealed C4 authority."""

    if not isinstance(position, PaperPosition):
        raise FastPaperProtectiveExitError("position must be a PaperPosition")
    if not isinstance(policy, FastPaperProtectiveExitPolicy):
        raise FastPaperProtectiveExitError(
            "policy must be a FastPaperProtectiveExitPolicy"
        )
    try:
        return create_exit_state(position, policy.exit_policy)
    except ValueError as error:
        raise FastPaperProtectiveExitError(str(error)) from error


def run_fast_paper_protective_event(
    *,
    state: FastPaperLoopState,
    update: FastPaperMaterialUpdate,
    position: PaperPosition,
    features: FeatureVector,
    context: ExitExecutionContext,
    protective_state: ExitState,
    protective_policy: FastPaperProtectiveExitPolicy,
    strategy_evaluator: FastPaperPositionApprovalEvaluator,
) -> FastPaperProtectiveEventResult:
    """Resolve one material Fast PAPER action with independent C4 protection.

    Sealed FL7.1 decides replay/materiality. The strategy evaluator and C4 are
    invoked only inside the FL7.1 evaluator callback, so replay/non-material
    events cannot create new strategy or protective authority.
    """

    if not isinstance(state, FastPaperLoopState):
        raise FastPaperProtectiveExitError("state must be a FastPaperLoopState")
    if not isinstance(update, FastPaperMaterialUpdate):
        raise FastPaperProtectiveExitError("update must be a FastPaperMaterialUpdate")
    if not isinstance(position, PaperPosition):
        raise FastPaperProtectiveExitError("position must be a PaperPosition")
    if not isinstance(features, FeatureVector):
        raise FastPaperProtectiveExitError("features must be a FeatureVector")
    if not isinstance(context, ExitExecutionContext):
        raise FastPaperProtectiveExitError(
            "context must be an ExitExecutionContext"
        )
    if not isinstance(protective_state, ExitState):
        raise FastPaperProtectiveExitError("protective_state must be an ExitState")
    if not isinstance(protective_policy, FastPaperProtectiveExitPolicy):
        raise FastPaperProtectiveExitError(
            "protective_policy must be a FastPaperProtectiveExitPolicy"
        )
    if not callable(strategy_evaluator):
        raise FastPaperProtectiveExitError("strategy_evaluator must be callable")

    captured: list[
        tuple[FastPaperPositionActionApproval, FastPaperPositionActionApproval, object]
    ] = []

    def evaluator(material_update: FastPaperMaterialUpdate):
        if captured:
            raise FastPaperProtectiveExitError(
                "protected FL7.1 evaluator was invoked more than once"
            )
        _validate_evaluation_inputs(
            material_update,
            position,
            features,
            context,
            protective_state,
            protective_policy,
        )
        strategy = strategy_evaluator(material_update)
        _validate_strategy_approval(material_update, position, strategy)

        protective = assess_exit(
            position,
            features,
            context,
            protective_state,
            protective_policy.exit_policy,
        )
        applied = _resolve_protective_authority(
            strategy,
            position,
            protective,
            protective_policy,
        )
        captured.append((strategy, applied, protective))
        return applied.assessment

    event_result = run_fast_paper_event(state, update, evaluator)

    if not captured:
        return FastPaperProtectiveEventResult(
            version=FAST_PAPER_PROTECTIVE_EXIT_VERSION,
            event_result=event_result,
            strategy_approval=None,
            applied_approval=None,
            protective_assessment=None,
            next_protective_state=protective_state,
            protective_triggered=False,
        )
    if len(captured) != 1:
        raise FastPaperProtectiveExitError(
            "protected FL7.1 evaluator invocation count is invalid"
        )

    strategy, applied, protective = captured[0]
    return FastPaperProtectiveEventResult(
        version=FAST_PAPER_PROTECTIVE_EXIT_VERSION,
        event_result=event_result,
        strategy_approval=strategy,
        applied_approval=applied,
        protective_assessment=protective,
        next_protective_state=protective.next_state,
        protective_triggered=protective.action is DecisionAction.EXIT,
    )


def _validate_evaluation_inputs(
    update: FastPaperMaterialUpdate,
    position: PaperPosition,
    features: FeatureVector,
    context: ExitExecutionContext,
    protective_state: ExitState,
    policy: FastPaperProtectiveExitPolicy,
) -> None:
    if position.state is not PaperPositionState.OPEN:
        raise FastPaperProtectiveExitError(
            "protective arbitration requires an authoritative OPEN position"
        )
    if features.as_of_unix_ms != update.as_of_unix_ms:
        raise FastPaperProtectiveExitError(
            "FeatureVector decision clock must match triggering update"
        )
    if context.as_of_unix_ms != update.as_of_unix_ms:
        raise FastPaperProtectiveExitError(
            "ExitExecutionContext decision clock must match triggering update"
        )
    if protective_state.position_id != position.position_id:
        raise FastPaperProtectiveExitError(
            "protective state position_id does not match authoritative position"
        )
    if protective_state.mint != position.mint:
        raise FastPaperProtectiveExitError(
            "protective state mint does not match authoritative position"
        )
    if protective_state.policy_version != policy.exit_policy.version:
        raise FastPaperProtectiveExitError(
            "protective state policy version does not match C4 policy"
        )


def _validate_strategy_approval(
    update: FastPaperMaterialUpdate,
    position: PaperPosition,
    approval: object,
) -> None:
    if not isinstance(approval, FastPaperPositionActionApproval):
        raise FastPaperProtectiveExitError(
            "strategy evaluator must return FastPaperPositionActionApproval"
        )
    assessment = approval.assessment
    checks = (
        ("source_event_id", assessment.source_event_id, update.source_event_id),
        ("market_key", assessment.market_key, update.market_key),
        ("source_sequence", assessment.source_sequence, update.source_sequence),
        ("as_of_unix_ms", assessment.as_of_unix_ms, update.as_of_unix_ms),
        ("state_version", approval.state_version, update.state_version),
        ("position_id", approval.position_id, position.position_id),
        ("mint", approval.mint, position.mint),
    )
    for name, observed, expected in checks:
        if observed != expected:
            raise FastPaperProtectiveExitError(
                f"strategy approval {name} does not match triggering authority"
            )


def _resolve_protective_authority(
    strategy: FastPaperPositionActionApproval,
    position: PaperPosition,
    protective,
    policy: FastPaperProtectiveExitPolicy,
) -> FastPaperPositionActionApproval:
    if protective.action is DecisionAction.HOLD:
        return strategy
    if protective.action is DecisionAction.REDUCE:
        raise FastPaperProtectiveExitError(
            "protective-only C4 policy unexpectedly produced REDUCE"
        )
    if protective.action is not DecisionAction.EXIT:
        raise FastPaperProtectiveExitError(
            "C4 protective assessment produced unsupported action"
        )

    protective_reasons = tuple(
        f"protective:{finding.code.value}" for finding in protective.findings
    )
    if not protective_reasons:
        raise FastPaperProtectiveExitError(
            "protective C4 EXIT must carry at least one finding"
        )
    audit_reasons = (
        f"strategy_action:{strategy.assessment.action.value}",
    ) + tuple(f"strategy:{reason}" for reason in strategy.assessment.reasons)

    assessment = type(strategy.assessment)(
        version=strategy.assessment.version,
        source_event_id=strategy.assessment.source_event_id,
        market_key=strategy.assessment.market_key,
        source_sequence=strategy.assessment.source_sequence,
        as_of_unix_ms=strategy.assessment.as_of_unix_ms,
        strategy_family=FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY,
        strategy_version=policy.version,
        action=FastPaperAction.SELL,
        reasons=protective_reasons + audit_reasons,
    )
    return FastPaperPositionActionApproval(
        version=strategy.version,
        assessment=assessment,
        position_id=strategy.position_id,
        mint=strategy.mint,
        quote_mint=strategy.quote_mint,
        state_version=strategy.state_version,
        target_base_quantity=position.quantity,
    )
