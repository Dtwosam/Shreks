from __future__ import annotations

import math

from shreks_brain.evaluation import EvaluatedTrade
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
from shreks_brain.risk import TradeIntent, TradeSide

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


def build_evaluated_trades(
    paper_run_id: str,
    candidate_version: str,
    entry_provenance: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> tuple[EvaluatedTrade, ...]:
    """Normalize one paper run/candidate into reconciled closed E5 trades."""

    _require_non_empty_string("paper_run_id", paper_run_id)
    _require_non_empty_string("candidate_version", candidate_version)
    _require_exact_tuple("entry_provenance", entry_provenance, PaperEntryProvenance)
    _require_exact_tuple("executions", executions, PaperPositionExecutionEvidence)
    _require_exact_tuple("closures", closures, PaperClosedPositionEvidence)
    _require_exact_tuple("orphan_costs", orphan_costs, PaperOrphanCostEvidence)

    target_entries = tuple(
        value
        for value in entry_provenance
        if value.paper_run_id == paper_run_id
        and value.candidate_version == candidate_version
    )
    target_executions = tuple(
        value
        for value in executions
        if value.paper_run_id == paper_run_id
        and value.candidate_version == candidate_version
    )
    target_closures = tuple(
        value
        for value in closures
        if value.paper_run_id == paper_run_id
        and value.candidate_version == candidate_version
    )
    target_orphans = tuple(
        value
        for value in orphan_costs
        if value.paper_run_id == paper_run_id
        and value.candidate_version == candidate_version
    )

    _require_target_not_silently_misattributed(
        paper_run_id,
        candidate_version,
        entry_provenance,
        executions,
        closures,
        orphan_costs,
    )
    _require_canonical_normalization_inputs(
        target_entries,
        target_executions,
        target_closures,
        target_orphans,
    )
    _require_coherent_attribution(
        target_entries,
        target_executions,
        target_closures,
        target_orphans,
    )

    if target_orphans:
        raise ValueError(
            "positive orphan paper execution cost blocks candidate/run normalization"
        )
    if not target_closures:
        return ()

    trades: list[EvaluatedTrade] = []
    for closure in target_closures:
        linked = tuple(
            value
            for value in target_executions
            if value.position_id == closure.position_id
        )
        if not linked:
            raise ValueError("closure requires linked execution evidence")
        if any(value.mint != closure.mint for value in linked):
            raise ValueError("closure mint does not match linked execution evidence")
        if linked[-1].ledger_sequence != closure.closing_ledger_sequence:
            raise ValueError("closing ledger sequence must be the final linked execution")

        closing = linked[-1]
        if (
            closing.side is not TradeSide.SELL
            or closing.execution_state
            not in (PaperExecutionState.PARTIAL, PaperExecutionState.FILLED)
            or closing.ledger_reason_code is not PaperLedgerReasonCode.POSITION_CLOSED
        ):
            raise ValueError("closing execution evidence must be a successful POSITION_CLOSED sell")

        successful = tuple(
            value
            for value in linked
            if value.execution_state
            in (PaperExecutionState.PARTIAL, PaperExecutionState.FILLED)
        )
        buys = tuple(value for value in successful if value.side is TradeSide.BUY)
        sells = tuple(value for value in successful if value.side is TradeSide.SELL)
        if len(buys) != closure.buy_fill_count:
            raise ValueError("BUY fill count does not match closure evidence")
        if len(sells) != closure.sell_fill_count:
            raise ValueError("SELL fill count does not match closure evidence")
        if not buys or not sells:
            raise ValueError("closed trade requires BUY and SELL fill evidence")

        opener = buys[0]
        if opener.ledger_reason_code is not PaperLedgerReasonCode.POSITION_OPENED:
            raise ValueError("first BUY fill must be the position-opening execution")
        matching_provenance = tuple(
            value
            for value in target_entries
            if value.intent_idempotency_key == opener.intent_idempotency_key
        )
        if len(matching_provenance) != 1:
            raise ValueError("missing or duplicate entry provenance for opening BUY intent")
        provenance = matching_provenance[0]
        if provenance.mint != closure.mint:
            raise ValueError("entry provenance mint does not match closure")
        if provenance.intent_idempotency_key != opener.intent_idempotency_key:
            raise ValueError("entry provenance intent does not match opening BUY")

        entry_notional = sum(_filled_notional(value) for value in buys)
        turnover = sum(_filled_notional(value) for value in successful)
        friction = sum(
            max(0.0, _signed_slippage(value)) for value in successful
        )
        explicit_cost = sum(value.explicit_cost_usd for value in linked)
        if not math.isclose(
            closure.accumulated_costs_usd,
            explicit_cost,
            rel_tol=_REL_TOL,
            abs_tol=_ABS_TOL,
        ):
            raise ValueError("closure accumulated cost does not match linked booked costs")

        net_pnl = closure.realized_pnl_usd
        gross_pnl = net_pnl + friction + explicit_cost
        trades.append(
            EvaluatedTrade(
                candidate_version=candidate_version,
                position_id=closure.position_id,
                candidate_mint=closure.mint,
                setup_name=provenance.setup_name,
                market_regime=provenance.market_regime.value,
                opened_at_unix_ms=closure.opened_at_unix_ms,
                closed_at_unix_ms=closure.closed_at_unix_ms,
                entry_notional_usd=entry_notional,
                turnover_usd=turnover,
                gross_pnl_usd=gross_pnl,
                execution_friction_usd=friction,
                explicit_cost_usd=explicit_cost,
                net_pnl_usd=net_pnl,
            )
        )

    return tuple(trades)


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


def _require_target_not_silently_misattributed(
    paper_run_id: str,
    candidate_version: str,
    entry_provenance: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> None:
    for collection in (entry_provenance, executions, closures, orphan_costs):
        for value in collection:
            if value.paper_run_id == paper_run_id and value.candidate_version != candidate_version:
                raise ValueError("candidate attribution mismatch within requested paper run")
            if value.candidate_version == candidate_version and value.paper_run_id != paper_run_id:
                continue


def _require_canonical_normalization_inputs(
    entries: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> None:
    entry_order = tuple(
        sorted(
            entries,
            key=lambda value: (
                value.decision_as_of_unix_ms,
                value.intent_idempotency_key,
            ),
        )
    )
    if entries != entry_order:
        raise ValueError("entry provenance must be in canonical order")
    entry_keys = tuple(value.intent_idempotency_key for value in entries)
    if len(entry_keys) != len(set(entry_keys)):
        raise ValueError("entry provenance intent identities must be unique")

    sequences = tuple(value.ledger_sequence for value in executions)
    if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
        raise ValueError("execution journal sequence must be strictly increasing")

    closure_order = tuple(
        sorted(closures, key=lambda value: (value.closed_at_unix_ms, value.position_id))
    )
    if closures != closure_order:
        raise ValueError("closure evidence must be in canonical order")
    closure_ids = tuple(value.position_id for value in closures)
    if len(closure_ids) != len(set(closure_ids)):
        raise ValueError("closure position identities must be unique")

    orphan_order = tuple(
        sorted(
            orphan_costs,
            key=lambda value: (
                value.evaluated_at_unix_ms,
                value.intent_idempotency_key,
            ),
        )
    )
    if orphan_costs != orphan_order:
        raise ValueError("orphan cost evidence must be in canonical order")


def _require_coherent_attribution(
    entries: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> None:
    values = entries + executions + closures + orphan_costs
    if not values:
        return
    expected = (
        values[0].candidate_fingerprint_sha256,
        values[0].strategy_version,
    )
    for value in values[1:]:
        actual = (value.candidate_fingerprint_sha256, value.strategy_version)
        if actual != expected:
            raise ValueError("candidate fingerprint or strategy attribution mismatch")


def _filled_notional(value: PaperPositionExecutionEvidence) -> float:
    if value.filled_notional_usd is None:
        raise ValueError("successful fill evidence is missing filled notional")
    return value.filled_notional_usd


def _signed_slippage(value: PaperPositionExecutionEvidence) -> float:
    if value.signed_slippage_usd is None:
        raise ValueError("successful fill evidence is missing signed slippage")
    return value.signed_slippage_usd


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


def _require_exact_tuple(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple) or not all(type(item) is expected_type for item in value):
        raise ValueError(f"{name} must be a tuple of exact {expected_type.__name__} values")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
        raise ValueError(f"{name} does not reconcile")
