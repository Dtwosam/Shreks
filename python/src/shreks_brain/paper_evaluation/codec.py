from __future__ import annotations

from dataclasses import fields
import hashlib
import json
from typing import Mapping

from shreks_brain.paper import PaperExecutionState, PaperLedgerReasonCode
from shreks_brain.regime import MarketRegime
from shreks_brain.risk import TradeSide

from .models import (
    PAPER_EVALUATION_SCHEMA_VERSION,
    PaperClosedPositionEvidence,
    PaperEntryProvenance,
    PaperEvaluationLedger,
    PaperOrphanCostEvidence,
    PaperPositionExecutionEvidence,
)


_ZERO_SHA256 = "0" * 64
_DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "entry_provenance",
        "executions",
        "closures",
        "orphan_costs",
        "document_fingerprint_sha256",
    }
)
_ENTRY_FIELDS = frozenset(field.name for field in fields(PaperEntryProvenance))
_EXECUTION_FIELDS = frozenset(
    field.name for field in fields(PaperPositionExecutionEvidence)
)
_CLOSURE_FIELDS = frozenset(field.name for field in fields(PaperClosedPositionEvidence))
_ORPHAN_FIELDS = frozenset(field.name for field in fields(PaperOrphanCostEvidence))


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"value is not canonical-JSON serializable: {error}") from error


def build_paper_evaluation_ledger(
    entry_provenance: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> PaperEvaluationLedger:
    _require_exact_tuple("entry_provenance", entry_provenance, PaperEntryProvenance)
    _require_exact_tuple("executions", executions, PaperPositionExecutionEvidence)
    _require_exact_tuple("closures", closures, PaperClosedPositionEvidence)
    _require_exact_tuple("orphan_costs", orphan_costs, PaperOrphanCostEvidence)

    canonical_entries = tuple(
        sorted(
            entry_provenance,
            key=lambda value: (
                value.paper_run_id,
                value.decision_as_of_unix_ms,
                value.intent_idempotency_key,
            ),
        )
    )
    canonical_executions = tuple(
        sorted(executions, key=lambda value: (value.paper_run_id, value.ledger_sequence))
    )
    canonical_closures = tuple(
        sorted(
            closures,
            key=lambda value: (
                value.paper_run_id,
                value.closed_at_unix_ms,
                value.position_id,
            ),
        )
    )
    canonical_orphans = tuple(
        sorted(
            orphan_costs,
            key=lambda value: (
                value.paper_run_id,
                value.evaluated_at_unix_ms,
                value.intent_idempotency_key,
            ),
        )
    )
    zeroed = PaperEvaluationLedger(
        schema_version=PAPER_EVALUATION_SCHEMA_VERSION,
        entry_provenance=canonical_entries,
        executions=canonical_executions,
        closures=canonical_closures,
        orphan_costs=canonical_orphans,
        document_fingerprint_sha256=_ZERO_SHA256,
    )
    digest = hashlib.sha256(
        canonical_json(build_paper_evaluation_document(zeroed)).encode("utf-8")
    ).hexdigest()
    return PaperEvaluationLedger(
        schema_version=PAPER_EVALUATION_SCHEMA_VERSION,
        entry_provenance=canonical_entries,
        executions=canonical_executions,
        closures=canonical_closures,
        orphan_costs=canonical_orphans,
        document_fingerprint_sha256=digest,
    )


def build_paper_evaluation_document(
    ledger: PaperEvaluationLedger,
) -> dict[str, object]:
    if type(ledger) is not PaperEvaluationLedger:
        raise ValueError("ledger must be an exact PaperEvaluationLedger")
    return {
        "schema_version": ledger.schema_version,
        "entry_provenance": [_entry_to_dict(value) for value in ledger.entry_provenance],
        "executions": [_execution_to_dict(value) for value in ledger.executions],
        "closures": [_closure_to_dict(value) for value in ledger.closures],
        "orphan_costs": [_orphan_to_dict(value) for value in ledger.orphan_costs],
        "document_fingerprint_sha256": ledger.document_fingerprint_sha256,
    }


def encode_paper_evaluation_ledger(ledger: PaperEvaluationLedger) -> str:
    return canonical_json(build_paper_evaluation_document(ledger)) + "\n"


def decode_paper_evaluation_document(document: object) -> PaperEvaluationLedger:
    mapping = _require_exact_mapping(
        "paper evaluation document", document, _DOCUMENT_FIELDS
    )
    if mapping["schema_version"] != PAPER_EVALUATION_SCHEMA_VERSION:
        raise ValueError(
            "paper evaluation document schema_version must equal "
            f"{PAPER_EVALUATION_SCHEMA_VERSION}"
        )
    stored_fingerprint = mapping["document_fingerprint_sha256"]
    _require_sha256("document_fingerprint_sha256", stored_fingerprint)

    entries = _decode_collection(
        "entry_provenance",
        mapping["entry_provenance"],
        _decode_entry,
    )
    executions = _decode_collection(
        "executions",
        mapping["executions"],
        _decode_execution,
    )
    closures = _decode_collection(
        "closures",
        mapping["closures"],
        _decode_closure,
    )
    orphans = _decode_collection(
        "orphan_costs",
        mapping["orphan_costs"],
        _decode_orphan,
    )

    ledger = PaperEvaluationLedger(
        schema_version=PAPER_EVALUATION_SCHEMA_VERSION,
        entry_provenance=entries,  # type: ignore[arg-type]
        executions=executions,  # type: ignore[arg-type]
        closures=closures,  # type: ignore[arg-type]
        orphan_costs=orphans,  # type: ignore[arg-type]
        document_fingerprint_sha256=stored_fingerprint,  # type: ignore[arg-type]
    )
    rebuilt = build_paper_evaluation_ledger(
        ledger.entry_provenance,
        ledger.executions,
        ledger.closures,
        ledger.orphan_costs,
    )
    if stored_fingerprint != rebuilt.document_fingerprint_sha256:
        raise ValueError("paper evaluation document fingerprint does not match content")
    return ledger


def _entry_to_dict(value: PaperEntryProvenance) -> dict[str, object]:
    return {
        "paper_run_id": value.paper_run_id,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "strategy_version": value.strategy_version,
        "intent_idempotency_key": value.intent_idempotency_key,
        "mint": value.mint,
        "decision_as_of_unix_ms": value.decision_as_of_unix_ms,
        "setup_name": value.setup_name,
        "market_regime": value.market_regime.value,
        "score_policy_version": value.score_policy_version,
        "decision_policy_version": value.decision_policy_version,
        "paper_execution_policy_version": value.paper_execution_policy_version,
    }


def _execution_to_dict(value: PaperPositionExecutionEvidence) -> dict[str, object]:
    return {
        "paper_run_id": value.paper_run_id,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "strategy_version": value.strategy_version,
        "position_id": value.position_id,
        "ledger_sequence": value.ledger_sequence,
        "intent_idempotency_key": value.intent_idempotency_key,
        "mint": value.mint,
        "side": value.side.value,
        "execution_state": value.execution_state.value,
        "ledger_reason_code": value.ledger_reason_code.value,
        "booked_at_unix_ms": value.booked_at_unix_ms,
        "evaluated_at_unix_ms": value.evaluated_at_unix_ms,
        "requested_notional_usd": value.requested_notional_usd,
        "explicit_cost_usd": value.explicit_cost_usd,
        "filled_notional_usd": value.filled_notional_usd,
        "filled_quantity": value.filled_quantity,
        "reference_price_usd": value.reference_price_usd,
        "execution_price_usd": value.execution_price_usd,
        "signed_slippage_usd": value.signed_slippage_usd,
        "quote_provider": value.quote_provider,
        "executed_at_unix_ms": value.executed_at_unix_ms,
    }


def _closure_to_dict(value: PaperClosedPositionEvidence) -> dict[str, object]:
    return {
        "paper_run_id": value.paper_run_id,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "strategy_version": value.strategy_version,
        "position_id": value.position_id,
        "mint": value.mint,
        "opened_at_unix_ms": value.opened_at_unix_ms,
        "closed_at_unix_ms": value.closed_at_unix_ms,
        "realized_pnl_usd": value.realized_pnl_usd,
        "accumulated_costs_usd": value.accumulated_costs_usd,
        "buy_fill_count": value.buy_fill_count,
        "sell_fill_count": value.sell_fill_count,
        "closing_ledger_sequence": value.closing_ledger_sequence,
    }


def _orphan_to_dict(value: PaperOrphanCostEvidence) -> dict[str, object]:
    return {
        "paper_run_id": value.paper_run_id,
        "candidate_version": value.candidate_version,
        "candidate_fingerprint_sha256": value.candidate_fingerprint_sha256,
        "strategy_version": value.strategy_version,
        "intent_idempotency_key": value.intent_idempotency_key,
        "mint": value.mint,
        "explicit_cost_usd": value.explicit_cost_usd,
        "evaluated_at_unix_ms": value.evaluated_at_unix_ms,
    }


def _decode_entry(value: object) -> PaperEntryProvenance:
    mapping = _require_exact_mapping("entry provenance", value, _ENTRY_FIELDS)
    try:
        regime = MarketRegime(mapping["market_regime"])
    except (TypeError, ValueError) as error:
        raise ValueError("market_regime is invalid") from error
    return PaperEntryProvenance(
        paper_run_id=mapping["paper_run_id"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        strategy_version=mapping["strategy_version"],  # type: ignore[arg-type]
        intent_idempotency_key=mapping["intent_idempotency_key"],  # type: ignore[arg-type]
        mint=mapping["mint"],  # type: ignore[arg-type]
        decision_as_of_unix_ms=mapping["decision_as_of_unix_ms"],  # type: ignore[arg-type]
        setup_name=mapping["setup_name"],  # type: ignore[arg-type]
        market_regime=regime,
        score_policy_version=mapping["score_policy_version"],  # type: ignore[arg-type]
        decision_policy_version=mapping["decision_policy_version"],  # type: ignore[arg-type]
        paper_execution_policy_version=mapping["paper_execution_policy_version"],  # type: ignore[arg-type]
    )


def _decode_execution(value: object) -> PaperPositionExecutionEvidence:
    mapping = _require_exact_mapping("execution evidence", value, _EXECUTION_FIELDS)
    try:
        side = TradeSide(mapping["side"])
        execution_state = PaperExecutionState(mapping["execution_state"])
        ledger_reason = PaperLedgerReasonCode(mapping["ledger_reason_code"])
    except (TypeError, ValueError) as error:
        raise ValueError("execution enum value is invalid") from error
    return PaperPositionExecutionEvidence(
        paper_run_id=mapping["paper_run_id"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        strategy_version=mapping["strategy_version"],  # type: ignore[arg-type]
        position_id=mapping["position_id"],  # type: ignore[arg-type]
        ledger_sequence=mapping["ledger_sequence"],  # type: ignore[arg-type]
        intent_idempotency_key=mapping["intent_idempotency_key"],  # type: ignore[arg-type]
        mint=mapping["mint"],  # type: ignore[arg-type]
        side=side,
        execution_state=execution_state,
        ledger_reason_code=ledger_reason,
        booked_at_unix_ms=mapping["booked_at_unix_ms"],  # type: ignore[arg-type]
        evaluated_at_unix_ms=mapping["evaluated_at_unix_ms"],  # type: ignore[arg-type]
        requested_notional_usd=mapping["requested_notional_usd"],  # type: ignore[arg-type]
        explicit_cost_usd=mapping["explicit_cost_usd"],  # type: ignore[arg-type]
        filled_notional_usd=mapping["filled_notional_usd"],  # type: ignore[arg-type]
        filled_quantity=mapping["filled_quantity"],  # type: ignore[arg-type]
        reference_price_usd=mapping["reference_price_usd"],  # type: ignore[arg-type]
        execution_price_usd=mapping["execution_price_usd"],  # type: ignore[arg-type]
        signed_slippage_usd=mapping["signed_slippage_usd"],  # type: ignore[arg-type]
        quote_provider=mapping["quote_provider"],  # type: ignore[arg-type]
        executed_at_unix_ms=mapping["executed_at_unix_ms"],  # type: ignore[arg-type]
    )


def _decode_closure(value: object) -> PaperClosedPositionEvidence:
    mapping = _require_exact_mapping("closure evidence", value, _CLOSURE_FIELDS)
    return PaperClosedPositionEvidence(
        paper_run_id=mapping["paper_run_id"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        strategy_version=mapping["strategy_version"],  # type: ignore[arg-type]
        position_id=mapping["position_id"],  # type: ignore[arg-type]
        mint=mapping["mint"],  # type: ignore[arg-type]
        opened_at_unix_ms=mapping["opened_at_unix_ms"],  # type: ignore[arg-type]
        closed_at_unix_ms=mapping["closed_at_unix_ms"],  # type: ignore[arg-type]
        realized_pnl_usd=mapping["realized_pnl_usd"],  # type: ignore[arg-type]
        accumulated_costs_usd=mapping["accumulated_costs_usd"],  # type: ignore[arg-type]
        buy_fill_count=mapping["buy_fill_count"],  # type: ignore[arg-type]
        sell_fill_count=mapping["sell_fill_count"],  # type: ignore[arg-type]
        closing_ledger_sequence=mapping["closing_ledger_sequence"],  # type: ignore[arg-type]
    )


def _decode_orphan(value: object) -> PaperOrphanCostEvidence:
    mapping = _require_exact_mapping("orphan cost evidence", value, _ORPHAN_FIELDS)
    return PaperOrphanCostEvidence(
        paper_run_id=mapping["paper_run_id"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        strategy_version=mapping["strategy_version"],  # type: ignore[arg-type]
        intent_idempotency_key=mapping["intent_idempotency_key"],  # type: ignore[arg-type]
        mint=mapping["mint"],  # type: ignore[arg-type]
        explicit_cost_usd=mapping["explicit_cost_usd"],  # type: ignore[arg-type]
        evaluated_at_unix_ms=mapping["evaluated_at_unix_ms"],  # type: ignore[arg-type]
    )


def _decode_collection(name: str, value: object, decoder) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return tuple(decoder(item) for item in value)


def _require_exact_mapping(
    name: str,
    value: object,
    expected_fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    if frozenset(value) != expected_fields or len(value) != len(expected_fields):
        raise ValueError(f"{name} fields must match the sealed schema exactly")
    return value


def _require_exact_tuple(name: str, value: object, expected_type: type) -> None:
    if not isinstance(value, tuple) or any(type(item) is not expected_type for item in value):
        raise ValueError(f"{name} must be a tuple of exact {expected_type.__name__} values")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
