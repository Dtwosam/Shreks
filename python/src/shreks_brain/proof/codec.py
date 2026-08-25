from __future__ import annotations

from dataclasses import asdict, fields
import json
from typing import Mapping

from .fingerprint import sha256_canonical
from .models import (
    PAPER_PROOF_SCHEMA_VERSION,
    CandidateProofAssessment,
    PaperProofDecision,
    PaperProofGateCode,
    PaperProofGateResult,
    PaperProofGateStatus,
)


_DOCUMENT_FIELDS = frozenset(("schema_version", "assessments"))
_ASSESSMENT_FIELDS = frozenset(field.name for field in fields(CandidateProofAssessment))
_GATE_FIELDS = frozenset(field.name for field in fields(PaperProofGateResult))


def gate_to_dict(gate: PaperProofGateResult) -> dict[str, object]:
    return {
        "code": gate.code.value,
        "status": gate.status.value,
        "observed_value": gate.observed_value,
        "threshold_value": gate.threshold_value,
        "message": gate.message,
    }


def assessment_to_dict(assessment: CandidateProofAssessment) -> dict[str, object]:
    return {
        "schema_version": assessment.schema_version,
        "policy_version": assessment.policy_version,
        "candidate_version": assessment.candidate_version,
        "candidate_fingerprint_sha256": assessment.candidate_fingerprint_sha256,
        "registry_fingerprint_sha256": assessment.registry_fingerprint_sha256,
        "e8_assessment_fingerprint_sha256": assessment.e8_assessment_fingerprint_sha256,
        "paper_run_id": assessment.paper_run_id,
        "paper_ledger_fingerprint_sha256": assessment.paper_ledger_fingerprint_sha256,
        "paper_evaluation_fingerprint_sha256": assessment.paper_evaluation_fingerprint_sha256,
        "paper_trade_evidence_fingerprint_sha256": assessment.paper_trade_evidence_fingerprint_sha256,
        "evaluated_at_unix_ms": assessment.evaluated_at_unix_ms,
        "gates": [gate_to_dict(gate) for gate in assessment.gates],
        "decision": assessment.decision.value,
        "assessment_fingerprint_sha256": assessment.assessment_fingerprint_sha256,
    }


def assessments_document(
    assessments: tuple[CandidateProofAssessment, ...],
) -> dict[str, object]:
    ordered = tuple(sorted(assessments, key=assessment_sort_key))
    return {
        "schema_version": PAPER_PROOF_SCHEMA_VERSION,
        "assessments": [assessment_to_dict(value) for value in ordered],
    }


def encode_assessments(assessments: tuple[CandidateProofAssessment, ...]) -> str:
    try:
        return json.dumps(
            assessments_document(assessments),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ValueError(f"proof assessments are not canonical JSON: {error}") from error


def decode_assessments_document(
    document: object,
) -> tuple[CandidateProofAssessment, ...]:
    mapping = _require_exact_mapping("proof document", document, _DOCUMENT_FIELDS)
    if mapping["schema_version"] != PAPER_PROOF_SCHEMA_VERSION:
        raise ValueError(
            "proof document schema_version must equal e12-paper-proof-v1"
        )
    raw_assessments = mapping["assessments"]
    if not isinstance(raw_assessments, list):
        raise ValueError("proof document assessments must be a list")
    assessments = tuple(_decode_assessment(value) for value in raw_assessments)
    if assessments != tuple(sorted(assessments, key=assessment_sort_key)):
        raise ValueError("proof assessments must be in canonical order")
    identities = tuple(assessment_identity(value) for value in assessments)
    if len(identities) != len(set(identities)):
        raise ValueError("proof assessment identities must be unique")
    return assessments


def compute_assessment_fingerprint(assessment: CandidateProofAssessment) -> str:
    material = asdict(assessment)
    material["assessment_fingerprint_sha256"] = "0" * 64
    return sha256_canonical(material)


def assessment_identity(
    assessment: CandidateProofAssessment,
) -> tuple[str, str, str, int]:
    return (
        assessment.candidate_version,
        assessment.policy_version,
        assessment.paper_run_id,
        assessment.evaluated_at_unix_ms,
    )


def assessment_sort_key(
    assessment: CandidateProofAssessment,
) -> tuple[int, str, str, str, str]:
    return (
        assessment.evaluated_at_unix_ms,
        assessment.candidate_version,
        assessment.policy_version,
        assessment.paper_run_id,
        assessment.assessment_fingerprint_sha256,
    )


def _decode_assessment(value: object) -> CandidateProofAssessment:
    mapping = _require_exact_mapping("proof assessment", value, _ASSESSMENT_FIELDS)
    try:
        decision = PaperProofDecision(mapping["decision"])
    except (TypeError, ValueError) as error:
        raise ValueError("proof assessment contains an unsupported enum value") from error

    raw_gates = mapping["gates"]
    if not isinstance(raw_gates, list):
        raise ValueError("proof assessment gates must be a list")
    gates = tuple(_decode_gate(value) for value in raw_gates)

    assessment = CandidateProofAssessment(
        schema_version=mapping["schema_version"],  # type: ignore[arg-type]
        policy_version=mapping["policy_version"],  # type: ignore[arg-type]
        candidate_version=mapping["candidate_version"],  # type: ignore[arg-type]
        candidate_fingerprint_sha256=mapping["candidate_fingerprint_sha256"],  # type: ignore[arg-type]
        registry_fingerprint_sha256=mapping["registry_fingerprint_sha256"],  # type: ignore[arg-type]
        e8_assessment_fingerprint_sha256=mapping["e8_assessment_fingerprint_sha256"],  # type: ignore[arg-type]
        paper_run_id=mapping["paper_run_id"],  # type: ignore[arg-type]
        paper_ledger_fingerprint_sha256=mapping["paper_ledger_fingerprint_sha256"],  # type: ignore[arg-type]
        paper_evaluation_fingerprint_sha256=mapping["paper_evaluation_fingerprint_sha256"],  # type: ignore[arg-type]
        paper_trade_evidence_fingerprint_sha256=mapping["paper_trade_evidence_fingerprint_sha256"],  # type: ignore[arg-type]
        evaluated_at_unix_ms=mapping["evaluated_at_unix_ms"],  # type: ignore[arg-type]
        gates=gates,
        decision=decision,
        assessment_fingerprint_sha256=mapping["assessment_fingerprint_sha256"],  # type: ignore[arg-type]
    )
    expected = compute_assessment_fingerprint(assessment)
    if assessment.assessment_fingerprint_sha256 != expected:
        raise ValueError("proof assessment fingerprint does not match assessment content")
    return assessment


def _decode_gate(value: object) -> PaperProofGateResult:
    mapping = _require_exact_mapping("proof gate", value, _GATE_FIELDS)
    try:
        code = PaperProofGateCode(mapping["code"])
        status = PaperProofGateStatus(mapping["status"])
    except (TypeError, ValueError) as error:
        raise ValueError("proof gate contains an unsupported enum value") from error
    return PaperProofGateResult(
        code=code,
        status=status,
        observed_value=mapping["observed_value"],  # type: ignore[arg-type]
        threshold_value=mapping["threshold_value"],  # type: ignore[arg-type]
        message=mapping["message"],  # type: ignore[arg-type]
    )


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
