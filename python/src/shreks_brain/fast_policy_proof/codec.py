from __future__ import annotations

import json

from shreks_brain.evaluation.codec import (
    build_evidence_document,
    decode_evidence_document,
)

from .engine import (
    _report_material,
    _sha256_canonical,
    fast_policy_run_evidence_fingerprint_sha256,
)
from .models import (
    FAST_POLICY_PROOF_SCHEMA_NAME,
    FAST_POLICY_PROOF_SCHEMA_VERSION,
    FastPolicyProofDecision,
    FastPolicyProofGateCode,
    FastPolicyProofGateResult,
    FastPolicyProofGateStatus,
    FastPolicyRunEvidence,
    FastPolicySuperiorityReport,
)


FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_NAME = (
    "shreks.fast_policy_run_evidence_batch"
)
FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_VERSION = 1

_RUN_BATCH_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "runs",
        "batch_fingerprint_sha256",
    }
)
_RUN_FIELDS = frozenset(
    {
        "schema_name",
        "schema_version",
        "paper_run_id",
        "candidate_version",
        "candidate_fingerprint_sha256",
        "strategy_version",
        "trading_evaluation",
        "event_population_fingerprint_sha256",
        "action_journal_fingerprint_sha256",
        "material_update_count",
        "decision_count",
        "distinct_market_count",
        "observed_from_unix_ms",
        "observed_through_unix_ms",
        "run_evidence_fingerprint_sha256",
    }
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


def encode_fast_policy_run_evidence_batch(
    runs: tuple[FastPolicyRunEvidence, ...],
) -> str:
    if (
        not isinstance(runs, tuple)
        or not runs
        or not all(type(value) is FastPolicyRunEvidence for value in runs)
    ):
        raise ValueError(
            "runs must be a non-empty tuple of exact FastPolicyRunEvidence values"
        )
    versions = tuple(value.candidate_version for value in runs)
    if versions != tuple(sorted(versions)):
        raise ValueError("run candidate versions must be in lexical order")
    if len(versions) != len(set(versions)):
        raise ValueError("run candidate versions must be unique")

    run_documents = [_run_evidence_document(value) for value in runs]
    material = {
        "schema_name": FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_NAME,
        "schema_version": FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_VERSION,
        "runs": run_documents,
    }
    document = {
        **material,
        "batch_fingerprint_sha256": _sha256_canonical(material),
    }
    return _canonical_json(document)


def decode_fast_policy_run_evidence_batch(
    payload: str,
) -> tuple[FastPolicyRunEvidence, ...]:
    if not isinstance(payload, str) or not payload:
        raise ValueError("payload must be a non-empty JSON string")
    try:
        document = json.loads(payload, parse_constant=_reject_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed Fast policy run evidence JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("Fast policy run evidence document must be a JSON object")
    if frozenset(document) != _RUN_BATCH_FIELDS:
        raise ValueError(
            "Fast policy run evidence document has unknown or missing fields"
        )
    if payload != _canonical_json(document):
        raise ValueError("Fast policy run evidence JSON must be canonical")
    if document["schema_name"] != FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_NAME:
        raise ValueError("Fast policy run evidence batch schema name is incompatible")
    if document["schema_version"] != FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_VERSION:
        raise ValueError(
            "Fast policy run evidence batch schema version is incompatible"
        )

    raw_runs = document["runs"]
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("Fast policy run evidence runs must be a non-empty JSON array")
    runs = tuple(_run_evidence_from_document(value) for value in raw_runs)

    versions = tuple(value.candidate_version for value in runs)
    if versions != tuple(sorted(versions)):
        raise ValueError("run candidate versions must be in lexical order")
    if len(versions) != len(set(versions)):
        raise ValueError("run candidate versions must be unique")

    material = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "runs": raw_runs,
    }
    expected = _sha256_canonical(material)
    if document["batch_fingerprint_sha256"] != expected:
        raise ValueError("run evidence batch fingerprint is invalid or tampered")
    return runs


def _run_evidence_document(
    run: FastPolicyRunEvidence,
) -> dict[str, object]:
    expected = fast_policy_run_evidence_fingerprint_sha256(run)
    if run.run_evidence_fingerprint_sha256 != expected:
        raise ValueError("run evidence fingerprint does not match run material")
    return {
        "schema_name": run.schema_name,
        "schema_version": run.schema_version,
        "paper_run_id": run.paper_run_id,
        "candidate_version": run.candidate_version,
        "candidate_fingerprint_sha256": run.candidate_fingerprint_sha256,
        "strategy_version": run.strategy_version,
        "trading_evaluation": build_evidence_document(
            (run.trading_evaluation,)
        ),
        "event_population_fingerprint_sha256": (
            run.event_population_fingerprint_sha256
        ),
        "action_journal_fingerprint_sha256": (
            run.action_journal_fingerprint_sha256
        ),
        "material_update_count": run.material_update_count,
        "decision_count": run.decision_count,
        "distinct_market_count": run.distinct_market_count,
        "observed_from_unix_ms": run.observed_from_unix_ms,
        "observed_through_unix_ms": run.observed_through_unix_ms,
        "run_evidence_fingerprint_sha256": (
            run.run_evidence_fingerprint_sha256
        ),
    }


def _run_evidence_from_document(
    value: object,
) -> FastPolicyRunEvidence:
    if not isinstance(value, dict) or frozenset(value) != _RUN_FIELDS:
        raise ValueError("run evidence has unknown or missing fields")
    evaluations = decode_evidence_document(value["trading_evaluation"])
    if len(evaluations) != 1:
        raise ValueError(
            "run evidence must carry exactly one trading evaluation"
        )
    evaluation = evaluations[0]
    if evaluation.candidate_version != value["candidate_version"]:
        raise ValueError(
            "run evidence candidate version contradicts trading evaluation"
        )
    try:
        run = FastPolicyRunEvidence(
            schema_name=value["schema_name"],
            schema_version=value["schema_version"],
            paper_run_id=value["paper_run_id"],
            candidate_version=value["candidate_version"],
            candidate_fingerprint_sha256=value[
                "candidate_fingerprint_sha256"
            ],
            strategy_version=value["strategy_version"],
            trading_evaluation=evaluation,
            event_population_fingerprint_sha256=value[
                "event_population_fingerprint_sha256"
            ],
            action_journal_fingerprint_sha256=value[
                "action_journal_fingerprint_sha256"
            ],
            material_update_count=value["material_update_count"],
            decision_count=value["decision_count"],
            distinct_market_count=value["distinct_market_count"],
            observed_from_unix_ms=value["observed_from_unix_ms"],
            observed_through_unix_ms=value["observed_through_unix_ms"],
            run_evidence_fingerprint_sha256=value[
                "run_evidence_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("run evidence content is incompatible") from exc
    expected = fast_policy_run_evidence_fingerprint_sha256(run)
    if run.run_evidence_fingerprint_sha256 != expected:
        raise ValueError("run evidence fingerprint is invalid or tampered")
    return run


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
