from __future__ import annotations

import json

from .engine import _report_material, _sha256_canonical
from .models import (
    FAST_POLICY_PROOF_SCHEMA_NAME,
    FAST_POLICY_PROOF_SCHEMA_VERSION,
    FastPolicyProofDecision,
    FastPolicyProofGateCode,
    FastPolicyProofGateResult,
    FastPolicyProofGateStatus,
    FastPolicySuperiorityReport,
)


_REPORT_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "policy_version",
        "candidate_version",
        "candidate_fingerprint_sha256",
        "candidate_run_evidence_fingerprint_sha256",
        "candidate_evaluation_fingerprint_sha256",
        "event_population_fingerprint_sha256",
        "baseline_evaluation_identities",
        "best_baseline_version",
        "best_baseline_evaluation_fingerprint_sha256",
        "candidate_net_expectancy_pct",
        "best_baseline_net_expectancy_pct",
        "expectancy_advantage_pct",
        "gates",
        "decision",
        "report_fingerprint_sha256",
    }
)
_GATE_FIELDS = frozenset(
    {"code", "status", "observed_value", "threshold_value", "message"}
)


def encode_fast_policy_superiority_report(
    report: FastPolicySuperiorityReport,
) -> str:
    if type(report) is not FastPolicySuperiorityReport:
        raise ValueError("report must be an exact FastPolicySuperiorityReport")
    expected = _sha256_canonical(_report_material(report))
    if report.report_fingerprint_sha256 != expected:
        raise ValueError("report fingerprint does not match report material")
    document = {
        **_report_material(report),
        "report_fingerprint_sha256": report.report_fingerprint_sha256,
    }
    return _canonical_json(document)


def decode_fast_policy_superiority_report(
    payload: str,
) -> FastPolicySuperiorityReport:
    if not isinstance(payload, str) or not payload:
        raise ValueError("payload must be a non-empty JSON string")
    try:
        document = json.loads(payload, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed Fast policy superiority JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("Fast policy superiority document must be a JSON object")
    if frozenset(document) != _REPORT_FIELDS:
        raise ValueError("Fast policy superiority document has unknown or missing fields")
    canonical = _canonical_json(document)
    if payload != canonical:
        raise ValueError("Fast policy superiority JSON must be canonical")

    gates_raw = document["gates"]
    if not isinstance(gates_raw, list):
        raise ValueError("gates must be a JSON array")
    gates = []
    for raw in gates_raw:
        if not isinstance(raw, dict) or frozenset(raw) != _GATE_FIELDS:
            raise ValueError("gate has unknown or missing fields")
        try:
            code = FastPolicyProofGateCode(raw["code"])
            status = FastPolicyProofGateStatus(raw["status"])
        except (TypeError, ValueError) as exc:
            raise ValueError("gate enum value is invalid") from exc
        gates.append(
            FastPolicyProofGateResult(
                code=code,
                status=status,
                observed_value=raw["observed_value"],
                threshold_value=raw["threshold_value"],
                message=raw["message"],
            )
        )

    baseline_raw = document["baseline_evaluation_identities"]
    if not isinstance(baseline_raw, list):
        raise ValueError("baseline_evaluation_identities must be a JSON array")
    baseline_identities = []
    for value in baseline_raw:
        if (
            not isinstance(value, list)
            or len(value) != 3
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError("baseline identity must be a three-string JSON array")
        baseline_identities.append(tuple(value))

    try:
        decision = FastPolicyProofDecision(document["decision"])
    except (TypeError, ValueError) as exc:
        raise ValueError("proof decision is invalid") from exc

    report = FastPolicySuperiorityReport(
        schema_name=document["schema_name"],
        schema_version=document["schema_version"],
        policy_version=document["policy_version"],
        candidate_version=document["candidate_version"],
        candidate_fingerprint_sha256=document["candidate_fingerprint_sha256"],
        candidate_run_evidence_fingerprint_sha256=document[
            "candidate_run_evidence_fingerprint_sha256"
        ],
        candidate_evaluation_fingerprint_sha256=document[
            "candidate_evaluation_fingerprint_sha256"
        ],
        event_population_fingerprint_sha256=document[
            "event_population_fingerprint_sha256"
        ],
        baseline_evaluation_identities=tuple(baseline_identities),
        best_baseline_version=document["best_baseline_version"],
        best_baseline_evaluation_fingerprint_sha256=document[
            "best_baseline_evaluation_fingerprint_sha256"
        ],
        candidate_net_expectancy_pct=document["candidate_net_expectancy_pct"],
        best_baseline_net_expectancy_pct=document[
            "best_baseline_net_expectancy_pct"
        ],
        expectancy_advantage_pct=document["expectancy_advantage_pct"],
        gates=tuple(gates),
        decision=decision,
        report_fingerprint_sha256=document["report_fingerprint_sha256"],
    )
    expected = _sha256_canonical(_report_material(report))
    if report.report_fingerprint_sha256 != expected:
        raise ValueError("report fingerprint does not match report material")
    return report


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")
