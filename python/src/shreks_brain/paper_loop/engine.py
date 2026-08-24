from __future__ import annotations

from shreks_brain.decision import decide_entry
from shreks_brain.exits import create_exit_state
from shreks_brain.paper import (
    PaperExecutionContext,
    PaperExecutionState,
    PaperLedger,
    PaperLedgerUpdateState,
    PaperPosition,
    PaperPositionState,
    apply_paper_execution,
    execute_paper_intent,
)
from shreks_brain.regime import RegimeAssessment
from shreks_brain.risk import RiskState, RuntimeMode, assess_entry_risk
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
    PaperLoopFinding,
    PaperLoopPolicy,
    PaperLoopReasonCode,
    PaperLoopState,
    PaperPendingEntryResult,
    PendingPaperEntry,
)


def create_paper_loop_state(
    ledger: PaperLedger,
    loop_policy: PaperLoopPolicy,
    paper_fill_policy,
    managed_positions: tuple[ManagedPaperPosition, ...] = (),
    pending_entry: PendingPaperEntry | None = None,
) -> PaperLoopState:
    """Create one validated in-memory C5 orchestration state."""

    if not isinstance(ledger, PaperLedger):
        raise ValueError("ledger must be a PaperLedger")
    if not isinstance(loop_policy, PaperLoopPolicy):
        raise ValueError("loop_policy must be a PaperLoopPolicy")

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
        exit_results=(),
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


def _find_open_position(ledger: PaperLedger, mint: str) -> PaperPosition | None:
    for position in ledger.positions:
        if position.mint == mint and position.state is PaperPositionState.OPEN:
            return position
    return None


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
