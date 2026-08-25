from __future__ import annotations

import math

from shreks_brain.paper import (
    PaperExecutionResult,
    PaperExecutionState,
    PaperLedgerReasonCode,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPositionState,
)
from shreks_brain.paper_loop import PaperCycleResult
from shreks_brain.registry import RegistryCandidate
from shreks_brain.risk import TradeIntent

from .models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationCapture,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)


_REL_TOL = 1e-12
_ABS_TOL = 1e-9


def extract_paper_evaluation_evidence(
    paper_run_id: str,
    candidate: RegistryCandidate,
    cycle: PaperCycleResult,
) -> PaperEvaluationCapture:
    """Capture only evidence that C5 and C3 actually produced in one paper cycle."""

    if not isinstance(paper_run_id, str) or not paper_run_id.strip():
        raise ValueError("paper_run_id must be a non-empty string")
    if type(candidate) is not RegistryCandidate:
        raise ValueError("candidate must be an exact RegistryCandidate")
    if type(cycle) is not PaperCycleResult:
        raise ValueError("cycle must be an exact PaperCycleResult")

    provenance: list[PaperEntryProvenance] = []
    executions: list[PaperPositionExecutionEvidence] = []
    closures: list[PaperClosedPositionEvidence] = []
    orphan_costs: list[PaperOrphanCostEvidence] = []

    if cycle.pending_entry_result is not None:
        _capture_applied_execution(
            paper_run_id,
            candidate,
            cycle.pending_entry_result.execution,
            cycle.pending_entry_result.ledger_update,
            intent=None,
            expected_position_id=None,
            executions=executions,
            closures=closures,
            orphan_costs=orphan_costs,
        )

    for entry_result in cycle.entry_results:
        if not entry_result.selected_for_entry:
            continue
        execution = entry_result.execution
        if execution is None:
            raise ValueError("selected entry requires execution evidence")
        decision = entry_result.decision
        if decision.setup_policy_version != candidate.strategy_version:
            raise ValueError("candidate strategy does not match selected entry strategy")
        if decision.mint != entry_result.mint or execution.mint != entry_result.mint:
            raise ValueError("selected entry mint evidence does not reconcile")
        intent = None
        if entry_result.risk_assessment is not None:
            intent = entry_result.risk_assessment.intent
        if intent is None:
            raise ValueError("selected entry requires original risk-approved intent")
        if intent.idempotency_key != execution.intent_idempotency_key:
            raise ValueError("selected entry intent key does not match execution")
        if intent.strategy_version != candidate.strategy_version:
            raise ValueError("candidate strategy does not match selected entry intent")

        provenance.append(
            PaperEntryProvenance(
                paper_run_id=paper_run_id,
                candidate_version=candidate.candidate_version,
                candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
                strategy_version=candidate.strategy_version,
                intent_idempotency_key=intent.idempotency_key,
                mint=entry_result.mint,
                decision_as_of_unix_ms=decision.as_of_unix_ms,
                setup_name=decision.setup_name,
                market_regime=decision.market_regime,
                score_policy_version=decision.score_policy_version,
                decision_policy_version=decision.policy_version,
                paper_execution_policy_version=execution.policy_version,
            )
        )
        _capture_applied_execution(
            paper_run_id,
            candidate,
            execution,
            entry_result.ledger_update,
            intent=intent,
            expected_position_id=None,
            executions=executions,
            closures=closures,
            orphan_costs=orphan_costs,
        )

    for exit_result in cycle.exit_results:
        if exit_result.execution is None:
            continue
        _capture_applied_execution(
            paper_run_id,
            candidate,
            exit_result.execution,
            exit_result.execution_ledger_update,
            intent=exit_result.intent,
            expected_position_id=exit_result.position_id,
            executions=executions,
            closures=closures,
            orphan_costs=orphan_costs,
        )

    provenance.sort(
        key=lambda value: (
            value.paper_run_id,
            value.decision_as_of_unix_ms,
            value.intent_idempotency_key,
        )
    )
    executions.sort(key=lambda value: (value.paper_run_id, value.ledger_sequence))
    closures.sort(
        key=lambda value: (
            value.paper_run_id,
            value.closed_at_unix_ms,
            value.position_id,
        )
    )
    orphan_costs.sort(
        key=lambda value: (
            value.paper_run_id,
            value.evaluated_at_unix_ms,
            value.intent_idempotency_key,
        )
    )

    return PaperEvaluationCapture(
        paper_run_id=paper_run_id,
        candidate_version=candidate.candidate_version,
        candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
        strategy_version=candidate.strategy_version,
        entry_provenance=tuple(provenance),
        executions=tuple(executions),
        closures=tuple(closures),
        orphan_costs=tuple(orphan_costs),
    )


def _capture_applied_execution(
    paper_run_id: str,
    candidate: RegistryCandidate,
    execution: PaperExecutionResult,
    update: PaperLedgerUpdate | None,
    *,
    intent: TradeIntent | None,
    expected_position_id: str | None,
    executions: list[PaperPositionExecutionEvidence],
    closures: list[PaperClosedPositionEvidence],
    orphan_costs: list[PaperOrphanCostEvidence],
) -> None:
    if update is None or update.state is not PaperLedgerUpdateState.APPLIED:
        return
    if execution.state is PaperExecutionState.DEFERRED:
        raise ValueError("APPLIED ledger update cannot correspond to DEFERRED execution")
    if not update.ledger.entries:
        raise ValueError("APPLIED ledger update requires a journal entry")

    journal = update.ledger.entries[-1]
    if journal.intent_idempotency_key != execution.intent_idempotency_key:
        raise ValueError("journal intent key does not match execution")
    if journal.mint != execution.mint:
        raise ValueError("journal mint does not match execution")
    if journal.side is not execution.side:
        raise ValueError("journal side does not match execution")
    if journal.execution_state is not execution.state:
        raise ValueError("journal execution state does not match execution")
    if journal.paper_policy_version != execution.policy_version:
        raise ValueError("journal paper policy does not match execution")
    if journal.strategy_version != candidate.strategy_version:
        raise ValueError("candidate strategy does not match journal strategy")
    if journal.paper_execution_reason_code is not execution.findings[0].code:
        raise ValueError("journal execution reason does not match execution")
    _require_close("journal explicit cost", journal.explicit_cost_usd, execution.explicit_cost_usd)

    if update.position_id != journal.position_id:
        raise ValueError("ledger update position_id does not match journal")
    if expected_position_id is not None and journal.position_id != expected_position_id:
        raise ValueError("cycle position_id does not match journal")

    if intent is not None:
        _require_intent_matches_journal(intent, journal, execution)

    fill = execution.fill
    if fill is not None:
        if journal.position_id is None:
            raise ValueError("filled execution requires an attributed position")
        _require_close("journal filled notional", journal.filled_notional_usd, fill.filled_notional_usd)
        _require_close("journal filled quantity", journal.filled_quantity, fill.quantity)
        executions.append(
            PaperPositionExecutionEvidence(
                paper_run_id=paper_run_id,
                candidate_version=candidate.candidate_version,
                candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
                strategy_version=candidate.strategy_version,
                position_id=journal.position_id,
                ledger_sequence=journal.sequence,
                intent_idempotency_key=journal.intent_idempotency_key,
                mint=journal.mint,
                side=journal.side,
                execution_state=journal.execution_state,
                ledger_reason_code=journal.ledger_reason_code,
                booked_at_unix_ms=journal.booked_at_unix_ms,
                evaluated_at_unix_ms=execution.evaluated_at_unix_ms,
                requested_notional_usd=execution.requested_notional_usd,
                explicit_cost_usd=journal.explicit_cost_usd,
                filled_notional_usd=fill.filled_notional_usd,
                filled_quantity=fill.quantity,
                reference_price_usd=fill.reference_price_usd,
                execution_price_usd=fill.execution_price_usd,
                signed_slippage_usd=fill.signed_slippage_usd,
                quote_provider=fill.quote_provider,
                executed_at_unix_ms=fill.executed_at_unix_ms,
            )
        )
    elif execution.state is PaperExecutionState.FAILED:
        _require_close("failed journal filled notional", journal.filled_notional_usd, 0.0)
        _require_close("failed journal filled quantity", journal.filled_quantity, 0.0)
        if journal.position_id is not None:
            executions.append(
                PaperPositionExecutionEvidence(
                    paper_run_id=paper_run_id,
                    candidate_version=candidate.candidate_version,
                    candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
                    strategy_version=candidate.strategy_version,
                    position_id=journal.position_id,
                    ledger_sequence=journal.sequence,
                    intent_idempotency_key=journal.intent_idempotency_key,
                    mint=journal.mint,
                    side=journal.side,
                    execution_state=journal.execution_state,
                    ledger_reason_code=journal.ledger_reason_code,
                    booked_at_unix_ms=journal.booked_at_unix_ms,
                    evaluated_at_unix_ms=execution.evaluated_at_unix_ms,
                    requested_notional_usd=execution.requested_notional_usd,
                    explicit_cost_usd=journal.explicit_cost_usd,
                    filled_notional_usd=None,
                    filled_quantity=None,
                    reference_price_usd=None,
                    execution_price_usd=None,
                    signed_slippage_usd=None,
                    quote_provider=None,
                    executed_at_unix_ms=None,
                )
            )
        elif journal.explicit_cost_usd > 0.0:
            orphan_costs.append(
                PaperOrphanCostEvidence(
                    paper_run_id=paper_run_id,
                    candidate_version=candidate.candidate_version,
                    candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
                    strategy_version=candidate.strategy_version,
                    intent_idempotency_key=journal.intent_idempotency_key,
                    mint=journal.mint,
                    explicit_cost_usd=journal.explicit_cost_usd,
                    evaluated_at_unix_ms=execution.evaluated_at_unix_ms,
                )
            )
    else:
        raise ValueError("terminal successful execution requires fill evidence")

    if journal.ledger_reason_code is PaperLedgerReasonCode.POSITION_CLOSED:
        if journal.position_id is None:
            raise ValueError("POSITION_CLOSED journal requires position_id")
        matches = tuple(
            position
            for position in update.ledger.positions
            if position.position_id == journal.position_id
        )
        if len(matches) != 1:
            raise ValueError("POSITION_CLOSED journal requires one exact ledger position")
        position = matches[0]
        if position.state is not PaperPositionState.CLOSED:
            raise ValueError("POSITION_CLOSED journal requires CLOSED ledger position")
        if position.closed_at_unix_ms is None:
            raise ValueError("CLOSED ledger position requires closed_at_unix_ms")
        closures.append(
            PaperClosedPositionEvidence(
                paper_run_id=paper_run_id,
                candidate_version=candidate.candidate_version,
                candidate_fingerprint_sha256=candidate.candidate_fingerprint_sha256,
                strategy_version=candidate.strategy_version,
                position_id=position.position_id,
                mint=position.mint,
                opened_at_unix_ms=position.opened_at_unix_ms,
                closed_at_unix_ms=position.closed_at_unix_ms,
                realized_pnl_usd=position.realized_pnl_usd,
                accumulated_costs_usd=position.accumulated_costs_usd,
                buy_fill_count=position.buy_fill_count,
                sell_fill_count=position.sell_fill_count,
                closing_ledger_sequence=journal.sequence,
            )
        )


def _require_intent_matches_journal(intent, journal, execution: PaperExecutionResult) -> None:
    if intent.idempotency_key != journal.intent_idempotency_key:
        raise ValueError("intent key does not match journal")
    if intent.mint != journal.mint:
        raise ValueError("intent mint does not match journal")
    if intent.side is not journal.side:
        raise ValueError("intent side does not match journal")
    if intent.strategy_name != journal.strategy_name:
        raise ValueError("intent strategy name does not match journal")
    if intent.strategy_version != journal.strategy_version:
        raise ValueError("intent strategy version does not match journal")
    if intent.score_policy_version != journal.score_policy_version:
        raise ValueError("intent score policy does not match journal")
    if intent.decision_policy_version != journal.decision_policy_version:
        raise ValueError("intent decision policy does not match journal")
    if intent.risk_policy_version != journal.risk_policy_version:
        raise ValueError("intent risk policy does not match journal")
    _require_close(
        "intent requested notional",
        intent.requested_notional_usd,
        execution.requested_notional_usd,
    )


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
        raise ValueError(f"{name} does not reconcile")
