from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_context_hydration import (
    FastForecastContextHydrationPolicy,
    read_fast_forecast_context_hydration_artifact,
    write_fast_forecast_context_hydration_artifact,
)
from shreks_brain.fast_evaluation import FastForecastEvaluationPolicy
from shreks_brain.fast_first_champion import (
    FastFirstChampionFileRequest,
    build_fast_first_champion_file_request,
    decode_fast_first_champion_file_request,
    read_fast_first_champion_artifact,
    run_fast_first_champion_file_request,
    write_fast_first_champion_file_request,
)
from shreks_brain.fast_proof_workspace import read_fast_proof_workspace
from shreks_brain.fast_validation import FastChronologicalValidationPolicy
from shreks_brain.research.fast_training_bundle import (
    build_fast_training_bundle_from_runtime_sources,
)
from shreks_brain.research.fast_training_economics import (
    FastTrainingExecutionCostPolicy,
    fast_training_execution_cost_policy_fingerprint_sha256,
)


FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_NAME = (
    "shreks.fast_first_champion_preparation"
)
FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_VERSION = 2

_PROOF_DIR = "proof-workspace"
_HYDRATION_DIR = "context-hydration"
_REQUEST_FILE = "first-champion-request.json"
_CHAMPION_DIR = "first-champion"
_MANIFEST_FILE = "manifest.json"
_ROOT_ENTRIES = frozenset(
    {
        _PROOF_DIR,
        _HYDRATION_DIR,
        _REQUEST_FILE,
        _CHAMPION_DIR,
        _MANIFEST_FILE,
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "proof_workspace_release_source_sha",
        "proof_workspace_artifact_fingerprint_sha256",
        "proof_workspace_feature_jsonl_sha256",
        "proof_workspace_feature_logical_fingerprint_sha256",
        "proof_workspace_export_database_sha256",
        "proof_workspace_export_database_wal_sha256",
        "observer_database_sha256",
        "observer_database_wal_sha256",
        "training_economics_overlay_manifest_fingerprint_sha256",
        "training_execution_cost_policy_fingerprint_sha256",
        "training_bundle_fingerprint_sha256",
        "validation_policy_fingerprint_sha256",
        "hydration_artifact_fingerprint_sha256",
        "hydration_policy_fingerprint_sha256",
        "population_validation_run_fingerprint_sha256",
        "context_fingerprint_sha256",
        "request_fingerprint_sha256",
        "request_file_sha256",
        "first_champion_artifact_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "champion_version",
        "selection_decision_reference",
        "selection_decided_at_unix_ms",
        "selection_reason",
        "artifact_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionPreparationManifest:
    schema_name: str
    schema_version: int
    proof_workspace_release_source_sha: str
    proof_workspace_artifact_fingerprint_sha256: str
    proof_workspace_feature_jsonl_sha256: str
    proof_workspace_feature_logical_fingerprint_sha256: str
    proof_workspace_export_database_sha256: str
    proof_workspace_export_database_wal_sha256: str | None
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    training_economics_overlay_manifest_fingerprint_sha256: str
    training_execution_cost_policy_fingerprint_sha256: str
    training_bundle_fingerprint_sha256: str
    validation_policy_fingerprint_sha256: str
    hydration_artifact_fingerprint_sha256: str
    hydration_policy_fingerprint_sha256: str
    population_validation_run_fingerprint_sha256: str
    context_fingerprint_sha256: str
    request_fingerprint_sha256: str
    request_file_sha256: str
    first_champion_artifact_fingerprint_sha256: str
    champion_fingerprint_sha256: str
    champion_version: str
    selection_decision_reference: str
    selection_decided_at_unix_ms: int
    selection_reason: str
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_NAME:
            raise ValueError(
                "unsupported first champion preparation schema_name"
            )
        if self.schema_version != FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_VERSION:
            raise ValueError(
                "unsupported first champion preparation schema_version"
            )
        _require_source_sha(self.proof_workspace_release_source_sha)
        for name in (
            "proof_workspace_artifact_fingerprint_sha256",
            "proof_workspace_feature_jsonl_sha256",
            "proof_workspace_feature_logical_fingerprint_sha256",
            "proof_workspace_export_database_sha256",
            "observer_database_sha256",
            "training_economics_overlay_manifest_fingerprint_sha256",
            "training_execution_cost_policy_fingerprint_sha256",
            "training_bundle_fingerprint_sha256",
            "validation_policy_fingerprint_sha256",
            "hydration_artifact_fingerprint_sha256",
            "hydration_policy_fingerprint_sha256",
            "population_validation_run_fingerprint_sha256",
            "context_fingerprint_sha256",
            "request_fingerprint_sha256",
            "request_file_sha256",
            "first_champion_artifact_fingerprint_sha256",
            "champion_fingerprint_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        for name in (
            "proof_workspace_export_database_wal_sha256",
            "observer_database_wal_sha256",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_sha256(name, value)
        for name in (
            "champion_version",
            "selection_decision_reference",
            "selection_reason",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_non_negative_int(
            "selection_decided_at_unix_ms",
            self.selection_decided_at_unix_ms,
        )


@dataclass(frozen=True, slots=True)
class FastFirstChampionPreparationArtifact:
    path: Path
    manifest: FastFirstChampionPreparationManifest
    proof_workspace: object
    context_hydration: object
    request: FastFirstChampionFileRequest
    first_champion: object

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        if type(self.manifest) is not FastFirstChampionPreparationManifest:
            raise ValueError(
                "manifest must be exact FastFirstChampionPreparationManifest"
            )
        if type(self.request) is not FastFirstChampionFileRequest:
            raise ValueError(
                "request must be exact FastFirstChampionFileRequest"
            )


@dataclass(frozen=True, slots=True)
class _DatabaseSnapshot:
    database_sha256: str
    wal_sha256: str | None


@dataclass(frozen=True, slots=True)
class _TrainingEconomicsSnapshot:
    manifest_fingerprint_sha256: str
    manifest_file_sha256: str
    rows_file_sha256: str


def prepare_fast_first_champion_evidence(
    *,
    proof_workspace_path: str | Path,
    observer_database_path: str | Path,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
    destination: str | Path,
    hydration_policy: FastForecastContextHydrationPolicy,
    validation_policy: FastChronologicalValidationPolicy,
    evaluation_policy: FastForecastEvaluationPolicy,
    future_path_label_version: int,
    counterfactual_base_quantity: float,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    horizon_ms: int,
    model_version_prefix: str,
    training_policy_version: str,
    minimum_test_scored_observations: int,
) -> FastFirstChampionPreparationArtifact:
    source_workspace_path = Path(proof_workspace_path).expanduser().resolve()
    if source_workspace_path.is_symlink() or not source_workspace_path.is_dir():
        raise ValueError(
            "proof workspace source must be an existing real directory"
        )
    database = Path(observer_database_path).expanduser().resolve()
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "preparation observer database must be an existing regular file"
        )
    economics_overlay = Path(
        training_economics_overlay_path
    ).expanduser().resolve()
    if economics_overlay.is_symlink() or not economics_overlay.is_dir():
        raise ValueError(
            "training economics overlay must be an existing real directory"
        )
    if {child.name for child in economics_overlay.iterdir()} != {
        "rows.jsonl",
        "manifest.json",
    }:
        raise ValueError(
            "training economics overlay must contain exactly rows.jsonl and manifest.json"
        )
    if type(training_execution_cost_policy) is not FastTrainingExecutionCostPolicy:
        raise ValueError(
            "training_execution_cost_policy must be exact FastTrainingExecutionCostPolicy"
        )
    training_cost_policy_fingerprint = (
        fast_training_execution_cost_policy_fingerprint_sha256(
            training_execution_cost_policy
        )
    )
    economics_before = _capture_training_economics(economics_overlay)

    destination_path = Path(destination).expanduser().resolve()
    if destination_path.exists() or destination_path.is_symlink():
        raise FileExistsError(
            "first champion preparation destination already exists"
        )

    source_workspace = read_fast_proof_workspace(source_workspace_path)
    before = _capture_database(database)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_path.name}.tmp-",
            dir=destination_path.parent,
        )
    )
    staging.chmod(0o700)
    try:
        copied_workspace_path = staging / _PROOF_DIR
        shutil.copytree(
            source_workspace_path,
            copied_workspace_path,
            symlinks=False,
        )
        copied_workspace = read_fast_proof_workspace(copied_workspace_path)
        source_workspace_after_copy = read_fast_proof_workspace(
            source_workspace_path
        )
        if (
            copied_workspace.manifest != source_workspace.manifest
            or source_workspace_after_copy.manifest
            != source_workspace.manifest
        ):
            raise ValueError(
                "proof workspace source changed during preparation copy"
            )
        if (
            copied_workspace.features.source_sha256
            != source_workspace.features.source_sha256
            or copied_workspace.features.logical_fingerprint_sha256
            != source_workspace.features.logical_fingerprint_sha256
        ):
            raise ValueError(
                "copied proof workspace feature evidence mismatch"
            )

        feature_path = copied_workspace_path / "features.jsonl"
        bundle = build_fast_training_bundle_from_runtime_sources(
            feature_jsonl_path=feature_path,
            sqlite_path=database,
            future_path_label_version=future_path_label_version,
            counterfactual_base_quantity=counterfactual_base_quantity,
            training_economics_overlay_path=economics_overlay,
            training_execution_cost_policy=training_execution_cost_policy,
        )
        if (
            bundle.features.source_sha256
            != copied_workspace.manifest.feature_jsonl_sha256
            or bundle.features.logical_fingerprint_sha256
            != copied_workspace.manifest.feature_logical_fingerprint_sha256
        ):
            raise ValueError(
                "prepared training bundle does not match proof workspace features"
            )

        hydration_path = staging / _HYDRATION_DIR
        write_fast_forecast_context_hydration_artifact(
            bundle=bundle,
            observer_database_path=database,
            validation_policy=validation_policy,
            horizon_ms=horizon_ms,
            hydration_policy=hydration_policy,
            destination=hydration_path,
        )
        hydration = read_fast_forecast_context_hydration_artifact(
            hydration_path
        )
        _validate_hydration_chain(
            hydration=hydration,
            bundle=bundle,
            proof_workspace=copied_workspace,
            database_snapshot=before,
            validation_policy=validation_policy,
            horizon_ms=horizon_ms,
        )

        request = build_fast_first_champion_file_request(
            feature_jsonl_path=f"{_PROOF_DIR}/features.jsonl",
            observer_database_path=str(database),
            context_corpus_path=f"{_HYDRATION_DIR}/contexts.json",
            training_economics_overlay_path=str(economics_overlay),
            expected_training_economics_overlay_manifest_fingerprint_sha256=(
                economics_before.manifest_fingerprint_sha256
            ),
            training_execution_cost_policy=training_execution_cost_policy,
            training_execution_cost_policy_fingerprint_sha256=(
                training_cost_policy_fingerprint
            ),
            destination_path=_CHAMPION_DIR,
            future_path_label_version=future_path_label_version,
            counterfactual_base_quantity=counterfactual_base_quantity,
            validation_policy=validation_policy,
            evaluation_policy=evaluation_policy,
            champion_version=champion_version,
            decision_reference=decision_reference,
            decided_at_unix_ms=decided_at_unix_ms,
            reason=reason,
            horizon_ms=horizon_ms,
            model_version_prefix=model_version_prefix,
            training_policy_version=training_policy_version,
            minimum_test_scored_observations=(
                minimum_test_scored_observations
            ),
        )
        request_path = staging / _REQUEST_FILE
        write_fast_first_champion_file_request(request, request_path)
        first_champion = run_fast_first_champion_file_request(request_path)
        first_champion = read_fast_first_champion_artifact(
            staging / _CHAMPION_DIR
        )

        after = _capture_database(database)
        economics_after = _capture_training_economics(economics_overlay)
        if economics_after != economics_before:
            raise ValueError(
                "first champion preparation training economics source changed during execution"
            )
        if after != before:
            raise ValueError(
                "first champion preparation database source changed during execution"
            )

        _validate_first_champion_chain(
            first_champion=first_champion,
            request=request,
            hydration=hydration,
            bundle=bundle,
            proof_workspace=copied_workspace,
            database_snapshot=before,
        )

        material = _manifest_material(
            proof_workspace=copied_workspace,
            database_snapshot=before,
            training_economics_overlay_manifest_fingerprint_sha256=(
                economics_before.manifest_fingerprint_sha256
            ),
            training_execution_cost_policy_fingerprint_sha256=(
                training_cost_policy_fingerprint
            ),
            bundle=bundle,
            hydration=hydration,
            request=request,
            request_path=request_path,
            first_champion=first_champion,
        )
        manifest = FastFirstChampionPreparationManifest(
            **material,
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        manifest_path = staging / _MANIFEST_FILE
        manifest_path.write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)

        verified = read_fast_first_champion_preparation(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged first champion preparation did not round-trip"
            )
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(
                "first champion preparation destination appeared during write"
            )
        staging.rename(destination_path)
        return read_fast_first_champion_preparation(destination_path)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_first_champion_preparation(
    path: str | Path,
) -> FastFirstChampionPreparationArtifact:
    root = Path(path).expanduser().resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "first champion preparation must be an existing real directory"
        )
    names = {child.name for child in root.iterdir()}
    if names != _ROOT_ENTRIES:
        raise ValueError(
            "first champion preparation has unknown or missing entries"
        )
    for name in (_PROOF_DIR, _HYDRATION_DIR, _CHAMPION_DIR):
        child = root / name
        if child.is_symlink() or not child.is_dir():
            raise ValueError(
                "first champion preparation child artifacts must be real directories"
            )
    for name in (_REQUEST_FILE, _MANIFEST_FILE):
        child = root / name
        if child.is_symlink() or not child.is_file():
            raise ValueError(
                "first champion preparation metadata must be regular files"
            )

    document = _load_canonical(
        (root / _MANIFEST_FILE).read_text(encoding="utf-8"),
        label="first champion preparation manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
        raise ValueError(
            "first champion preparation manifest has unknown or missing fields"
        )
    try:
        manifest = FastFirstChampionPreparationManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            proof_workspace_release_source_sha=document[
                "proof_workspace_release_source_sha"
            ],
            proof_workspace_artifact_fingerprint_sha256=document[
                "proof_workspace_artifact_fingerprint_sha256"
            ],
            proof_workspace_feature_jsonl_sha256=document[
                "proof_workspace_feature_jsonl_sha256"
            ],
            proof_workspace_feature_logical_fingerprint_sha256=document[
                "proof_workspace_feature_logical_fingerprint_sha256"
            ],
            proof_workspace_export_database_sha256=document[
                "proof_workspace_export_database_sha256"
            ],
            proof_workspace_export_database_wal_sha256=document[
                "proof_workspace_export_database_wal_sha256"
            ],
            observer_database_sha256=document[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=document[
                "observer_database_wal_sha256"
            ],
            training_economics_overlay_manifest_fingerprint_sha256=document[
                "training_economics_overlay_manifest_fingerprint_sha256"
            ],
            training_execution_cost_policy_fingerprint_sha256=document[
                "training_execution_cost_policy_fingerprint_sha256"
            ],
            training_bundle_fingerprint_sha256=document[
                "training_bundle_fingerprint_sha256"
            ],
            validation_policy_fingerprint_sha256=document[
                "validation_policy_fingerprint_sha256"
            ],
            hydration_artifact_fingerprint_sha256=document[
                "hydration_artifact_fingerprint_sha256"
            ],
            hydration_policy_fingerprint_sha256=document[
                "hydration_policy_fingerprint_sha256"
            ],
            population_validation_run_fingerprint_sha256=document[
                "population_validation_run_fingerprint_sha256"
            ],
            context_fingerprint_sha256=document[
                "context_fingerprint_sha256"
            ],
            request_fingerprint_sha256=document[
                "request_fingerprint_sha256"
            ],
            request_file_sha256=document["request_file_sha256"],
            first_champion_artifact_fingerprint_sha256=document[
                "first_champion_artifact_fingerprint_sha256"
            ],
            champion_fingerprint_sha256=document[
                "champion_fingerprint_sha256"
            ],
            champion_version=document["champion_version"],
            selection_decision_reference=document[
                "selection_decision_reference"
            ],
            selection_decided_at_unix_ms=document[
                "selection_decided_at_unix_ms"
            ],
            selection_reason=document["selection_reason"],
            artifact_fingerprint_sha256=document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"first champion preparation manifest is invalid: {exc}"
        ) from exc

    material = dict(document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError(
            "first champion preparation artifact fingerprint mismatch"
        )

    proof_workspace = read_fast_proof_workspace(root / _PROOF_DIR)
    hydration = read_fast_forecast_context_hydration_artifact(
        root / _HYDRATION_DIR
    )
    request_path = root / _REQUEST_FILE
    if _sha256_file_stable(request_path) != manifest.request_file_sha256:
        raise ValueError(
            "first champion preparation request file hash mismatch"
        )
    request = decode_fast_first_champion_file_request(
        request_path.read_text(encoding="utf-8")
    )
    first_champion = read_fast_first_champion_artifact(
        root / _CHAMPION_DIR
    )

    _validate_reopened_chain(
        manifest=manifest,
        proof_workspace=proof_workspace,
        hydration=hydration,
        request=request,
        first_champion=first_champion,
    )
    return FastFirstChampionPreparationArtifact(
        path=root,
        manifest=manifest,
        proof_workspace=proof_workspace,
        context_hydration=hydration,
        request=request,
        first_champion=first_champion,
    )


def _validate_hydration_chain(
    *,
    hydration,
    bundle,
    proof_workspace,
    database_snapshot: _DatabaseSnapshot,
    validation_policy: FastChronologicalValidationPolicy,
    horizon_ms: int,
) -> None:
    manifest = hydration.manifest
    if manifest.validation_policy != validation_policy:
        raise ValueError(
            "context hydration validation policy does not match preparation"
        )
    if manifest.horizon_ms != horizon_ms:
        raise ValueError(
            "context hydration horizon does not match preparation"
        )
    if (
        manifest.training_bundle_fingerprint_sha256
        != bundle.manifest.bundle_fingerprint_sha256
    ):
        raise ValueError(
            "context hydration training bundle fingerprint mismatch"
        )
    if (
        manifest.feature_source_jsonl_sha256
        != proof_workspace.manifest.feature_jsonl_sha256
    ):
        raise ValueError(
            "context hydration feature source fingerprint mismatch"
        )
    if (
        manifest.observer_database_sha256
        != database_snapshot.database_sha256
        or manifest.observer_database_wal_sha256
        != database_snapshot.wal_sha256
    ):
        raise ValueError(
            "context hydration database snapshot mismatch"
        )


def _validate_first_champion_chain(
    *,
    first_champion,
    request: FastFirstChampionFileRequest,
    hydration,
    bundle,
    proof_workspace,
    database_snapshot: _DatabaseSnapshot,
) -> None:
    if first_champion.request != request:
        raise ValueError(
            "first champion artifact request does not match preparation request"
        )
    manifest = first_champion.manifest
    if (
        manifest.training_economics_overlay_manifest_fingerprint_sha256
        != request.expected_training_economics_overlay_manifest_fingerprint_sha256
        or manifest.training_execution_cost_policy_fingerprint_sha256
        != request.training_execution_cost_policy_fingerprint_sha256
    ):
        raise ValueError(
            "first champion economics fingerprint mismatch"
        )
    if (
        manifest.request_fingerprint_sha256
        != request.request_fingerprint_sha256
    ):
        raise ValueError(
            "first champion request fingerprint mismatch"
        )
    if (
        manifest.feature_jsonl_sha256
        != proof_workspace.manifest.feature_jsonl_sha256
    ):
        raise ValueError(
            "first champion feature source fingerprint mismatch"
        )
    if (
        manifest.observer_database_sha256
        != database_snapshot.database_sha256
        or manifest.observer_database_wal_sha256
        != database_snapshot.wal_sha256
    ):
        raise ValueError(
            "first champion database snapshot mismatch"
        )
    if (
        manifest.training_bundle_fingerprint_sha256
        != bundle.manifest.bundle_fingerprint_sha256
        or manifest.training_bundle_fingerprint_sha256
        != hydration.manifest.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "first champion training bundle fingerprint mismatch"
        )
    if (
        manifest.context_fingerprint_sha256
        != hydration.manifest.context_fingerprint_sha256
        or manifest.context_corpus_file_sha256
        != hydration.manifest.contexts_file_sha256
    ):
        raise ValueError(
            "first champion context hydration fingerprint mismatch"
        )


def _validate_reopened_chain(
    *,
    manifest: FastFirstChampionPreparationManifest,
    proof_workspace,
    hydration,
    request: FastFirstChampionFileRequest,
    first_champion,
) -> None:
    proof_manifest = proof_workspace.manifest
    hydration_manifest = hydration.manifest
    champion_manifest = first_champion.manifest

    if (
        proof_manifest.release_source_sha
        != manifest.proof_workspace_release_source_sha
        or proof_manifest.artifact_fingerprint_sha256
        != manifest.proof_workspace_artifact_fingerprint_sha256
        or proof_manifest.feature_jsonl_sha256
        != manifest.proof_workspace_feature_jsonl_sha256
        or proof_manifest.feature_logical_fingerprint_sha256
        != manifest.proof_workspace_feature_logical_fingerprint_sha256
        or proof_manifest.observer_database_sha256
        != manifest.proof_workspace_export_database_sha256
        or proof_manifest.observer_database_wal_sha256
        != manifest.proof_workspace_export_database_wal_sha256
    ):
        raise ValueError(
            "preparation proof workspace does not match manifest"
        )
    if (
        hydration_manifest.artifact_fingerprint_sha256
        != manifest.hydration_artifact_fingerprint_sha256
        or hydration_manifest.hydration_policy_fingerprint_sha256
        != manifest.hydration_policy_fingerprint_sha256
        or hydration_manifest.population_validation_run_fingerprint_sha256
        != manifest.population_validation_run_fingerprint_sha256
        or hydration_manifest.context_fingerprint_sha256
        != manifest.context_fingerprint_sha256
        or hydration_manifest.training_bundle_fingerprint_sha256
        != manifest.training_bundle_fingerprint_sha256
        or hydration_manifest.validation_policy_fingerprint_sha256
        != manifest.validation_policy_fingerprint_sha256
    ):
        raise ValueError(
            "preparation context hydration does not match manifest"
        )
    if request.request_fingerprint_sha256 != manifest.request_fingerprint_sha256:
        raise ValueError(
            "preparation request fingerprint does not match manifest"
        )
    if request.validation_policy != hydration_manifest.validation_policy:
        raise ValueError(
            "preparation request validation policy does not match hydration"
        )
    if request.horizon_ms != hydration_manifest.horizon_ms:
        raise ValueError(
            "preparation request horizon does not match hydration"
        )
    if (
        request.feature_jsonl_path != f"{_PROOF_DIR}/features.jsonl"
        or request.context_corpus_path
        != f"{_HYDRATION_DIR}/contexts.json"
        or request.destination_path != _CHAMPION_DIR
    ):
        raise ValueError(
            "preparation request internal evidence paths are incompatible"
        )

    if first_champion.request != request:
        raise ValueError(
            "preparation first champion request copy mismatch"
        )
    if (
        champion_manifest.artifact_fingerprint_sha256
        != manifest.first_champion_artifact_fingerprint_sha256
        or champion_manifest.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
        or champion_manifest.training_economics_overlay_manifest_fingerprint_sha256
        != manifest.training_economics_overlay_manifest_fingerprint_sha256
        or champion_manifest.training_execution_cost_policy_fingerprint_sha256
        != manifest.training_execution_cost_policy_fingerprint_sha256
        or champion_manifest.training_bundle_fingerprint_sha256
        != manifest.training_bundle_fingerprint_sha256
        or champion_manifest.context_fingerprint_sha256
        != manifest.context_fingerprint_sha256
        or champion_manifest.request_fingerprint_sha256
        != manifest.request_fingerprint_sha256
        or champion_manifest.feature_jsonl_sha256
        != manifest.proof_workspace_feature_jsonl_sha256
        or champion_manifest.observer_database_sha256
        != manifest.observer_database_sha256
        or champion_manifest.observer_database_wal_sha256
        != manifest.observer_database_wal_sha256
        or champion_manifest.context_corpus_file_sha256
        != hydration_manifest.contexts_file_sha256
    ):
        raise ValueError(
            "preparation first champion does not match manifest"
        )

    champion = first_champion.champion
    if (
        champion.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
        or champion.champion_version != manifest.champion_version
        or champion.selection.decision_reference
        != manifest.selection_decision_reference
        or champion.selection.decided_at_unix_ms
        != manifest.selection_decided_at_unix_ms
        or champion.selection.reason != manifest.selection_reason
    ):
        raise ValueError(
            "preparation champion selection does not match manifest"
        )
    if (
        hydration_manifest.observer_database_sha256
        != manifest.observer_database_sha256
        or hydration_manifest.observer_database_wal_sha256
        != manifest.observer_database_wal_sha256
    ):
        raise ValueError(
            "preparation child database snapshots do not match"
        )


def _manifest_material(
    *,
    proof_workspace,
    database_snapshot: _DatabaseSnapshot,
    training_economics_overlay_manifest_fingerprint_sha256: str,
    training_execution_cost_policy_fingerprint_sha256: str,
    bundle,
    hydration,
    request: FastFirstChampionFileRequest,
    request_path: Path,
    first_champion,
) -> dict[str, object]:
    proof = proof_workspace.manifest
    hydrated = hydration.manifest
    champion_manifest = first_champion.manifest
    champion = first_champion.champion
    return {
        "schema_name": FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_NAME,
        "schema_version": FAST_FIRST_CHAMPION_PREPARATION_SCHEMA_VERSION,
        "proof_workspace_release_source_sha": proof.release_source_sha,
        "proof_workspace_artifact_fingerprint_sha256": (
            proof.artifact_fingerprint_sha256
        ),
        "proof_workspace_feature_jsonl_sha256": (
            proof.feature_jsonl_sha256
        ),
        "proof_workspace_feature_logical_fingerprint_sha256": (
            proof.feature_logical_fingerprint_sha256
        ),
        "proof_workspace_export_database_sha256": (
            proof.observer_database_sha256
        ),
        "proof_workspace_export_database_wal_sha256": (
            proof.observer_database_wal_sha256
        ),
        "observer_database_sha256": database_snapshot.database_sha256,
        "observer_database_wal_sha256": database_snapshot.wal_sha256,
        "training_economics_overlay_manifest_fingerprint_sha256": (
            training_economics_overlay_manifest_fingerprint_sha256
        ),
        "training_execution_cost_policy_fingerprint_sha256": (
            training_execution_cost_policy_fingerprint_sha256
        ),
        "training_bundle_fingerprint_sha256": (
            bundle.manifest.bundle_fingerprint_sha256
        ),
        "validation_policy_fingerprint_sha256": (
            hydrated.validation_policy_fingerprint_sha256
        ),
        "hydration_artifact_fingerprint_sha256": (
            hydrated.artifact_fingerprint_sha256
        ),
        "hydration_policy_fingerprint_sha256": (
            hydrated.hydration_policy_fingerprint_sha256
        ),
        "population_validation_run_fingerprint_sha256": (
            hydrated.population_validation_run_fingerprint_sha256
        ),
        "context_fingerprint_sha256": (
            hydrated.context_fingerprint_sha256
        ),
        "request_fingerprint_sha256": (
            request.request_fingerprint_sha256
        ),
        "request_file_sha256": _sha256_file_stable(request_path),
        "first_champion_artifact_fingerprint_sha256": (
            champion_manifest.artifact_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            champion_manifest.champion_fingerprint_sha256
        ),
        "champion_version": champion.champion_version,
        "selection_decision_reference": (
            champion.selection.decision_reference
        ),
        "selection_decided_at_unix_ms": (
            champion.selection.decided_at_unix_ms
        ),
        "selection_reason": champion.selection.reason,
    }


def _manifest_document(
    manifest: FastFirstChampionPreparationManifest,
) -> dict[str, object]:
    return {
        "schema_name": manifest.schema_name,
        "schema_version": manifest.schema_version,
        "proof_workspace_release_source_sha": (
            manifest.proof_workspace_release_source_sha
        ),
        "proof_workspace_artifact_fingerprint_sha256": (
            manifest.proof_workspace_artifact_fingerprint_sha256
        ),
        "proof_workspace_feature_jsonl_sha256": (
            manifest.proof_workspace_feature_jsonl_sha256
        ),
        "proof_workspace_feature_logical_fingerprint_sha256": (
            manifest.proof_workspace_feature_logical_fingerprint_sha256
        ),
        "proof_workspace_export_database_sha256": (
            manifest.proof_workspace_export_database_sha256
        ),
        "proof_workspace_export_database_wal_sha256": (
            manifest.proof_workspace_export_database_wal_sha256
        ),
        "observer_database_sha256": manifest.observer_database_sha256,
        "observer_database_wal_sha256": (
            manifest.observer_database_wal_sha256
        ),
        "training_economics_overlay_manifest_fingerprint_sha256": (
            manifest.training_economics_overlay_manifest_fingerprint_sha256
        ),
        "training_execution_cost_policy_fingerprint_sha256": (
            manifest.training_execution_cost_policy_fingerprint_sha256
        ),
        "training_bundle_fingerprint_sha256": (
            manifest.training_bundle_fingerprint_sha256
        ),
        "validation_policy_fingerprint_sha256": (
            manifest.validation_policy_fingerprint_sha256
        ),
        "hydration_artifact_fingerprint_sha256": (
            manifest.hydration_artifact_fingerprint_sha256
        ),
        "hydration_policy_fingerprint_sha256": (
            manifest.hydration_policy_fingerprint_sha256
        ),
        "population_validation_run_fingerprint_sha256": (
            manifest.population_validation_run_fingerprint_sha256
        ),
        "context_fingerprint_sha256": (
            manifest.context_fingerprint_sha256
        ),
        "request_fingerprint_sha256": (
            manifest.request_fingerprint_sha256
        ),
        "request_file_sha256": manifest.request_file_sha256,
        "first_champion_artifact_fingerprint_sha256": (
            manifest.first_champion_artifact_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": (
            manifest.champion_fingerprint_sha256
        ),
        "champion_version": manifest.champion_version,
        "selection_decision_reference": (
            manifest.selection_decision_reference
        ),
        "selection_decided_at_unix_ms": (
            manifest.selection_decided_at_unix_ms
        ),
        "selection_reason": manifest.selection_reason,
        "artifact_fingerprint_sha256": (
            manifest.artifact_fingerprint_sha256
        ),
    }


def _capture_database(database: Path) -> _DatabaseSnapshot:
    wal = Path(str(database) + "-wal")
    return _DatabaseSnapshot(
        database_sha256=_sha256_file_stable(database),
        wal_sha256=_sha256_file_stable(wal) if wal.is_file() else None,
    )


def _capture_training_economics(
    overlay: Path,
) -> _TrainingEconomicsSnapshot:
    manifest = overlay / "manifest.json"
    rows = overlay / "rows.jsonl"
    if manifest.is_symlink() or rows.is_symlink():
        raise ValueError("training economics overlay files must not be symlinks")
    if not manifest.is_file() or not rows.is_file():
        raise ValueError("training economics overlay files are missing")
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("training economics overlay manifest is malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("training economics overlay manifest must be an object")
    fingerprint = document.get("manifest_fingerprint_sha256")
    _require_sha256(
        "training_economics_overlay_manifest_fingerprint_sha256",
        fingerprint,
    )
    return _TrainingEconomicsSnapshot(
        manifest_fingerprint_sha256=fingerprint,
        manifest_file_sha256=_sha256_file_stable(manifest),
        rows_file_sha256=_sha256_file_stable(rows),
    )


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(f"{label} must have exactly one trailing newline")
    try:
        value = json.loads(
            payload,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    if _canonical(value) != payload:
        raise ValueError(f"{label} must use canonical JSON")
    return value


def _reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _canonical(value: object) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"source must be an existing regular file: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("source changed while fingerprinting")
    return digest.hexdigest()


def _require_source_sha(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(
            "proof workspace release source SHA must be 40 lowercase hex characters"
        )


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
