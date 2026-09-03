from __future__ import annotations

from dataclasses import dataclass
import math
import string

from shreks_brain.fast_paper import FastPaperAction, FastPaperActionAssessment
from shreks_brain.paper import (
    PaperExecutionResult,
    PaperExecutionState,
    PaperLedgerReasonCode,
    PaperLedgerUpdate,
    PaperLedgerUpdateState,
    PaperPositionState,
)
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide

from .models import (
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationCapture,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)


FAST_PAPER_EVALUATION_ADAPTER_VERSION = "fl9-fast-paper-evaluation-v1"
FAST_PAPER_SCORE_POLICY_SENTINEL = "not-applicable:fast-lane-score"

_REL_TOL = 1e-12
_ABS_TOL = 1e-9


@dataclass(frozen=True, slots=True)
class FastPaperEvaluationIdentity:
    version: str
    paper_run_id: str
    candidate_version: str
    candidate_fingerprint_sha256: str
    strategy_version: str
    allowed_assessment_strategy_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version != FAST_PAPER_EVALUATION_ADAPTER_VERSION:
            raise ValueError("unsupported Fast PAPER evaluation adapter version")
        for name in ("paper_run_id", "candidate_version", "strategy_version"):
            _require_non_empty_string(name, getattr(self, name))
        _require_sha256(
            "candidate_fingerprint_sha256", self.candidate_fingerprint_sha256
        )
        values = self.allowed_assessment_strategy_versions
        if (
            not isinstance(values, tuple)
            or not values
            or not all(isinstance(value, str) and value.strip() for value in values)
        ):
            raise ValueError(
                "allowed_assessment_strategy_versions must be a non-empty tuple of strings"
            )
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise ValueError(
                "allowed_assessment_strategy_versions must be unique and in lexical order"
            )


@dataclass(frozen=True, slots=True)
class FastPaperEntryEvaluationContext:
    source_event_id: str
    market_regime: MarketRegime

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        if type(self.market_regime) is not MarketRegime:
            raise ValueError("market_regime must be an exact MarketRegime")


@dataclass(frozen=True, slots=True)
class FastPaperExecutionEvidenceInput:
    assessment: FastPaperActionAssessment
    execution: PaperExecutionResult
    ledger_update: PaperLedgerUpdate

    def __post_init__(self) -> None:
        if type(self.assessment) is not FastPaperActionAssessment:
            raise ValueError("assessment must be an exact FastPaperActionAssessment")
        if type(self.execution) is not PaperExecutionResult:
            raise ValueError("execution must be an exact PaperExecutionResult")
        if type(self.ledger_update) is not PaperLedgerUpdate:
            raise ValueError("ledger_update must be an exact PaperLedgerUpdate")


def extract_fast_paper_evaluation_evidence(
    identity: FastPaperEvaluationIdentity,
    entry_contexts: tuple[FastPaperEntryEvaluationContext, ...],
    execution_inputs: tuple[FastPaperExecutionEvidenceInput, ...],
) -> PaperEvaluationCapture:
    if type(identity) is not FastPaperEvaluationIdentity:
        raise ValueError("identity must be an exact FastPaperEvaluationIdentity")
    _require_exact_tuple(
        "entry_contexts", entry_contexts, FastPaperEntryEvaluationContext
    )
    _require_exact_tuple(
        "execution_inputs", execution_inputs, FastPaperExecutionEvidenceInput
    )

    context_by_event: dict[str, FastPaperEntryEvaluationContext] = {}
    for context in entry_contexts:
        if context.source_event_id in context_by_event:
            raise ValueError("entry contexts must have unique source_event_id values")
        context_by_event[context.source_event_id] = context

    rows: list[
        tuple[
            int,
            FastPaperExecutionEvidenceInput,
            object,
        ]
    ] = []
    seen_sequences: set[int] = set()
    for item in execution_inputs:
        update = item.ledger_update
        execution = item.execution
        assessment = item.assessment

        if update.state is not PaperLedgerUpdateState.APPLIED:
            raise ValueError("Fast PAPER evaluation requires an APPLIED ledger update")
        if execution.state is PaperExecutionState.DEFERRED:
            raise ValueError("DEFERRED execution cannot be evaluation evidence")
        if execution.state not in (
            PaperExecutionState.FAILED,
            PaperExecutionState.PARTIAL,
            PaperExecutionState.FILLED,
        ):
            raise ValueError("Fast PAPER execution evidence must be terminal")
        if not update.ledger.entries:
            raise ValueError("APPLIED ledger update requires a journal entry")

        journal = update.ledger.entries[-1]
        if journal.sequence in seen_sequences:
            raise ValueError("duplicate execution ledger sequence")
        seen_sequences.add(journal.sequence)

        _validate_execution_authority(identity, assessment, execution, update, journal)
        rows.append((journal.sequence, item, journal))

    rows.sort(key=lambda value: value[0])

    provenance: list[PaperEntryProvenance] = []
    executions: list[PaperPositionExecutionEvidence] = []
    closures: list[PaperClosedPositionEvidence] = []
    orphan_costs: list[PaperOrphanCostEvidence] = []
    used_contexts: set[str] = set()

    for _, item, journal_object in rows:
        assessment = item.assessment
        execution = item.execution
        update = item.ledger_update
        journal = journal_object

        if journal.ledger_reason_code is PaperLedgerReasonCode.POSITION_OPENED:
            if assessment.action is not FastPaperAction.BUY:
                raise ValueError("POSITION_OPENED requires a BUY assessment")
            context = context_by_event.get(assessment.source_event_id)
            if context is None:
                raise ValueError(
                    "opening BUY requires exact point-in-time entry context"
                )
            if assessment.source_event_id in used_contexts:
                raise ValueError("opening BUY entry context cannot be reused")
            used_contexts.add(assessment.source_event_id)
            provenance.append(
                PaperEntryProvenance(
                    paper_run_id=identity.paper_run_id,
                    candidate_version=identity.candidate_version,
                    candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
                    strategy_version=identity.strategy_version,
                    intent_idempotency_key=journal.intent_idempotency_key,
                    mint=journal.mint,
                    decision_as_of_unix_ms=assessment.as_of_unix_ms,
                    setup_name=assessment.strategy_family,
                    market_regime=context.market_regime,
                    score_policy_version=FAST_PAPER_SCORE_POLICY_SENTINEL,
                    decision_policy_version=assessment.strategy_version,
                    paper_execution_policy_version=execution.policy_version,
                )
            )

        fill = execution.fill
        if fill is not None:
            if journal.position_id is None:
                raise ValueError("filled execution requires an attributed position")
            _require_close(
                "journal filled notional",
                journal.filled_notional_usd,
                fill.filled_notional_usd,
            )
            _require_close(
                "journal filled quantity",
                journal.filled_quantity,
                fill.quantity,
            )
            executions.append(
                PaperPositionExecutionEvidence(
                    paper_run_id=identity.paper_run_id,
                    candidate_version=identity.candidate_version,
                    candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
                    strategy_version=identity.strategy_version,
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
            _require_close(
                "failed journal filled notional", journal.filled_notional_usd, 0.0
            )
            _require_close(
                "failed journal filled quantity", journal.filled_quantity, 0.0
            )
            if journal.position_id is not None:
                executions.append(
                    PaperPositionExecutionEvidence(
                        paper_run_id=identity.paper_run_id,
                        candidate_version=identity.candidate_version,
                        candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
                        strategy_version=identity.strategy_version,
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
                        paper_run_id=identity.paper_run_id,
                        candidate_version=identity.candidate_version,
                        candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
                        strategy_version=identity.strategy_version,
                        intent_idempotency_key=journal.intent_idempotency_key,
                        mint=journal.mint,
                        explicit_cost_usd=journal.explicit_cost_usd,
                        evaluated_at_unix_ms=execution.evaluated_at_unix_ms,
                    )
                )
        else:
            raise ValueError("successful terminal execution requires fill evidence")

        if journal.ledger_reason_code is PaperLedgerReasonCode.POSITION_CLOSED:
            if journal.position_id is None:
                raise ValueError("POSITION_CLOSED journal requires position_id")
            matches = tuple(
                position
                for position in update.ledger.positions
                if position.position_id == journal.position_id
            )
            if len(matches) != 1:
                raise ValueError(
                    "POSITION_CLOSED journal requires one exact ledger position"
                )
            position = matches[0]
            if position.state is not PaperPositionState.CLOSED:
                raise ValueError(
                    "POSITION_CLOSED journal requires CLOSED ledger position"
                )
            if position.closed_at_unix_ms is None:
                raise ValueError("CLOSED ledger position requires closed_at_unix_ms")
            closures.append(
                PaperClosedPositionEvidence(
                    paper_run_id=identity.paper_run_id,
                    candidate_version=identity.candidate_version,
                    candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
                    strategy_version=identity.strategy_version,
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

    unused_contexts = set(context_by_event) - used_contexts
    if unused_contexts:
        raise ValueError("entry context does not correspond to an opening BUY")

    provenance.sort(
        key=lambda value: (
            value.decision_as_of_unix_ms,
            value.intent_idempotency_key,
        )
    )
    executions.sort(key=lambda value: value.ledger_sequence)
    closures.sort(key=lambda value: (value.closed_at_unix_ms, value.position_id))
    orphan_costs.sort(
        key=lambda value: (
            value.evaluated_at_unix_ms,
            value.intent_idempotency_key,
        )
    )

    return PaperEvaluationCapture(
        paper_run_id=identity.paper_run_id,
        candidate_version=identity.candidate_version,
        candidate_fingerprint_sha256=identity.candidate_fingerprint_sha256,
        strategy_version=identity.strategy_version,
        entry_provenance=tuple(provenance),
        executions=tuple(executions),
        closures=tuple(closures),
        orphan_costs=tuple(orphan_costs),
    )


def _validate_execution_authority(
    identity: FastPaperEvaluationIdentity,
    assessment: FastPaperActionAssessment,
    execution: PaperExecutionResult,
    update: PaperLedgerUpdate,
    journal: object,
) -> None:
    if assessment.strategy_version not in identity.allowed_assessment_strategy_versions:
        raise ValueError("assessment strategy version is not allowed for candidate run")

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
    if journal.paper_execution_reason_code is not execution.findings[0].code:
        raise ValueError("journal execution reason does not match execution")
    if journal.strategy_name != assessment.strategy_family:
        raise ValueError("journal strategy name does not match authorizing assessment")
    if journal.strategy_version != assessment.strategy_version:
        raise ValueError(
            "journal strategy version does not match authorizing assessment"
        )
    _require_close(
        "journal explicit cost", journal.explicit_cost_usd, execution.explicit_cost_usd
    )

    if update.position_id != journal.position_id:
        raise ValueError("ledger update position_id does not match journal")

    if execution.side is TradeSide.BUY:
        if assessment.action is not FastPaperAction.BUY:
            raise ValueError("BUY execution requires BUY assessment")
    elif execution.side is TradeSide.SELL:
        if assessment.action not in (FastPaperAction.REDUCE, FastPaperAction.SELL):
            raise ValueError("SELL execution requires REDUCE or SELL assessment")
    else:
        raise ValueError("unsupported Fast PAPER trade side")


def _require_exact_tuple(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple) or not all(
        type(item) is expected_type for item in value
    ):
        raise ValueError(
            f"{name} must be a tuple of exact {expected_type.__name__} values"
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _require_close(name: str, actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=_REL_TOL, abs_tol=_ABS_TOL):
        raise ValueError(f"{name} does not reconcile")
