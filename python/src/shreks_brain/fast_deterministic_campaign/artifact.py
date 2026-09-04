from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicComparisonCatalog,
    decode_fast_deterministic_comparison_catalog,
    encode_fast_deterministic_comparison_catalog,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.fast_policy_proof import (
    FastPolicyRunEvidence,
    decode_fast_policy_run_evidence_batch,
    encode_fast_policy_run_evidence_batch,
)
from shreks_brain.paper import PaperFillPolicy, PaperLedger
from shreks_brain.research.fast_training_features import FastTrainingFeatureDataset
from shreks_brain.risk import RiskPolicy

from .comparison import run_fast_deterministic_comparison_catalog_matrix
from .evidence_bundle import (
    FastDeterministicComparisonEvidenceBundle,
    read_fast_deterministic_comparison_evidence_bundle,
    write_fast_deterministic_comparison_evidence_bundle,
)
from .hydration import hydrate_fast_deterministic_comparison_evidence
from .input_assembly import (
    FastDeterministicComparisonExecutionPolicy,
    FastDeterministicComparisonPointInTimeContext,
    assemble_fast_deterministic_comparison_hydration_inputs,
)


FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_NAME = (
    "shreks.fast_deterministic_campaign_artifact"
)
FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_VERSION = 1

_BUNDLE_DIR = "comparison_bundle"
_CATALOG_FILE = "comparison_catalog.json"
_RUN_FILE = "policy_runs.json"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset(
    {_BUNDLE_DIR, _CATALOG_FILE, _RUN_FILE, _MANIFEST_FILE}
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "catalog_fingerprint_sha256",
        "catalog_file_sha256",
        "comparison_bundle_fingerprint_sha256",
        "row_count",
        "event_population_fingerprint_sha256",
        "run_count",
        "run_batch_fingerprint_sha256",
        "run_batch_file_sha256",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignArtifactManifest:
    schema_name: str
    schema_version: int
    catalog_fingerprint_sha256: str
    catalog_file_sha256: str
    comparison_bundle_fingerprint_sha256: str
    row_count: int
    event_population_fingerprint_sha256: str
    run_count: int
    run_batch_fingerprint_sha256: str
    run_batch_file_sha256: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_NAME:
            raise ValueError(
                "unsupported deterministic campaign artifact schema_name"
            )
        if self.schema_version != FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported deterministic campaign artifact schema_version"
            )
        if (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count <= 0
        ):
            raise ValueError(
                "deterministic campaign artifact row_count must be positive"
            )
        if self.run_count != 8:
            raise ValueError(
                "deterministic campaign artifact must contain exactly eight runs"
            )
        for name in (
            "catalog_fingerprint_sha256",
            "catalog_file_sha256",
            "comparison_bundle_fingerprint_sha256",
            "event_population_fingerprint_sha256",
            "run_batch_fingerprint_sha256",
            "run_batch_file_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignArtifact:
    manifest: FastDeterministicCampaignArtifactManifest
    catalog: FastDeterministicComparisonCatalog
    comparison_bundle: FastDeterministicComparisonEvidenceBundle
    runs: tuple[FastPolicyRunEvidence, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not FastDeterministicCampaignArtifactManifest:
            raise ValueError(
                "manifest must be exact FastDeterministicCampaignArtifactManifest"
            )
        if type(self.catalog) is not FastDeterministicComparisonCatalog:
            raise ValueError(
                "catalog must be exact FastDeterministicComparisonCatalog"
            )
        if not isinstance(self.runs, tuple) or len(self.runs) != 8:
            raise ValueError(
                "runs must contain exactly eight policy run evidence values"
            )


def write_fast_deterministic_campaign_artifact(
    *,
    database_path: str | Path,
    feature_dataset: FastTrainingFeatureDataset,
    catalog: FastDeterministicComparisonCatalog,
    champion_path: str | Path,
    execution_policy: FastDeterministicComparisonExecutionPolicy,
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...],
    entry_authority_binary_path: str | Path,
    candidate_binary_path: str | Path,
    paper_run_id_prefix: str,
    assessment_version: str,
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
    destination: str | Path,
) -> FastDeterministicCampaignArtifactManifest:
    if type(catalog) is not FastDeterministicComparisonCatalog:
        raise ValueError(
            "catalog must be exact FastDeterministicComparisonCatalog"
        )
    _require_non_empty_string("paper_run_id_prefix", paper_run_id_prefix)
    _require_non_empty_string("assessment_version", assessment_version)

    destination_path = Path(destination)
    if destination_path.exists():
        raise FileExistsError(
            "deterministic campaign artifact destination already exists; artifacts are immutable"
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}-",
            dir=destination_path.parent,
        )
    )

    try:
        assembly = assemble_fast_deterministic_comparison_hydration_inputs(
            database_path=database_path,
            feature_dataset=feature_dataset,
            champion_path=champion_path,
            execution_policy=execution_policy,
            contexts=contexts,
        )
        hydrated = hydrate_fast_deterministic_comparison_evidence(
            database_path=database_path,
            feature_dataset=feature_dataset,
            catalog=catalog,
            hydration_inputs=assembly.hydration_inputs,
            entry_authority_binary_path=entry_authority_binary_path,
        )

        bundle_manifest = write_fast_deterministic_comparison_evidence_bundle(
            feature_dataset=feature_dataset,
            catalog=catalog,
            rows=hydrated.rows,
            provenance=hydrated.provenance,
            destination=staging_path / _BUNDLE_DIR,
        )

        catalog_payload = encode_fast_deterministic_comparison_catalog(catalog)
        catalog_path = staging_path / _CATALOG_FILE
        catalog_path.write_text(catalog_payload, encoding="utf-8")

        matrix = run_fast_deterministic_comparison_catalog_matrix(
            binary_path=candidate_binary_path,
            catalog=catalog,
            rows=hydrated.rows,
            paper_run_id_prefix=paper_run_id_prefix,
            assessment_version=assessment_version,
            starting_ledger=starting_ledger,
            fill_policy=fill_policy,
            risk_policy=risk_policy,
            position_policy=position_policy,
            evaluation_policy=evaluation_policy,
        )
        if len(matrix.runs) != len(catalog.candidates):
            raise ValueError(
                "deterministic campaign matrix run count does not match catalog"
            )

        run_payload = encode_fast_policy_run_evidence_batch(matrix.runs)
        run_document = _load_canonical_json(
            run_payload,
            label="policy run evidence batch",
        )
        batch_fingerprint = run_document.get("batch_fingerprint_sha256")
        _require_sha256(
            "run_batch_fingerprint_sha256",
            batch_fingerprint,
        )
        run_path = staging_path / _RUN_FILE
        run_path.write_text(run_payload, encoding="utf-8")

        manifest_material = {
            "schema_name": FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_NAME,
            "schema_version": FAST_DETERMINISTIC_CAMPAIGN_ARTIFACT_SCHEMA_VERSION,
            "catalog_fingerprint_sha256": (
                catalog.catalog_fingerprint_sha256
            ),
            "catalog_file_sha256": _sha256_file(catalog_path),
            "comparison_bundle_fingerprint_sha256": (
                bundle_manifest.bundle_fingerprint_sha256
            ),
            "row_count": bundle_manifest.row_count,
            "event_population_fingerprint_sha256": (
                matrix.event_population_fingerprint_sha256
            ),
            "run_count": len(matrix.runs),
            "run_batch_fingerprint_sha256": batch_fingerprint,
            "run_batch_file_sha256": _sha256_file(run_path),
        }
        manifest = FastDeterministicCampaignArtifactManifest(
            **manifest_material,
            artifact_fingerprint_sha256=_sha256_canonical(
                manifest_material
            ),
        )
        (staging_path / _MANIFEST_FILE).write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )

        staging_path.rename(destination_path)
        return manifest
    except Exception:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise


def read_fast_deterministic_campaign_artifact(
    source: str | Path,
) -> FastDeterministicCampaignArtifact:
    root = Path(source)
    if not root.is_dir():
        raise ValueError(
            "deterministic campaign artifact source must be an existing directory"
        )
    entries = frozenset(path.name for path in root.iterdir())
    if entries != _ROOT_ENTRIES:
        raise ValueError(
            "deterministic campaign artifact has unknown or missing entries"
        )

    manifest_payload = (root / _MANIFEST_FILE).read_text(encoding="utf-8")
    document = _load_canonical_json(
        manifest_payload,
        label="deterministic campaign artifact manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
        raise ValueError(
            "deterministic campaign artifact manifest has unknown or missing fields"
        )
    try:
        manifest = FastDeterministicCampaignArtifactManifest(**document)
    except TypeError as exc:
        raise ValueError(
            "deterministic campaign artifact manifest is invalid"
        ) from exc

    material = dict(document)
    claimed_artifact_fingerprint = material.pop(
        "artifact_fingerprint_sha256"
    )
    if _sha256_canonical(material) != claimed_artifact_fingerprint:
        raise ValueError(
            "deterministic campaign artifact fingerprint mismatch"
        )

    catalog_path = root / _CATALOG_FILE
    if _sha256_file(catalog_path) != manifest.catalog_file_sha256:
        raise ValueError(
            "deterministic campaign catalog file fingerprint mismatch"
        )
    catalog_payload = catalog_path.read_text(encoding="utf-8")
    catalog = decode_fast_deterministic_comparison_catalog(catalog_payload)
    if (
        catalog.catalog_fingerprint_sha256
        != manifest.catalog_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign catalog fingerprint mismatch"
        )

    bundle = read_fast_deterministic_comparison_evidence_bundle(
        root / _BUNDLE_DIR
    )
    if (
        bundle.manifest.bundle_fingerprint_sha256
        != manifest.comparison_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign comparison bundle fingerprint mismatch"
        )
    if (
        bundle.manifest.catalog_fingerprint_sha256
        != manifest.catalog_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign bundle catalog fingerprint mismatch"
        )
    if bundle.manifest.row_count != manifest.row_count:
        raise ValueError(
            "deterministic campaign bundle row count mismatch"
        )

    run_path = root / _RUN_FILE
    if _sha256_file(run_path) != manifest.run_batch_file_sha256:
        raise ValueError(
            "deterministic campaign run file fingerprint mismatch"
        )
    run_payload = run_path.read_text(encoding="utf-8")
    run_document = _load_canonical_json(
        run_payload,
        label="policy run evidence batch",
    )
    if (
        run_document.get("batch_fingerprint_sha256")
        != manifest.run_batch_fingerprint_sha256
    ):
        raise ValueError(
            "deterministic campaign run batch fingerprint mismatch"
        )
    runs = decode_fast_policy_run_evidence_batch(run_payload)
    if len(runs) != manifest.run_count:
        raise ValueError(
            "deterministic campaign run count mismatch"
        )

    expected_versions = tuple(
        value.candidate_version for value in catalog.candidates
    )
    actual_versions = tuple(value.candidate_version for value in runs)
    if actual_versions != expected_versions:
        raise ValueError(
            "deterministic campaign run candidate versions do not match catalog"
        )
    expected_fingerprints = tuple(
        value.candidate_fingerprint_sha256 for value in catalog.candidates
    )
    actual_fingerprints = tuple(
        value.candidate_fingerprint_sha256 for value in runs
    )
    if actual_fingerprints != expected_fingerprints:
        raise ValueError(
            "deterministic campaign run candidate fingerprints do not match catalog"
        )
    if any(
        value.event_population_fingerprint_sha256
        != manifest.event_population_fingerprint_sha256
        for value in runs
    ):
        raise ValueError(
            "deterministic campaign run population fingerprint mismatch"
        )

    return FastDeterministicCampaignArtifact(
        manifest=manifest,
        catalog=catalog,
        comparison_bundle=bundle,
        runs=runs,
    )


def _manifest_document(
    manifest: FastDeterministicCampaignArtifactManifest,
) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "catalog_fingerprint_sha256": (
            manifest.catalog_fingerprint_sha256
        ),
        "catalog_file_sha256": manifest.catalog_file_sha256,
        "comparison_bundle_fingerprint_sha256": (
            manifest.comparison_bundle_fingerprint_sha256
        ),
        "row_count": manifest.row_count,
        "event_population_fingerprint_sha256": (
            manifest.event_population_fingerprint_sha256
        ),
        "run_count": manifest.run_count,
        "run_batch_fingerprint_sha256": (
            manifest.run_batch_fingerprint_sha256
        ),
        "run_batch_file_sha256": manifest.run_batch_file_sha256,
        "artifact_fingerprint_sha256": (
            manifest.artifact_fingerprint_sha256
        ),
    }


def _load_canonical_json(
    payload: str,
    *,
    label: str,
) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty canonical JSON")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    if payload != _canonical(document):
        raise ValueError(f"{label} must be canonical JSON")
    return document


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
