from __future__ import annotations

from dataclasses import replace
import hashlib

from shreks_brain.decision import DecisionAction, decide_entry
from shreks_brain.exits import (
    ExitAssessment,
    acknowledge_exit_fill,
    assess_exit,
    create_exit_state,
)
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionState,
    PaperFillPolicy,
    PaperLedger,
    PaperLedgerEntry,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionMark,
    PaperPositionState,
    PaperQuote,
    apply_paper_execution,
    execute_paper_intent,
    mark_paper_position,
)
from shreks_brain.risk import (
    RiskState,
    TradeIntent,
    TradeSide,
    assess_entry_risk,
)
from shreks_brain.runtime import RuntimeMode
from shreks_brain.scoring import score_candidate
from shreks_brain.setups import (
    assess_first_pullback,
    assess_fresh_launch,
    assess_graduation_breakout,
)

from .models import (
    FirstPullbackSetupInput,
    FreshLaunchSetupInput,
    GraduationBreakoutSetupInput,
    ManagedPaperPosition,
    PaperCycleInput,
    PaperCycleResult,
    PaperEntryCandidate,
    PaperEntryResult,
    PaperExitResult,
    PaperLoopFinding,
    PaperLoopPolicy,
    PaperLoopReasonCode,
    PaperLoopState,
    PaperPendingEntryResult,
    PendingPaperEntry,
)


_EXIT_KEY_VERSION = "c5-exit-v1"


def create_paper_loop_state(
    ledger: PaperLedger,
    loop_policy: PaperLoopPolicy,
    paper_fill_policy: PaperFillPolicy,
    managed_positions: tuple[ManagedPaperPosition, ...] = (),
    pending_entry: PendingPaperEntry | None = None,
) -> PaperLoopState:
    """Create one validated in-memory C5 orchestration state."""

    if not isinstance(ledger, PaperLedger):
        raise ValueError("ledger must be a PaperLedger")
    if not isinstance(loop_policy, PaperLoopPolicy):
        raise ValueError("loop_policy must be a PaperLoopPolicy")
    if not isinstance(paper_fill_policy, PaperFillPolicy):
        raise ValueError("paper_fill_policy must be a PaperFillPolicy")

    last_cycle_at = ledger.as_of_unix_ms
    if managed_positions:
        last_cycle_at = max(
            last_cycle_at,
            *(managed.exit_state.last_evaluated_at_unix_ms for managed in managed_positions),
        )
    return PaperLoopState(
        ledger=ledger,
        loop_policy=loop_policy,
        paper_fill_policy=paper_fill_policy,
        managed_positions=managed_positions,
        pending_entry=pending_entry,
        last_cycle_at_unix_ms=last_cycle_at,
    )


def run_paper_cycle(
    state: PaperLoopState,
    cycle: PaperCycleInput,
) -> PaperCycleResult:
    """Run one deterministic C5 paper cycle using only earlier sealed engines."""

    if not isinstance(state, PaperLoopState):
        raise ValueError("state must be a PaperLoopState")
    if not isinstance(cycle, PaperCycleInput):
        raise ValueError("cycle must be a PaperCycleInput")

    if cycle.as_of_unix_ms < state.last_cycle_at_unix_ms:
        return PaperCycleResult(
            policy_version=state.loop_policy.version,
            as_of_unix_ms=cycle.as_of_unix_ms,
            next_state=state,
            pending_entry_result=None,
            entry_results=(),
            exit_results=(),
            findings=(
                PaperLoopFinding(
                    PaperLoopReasonCode.CYCLE_BEFORE_STATE,
                    "cycle timestamp precedes current paper-loop state",
                ),
            ),
        )

    cycle_start_position_ids = tuple(
        position.position_id
        for position in state.ledger.positions
        if position.state is PaperPositionState.OPEN
    )

    ledger = state.ledger
    managed_positions = list(state.managed_positions)
    pending_entry = state.pending_entry
    pending_result: PaperPendingEntryResult | None = None
    entry_slot_used = False

    quotes_by_mint = {quote.mint: quote for quote in cycle.quotes}

    if pending_entry is not None:
        entry_slot_used = True
        execution = execute_paper_intent(
            pending_entry.intent,
            PaperExecutionContext(
                evaluated_at_unix_ms=cycle.as_of_unix_ms,
                processed_intent_keys=ledger.processed_intent_keys,
                quote=quotes_by_mint.get(pending_entry.intent.mint),
            ),
            state.paper_fill_policy,
        )
        if execution.state is PaperExecutionState.DEFERRED:
            pending_result = PaperPendingEntryResult(
                intent_idempotency_key=pending_entry.intent.idempotency_key,
                mint=pending_entry.intent.mint,
                execution=execution,
                ledger_update=None,
                reason=PaperLoopReasonCode.PENDING_ENTRY_DEFERRED,
            )
        else:
            update = apply_paper_execution(ledger, pending_entry.intent, execution)
            ledger = update.ledger
            pending_result = PaperPendingEntryResult(
                intent_idempotency_key=pending_entry.intent.idempotency_key,
                mint=pending_entry.intent.mint,
                execution=execution,
                ledger_update=update,
                reason=PaperLoopReasonCode.PENDING_ENTRY_TERMINAL,
            )
            if update.state is PaperLedgerUpdateState.APPLIED and execution.state in (
                PaperExecutionState.PARTIAL,
                PaperExecutionState.FILLED,
            ):
                managed_positions = _ensure_managed_after_buy(
                    managed_positions,
                    ledger,
                    pending_entry.intent.mint,
                    pending_entry.exit_policy,
                )
            pending_entry = None

    entry_results: list[PaperEntryResult] = []
    for candidate in cycle.entry_candidates:
        setup = _assess_setup(candidate)
        score = score_candidate(
            candidate.features,
            setup,
            candidate.regime,
            candidate.score_policy,
        )
        decision = decide_entry(candidate.mint, score, candidate.decision_policy)

        if entry_slot_used:
            entry_results.append(
                PaperEntryResult(
                    mint=candidate.mint,
                    setup_assessment=setup,
                    score_assessment=score,
                    decision=decision,
                    risk_assessment=None,
                    selected_for_entry=False,
                    execution=None,
                    ledger_update=None,
                    reason=PaperLoopReasonCode.ENTRY_NOT_SELECTED,
                )
            )
            continue

        if _find_open_position(ledger, candidate.mint) is not None:
            entry_results.append(
                PaperEntryResult(
                    mint=candidate.mint,
                    setup_assessment=setup,
                    score_assessment=score,
                    decision=decision,
                    risk_assessment=None,
                    selected_for_entry=False,
                    execution=None,
                    ledger_update=None,
                    reason=PaperLoopReasonCode.ENTRY_OPEN_POSITION_EXISTS,
                )
            )
            continue

        if candidate.risk_context.active_intent_keys:
            entry_results.append(
                PaperEntryResult(
                    mint=candidate.mint,
                    setup_assessment=setup,
                    score_assessment=score,
                    decision=decision,
                    risk_assessment=None,
                    selected_for_entry=False,
                    execution=None,
                    ledger_update=None,
                    reason=(
                        PaperLoopReasonCode.ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH
                    ),
                )
            )
            continue

        risk = assess_entry_risk(
            decision,
            candidate.risk_context,
            candidate.risk_policy,
            RuntimeMode.PAPER,
        )
        if risk.state is RiskState.REJECTED:
            entry_results.append(
                PaperEntryResult(
                    mint=candidate.mint,
                    setup_assessment=setup,
                    score_assessment=score,
                    decision=decision,
                    risk_assessment=risk,
                    selected_for_entry=False,
                    execution=None,
                    ledger_update=None,
                    reason=PaperLoopReasonCode.ENTRY_RISK_REJECTED,
                )
            )
            continue

        intent = risk.intent
        assert intent is not None
        entry_slot_used = True
        execution = execute_paper_intent(
            intent,
            PaperExecutionContext(
                evaluated_at_unix_ms=cycle.as_of_unix_ms,
                processed_intent_keys=ledger.processed_intent_keys,
                quote=quotes_by_mint.get(candidate.mint),
            ),
            state.paper_fill_policy,
        )

        if execution.state is PaperExecutionState.DEFERRED:
            pending_entry = PendingPaperEntry(intent, candidate.exit_policy)
            update = None
            reason = PaperLoopReasonCode.ENTRY_EXECUTION_DEFERRED
        else:
            update = apply_paper_execution(ledger, intent, execution)
            ledger = update.ledger
            if update.state is PaperLedgerUpdateState.APPLIED and execution.state in (
                PaperExecutionState.PARTIAL,
                PaperExecutionState.FILLED,
            ):
                managed_positions = _ensure_managed_after_buy(
                    managed_positions,
                    ledger,
                    candidate.mint,
                    candidate.exit_policy,
                )
            reason = PaperLoopReasonCode.ENTRY_EXECUTION_TERMINAL

        entry_results.append(
            PaperEntryResult(
                mint=candidate.mint,
                setup_assessment=setup,
                score_assessment=score,
                decision=decision,
                risk_assessment=risk,
                selected_for_entry=True,
                execution=execution,
                ledger_update=update,
                reason=reason,
            )
        )

    observations_by_position = {
        observation.position_id: observation for observation in cycle.exit_observations
    }
    exit_results: list[PaperExitResult] = []

    for position_id in cycle_start_position_ids:
        position = _find_position_by_id(ledger, position_id)
        managed = _find_managed(managed_positions, position_id)
        if position is None or managed is None:
            continue
        if position.state is not PaperPositionState.OPEN:
            managed_positions = _remove_managed(managed_positions, position_id)
            continue

        observation = observations_by_position.get(position_id)
        fresh_assessment: ExitAssessment | None = None
        latest_exit_state = managed.exit_state
        pending_exit = managed.pending_exit

        if observation is not None:
            fresh_assessment = assess_exit(
                position,
                observation.features,
                observation.execution_context,
                managed.exit_state,
                managed.exit_policy,
            )
            latest_exit_state = fresh_assessment.next_state
            pending_exit = _reconcile_pending_exit(
                pending_exit,
                fresh_assessment,
            )

        current_managed = ManagedPaperPosition(
            position_id=managed.position_id,
            exit_policy=managed.exit_policy,
            exit_state=latest_exit_state,
            pending_exit=pending_exit,
        )
        managed_positions = _replace_managed(managed_positions, current_managed)

        intent: TradeIntent | None = None
        execution = None
        execution_update: PaperLedgerUpdate | None = None
        mark_update: PaperLedgerUpdate | None = None

        if pending_exit is None:
            if fresh_assessment is None:
                reason = PaperLoopReasonCode.EXIT_OBSERVATION_MISSING
            else:
                reason = PaperLoopReasonCode.EXIT_HOLD
                ledger, mark_update = _mark_from_fresh_assessment(
                    ledger,
                    position_id,
                    fresh_assessment,
                    cycle.as_of_unix_ms,
                )
            exit_results.append(
                PaperExitResult(
                    position_id=position_id,
                    mint=position.mint,
                    exit_assessment=fresh_assessment,
                    intent=None,
                    execution=None,
                    execution_ledger_update=None,
                    mark_ledger_update=mark_update,
                    reason=reason,
                )
            )
            continue

        quote = quotes_by_mint.get(position.mint)
        reason = _pending_exit_quote_reason(
            pending_exit,
            quote,
            cycle.as_of_unix_ms,
            state.paper_fill_policy,
        )

        if reason is None:
            assert quote is not None
            assert quote.execution_price_usd is not None
            lifecycle_entry = _find_lifecycle_entry(ledger, position_id)
            intent = _build_exit_intent(
                position,
                pending_exit,
                quote,
                state.loop_policy,
                lifecycle_entry,
            )
            before_position = position
            execution = execute_paper_intent(
                intent,
                PaperExecutionContext(
                    evaluated_at_unix_ms=cycle.as_of_unix_ms,
                    processed_intent_keys=ledger.processed_intent_keys,
                    quote=quote,
                ),
                state.paper_fill_policy,
            )

            if execution.state is PaperExecutionState.DEFERRED:
                reason = PaperLoopReasonCode.EXIT_QUOTE_BEFORE_LATENCY
            else:
                execution_update = apply_paper_execution(ledger, intent, execution)
                ledger = execution_update.ledger
                pending_for_ack = pending_exit
                pending_exit = None

                after_position = _find_position_by_id(ledger, position_id)
                acknowledged_state = latest_exit_state
                if (
                    execution_update.state is PaperLedgerUpdateState.APPLIED
                    and after_position is not None
                ):
                    acknowledged_state = acknowledge_exit_fill(
                        latest_exit_state,
                        pending_for_ack,
                        before_position,
                        after_position,
                    )

                if (
                    after_position is not None
                    and after_position.state is PaperPositionState.CLOSED
                ):
                    managed_positions = _remove_managed(managed_positions, position_id)
                    reason = PaperLoopReasonCode.EXIT_POSITION_CLOSED
                else:
                    current_managed = ManagedPaperPosition(
                        position_id=position_id,
                        exit_policy=managed.exit_policy,
                        exit_state=acknowledged_state,
                        pending_exit=None,
                    )
                    managed_positions = _replace_managed(
                        managed_positions,
                        current_managed,
                    )
                    reason = PaperLoopReasonCode.EXIT_EXECUTION_TERMINAL

        if execution is None or execution.state is PaperExecutionState.DEFERRED:
            current_managed = ManagedPaperPosition(
                position_id=position_id,
                exit_policy=managed.exit_policy,
                exit_state=latest_exit_state,
                pending_exit=pending_exit,
            )
            managed_positions = _replace_managed(managed_positions, current_managed)

        current_position = _find_position_by_id(ledger, position_id)
        if (
            current_position is not None
            and current_position.state is PaperPositionState.OPEN
            and fresh_assessment is not None
        ):
            ledger, mark_update = _mark_from_fresh_assessment(
                ledger,
                position_id,
                fresh_assessment,
                cycle.as_of_unix_ms,
            )

        exit_results.append(
            PaperExitResult(
                position_id=position_id,
                mint=position.mint,
                exit_assessment=fresh_assessment,
                intent=intent,
                execution=execution,
                execution_ledger_update=execution_update,
                mark_ledger_update=mark_update,
                reason=reason,
            )
        )

    next_state = PaperLoopState(
        ledger=ledger,
        loop_policy=state.loop_policy,
        paper_fill_policy=state.paper_fill_policy,
        managed_positions=tuple(managed_positions),
        pending_entry=pending_entry,
        last_cycle_at_unix_ms=cycle.as_of_unix_ms,
    )
    return PaperCycleResult(
        policy_version=state.loop_policy.version,
        as_of_unix_ms=cycle.as_of_unix_ms,
        next_state=next_state,
        pending_entry_result=pending_result,
        entry_results=tuple(entry_results),
        exit_results=tuple(exit_results),
        findings=(
            PaperLoopFinding(
                PaperLoopReasonCode.CYCLE_APPLIED,
                "paper cycle applied",
            ),
        ),
    )


def _assess_setup(candidate: PaperEntryCandidate):
    setup = candidate.setup
    if isinstance(setup, FreshLaunchSetupInput):
        return assess_fresh_launch(candidate.features, setup.policy)
    if isinstance(setup, GraduationBreakoutSetupInput):
        return assess_graduation_breakout(
            candidate.features,
            setup.context,
            setup.policy,
        )
    if isinstance(setup, FirstPullbackSetupInput):
        return assess_first_pullback(candidate.features, setup.context, setup.policy)
    raise TypeError("unsupported setup input")


def _reconcile_pending_exit(
    pending: ExitAssessment | None,
    fresh: ExitAssessment,
) -> ExitAssessment | None:
    if fresh.action is DecisionAction.EXIT:
        if pending is None or pending.action is DecisionAction.REDUCE:
            return fresh
        return pending
    if fresh.action is DecisionAction.REDUCE:
        return fresh if pending is None else pending
    return pending


def _pending_exit_quote_reason(
    pending: ExitAssessment,
    quote: PaperQuote | None,
    cycle_as_of_unix_ms: int,
    fill_policy: PaperFillPolicy,
) -> PaperLoopReasonCode | None:
    if quote is None:
        return PaperLoopReasonCode.EXIT_QUOTE_MISSING
    if quote.observed_at_unix_ms > cycle_as_of_unix_ms:
        return PaperLoopReasonCode.EXIT_QUOTE_AFTER_CYCLE
    eligible_at_unix_ms = pending.as_of_unix_ms + fill_policy.assumed_latency_ms
    if quote.observed_at_unix_ms < eligible_at_unix_ms:
        return PaperLoopReasonCode.EXIT_QUOTE_BEFORE_LATENCY
    if quote.execution_price_usd is None:
        return PaperLoopReasonCode.EXIT_EXECUTION_PRICE_UNAVAILABLE
    return None


def _build_exit_intent(
    position: PaperPosition,
    pending: ExitAssessment,
    quote: PaperQuote,
    loop_policy: PaperLoopPolicy,
    lifecycle_entry: PaperLedgerEntry,
) -> TradeIntent:
    assert quote.execution_price_usd is not None
    return TradeIntent(
        mint=position.mint,
        side=TradeSide.SELL,
        requested_notional_usd=(
            pending.target_quantity * quote.execution_price_usd
        ),
        max_slippage_bps=loop_policy.exit_max_slippage_bps,
        strategy_name=lifecycle_entry.strategy_name,
        strategy_version=lifecycle_entry.strategy_version,
        score_policy_version=lifecycle_entry.score_policy_version,
        decision_policy_version=lifecycle_entry.decision_policy_version,
        risk_policy_version=lifecycle_entry.risk_policy_version,
        reason=pending.primary_reason.value,
        idempotency_key=_exit_idempotency_key(position, pending),
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=pending.as_of_unix_ms,
    )


def _exit_idempotency_key(
    position: PaperPosition,
    pending: ExitAssessment,
) -> str:
    payload = "|".join(
        (
            _EXIT_KEY_VERSION,
            position.position_id,
            pending.policy_version,
            str(pending.as_of_unix_ms),
            pending.primary_reason.value,
            float(pending.target_quantity).hex(),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_lifecycle_entry(
    ledger: PaperLedger,
    position_id: str,
) -> PaperLedgerEntry:
    for entry in ledger.entries:
        if entry.position_id == position_id and entry.side is TradeSide.BUY:
            return entry
    raise ValueError("OPEN paper position has no linked BUY lifecycle entry")


def _mark_from_fresh_assessment(
    ledger: PaperLedger,
    position_id: str,
    assessment: ExitAssessment,
    cycle_as_of_unix_ms: int,
) -> tuple[PaperLedger, PaperLedgerUpdate | None]:
    if assessment.current_price_usd is None:
        return ledger, None
    position = _find_position_by_id(ledger, position_id)
    if position is None or position.state is not PaperPositionState.OPEN:
        return ledger, None
    update = mark_paper_position(
        ledger,
        PaperPositionMark(
            position_id=position.position_id,
            mint=position.mint,
            observed_at_unix_ms=cycle_as_of_unix_ms,
            mark_price_usd=assessment.current_price_usd,
        ),
    )
    return update.ledger, update


def _find_open_position(ledger: PaperLedger, mint: str) -> PaperPosition | None:
    for position in ledger.positions:
        if position.mint == mint and position.state is PaperPositionState.OPEN:
            return position
    return None


def _find_position_by_id(
    ledger: PaperLedger,
    position_id: str,
) -> PaperPosition | None:
    for position in ledger.positions:
        if position.position_id == position_id:
            return position
    return None


def _find_managed(
    managed_positions: list[ManagedPaperPosition],
    position_id: str,
) -> ManagedPaperPosition | None:
    for managed in managed_positions:
        if managed.position_id == position_id:
            return managed
    return None


def _replace_managed(
    managed_positions: list[ManagedPaperPosition],
    replacement: ManagedPaperPosition,
) -> list[ManagedPaperPosition]:
    return [
        replacement if managed.position_id == replacement.position_id else managed
        for managed in managed_positions
    ]


def _remove_managed(
    managed_positions: list[ManagedPaperPosition],
    position_id: str,
) -> list[ManagedPaperPosition]:
    return [managed for managed in managed_positions if managed.position_id != position_id]


def _ensure_managed_after_buy(
    managed_positions: list[ManagedPaperPosition],
    ledger: PaperLedger,
    mint: str,
    exit_policy,
) -> list[ManagedPaperPosition]:
    position = _find_open_position(ledger, mint)
    if position is None:
        return managed_positions
    for managed in managed_positions:
        if managed.position_id == position.position_id:
            return managed_positions
    return managed_positions + [
        ManagedPaperPosition(
            position_id=position.position_id,
            exit_policy=exit_policy,
            exit_state=create_exit_state(position, exit_policy),
        )
    ]
