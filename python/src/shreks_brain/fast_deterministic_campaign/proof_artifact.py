from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_policy_proof import (
    FastPolicyProofDecision,
    FastPolicyRunEvidence,
    FastPolicySuperiorityPolicy,
    FastPolicySuperiorityReport,
    decode_fast_policy_run_evidence_batch,
    decode_fast_policy_superiority_policy,
    decode_fast_policy_superiority_report,
    encode_fast_policy_run_evidence_batch,
    encode_fast_policy_superiority_policy,
    encode_fast_policy_superiority_report,
    evaluate_fast_policy_superiority,
    fast_policy_run_evidence_fingerprint_sha256,
    fast_policy_superiority_policy_fingerprint_sha256,
)

from .artifact import read_fast_deterministic_campaign_artifact
from .invocation import read_fast_deterministic_campaign_invocation_seal


FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME = (
    "shreks.fast_policy_comparison_artifact"
)
FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION = 1

_LEARNED_RUN_FILE = "learned_run.json"
_POLICY_FILE = "superiority_policy.json"
_REPORT_FILE = "superiority_report.json"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset(
    {
        _LEARNED_RUN_FILE,
        _POLICY_FILE,
        _REPORT_FILE,
        _MANIFEST_FILE,
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "baseline_invocation_directory_name",
        "baseline_invocation_fingerprint_sha256",
        "baseline_request_fingerprint_sha256",
        "baseline_campaign_artifact_fingerprint_sha256",
        "baseline_catalog_fingerprint_sha256",
        "baseline_run_batch_fingerprint_sha256",
        "baseline_run_count",
        "baseline_event_population_fingerprint_sha256",
        "learned_candidate_version",
        "learned_candidate_fingerprint_sha256",
        "learned_run_evidence_fingerprint_sha256",
        "learned_run_batch_fingerprint_sha256",
        "learned_event_population_fingerprint_sha256",
        "superiority_policy_version",
        "superiority_policy_fingerprint_sha256",
        "superiority_report_fingerprint_sha256",
        "decision",
        "learned_run_file_sha256",
        "superiority_policy_file_sha256",
        "superiority_report_file_sha256",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastPolicyComparisonArtifactManifest:
    schema_name: str
    schema_version: int
    baseline_invocation_directory_name: str
    baseline_invocation_fingerprint_sha256: str
    baseline_request_fingerprint_sha256: str
    baseline_campaign_artifact_fingerprint_sha256: str
    baseline_catalog_fingerprint_sha256: str
    baseline_run_batch_fingerprint_sha256: str
    baseline_run_count: int
    baseline_event_population_fingerprint_sha256: str
    learned_candidate_version: str
    learned_candidate_fingerprint_sha256: str
    learned_run_evidence_fingerprint_sha256: str
    learned_run_batch_fingerprint_sha256: str
    learned_event_population_fingerprint_sha256: str
    superiority_policy_version: str
    superiority_policy_fingerprint_sha256: str
    superiority_report_fingerprint_sha256: str
    decision: str
    learned_run_file_sha256: str
    superiority_policy_file_sha256: str
    superiority_report_file_sha256: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME:
            raise ValueError(
                "unsupported Fast policy comparison artifact schema_name"
            )
        if self.schema_version != FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported Fast policy comparison artifact schema_version"
            )
        _require_leaf_name(
            "baseline_invocation_directory_name",
            self.baseline_invocation_directory_name,
        )
        if self.baseline_run_count != 8:
            raise ValueError(
                "Fast policy comparison artifact requires exactly eight baselines"
            )
        for name in (
            "learned_candidate_version",
            "superiority_policy_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        try:
            FastPolicyProofDecision(self.decision)
        except ValueError as exc:
            raise ValueError(
                "Fast policy comparison decision is invalid"
            ) from exc
        for name in (
            "baseline_invocation_fingerprint_sha256",
            "baseline_request_fingerprint_sha256",
            "baseline_campaign_artifact_fingerprint_sha256",
            "baseline_catalog_fingerprint_sha256",
            "baseline_run_batch_fingerprint_sha256",
            "baseline_event_population_fingerprint_sha256",
            "learned_candidate_fingerprint_sha256",
            "learned_run_evidence_fingerprint_sha256",
            "learned_run_batch_fingerprint_sha256",
            "learned_event_population_fingerprint_sha256",
            "superiority_policy_fingerprint_sha256",
            "superiority_report_fingerprint_sha256",
            "learned_run_file_sha256",
            "superiority_policy_file_sha256",
            "superiority_report_file_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class FastPolicyComparisonArtifact:
    path: Path
    manifest: FastPolicyComparisonArtifactManifest
    baseline_runs: tuple[FastPolicyRunEvidence, ...]
    learned_run: FastPolicyRunEvidence
    superiority_policy: FastPolicySuperiorityPolicy
    superiority_report: FastPolicySuperiorityReport

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path-like")
        if type(self.manifest) is not FastPolicyComparisonArtifactManifest:
            raise ValueError(
                "manifest must be exact FastPolicyComparisonArtifactManifest"
            )
        if (
            not isinstance(self.baseline_runs, tuple)
            or len(self.baseline_runs) != 8
            or not all(
                type(value) is FastPolicyRunEvidence
                for value in self.baseline_runs
            )
        ):
            raise ValueError(
                "baseline_runs must contain exactly eight FastPolicyRunEvidence values"
            )
        if type(self.learned_run) is not FastPolicyRunEvidence:
            raise ValueError(
                "learned_run must be exact FastPolicyRunEvidence"
            )
        if type(self.superiority_policy) is not FastPolicySuperiorityPolicy:
            raise ValueError(
                "superiority_policy must be exact FastPolicySuperiorityPolicy"
            )
        if type(self.superiority_report) is not FastPolicySuperiorityReport:
            raise ValueError(
                "superiority_report must be exact FastPolicySuperiorityReport"
            )


def write_fast_policy_comparison_artifact(
    *,
    baseline_invocation_path: str | Path,
    learned_run: FastPolicyRunEvidence,
    superiority_policy: FastPolicySuperiorityPolicy,
    destination: str | Path,
) -> FastPolicyComparisonArtifactManifest:
    if type(learned_run) is not FastPolicyRunEvidence:
        raise ValueError(
            "learned_run must be exact FastPolicyRunEvidence"
        )
    if type(superiority_policy) is not FastPolicySuperiorityPolicy:
        raise ValueError(
            "superiority_policy must be exact FastPolicySuperiorityPolicy"
        )
    expected_learned = fast_policy_run_evidence_fingerprint_sha256(
        learned_run
    )
    if (
        expected_learned
        != learned_run.run_evidence_fingerprint_sha256
    ):
        raise ValueError(
            "learned Fast policy run evidence fingerprint mismatch"
        )

    invocation_path = Path(
        baseline_invocation_path
    ).expanduser().resolve()
    invocation = read_fast_deterministic_campaign_invocation_seal(
        invocation_path
    )

    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists():
        raise FileExistsError(
            "Fast policy comparison artifact destination already exists"
        )
    if destination_path.parent != invocation_path.parent:
        raise ValueError(
            "Fast policy comparison artifact must be a sibling of the baseline invocation"
        )

    campaign_path = (
        invocation_path.parent
        / invocation.manifest.campaign_directory_name
    )
    campaign = read_fast_deterministic_campaign_artifact(
        campaign_path
    )
    _validate_baseline_chain(
        invocation=invocation,
        campaign=campaign,
        policy=superiority_policy,
    )

    report = evaluate_fast_policy_superiority(
        learned_run,
        campaign.runs,
        superiority_policy,
    )

    learned_payload = encode_fast_policy_run_evidence_batch(
        (learned_run,)
    )
    learned_document = _load_canonical(
        learned_payload,
        label="learned Fast policy run batch",
    )
    learned_batch_fingerprint = learned_document.get(
        "batch_fingerprint_sha256"
    )
    _require_sha256(
        "learned_run_batch_fingerprint_sha256",
        learned_batch_fingerprint,
    )

    policy_payload = encode_fast_policy_superiority_policy(
        superiority_policy
    )
    policy_document = _load_canonical(
        policy_payload,
        label="Fast policy superiority policy",
    )
    policy_fingerprint = policy_document.get(
        "policy_fingerprint_sha256"
    )
    _require_sha256(
        "superiority_policy_fingerprint_sha256",
        policy_fingerprint,
    )

    report_payload = encode_fast_policy_superiority_report(report)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}-",
            dir=destination_path.parent,
        )
    )
    try:
        learned_path = staging_path / _LEARNED_RUN_FILE
        policy_path = staging_path / _POLICY_FILE
        report_path = staging_path / _REPORT_FILE
        learned_path.write_text(learned_payload, encoding="utf-8")
        policy_path.write_text(policy_payload, encoding="utf-8")
        report_path.write_text(report_payload, encoding="utf-8")

        manifest_material = {
            "schema_name": FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_NAME,
            "schema_version": FAST_POLICY_COMPARISON_ARTIFACT_SCHEMA_VERSION,
            "baseline_invocation_directory_name": invocation_path.name,
            "baseline_invocation_fingerprint_sha256": (
                invocation.manifest.invocation_fingerprint_sha256
            ),
            "baseline_request_fingerprint_sha256": (
                invocation.manifest.request_fingerprint_sha256
            ),
            "baseline_campaign_artifact_fingerprint_sha256": (
                campaign.manifest.artifact_fingerprint_sha256
            ),
            "baseline_catalog_fingerprint_sha256": (
                campaign.manifest.catalog_fingerprint_sha256
            ),
            "baseline_run_batch_fingerprint_sha256": (
                campaign.manifest.run_batch_fingerprint_sha256
            ),
            "baseline_run_count": len(campaign.runs),
            "baseline_event_population_fingerprint_sha256": (
                campaign.manifest.event_population_fingerprint_sha256
            ),
            "learned_candidate_version": learned_run.candidate_version,
            "learned_candidate_fingerprint_sha256": (
                learned_run.candidate_fingerprint_sha256
            ),
            "learned_run_evidence_fingerprint_sha256": (
                learned_run.run_evidence_fingerprint_sha256
            ),
            "learned_run_batch_fingerprint_sha256": (
                learned_batch_fingerprint
            ),
            "learned_event_population_fingerprint_sha256": (
                learned_run.event_population_fingerprint_sha256
            ),
            "superiority_policy_version": superiority_policy.version,
            "superiority_policy_fingerprint_sha256": policy_fingerprint,
            "superiority_report_fingerprint_sha256": (
                report.report_fingerprint_sha256
            ),
            "decision": report.decision.value,
            "learned_run_file_sha256": _sha256_file(learned_path),
            "superiority_policy_file_sha256": _sha256_file(policy_path),
            "superiority_report_file_sha256": _sha256_file(report_path),
        }
        manifest = FastPolicyComparisonArtifactManifest(
            **manifest_material,
            artifact_fingerprint_sha256=_sha256_canonical(
                manifest_material
            ),
        )
        (staging_path / _MANIFEST_FILE).write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )

        verified = read_fast_policy_comparison_artifact(staging_path)
        if verified.manifest != manifest:
            raise ValueError(
                "staged Fast policy comparison artifact did not round-trip"
            )

        staging_path.rename(destination_path)
        return manifest
    except Exception:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise


def read_fast_policy_comparison_artifact(
    source: str | Path,
) -> FastPolicyComparisonArtifact:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            "Fast policy comparison artifact source must be an existing directory"
        )
    entries = frozenset(path.name for path in root.iterdir())
    if entries != _ROOT_ENTRIES:
        raise ValueError(
            "Fast policy comparison artifact has unknown or missing entries"
        )

    manifest_payload = (root / _MANIFEST_FILE).read_text(
        encoding="utf-8"
    )
    manifest_document = _load_canonical(
        manifest_payload,
        label="Fast policy comparison artifact manifest",
    )
    if frozenset(manifest_document) != _MANIFEST_KEYS:
        raise ValueError(
            "Fast policy comparison artifact manifest has unknown or missing fields"
        )
    try:
        manifest = FastPolicyComparisonArtifactManifest(
            **manifest_document
        )
    except TypeError as exc:
        raise ValueError(
            "Fast policy comparison artifact manifest is invalid"
        ) from exc

    material = dict(manifest_document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "Fast policy comparison artifact fingerprint mismatch"
        )

    learned_path = root / _LEARNED_RUN_FILE
    policy_path = root / _POLICY_FILE
    report_path = root / _REPORT_FILE
    if _sha256_file(learned_path) != manifest.learned_run_file_sha256:
        raise ValueError(
            "Fast policy comparison learned run file fingerprint mismatch"
        )
    if _sha256_file(policy_path) != manifest.superiority_policy_file_sha256:
        raise ValueError(
            "Fast policy comparison policy file fingerprint mismatch"
        )
    if _sha256_file(report_path) != manifest.superiority_report_file_sha256:
        raise ValueError(
            "Fast policy comparison report file fingerprint mismatch"
        )

    learned_payload = learned_path.read_text(encoding="utf-8")
    learned_document = _load_canonical(
        learned_payload,
        label="learned Fast policy run batch",
    )
    if (
        learned_document.get("batch_fingerprint_sha256")
        != manifest.learned_run_batch_fingerprint_sha256
    ):
        raise ValueError(
            "Fast policy comparison learned run batch fingerprint mismatch"
        )
    learned_runs = decode_fast_policy_run_evidence_batch(
        learned_payload
    )
    if len(learned_runs) != 1:
        raise ValueError(
            "Fast policy comparison must contain exactly one learned run"
        )
    learned_run = learned_runs[0]
    if (
        fast_policy_run_evidence_fingerprint_sha256(learned_run)
        != learned_run.run_evidence_fingerprint_sha256
    ):
        raise ValueError(
            "Fast policy comparison learned run fingerprint mismatch"
        )

    policy_payload = policy_path.read_text(encoding="utf-8")
    policy_document = _load_canonical(
        policy_payload,
        label="Fast policy superiority policy",
    )
    if (
        policy_document.get("policy_fingerprint_sha256")
        != manifest.superiority_policy_fingerprint_sha256
    ):
        raise ValueError(
            "Fast policy comparison superiority policy fingerprint mismatch"
        )
    policy = decode_fast_policy_superiority_policy(policy_payload)
    if (
        fast_policy_superiority_policy_fingerprint_sha256(policy)
        != manifest.superiority_policy_fingerprint_sha256
    ):
        raise ValueError(
            "Fast policy comparison superiority policy recomputation mismatch"
        )

    report = decode_fast_policy_superiority_report(
        report_path.read_text(encoding="utf-8")
    )

    invocation_path = (
        root.parent / manifest.baseline_invocation_directory_name
    )
    invocation = read_fast_deterministic_campaign_invocation_seal(
        invocation_path
    )
    campaign_path = (
        root.parent / invocation.manifest.campaign_directory_name
    )
    campaign = read_fast_deterministic_campaign_artifact(
        campaign_path
    )
    _validate_baseline_chain(
        invocation=invocation,
        campaign=campaign,
        policy=policy,
    )

    _validate_manifest_bindings(
        manifest=manifest,
        invocation=invocation,
        campaign=campaign,
        learned_run=learned_run,
        policy=policy,
        report=report,
    )

    recomputed = evaluate_fast_policy_superiority(
        learned_run,
        campaign.runs,
        policy,
    )
    if recomputed != report:
        raise ValueError(
            "Fast policy comparison superiority report does not recompute exactly"
        )

    return FastPolicyComparisonArtifact(
        path=root,
        manifest=manifest,
        baseline_runs=campaign.runs,
        learned_run=learned_run,
        superiority_policy=policy,
        superiority_report=report,
    )


def _validate_baseline_chain(
    *,
    invocation: object,
    campaign: object,
    policy: FastPolicySuperiorityPolicy,
) -> None:
    if (
        campaign.manifest.artifact_fingerprint_sha256
        != invocation.manifest.campaign_artifact_fingerprint_sha256
    ):
        raise ValueError(
            "baseline invocation/campaign artifact fingerprint mismatch"
        )
    versions = tuple(
        value.candidate_version
        for value in campaign.catalog.candidates
    )
    if versions != policy.required_baseline_versions:
        raise ValueError(
            "superiority policy required baselines do not match deterministic catalog"
        )
    if len(campaign.runs) != 8:
        raise ValueError(
            "baseline deterministic campaign must contain exactly eight runs"
        )


def _validate_manifest_bindings(
    *,
    manifest: FastPolicyComparisonArtifactManifest,
    invocation: object,
    campaign: object,
    learned_run: FastPolicyRunEvidence,
    policy: FastPolicySuperiorityPolicy,
    report: FastPolicySuperiorityReport,
) -> None:
    expected = {
        "baseline_invocation_fingerprint_sha256": (
            invocation.manifest.invocation_fingerprint_sha256
        ),
        "baseline_request_fingerprint_sha256": (
            invocation.manifest.request_fingerprint_sha256
        ),
        "baseline_campaign_artifact_fingerprint_sha256": (
            campaign.manifest.artifact_fingerprint_sha256
        ),
        "baseline_catalog_fingerprint_sha256": (
            campaign.manifest.catalog_fingerprint_sha256
        ),
        "baseline_run_batch_fingerprint_sha256": (
            campaign.manifest.run_batch_fingerprint_sha256
        ),
        "baseline_run_count": len(campaign.runs),
        "baseline_event_population_fingerprint_sha256": (
            campaign.manifest.event_population_fingerprint_sha256
        ),
        "learned_candidate_version": learned_run.candidate_version,
        "learned_candidate_fingerprint_sha256": (
            learned_run.candidate_fingerprint_sha256
        ),
        "learned_run_evidence_fingerprint_sha256": (
            learned_run.run_evidence_fingerprint_sha256
        ),
        "learned_event_population_fingerprint_sha256": (
            learned_run.event_population_fingerprint_sha256
        ),
        "superiority_policy_version": policy.version,
        "superiority_report_fingerprint_sha256": (
            report.report_fingerprint_sha256
        ),
        "decision": report.decision.value,
    }
    for name, value in expected.items():
        if getattr(manifest, name) != value:
            raise ValueError(
                f"Fast policy comparison manifest binding mismatch: {name}"
            )


def _manifest_document(
    manifest: FastPolicyComparisonArtifactManifest,
) -> dict[str, object]:
    return {
        name: getattr(manifest, name)
        for name in _MANIFEST_KEYS
    }


def _load_canonical(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty canonical JSON")
    try:
        document = json.loads(
            payload,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    if payload != _canonical(document):
        raise ValueError(f"{label} must be canonical JSON")
    return document


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _require_leaf_name(name: str, value: object) -> None:
    _require_non_empty_string(name, value)
    assert isinstance(value, str)
    path = Path(value)
    if path.name != value or value in {".", ".."}:
        raise ValueError(f"{name} must be a single path component")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
