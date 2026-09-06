from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from .counterfactual_parquet import (
    COUNTERFACTUAL_DATASET_SCHEMA_NAME,
    COUNTERFACTUAL_DATASET_SCHEMA_VERSION,
    CounterfactualDatasetManifest,
    build_counterfactual_dataset,
    read_counterfactual_parquet,
)
from .counterfactual_source import load_entry_counterfactual_from_sqlite
from .counterfactuals import (
    CounterfactualAction,
    CounterfactualOutcomeSet,
    ExecutionStatus,
    label_entry_counterfactuals,
)
from .fast_training_economics import (
    FastTrainingEconomicsOverlayRow,
    FastTrainingEconomicsStatus,
    FastTrainingExecutionCostPolicy,
    build_entry_counterfactual_context_from_training_economics,
    read_fast_training_economics_overlay,
)
from .fast_training_features import (
    FAST_TRAINING_FEATURE_SCHEMA_NAME,
    FAST_TRAINING_FEATURE_SCHEMA_VERSION,
    FastTrainingFeatureDataset,
    feature_logical_fingerprint_sha256,
    read_fast_training_feature_jsonl,
    read_fast_training_feature_parquet,
    write_fast_training_feature_parquet,
)
from .fast_training_targets import (
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
    FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
    FuturePathTrainingLabelDataset,
    future_path_logical_fingerprint_sha256,
    load_future_path_training_labels_from_sqlite,
    read_future_path_training_parquet,
    write_future_path_training_parquet,
)


FAST_TRAINING_BUNDLE_SCHEMA_NAME = "shreks.fast_lane_training_bundle"
FAST_TRAINING_BUNDLE_SCHEMA_VERSION = 1

_FEATURES_FILENAME = "features.parquet"
_FUTURE_PATH_FILENAME = "future_path_labels.parquet"
_COUNTERFACTUAL_FILENAME = "counterfactual_action_labels.parquet"
_MANIFEST_FILENAME = "manifest.json"

_DECISION_ID_RE = re.compile(
    r"^(?P<signature>.+):(?P<ordinal>[0-9]+):h(?P<horizon>[0-9]+):v(?P<version>[0-9]+)$"
)

_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "feature_schema_name",
        "feature_schema_version",
        "future_path_schema_name",
        "future_path_schema_version",
        "future_path_label_version",
        "counterfactual_schema_name",
        "counterfactual_schema_version",
        "counterfactual_label_version",
        "decision_count",
        "future_path_label_row_count",
        "counterfactual_row_count",
        "min_decision_observed_at_unix_ms",
        "max_decision_observed_at_unix_ms",
        "feature_logical_fingerprint_sha256",
        "feature_source_jsonl_sha256",
        "future_path_logical_fingerprint_sha256",
        "counterfactual_logical_fingerprint_sha256",
        "bundle_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastTrainingBundleManifest:
    schema_name: str
    schema_version: int
    feature_schema_name: str
    feature_schema_version: int
    future_path_schema_name: str
    future_path_schema_version: int
    future_path_label_version: int
    counterfactual_schema_name: str
    counterfactual_schema_version: int
    counterfactual_label_version: int
    decision_count: int
    future_path_label_row_count: int
    counterfactual_row_count: int
    min_decision_observed_at_unix_ms: int
    max_decision_observed_at_unix_ms: int
    feature_logical_fingerprint_sha256: str
    feature_source_jsonl_sha256: str
    future_path_logical_fingerprint_sha256: str
    counterfactual_logical_fingerprint_sha256: str
    bundle_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_TRAINING_BUNDLE_SCHEMA_NAME:
            raise ValueError("training bundle schema name is incompatible")
        if self.schema_version != FAST_TRAINING_BUNDLE_SCHEMA_VERSION:
            raise ValueError("training bundle schema version is incompatible")
        if self.feature_schema_name != FAST_TRAINING_FEATURE_SCHEMA_NAME:
            raise ValueError("training bundle feature schema name is incompatible")
        if self.feature_schema_version != FAST_TRAINING_FEATURE_SCHEMA_VERSION:
            raise ValueError("training bundle feature schema version is incompatible")
        if self.future_path_schema_name != FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME:
            raise ValueError("training bundle future-path schema name is incompatible")
        if self.future_path_schema_version != FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION:
            raise ValueError("training bundle future-path schema version is incompatible")
        if self.counterfactual_schema_name != COUNTERFACTUAL_DATASET_SCHEMA_NAME:
            raise ValueError("training bundle counterfactual schema name is incompatible")
        if self.counterfactual_schema_version != COUNTERFACTUAL_DATASET_SCHEMA_VERSION:
            raise ValueError("training bundle counterfactual schema version is incompatible")
        _positive_int("future_path_label_version", self.future_path_label_version)
        _positive_int("counterfactual_label_version", self.counterfactual_label_version)
        _positive_int("decision_count", self.decision_count)
        _positive_int("future_path_label_row_count", self.future_path_label_row_count)
        _positive_int("counterfactual_row_count", self.counterfactual_row_count)
        _non_negative_int(
            "min_decision_observed_at_unix_ms", self.min_decision_observed_at_unix_ms
        )
        _non_negative_int(
            "max_decision_observed_at_unix_ms", self.max_decision_observed_at_unix_ms
        )
        if self.min_decision_observed_at_unix_ms > self.max_decision_observed_at_unix_ms:
            raise ValueError("training bundle decision timestamp range is incompatible")
        for name in (
            "feature_logical_fingerprint_sha256",
            "feature_source_jsonl_sha256",
            "future_path_logical_fingerprint_sha256",
            "counterfactual_logical_fingerprint_sha256",
            "bundle_fingerprint_sha256",
        ):
            _sha256(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class FastTrainingBundle:
    manifest: FastTrainingBundleManifest
    features: FastTrainingFeatureDataset
    future_path_labels: FuturePathTrainingLabelDataset
    counterfactual_rows: tuple[dict[str, object], ...]
    counterfactual_manifest: CounterfactualDatasetManifest


def build_fast_training_bundle_from_components(
    *,
    features: FastTrainingFeatureDataset,
    future_path_labels: FuturePathTrainingLabelDataset,
    counterfactual_outcome_sets: tuple[CounterfactualOutcomeSet, ...],
) -> FastTrainingBundle:
    """Assemble the sealed FL8.1 logical bundle without choosing a storage format."""
    if type(features) is not FastTrainingFeatureDataset:
        raise ValueError("features must be an exact FastTrainingFeatureDataset")
    if type(future_path_labels) is not FuturePathTrainingLabelDataset:
        raise ValueError(
            "future_path_labels must be an exact FuturePathTrainingLabelDataset"
        )
    if (
        not isinstance(counterfactual_outcome_sets, tuple)
        or not counterfactual_outcome_sets
        or not all(
            type(value) is CounterfactualOutcomeSet
            for value in counterfactual_outcome_sets
        )
    ):
        raise ValueError(
            "counterfactual_outcome_sets must be a non-empty tuple of exact CounterfactualOutcomeSet values"
        )

    actual_feature_fingerprint = feature_logical_fingerprint_sha256(
        features.records
    )
    if actual_feature_fingerprint != features.logical_fingerprint_sha256:
        raise ValueError("feature logical fingerprint does not match records")
    _sha256("feature source JSONL fingerprint", features.source_sha256)

    actual_future_path_fingerprint = future_path_logical_fingerprint_sha256(
        future_path_labels.labels
    )
    if (
        actual_future_path_fingerprint
        != future_path_labels.logical_fingerprint_sha256
    ):
        raise ValueError(
            "future-path logical fingerprint does not match labels"
        )

    counterfactual_rows, counterfactual_manifest = (
        build_counterfactual_dataset(counterfactual_outcome_sets)
    )
    _validate_bundle_joins(
        features,
        future_path_labels,
        counterfactual_rows,
        counterfactual_manifest,
        future_path_label_version=future_path_labels.label_version,
    )
    manifest = _build_manifest(
        features,
        future_path_labels,
        counterfactual_manifest,
        future_path_label_version=future_path_labels.label_version,
    )
    return FastTrainingBundle(
        manifest=manifest,
        features=features,
        future_path_labels=future_path_labels,
        counterfactual_rows=counterfactual_rows,
        counterfactual_manifest=counterfactual_manifest,
    )


def build_fast_training_bundle_from_runtime_sources(
    *,
    feature_jsonl_path: str | Path,
    sqlite_path: str | Path,
    future_path_label_version: int,
    counterfactual_base_quantity: float,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
) -> FastTrainingBundle:
    """Build the exact logical FL8.1 bundle from authenticated read-only sources."""
    _positive_int("future_path_label_version", future_path_label_version)
    if (
        isinstance(counterfactual_base_quantity, bool)
        or not isinstance(counterfactual_base_quantity, (int, float))
        or not math.isfinite(float(counterfactual_base_quantity))
        or counterfactual_base_quantity <= 0
    ):
        raise ValueError(
            "counterfactual_base_quantity must be positive and finite"
        )
    if type(training_execution_cost_policy) is not FastTrainingExecutionCostPolicy:
        raise ValueError(
            "training_execution_cost_policy must be an exact FastTrainingExecutionCostPolicy"
        )

    features = read_fast_training_feature_jsonl(feature_jsonl_path)
    future_path = load_future_path_training_labels_from_sqlite(
        sqlite_path,
        future_path_label_version=future_path_label_version,
    )
    overlay = read_fast_training_economics_overlay(
        training_economics_overlay_path
    )

    if (
        overlay.manifest.feature_source_jsonl_sha256
        != features.source_sha256
    ):
        raise ValueError(
            "training economics overlay feature-source fingerprint does not match runtime features"
        )
    if (
        overlay.manifest.future_path_logical_fingerprint_sha256
        != future_path.logical_fingerprint_sha256
    ):
        raise ValueError(
            "training economics overlay FL4 logical fingerprint does not match runtime labels"
        )
    if (
        overlay.manifest.future_path_label_version
        != future_path_label_version
    ):
        raise ValueError(
            "training economics overlay label version does not match runtime request"
        )
    if Decimal(overlay.manifest.counterfactual_base_quantity) != Decimal(
        str(counterfactual_base_quantity)
    ):
        raise ValueError(
            "training economics overlay counterfactual quantity does not match runtime request"
        )

    labels_by_key = {
        (
            label.decision_signature,
            label.decision_ordinal,
            label.horizon_ms,
            label.label_version,
        ): label
        for label in future_path.labels
    }
    if len(labels_by_key) != len(future_path.labels):
        raise ValueError(
            "runtime FL4 component contains duplicate decision/horizon identities"
        )
    overlay_by_key = {
        (
            row.decision_signature,
            row.decision_ordinal,
            row.horizon_ms,
            row.future_path_label_version,
        ): row
        for row in overlay.rows
    }
    if len(overlay_by_key) != len(overlay.rows):
        raise ValueError(
            "training economics overlay contains duplicate decision/horizon identities"
        )
    if set(overlay_by_key) != set(labels_by_key):
        raise ValueError(
            "training economics overlay population does not match FL4 exactly"
        )

    outcome_sets: list[CounterfactualOutcomeSet] = []
    projected_labels = []
    for key, label in labels_by_key.items():
        row = overlay_by_key[key]
        _validate_runtime_training_economics_row(row, label)

        loaded = load_entry_counterfactual_from_sqlite(
            sqlite_path,
            decision_signature=label.decision_signature,
            decision_ordinal=label.decision_ordinal,
            horizon_ms=label.horizon_ms,
            label_version=label.label_version,
            base_quantity=float(counterfactual_base_quantity),
        )
        provenance = loaded.provenance
        if (
            provenance.decision_signature != label.decision_signature
            or provenance.decision_ordinal != label.decision_ordinal
            or provenance.decision_sequence != label.decision_sequence
            or provenance.decision_observed_at_unix_ms
            != label.decision_observed_at_unix_ms
            or provenance.mint != label.decision_mint
            or provenance.quote_mint != label.decision_quote_mint
            or provenance.venue != label.decision_venue
            or provenance.horizon_ms != label.horizon_ms
            or provenance.future_path_label_version != label.label_version
            or provenance.completeness != label.completeness
            or provenance.endpoint_signature != label.endpoint_signature
            or provenance.endpoint_ordinal != label.endpoint_ordinal
            or provenance.endpoint_observed_at_unix_ms
            != label.endpoint_observed_at_unix_ms
        ):
            raise ValueError(
                "runtime counterfactual provenance does not match FL4 training label"
            )

        context = build_entry_counterfactual_context_from_training_economics(
            row,
            policy=training_execution_cost_policy,
            overlay_manifest_fingerprint_sha256=(
                overlay.manifest.manifest_fingerprint_sha256
            ),
            base_quantity=float(counterfactual_base_quantity),
            horizon_complete=label.completeness == "complete",
        )
        outcomes = label_entry_counterfactuals(context)
        outcome_sets.append(outcomes)

        buy_now = outcomes[0]
        if buy_now.action is not CounterfactualAction.BUY_NOW:
            raise ValueError(
                "runtime counterfactual outcome order does not begin with BUY_NOW"
            )
        endpoint_cost_adjusted_return_bps = (
            label.endpoint_cost_adjusted_return_bps
        )
        if (
            endpoint_cost_adjusted_return_bps is None
            and buy_now.execution_status is ExecutionStatus.EXECUTABLE
        ):
            if buy_now.return_bps is None:
                raise ValueError(
                    "executable runtime BUY_NOW outcome is missing return_bps"
                )
            endpoint_cost_adjusted_return_bps = buy_now.return_bps

        route_unavailability_observed = (
            label.route_unavailability_observed
        )
        if route_unavailability_observed is None:
            if (
                row.status
                is FastTrainingEconomicsStatus.EXIT_PROJECTION_UNAVAILABLE
            ):
                route_unavailability_observed = True
            elif row.exit_projection is not None:
                route_unavailability_observed = False

        projected_labels.append(
            replace(
                label,
                route_unavailability_observed=(
                    route_unavailability_observed
                ),
                endpoint_cost_adjusted_return_bps=(
                    endpoint_cost_adjusted_return_bps
                ),
            )
        )

    projected_label_tuple = tuple(projected_labels)
    projected_future_path = FuturePathTrainingLabelDataset(
        labels=projected_label_tuple,
        logical_fingerprint_sha256=(
            future_path_logical_fingerprint_sha256(
                projected_label_tuple
            )
        ),
        label_version=future_path.label_version,
    )

    return build_fast_training_bundle_from_components(
        features=features,
        future_path_labels=projected_future_path,
        counterfactual_outcome_sets=tuple(outcome_sets),
    )


def _validate_runtime_training_economics_row(
    row: FastTrainingEconomicsOverlayRow,
    label,
) -> None:
    if (
        row.decision_signature != label.decision_signature
        or row.decision_ordinal != label.decision_ordinal
        or row.decision_sequence != label.decision_sequence
        or row.decision_observed_at_unix_ms
        != label.decision_observed_at_unix_ms
        or row.mint != label.decision_mint
        or row.quote_mint != label.decision_quote_mint
        or row.venue != label.decision_venue
        or row.horizon_ms != label.horizon_ms
        or row.future_path_label_version != label.label_version
        or row.endpoint_signature != label.endpoint_signature
        or row.endpoint_ordinal != label.endpoint_ordinal
        or row.endpoint_observed_at_unix_ms
        != label.endpoint_observed_at_unix_ms
    ):
        raise ValueError(
            "training economics overlay row provenance does not match FL4 label"
        )



def write_fast_training_bundle(
    *,
    feature_jsonl_path: str | Path,
    sqlite_path: str | Path,
    counterfactual_parquet_path: str | Path,
    destination: str | Path,
    future_path_label_version: int,
) -> FastTrainingBundleManifest:
    destination_path = Path(destination)
    if destination_path.exists():
        raise FileExistsError("training bundle destination already exists; bundles are immutable")
    if not destination_path.name:
        raise ValueError("training bundle destination is invalid")

    features = read_fast_training_feature_jsonl(feature_jsonl_path)
    future_path = load_future_path_training_labels_from_sqlite(
        sqlite_path, future_path_label_version=future_path_label_version
    )
    counterfactual_rows, counterfactual_manifest = read_counterfactual_parquet(
        counterfactual_parquet_path
    )
    _validate_bundle_joins(
        features,
        future_path,
        counterfactual_rows,
        counterfactual_manifest,
        future_path_label_version=future_path_label_version,
    )
    manifest = _build_manifest(
        features,
        future_path,
        counterfactual_manifest,
        future_path_label_version=future_path_label_version,
    )

    parent = destination_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination_path.name}.tmp-", dir=parent)
    )
    try:
        write_fast_training_feature_parquet(features, temporary / _FEATURES_FILENAME)
        write_future_path_training_parquet(future_path, temporary / _FUTURE_PATH_FILENAME)
        shutil.copyfile(counterfactual_parquet_path, temporary / _COUNTERFACTUAL_FILENAME)
        (temporary / _MANIFEST_FILENAME).write_text(
            _manifest_json(manifest), encoding="utf-8"
        )
        if destination_path.exists():
            raise FileExistsError(
                "training bundle destination appeared during write; refusing to overwrite"
            )
        temporary.rename(destination_path)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def read_fast_training_bundle(path: str | Path) -> FastTrainingBundle:
    source = Path(path)
    if not source.is_dir():
        raise ValueError("training bundle path must be an existing directory")
    actual_names = {entry.name for entry in source.iterdir()}
    expected_names = {
        _FEATURES_FILENAME,
        _FUTURE_PATH_FILENAME,
        _COUNTERFACTUAL_FILENAME,
        _MANIFEST_FILENAME,
    }
    if actual_names != expected_names:
        raise ValueError("training bundle file set is incompatible")

    manifest = _read_manifest(source / _MANIFEST_FILENAME)
    features = read_fast_training_feature_parquet(source / _FEATURES_FILENAME)
    future_path = read_future_path_training_parquet(source / _FUTURE_PATH_FILENAME)
    counterfactual_rows, counterfactual_manifest = read_counterfactual_parquet(
        source / _COUNTERFACTUAL_FILENAME
    )
    _validate_bundle_joins(
        features,
        future_path,
        counterfactual_rows,
        counterfactual_manifest,
        future_path_label_version=manifest.future_path_label_version,
    )
    expected_manifest = _build_manifest(
        features,
        future_path,
        counterfactual_manifest,
        future_path_label_version=manifest.future_path_label_version,
    )
    if manifest != expected_manifest:
        raise ValueError("training bundle manifest does not match its component artifacts")
    return FastTrainingBundle(
        manifest=manifest,
        features=features,
        future_path_labels=future_path,
        counterfactual_rows=counterfactual_rows,
        counterfactual_manifest=counterfactual_manifest,
    )


def bundle_logical_fingerprint_sha256(manifest: FastTrainingBundleManifest) -> str:
    if type(manifest) is not FastTrainingBundleManifest:
        raise ValueError("manifest must be an exact FastTrainingBundleManifest")
    payload = asdict(manifest)
    payload.pop("bundle_fingerprint_sha256")
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_bundle_joins(
    features: FastTrainingFeatureDataset,
    future_path: FuturePathTrainingLabelDataset,
    counterfactual_rows: tuple[dict[str, object], ...],
    counterfactual_manifest: CounterfactualDatasetManifest,
    *,
    future_path_label_version: int,
) -> None:
    if future_path.label_version != future_path_label_version:
        raise ValueError("FL4 label version does not match requested training bundle version")
    if not counterfactual_rows:
        raise ValueError("counterfactual training component cannot be empty")

    feature_by_identity = {record.decision_identity: record for record in features.records}
    if len(feature_by_identity) != len(features.records):
        raise ValueError("feature component contains duplicate decision identities")

    label_decision_identities = {label.decision_identity for label in future_path.labels}
    if set(feature_by_identity) != label_decision_identities:
        raise ValueError("feature and FL4 decision identities do not match exactly")

    labels_by_key = {
        (
            label.decision_signature,
            label.decision_ordinal,
            label.horizon_ms,
            label.label_version,
        ): label
        for label in future_path.labels
    }
    if len(labels_by_key) != len(future_path.labels):
        raise ValueError("FL4 component contains duplicate decision/horizon identities")

    for row in counterfactual_rows:
        decision_id = row.get("decision_id")
        if not isinstance(decision_id, str):
            raise ValueError("counterfactual decision_id is incompatible")
        signature, ordinal, horizon, version = _parse_entry_decision_id(decision_id)
        key = (signature, ordinal, horizon, version)
        label = labels_by_key.get(key)
        if label is None:
            raise ValueError(
                "counterfactual decision/horizon does not map to an FL4 training label"
            )
        if version != future_path_label_version:
            raise ValueError("counterfactual decision label version does not match FL4")
        if row.get("mint") != label.decision_mint:
            raise ValueError("counterfactual mint does not match its FL4 decision")
        if row.get("quote_mint") != label.decision_quote_mint:
            raise ValueError("counterfactual quote mint does not match its FL4 decision")
        if row.get("horizon_ms") != label.horizon_ms:
            raise ValueError("counterfactual horizon does not match its FL4 decision")
        if row.get("label_version") != counterfactual_manifest.label_version:
            raise ValueError("counterfactual row label version contradicts its dataset")
        action_time = row.get("action_observed_at_unix_ms")
        if isinstance(action_time, bool) or not isinstance(action_time, int):
            raise ValueError("counterfactual action timestamp is incompatible")
        if not (
            label.decision_observed_at_unix_ms
            <= action_time
            <= label.decision_observed_at_unix_ms + label.horizon_ms
        ):
            raise ValueError(
                "counterfactual action timestamp is outside its FL4 decision horizon"
            )


def _parse_entry_decision_id(decision_id: str) -> tuple[str, int, int, int]:
    match = _DECISION_ID_RE.fullmatch(decision_id)
    if match is None:
        raise ValueError(
            "counterfactual decision_id is not a canonical FL4 entry decision identity"
        )
    signature = match.group("signature")
    if not signature:
        raise ValueError("counterfactual decision signature cannot be empty")
    ordinal = int(match.group("ordinal"))
    horizon = int(match.group("horizon"))
    version = int(match.group("version"))
    if horizon <= 0 or version <= 0:
        raise ValueError("counterfactual decision horizon/version must be positive")
    return signature, ordinal, horizon, version


def _build_manifest(
    features: FastTrainingFeatureDataset,
    future_path: FuturePathTrainingLabelDataset,
    counterfactual_manifest: CounterfactualDatasetManifest,
    *,
    future_path_label_version: int,
) -> FastTrainingBundleManifest:
    decision_times = tuple(
        record.decision_observed_at_unix_ms for record in features.records
    )
    values = dict(
        schema_name=FAST_TRAINING_BUNDLE_SCHEMA_NAME,
        schema_version=FAST_TRAINING_BUNDLE_SCHEMA_VERSION,
        feature_schema_name=FAST_TRAINING_FEATURE_SCHEMA_NAME,
        feature_schema_version=FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        future_path_schema_name=FUTURE_PATH_TRAINING_DATASET_SCHEMA_NAME,
        future_path_schema_version=FUTURE_PATH_TRAINING_DATASET_SCHEMA_VERSION,
        future_path_label_version=future_path_label_version,
        counterfactual_schema_name=counterfactual_manifest.schema_name,
        counterfactual_schema_version=counterfactual_manifest.schema_version,
        counterfactual_label_version=counterfactual_manifest.label_version,
        decision_count=len(features.records),
        future_path_label_row_count=len(future_path.labels),
        counterfactual_row_count=counterfactual_manifest.row_count,
        min_decision_observed_at_unix_ms=min(decision_times),
        max_decision_observed_at_unix_ms=max(decision_times),
        feature_logical_fingerprint_sha256=features.logical_fingerprint_sha256,
        feature_source_jsonl_sha256=features.source_sha256,
        future_path_logical_fingerprint_sha256=future_path.logical_fingerprint_sha256,
        counterfactual_logical_fingerprint_sha256=counterfactual_manifest.dataset_fingerprint_sha256,
    )
    provisional = FastTrainingBundleManifest(
        **values,
        bundle_fingerprint_sha256="0" * 64,
    )
    return FastTrainingBundleManifest(
        **values,
        bundle_fingerprint_sha256=bundle_logical_fingerprint_sha256(provisional),
    )


def _manifest_json(manifest: FastTrainingBundleManifest) -> str:
    return json.dumps(
        asdict(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _read_manifest(path: Path) -> FastTrainingBundleManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("training bundle manifest is unreadable or invalid JSON") from exc
    if not isinstance(value, dict) or frozenset(value) != _MANIFEST_KEYS:
        raise ValueError("training bundle manifest keys are incompatible")
    try:
        manifest = FastTrainingBundleManifest(**value)
    except TypeError as exc:
        raise ValueError("training bundle manifest fields are incompatible") from exc
    actual = bundle_logical_fingerprint_sha256(manifest)
    if actual != manifest.bundle_fingerprint_sha256:
        raise ValueError("training bundle logical fingerprint does not match manifest")
    return manifest


def _positive_int(name: str, value: object) -> int:
    result = _non_negative_int(name, value)
    if result == 0:
        raise ValueError(f"{name} must be positive")
    return result


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value
