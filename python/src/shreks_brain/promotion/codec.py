from __future__ import annotations

from dataclasses import fields
from typing import Mapping

from .fingerprint import sha256_canonical
from .models import (
    PROMOTION_SCHEMA_VERSION,
    PromotionAssessment,
    PromotionDecision,
    PromotionGateCode,
    PromotionGateResult,
    PromotionGateStatus,
)


_DOCUMENT_FIELDS = frozenset(("schema_version", "assessments"))
_ASSESSMENT_FIELDS = frozenset(field.name for field in fields(PromotionAssessment))
_GATE_FIELDS = frozenset(field.name for field in fields(PromotionGateResult))


def assessment_to_dict(assessment: PromotionAssessment) -> dict[str, object]:
    return {
        "schema_version": assessment.schema_version,
        "policy_version": assessment.policy_version,
        "candidate_version": assessment.candidate_version,
        "candidate_fingerprint_sha256": assessment.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": assessment.registry_fingerprint_sha256,
        "evaluation_fingerprint_sha256": assessment.evaluation_fingerprint_sha256,
        "trade_evidence_fingerprint_sha256": assessment.trade_evidence_fingerprint_sha256,
        "shadow_ledger_fingerprint_sha256": assessment.shadow_ledger_fingerprint_sha256,
        "baseline_evaluation_identities": [
            [version, fingerprint]
            for version, fingerprint in assessment.baseline_evaluation_identities
        ],
        "evaluated_at_unix_ms": assessment.evaluated_at_unix_ms,
        "gates": [gate_to_dict(gate) for gate in assessment.gates],
        "decision": assessment.decision.value,
        "assessment_fingerprint_sha256": assessment.assessment_fingerprint_sha256,
    }


def gate_to_dict(gate: PromotionGateResult) -> dict[str, object]:
    return {
        "code": gate.code.value,
        "status": gate.status.value,
        "observed_value": gate.observed_value,
        "threshold_value": gate.threshold_value,
        "message": gate.message,
    }


def assessments_document(
    assessments: tuple[PromotionAssessment, ...],
) -> dict[str, object]:
    ordered = tuple(sorted(assessments, key=assessment_sort_key))
    return {
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "assessments": [assessment_to_dict(value) for value in ordered],
    }


def decode_assessments_document(document: object) -> tuple[PromotionAssessment, ...]:
    mapping = _require_exact_mapping("promotion document", document, _DOCUMENT_FIELDS)
    if mapping["schema_version"] != PROMOTION_SCHEMA_VERSION:
        raise ValueError("promotion document schema_version must equal e8-promotion-v1")
    raw_assessments = mapping["assessments"]
    if not isinstance(raw_assessments, list):
        raise ValueError("promotion document assessments must be a list")
    assessments = tuple(_decode_assessment(value) for value in raw_assessments)
    if assessments != tuple(sorted(assessments, key=assessment_sort_key)):
        raise ValueError("promotion assessments must be in canonical order")
    identities = tuple(assessment_identity(value) for value in assessments)
    if len(identities) != len(set(identities)):
        raise ValueError("promotion assessment identities must be unique")
    return assessments


def compute_assessment_fingerprint(assessment: PromotionAssessment) -> str:
    return sha256_canonical(_assessment_material(assessment))


def assessment_identity(assessment: PromotionAssessment) -> tuple[str, str, int]:
    return (
        assessment.candidate_version,
        assessment.policy_version,
        assessment.evaluated_at_unix_ms,
    )


def assessment_sort_key(assessment: PromotionAssessment) -> tuple[int, str, str, str]:
    return (
        assessment.evaluated_at_unix_ms,
        assessment.candidate_version,
        assessment.policy_version,
        assessment.assessment_fingerprint_sha256,
    )


def _decode_assessment(value: object) -> PromotionAssessment:
    mapping = _require_exact_mapping("assessment", value, _ASSESSMENT_FIELDS)
    try:
        decision = PromotionDecision(mapping["decision"])
    except (TypeError, ValueError) as error:
        raise ValueError("assessment contains an unsupported enum value") from error

    raw_baselines = mapping["baseline_evaluation_identities"]
    if not isinstance(raw_baselines, list):
        raise ValueError("baseline_evaluation_identities must be a list")
    baselines: list[tuple[object, object]] = []
    for identity in raw_baselines:
        if not isinstance(identity, list) or len(identity) != 2:
            raise ValueError("baseline evaluation identity must be a two-item list")
        baselines.append((identity[0], identity[1]))

    raw_gates = mapping["gates"]
    if not isinstance(raw_gates, list):
        raise ValueError("assessment gates must be a list")
    gates = tuple(_decode_gate(gate) for gate in raw_gates)

    assessment = PromotionAssessment(
        schema_version=mapping["schema_version"],  # type: ignore[arg-type]
        policy_version=mapping["policy_version"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        registry_fingerprint_sha256=mapping["registry_fingerprint_sha256"],  # type: ignore[arg-type]
        evaluation_fingerprint_sha256=mapping["evaluation_fingerprint_sha256"],  # type: ignore[arg-type]
        trade_evidence_fingerprint_sha256=mapping["trade_evidence_fingerprint_sha256"],  # type: ignore[arg-type]
        shadow_ledger_fingerprint_sha256=mapping["shadow_ledger_fingerprint_sha256"],  # type: ignore[arg-type]
        baseline_evaluation_identities=tuple(baselines),  # type: ignore[arg-type]
        evaluated_at_unix_ms=mapping["evaluated_at_unix_ms"],  # type: ignore[arg-type]
        gates=gates,
        decision=decision,
        assessment_fingerprint_sha256=mapping["assessment_fingerprint_sha256"],  # type: ignore[arg-type]
    )
    expected = compute_assessment_fingerprint(assessment)
    if assessment.assessment_fingerprint_sha256 != expected:
        raise ValueError("assessment fingerprint does not match assessment content")
    return assessment


def _decode_gate(value: object) -> PromotionGateResult:
    mapping = _require_exact_mapping("promotion gate", value, _GATE_FIELDS)
    try:
        code = PromotionGateCode(mapping["code"])
        status = PromotionGateStatus(mapping["status"])
    except (TypeError, ValueError) as error:
        raise ValueError("promotion gate contains an unsupported enum value") from error
    return PromotionGateResult(
        code=code,
        status=status,
        observed_value=mapping["observed_value"],  # type: ignore[arg-type]
        threshold_value=mapping["threshold_value"],  # type: ignore[arg-type]
        message=mapping["message"],  # type: ignore[arg-type]
    )


def _assessment_material(assessment: PromotionAssessment) -> dict[str, object]:
    return {
        "schema_version": assessment.schema_version,
        "policy_version": assessment.policy_version,
        "candidate_version": assessment.candidate_version,
        "candidate_fingerprint_sha256": assessment.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": assessment.registry_fingerprint_sha256,
        "evaluation_fingerprint_sha256": assessment.evaluation_fingerprint_sha256,
        "trade_evidence_fingerprint_sha256": assessment.trade_evidence_fingerprint_sha256,
        "shadow_ledger_fingerprint_sha256": assessment.shadow_ledger_fingerprint_sha256,
        "baseline_evaluation_identities": assessment.baseline_evaluation_identities,
        "evaluated_at_unix_ms": assessment.evaluated_at_unix_ms,
        "gates": tuple(
            {
                "code": gate.code,
                "status": gate.status,
                "observed_value": gate.observed_value,
                "threshold_value": gate.threshold_value,
                "message": gate.message,
            }
            for gate in assessment.gates
        ),
        "decision": assessment.decision,
    }


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
