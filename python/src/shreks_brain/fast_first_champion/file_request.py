from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

from shreks_brain.fast_champion import (
    FastForecastChampionArtifact,
    read_fast_forecast_champion,
    write_fast_forecast_champion,
)
from shreks_brain.fast_evaluation import (
    FastForecastEvaluationPartition,
    FastForecastEvaluationPolicy,
    FastForecastEvaluationReport,
    read_fast_forecast_evaluation_report,
    write_fast_forecast_evaluation_report,
)
from shreks_brain.fast_validation import (
    FastChronologicalFold,
    FastChronologicalValidationPolicy,
)
from shreks_brain.research.fast_training_bundle import (
    build_fast_training_bundle_from_runtime_sources,
)

from .builder import build_fast_first_champion
from .context_corpus import (
    read_fast_forecast_evaluation_context_corpus,
)


FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME = (
    "shreks.fast_first_champion_file_request"
)
FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION = 1
FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_NAME = (
    "shreks.fast_first_champion_artifact"
)
FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_VERSION = 1

_REQUEST_FILE = "request.json"
_CHAMPION_FILE = "champion.json"
_MANIFEST_FILE = "manifest.json"

_REQUEST_FIELDS = (
    "feature_jsonl_path",
    "observer_database_path",
    "context_corpus_path",
    "destination_path",
    "future_path_label_version",
    "counterfactual_base_quantity",
    "validation_policy",
    "evaluation_policy",
    "champion_version",
    "decision_reference",
    "decided_at_unix_ms",
    "reason",
    "horizon_ms",
    "model_version_prefix",
    "training_policy_version",
    "minimum_test_scored_observations",
)
_TOP_REQUEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request",
        "request_fingerprint_sha256",
    }
)
_VALIDATION_POLICY_KEYS = frozenset({"version", "folds"})
_FOLD_KEYS = frozenset(
    {
        "name",
        "training_started_at_unix_ms",
        "training_ended_at_unix_ms",
        "validation_started_at_unix_ms",
        "validation_ended_at_unix_ms",
        "test_started_at_unix_ms",
        "test_ended_at_unix_ms",
    }
)
_EVALUATION_POLICY_KEYS = frozenset(
    {
        "version",
        "partition",
        "probability_bucket_count",
        "liquidity_capacity_quote_boundaries",
        "round_trip_cost_bps_boundaries",
        "binary_log_loss_clip_epsilon",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request_fingerprint_sha256",
        "request_file_sha256",
        "feature_jsonl_sha256",
        "observer_database_sha256",
        "observer_database_wal_sha256",
        "context_corpus_file_sha256",
        "context_fingerprint_sha256",
        "training_bundle_fingerprint_sha256",
        "champion_fingerprint_sha256",
        "champion_file_sha256",
        "evaluation_reports",
        "artifact_fingerprint_sha256",
    }
)
_REPORT_ENTRY_KEYS = frozenset(
    {
        "target",
        "horizon_ms",
        "file_name",
        "file_sha256",
        "validation_run_fingerprint_sha256",
        "evaluation_report_fingerprint_sha256",
        "test_scored_observation_count",
        "test_target_unavailable_count",
    }
)


@dataclass(frozen=True, slots=True)
class FastFirstChampionFileRequest:
    schema_name: str
    schema_version: int
    feature_jsonl_path: str
    observer_database_path: str
    context_corpus_path: str
    destination_path: str
    future_path_label_version: int
    counterfactual_base_quantity: float
    validation_policy: FastChronologicalValidationPolicy
    evaluation_policy: FastForecastEvaluationPolicy
    champion_version: str
    decision_reference: str
    decided_at_unix_ms: int
    reason: str
    horizon_ms: int
    model_version_prefix: str
    training_policy_version: str
    minimum_test_scored_observations: int
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME:
            raise ValueError("unsupported first champion file request schema_name")
        if self.schema_version != FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported first champion file request schema_version")
        for name in (
            "feature_jsonl_path",
            "observer_database_path",
            "context_corpus_path",
            "destination_path",
            "champion_version",
            "decision_reference",
            "reason",
            "model_version_prefix",
            "training_policy_version",
        ):
            _require_non_empty(name, getattr(self, name))
        _require_positive_int(
            "future_path_label_version",
            self.future_path_label_version,
        )
        _require_positive_numeric(
            "counterfactual_base_quantity",
            self.counterfactual_base_quantity,
        )
        if type(self.validation_policy) is not FastChronologicalValidationPolicy:
            raise ValueError(
                "validation_policy must be exact FastChronologicalValidationPolicy"
            )
        if type(self.evaluation_policy) is not FastForecastEvaluationPolicy:
            raise ValueError(
                "evaluation_policy must be exact FastForecastEvaluationPolicy"
            )
        if (
            self.evaluation_policy.partition
            is not FastForecastEvaluationPartition.TEST
        ):
            raise ValueError("first champion file request requires TEST evaluation")
        _require_non_negative_int("decided_at_unix_ms", self.decided_at_unix_ms)
        _require_positive_int("horizon_ms", self.horizon_ms)
        _require_positive_int(
            "minimum_test_scored_observations",
            self.minimum_test_scored_observations,
        )
        _require_sha256(
            "request_fingerprint_sha256",
            self.request_fingerprint_sha256,
        )
        if self.request_fingerprint_sha256 != _request_fingerprint(self):
            raise ValueError("first champion file request fingerprint mismatch")


@dataclass(frozen=True, slots=True)
class FastFirstChampionEvaluationEvidenceEntry:
    target: str
    horizon_ms: int
    file_name: str
    file_sha256: str
    validation_run_fingerprint_sha256: str
    evaluation_report_fingerprint_sha256: str
    test_scored_observation_count: int
    test_target_unavailable_count: int

    def __post_init__(self) -> None:
        _require_non_empty("target", self.target)
        _require_positive_int("horizon_ms", self.horizon_ms)
        _require_leaf_name("file_name", self.file_name)
        if not self.file_name.startswith("evaluation-") or not self.file_name.endswith(
            ".json"
        ):
            raise ValueError("evaluation evidence file_name is invalid")
        for name in (
            "file_sha256",
            "validation_run_fingerprint_sha256",
            "evaluation_report_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        _require_positive_int(
            "test_scored_observation_count",
            self.test_scored_observation_count,
        )
        _require_non_negative_int(
            "test_target_unavailable_count",
            self.test_target_unavailable_count,
        )


@dataclass(frozen=True, slots=True)
class FastFirstChampionArtifactManifest:
    schema_name: str
    schema_version: int
    request_fingerprint_sha256: str
    request_file_sha256: str
    feature_jsonl_sha256: str
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    context_corpus_file_sha256: str
    context_fingerprint_sha256: str
    training_bundle_fingerprint_sha256: str
    champion_fingerprint_sha256: str
    champion_file_sha256: str
    evaluation_reports: tuple[FastFirstChampionEvaluationEvidenceEntry, ...]
    artifact_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_NAME:
            raise ValueError("unsupported first champion artifact schema_name")
        if self.schema_version != FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported first champion artifact schema_version")
        for name in (
            "request_fingerprint_sha256",
            "request_file_sha256",
            "feature_jsonl_sha256",
            "observer_database_sha256",
            "context_corpus_file_sha256",
            "context_fingerprint_sha256",
            "training_bundle_fingerprint_sha256",
            "champion_fingerprint_sha256",
            "champion_file_sha256",
            "artifact_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))
        if self.observer_database_wal_sha256 is not None:
            _require_sha256(
                "observer_database_wal_sha256",
                self.observer_database_wal_sha256,
            )
        if (
            not isinstance(self.evaluation_reports, tuple)
            or len(self.evaluation_reports) != 5
            or not all(
                type(value) is FastFirstChampionEvaluationEvidenceEntry
                for value in self.evaluation_reports
            )
        ):
            raise ValueError(
                "first champion artifact requires exactly five evaluation reports"
            )
        names = tuple(value.file_name for value in self.evaluation_reports)
        keys = tuple(
            (value.target, value.horizon_ms) for value in self.evaluation_reports
        )
        if names != tuple(sorted(names)) or len(set(names)) != len(names):
            raise ValueError(
                "first champion evaluation report files must use unique lexical names"
            )
        if len(set(keys)) != len(keys):
            raise ValueError(
                "first champion evaluation report target/horizon keys must be unique"
            )


@dataclass(frozen=True, slots=True)
class FastFirstChampionArtifact:
    path: Path
    manifest: FastFirstChampionArtifactManifest
    request: FastFirstChampionFileRequest
    champion: FastForecastChampionArtifact
    evaluation_reports: tuple[FastForecastEvaluationReport, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be Path")
        if type(self.manifest) is not FastFirstChampionArtifactManifest:
            raise ValueError(
                "manifest must be exact FastFirstChampionArtifactManifest"
            )
        if type(self.request) is not FastFirstChampionFileRequest:
            raise ValueError(
                "request must be exact FastFirstChampionFileRequest"
            )
        if type(self.champion) is not FastForecastChampionArtifact:
            raise ValueError("champion must be exact FastForecastChampionArtifact")
        if (
            not isinstance(self.evaluation_reports, tuple)
            or len(self.evaluation_reports) != 5
            or not all(
                type(value) is FastForecastEvaluationReport
                for value in self.evaluation_reports
            )
        ):
            raise ValueError(
                "evaluation_reports must contain exactly five FastForecastEvaluationReport values"
            )


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    feature_jsonl_sha256: str
    observer_database_sha256: str
    observer_database_wal_sha256: str | None
    context_corpus_file_sha256: str


def build_fast_first_champion_file_request(
    *,
    feature_jsonl_path: str,
    observer_database_path: str,
    context_corpus_path: str,
    destination_path: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float,
    validation_policy: FastChronologicalValidationPolicy,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    horizon_ms: int,
    model_version_prefix: str,
    training_policy_version: str,
    minimum_test_scored_observations: int,
) -> FastFirstChampionFileRequest:
    material = _request_document_from_values(
        feature_jsonl_path=feature_jsonl_path,
        observer_database_path=observer_database_path,
        context_corpus_path=context_corpus_path,
        destination_path=destination_path,
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
        minimum_test_scored_observations=minimum_test_scored_observations,
    )
    return FastFirstChampionFileRequest(
        schema_name=FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME,
        schema_version=FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION,
        feature_jsonl_path=feature_jsonl_path,
        observer_database_path=observer_database_path,
        context_corpus_path=context_corpus_path,
        destination_path=destination_path,
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
        minimum_test_scored_observations=minimum_test_scored_observations,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_first_champion_file_request(
    request: FastFirstChampionFileRequest,
) -> str:
    if type(request) is not FastFirstChampionFileRequest:
        raise ValueError(
            "request must be exact FastFirstChampionFileRequest"
        )
    if request.request_fingerprint_sha256 != _request_fingerprint(request):
        raise ValueError("first champion file request fingerprint mismatch before encode")
    document = {
        "schema_name": request.schema_name,
        "schema_version": request.schema_version,
        "request": _request_document(request),
        "request_fingerprint_sha256": request.request_fingerprint_sha256,
    }
    return _canonical(document)


def decode_fast_first_champion_file_request(
    payload: str,
) -> FastFirstChampionFileRequest:
    document = _load_canonical(
        payload,
        label="first champion file request",
    )
    if frozenset(document) != _TOP_REQUEST_KEYS:
        raise ValueError(
            "first champion file request has unknown or missing top-level fields"
        )
    if document["schema_name"] != FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_NAME:
        raise ValueError("unsupported first champion file request schema_name")
    if (
        document["schema_version"]
        != FAST_FIRST_CHAMPION_FILE_REQUEST_SCHEMA_VERSION
    ):
        raise ValueError("unsupported first champion file request schema_version")
    raw = document["request"]
    if (
        not isinstance(raw, dict)
        or frozenset(raw) != frozenset(_REQUEST_FIELDS)
        or len(raw) != len(_REQUEST_FIELDS)
    ):
        raise ValueError(
            "first champion file request fields must match the sealed schema exactly"
        )
    validation_policy = _decode_validation_policy(raw["validation_policy"])
    evaluation_policy = _decode_evaluation_policy(raw["evaluation_policy"])
    try:
        request = FastFirstChampionFileRequest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            feature_jsonl_path=_text(raw["feature_jsonl_path"], "feature_jsonl_path"),
            observer_database_path=_text(
                raw["observer_database_path"],
                "observer_database_path",
            ),
            context_corpus_path=_text(
                raw["context_corpus_path"],
                "context_corpus_path",
            ),
            destination_path=_text(raw["destination_path"], "destination_path"),
            future_path_label_version=_integer(
                raw["future_path_label_version"],
                "future_path_label_version",
            ),
            counterfactual_base_quantity=_decode_numeric(
                raw["counterfactual_base_quantity"],
                "counterfactual_base_quantity",
            ),
            validation_policy=validation_policy,
            evaluation_policy=evaluation_policy,
            champion_version=_text(raw["champion_version"], "champion_version"),
            decision_reference=_text(
                raw["decision_reference"],
                "decision_reference",
            ),
            decided_at_unix_ms=_integer(
                raw["decided_at_unix_ms"],
                "decided_at_unix_ms",
            ),
            reason=_text(raw["reason"], "reason"),
            horizon_ms=_integer(raw["horizon_ms"], "horizon_ms"),
            model_version_prefix=_text(
                raw["model_version_prefix"],
                "model_version_prefix",
            ),
            training_policy_version=_text(
                raw["training_policy_version"],
                "training_policy_version",
            ),
            minimum_test_scored_observations=_integer(
                raw["minimum_test_scored_observations"],
                "minimum_test_scored_observations",
            ),
            request_fingerprint_sha256=_text(
                document["request_fingerprint_sha256"],
                "request_fingerprint_sha256",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"first champion file request content is incompatible: {exc}"
        ) from exc
    if encode_fast_first_champion_file_request(request) != payload:
        raise ValueError("first champion file request must use canonical JSON")
    return request


def write_fast_first_champion_file_request(
    request: FastFirstChampionFileRequest,
    path: str | Path,
) -> None:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(
            "first champion file request destination already exists"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        encode_fast_first_champion_file_request(request),
        encoding="utf-8",
    )


def run_fast_first_champion_file_request(
    request_path: str | Path,
) -> FastFirstChampionArtifact:
    source = Path(request_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(
            "first champion file request path must be an existing file"
        )
    request_payload = source.read_text(encoding="utf-8")
    request = decode_fast_first_champion_file_request(request_payload)
    base = source.parent

    feature_path = _resolve_source(base, request.feature_jsonl_path)
    database_path = _resolve_source(base, request.observer_database_path)
    context_path = _resolve_source(base, request.context_corpus_path)
    destination = _resolve_destination(base, request.destination_path)
    if destination.exists():
        raise FileExistsError(
            "first champion artifact destination already exists"
        )

    before = _capture_sources(
        feature_path=feature_path,
        database_path=database_path,
        context_path=context_path,
    )
    context_corpus = read_fast_forecast_evaluation_context_corpus(
        context_path
    )
    bundle = build_fast_training_bundle_from_runtime_sources(
        feature_jsonl_path=feature_path,
        sqlite_path=database_path,
        future_path_label_version=request.future_path_label_version,
        counterfactual_base_quantity=request.counterfactual_base_quantity,
    )
    if bundle.features.source_sha256 != before.feature_jsonl_sha256:
        raise ValueError(
            "runtime training bundle feature source fingerprint mismatch"
        )
    result = build_fast_first_champion(
        bundle=bundle,
        contexts=context_corpus.contexts,
        validation_policy=request.validation_policy,
        evaluation_policy=request.evaluation_policy,
        champion_version=request.champion_version,
        decision_reference=request.decision_reference,
        decided_at_unix_ms=request.decided_at_unix_ms,
        reason=request.reason,
        horizon_ms=request.horizon_ms,
        model_version_prefix=request.model_version_prefix,
        training_policy_version=request.training_policy_version,
        minimum_test_scored_observations=(
            request.minimum_test_scored_observations
        ),
    )
    if any(
        report.context_fingerprint_sha256
        != context_corpus.context_fingerprint_sha256
        for report in result.evaluation_reports
    ):
        raise ValueError(
            "first champion TEST report context fingerprint mismatch"
        )

    after = _capture_sources(
        feature_path=feature_path,
        database_path=database_path,
        context_path=context_path,
    )
    if after != before:
        raise ValueError(
            "first champion source fingerprint changed during execution"
        )
    if source.read_text(encoding="utf-8") != request_payload:
        raise ValueError(
            "first champion request changed during execution"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        (staging / _REQUEST_FILE).write_text(
            request_payload,
            encoding="utf-8",
        )
        write_fast_forecast_champion(
            result.champion,
            staging / _CHAMPION_FILE,
        )
        report_entries: list[FastFirstChampionEvaluationEvidenceEntry] = []
        for report in result.evaluation_reports:
            file_name = _evaluation_file_name(report)
            report_path = staging / file_name
            write_fast_forecast_evaluation_report(report, report_path)
            report_entries.append(
                FastFirstChampionEvaluationEvidenceEntry(
                    target=report.target.value,
                    horizon_ms=report.horizon_ms,
                    file_name=file_name,
                    file_sha256=_sha256_file(report_path),
                    validation_run_fingerprint_sha256=(
                        report.validation_run_fingerprint_sha256
                    ),
                    evaluation_report_fingerprint_sha256=(
                        report.evaluation_report_fingerprint_sha256
                    ),
                    test_scored_observation_count=(
                        report.overall.scored_observation_count
                    ),
                    test_target_unavailable_count=(
                        report.overall.target_unavailable_count
                    ),
                )
            )
        report_entries.sort(key=lambda value: value.file_name)

        material = {
            "schema_name": FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_NAME,
            "schema_version": FAST_FIRST_CHAMPION_ARTIFACT_SCHEMA_VERSION,
            "request_fingerprint_sha256": request.request_fingerprint_sha256,
            "request_file_sha256": _sha256_file(staging / _REQUEST_FILE),
            "feature_jsonl_sha256": before.feature_jsonl_sha256,
            "observer_database_sha256": before.observer_database_sha256,
            "observer_database_wal_sha256": (
                before.observer_database_wal_sha256
            ),
            "context_corpus_file_sha256": (
                before.context_corpus_file_sha256
            ),
            "context_fingerprint_sha256": (
                context_corpus.context_fingerprint_sha256
            ),
            "training_bundle_fingerprint_sha256": (
                bundle.manifest.bundle_fingerprint_sha256
            ),
            "champion_fingerprint_sha256": (
                result.champion.champion_fingerprint_sha256
            ),
            "champion_file_sha256": _sha256_file(staging / _CHAMPION_FILE),
            "evaluation_reports": [
                _report_entry_document(value) for value in report_entries
            ],
        }
        manifest = FastFirstChampionArtifactManifest(
            schema_name=material["schema_name"],
            schema_version=material["schema_version"],
            request_fingerprint_sha256=material[
                "request_fingerprint_sha256"
            ],
            request_file_sha256=material["request_file_sha256"],
            feature_jsonl_sha256=material["feature_jsonl_sha256"],
            observer_database_sha256=material[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=material[
                "observer_database_wal_sha256"
            ],
            context_corpus_file_sha256=material[
                "context_corpus_file_sha256"
            ],
            context_fingerprint_sha256=material[
                "context_fingerprint_sha256"
            ],
            training_bundle_fingerprint_sha256=material[
                "training_bundle_fingerprint_sha256"
            ],
            champion_fingerprint_sha256=material[
                "champion_fingerprint_sha256"
            ],
            champion_file_sha256=material["champion_file_sha256"],
            evaluation_reports=tuple(report_entries),
            artifact_fingerprint_sha256=_sha256_canonical(material),
        )
        (staging / _MANIFEST_FILE).write_text(
            _canonical(_manifest_document(manifest)),
            encoding="utf-8",
        )

        verified = read_fast_first_champion_artifact(staging)
        if verified.manifest != manifest:
            raise ValueError(
                "staged first champion artifact did not round-trip"
            )
        if destination.exists():
            raise FileExistsError(
                "first champion artifact destination appeared during write"
            )
        staging.rename(destination)
        return read_fast_first_champion_artifact(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def read_fast_first_champion_artifact(
    path: str | Path,
) -> FastFirstChampionArtifact:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            "first champion artifact source must be an existing directory"
        )
    manifest_path = root / _MANIFEST_FILE
    if not manifest_path.is_file():
        raise ValueError("first champion artifact manifest is missing")
    document = _load_canonical(
        manifest_path.read_text(encoding="utf-8"),
        label="first champion artifact manifest",
    )
    if frozenset(document) != _MANIFEST_KEYS:
        raise ValueError(
            "first champion artifact manifest has unknown or missing fields"
        )
    rows_raw = document["evaluation_reports"]
    if not isinstance(rows_raw, list):
        raise ValueError(
            "first champion artifact evaluation_reports must be an array"
        )
    rows = tuple(_report_entry_from_document(value) for value in rows_raw)
    try:
        manifest = FastFirstChampionArtifactManifest(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            request_fingerprint_sha256=document[
                "request_fingerprint_sha256"
            ],
            request_file_sha256=document["request_file_sha256"],
            feature_jsonl_sha256=document["feature_jsonl_sha256"],
            observer_database_sha256=document[
                "observer_database_sha256"
            ],
            observer_database_wal_sha256=document[
                "observer_database_wal_sha256"
            ],
            context_corpus_file_sha256=document[
                "context_corpus_file_sha256"
            ],
            context_fingerprint_sha256=document[
                "context_fingerprint_sha256"
            ],
            training_bundle_fingerprint_sha256=document[
                "training_bundle_fingerprint_sha256"
            ],
            champion_fingerprint_sha256=document[
                "champion_fingerprint_sha256"
            ],
            champion_file_sha256=document["champion_file_sha256"],
            evaluation_reports=rows,
            artifact_fingerprint_sha256=document[
                "artifact_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"first champion artifact manifest is invalid: {exc}"
        ) from exc

    material = dict(document)
    claimed = material.pop("artifact_fingerprint_sha256")
    if _sha256_canonical(material) != claimed:
        raise ValueError("first champion artifact fingerprint mismatch")

    expected_entries = {
        _REQUEST_FILE,
        _CHAMPION_FILE,
        _MANIFEST_FILE,
        *(value.file_name for value in manifest.evaluation_reports),
    }
    if {value.name for value in root.iterdir()} != expected_entries:
        raise ValueError(
            "first champion artifact has unknown or missing entries"
        )

    request_path = root / _REQUEST_FILE
    champion_path = root / _CHAMPION_FILE
    if _sha256_file(request_path) != manifest.request_file_sha256:
        raise ValueError("first champion request file hash mismatch")
    if _sha256_file(champion_path) != manifest.champion_file_sha256:
        raise ValueError("first champion file hash mismatch")

    request = decode_fast_first_champion_file_request(
        request_path.read_text(encoding="utf-8")
    )
    if (
        request.request_fingerprint_sha256
        != manifest.request_fingerprint_sha256
    ):
        raise ValueError(
            "first champion request fingerprint does not match manifest"
        )
    champion = read_fast_forecast_champion(champion_path)
    if (
        champion.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "first champion fingerprint does not match manifest"
        )
    if (
        champion.training_bundle_fingerprint_sha256
        != manifest.training_bundle_fingerprint_sha256
    ):
        raise ValueError(
            "first champion training bundle fingerprint does not match manifest"
        )
    if (
        champion.champion_version != request.champion_version
        or champion.selection.decision_reference != request.decision_reference
        or champion.selection.decided_at_unix_ms != request.decided_at_unix_ms
        or champion.selection.reason != request.reason
    ):
        raise ValueError(
            "first champion selection does not match sealed request"
        )

    reports: list[FastForecastEvaluationReport] = []
    for entry in manifest.evaluation_reports:
        report_path = root / entry.file_name
        if _sha256_file(report_path) != entry.file_sha256:
            raise ValueError(
                "first champion evaluation report file hash mismatch"
            )
        report = read_fast_forecast_evaluation_report(report_path)
        if (
            report.target.value != entry.target
            or report.horizon_ms != entry.horizon_ms
            or report.validation_run_fingerprint_sha256
            != entry.validation_run_fingerprint_sha256
            or report.evaluation_report_fingerprint_sha256
            != entry.evaluation_report_fingerprint_sha256
            or report.overall.scored_observation_count
            != entry.test_scored_observation_count
            or report.overall.target_unavailable_count
            != entry.test_target_unavailable_count
        ):
            raise ValueError(
                "first champion evaluation report does not match manifest"
            )
        if report.context_fingerprint_sha256 != manifest.context_fingerprint_sha256:
            raise ValueError(
                "first champion evaluation report context fingerprint mismatch"
            )
        if (
            report.training_bundle_fingerprint_sha256
            != manifest.training_bundle_fingerprint_sha256
        ):
            raise ValueError(
                "first champion evaluation report bundle fingerprint mismatch"
            )
        if report.evaluation_policy.partition is not FastForecastEvaluationPartition.TEST:
            raise ValueError(
                "first champion artifact contains a non-TEST evaluation report"
            )
        member = champion.member_for(report.target, report.horizon_ms)
        if (
            member.validation_run_fingerprint_sha256
            != report.validation_run_fingerprint_sha256
            or member.test_evaluation_report_fingerprint_sha256
            != report.evaluation_report_fingerprint_sha256
            or member.test_scored_observation_count
            != report.overall.scored_observation_count
            or member.test_target_unavailable_count
            != report.overall.target_unavailable_count
        ):
            raise ValueError(
                "first champion member evidence does not match TEST report"
            )
        reports.append(report)

    reports.sort(key=lambda value: _evaluation_file_name(value))
    return FastFirstChampionArtifact(
        path=root,
        manifest=manifest,
        request=request,
        champion=champion,
        evaluation_reports=tuple(reports),
    )


def _request_fingerprint(
    request: FastFirstChampionFileRequest,
) -> str:
    return _sha256_canonical(_request_document(request))


def _request_document(
    request: FastFirstChampionFileRequest,
) -> dict[str, object]:
    return _request_document_from_values(
        feature_jsonl_path=request.feature_jsonl_path,
        observer_database_path=request.observer_database_path,
        context_corpus_path=request.context_corpus_path,
        destination_path=request.destination_path,
        future_path_label_version=request.future_path_label_version,
        counterfactual_base_quantity=request.counterfactual_base_quantity,
        validation_policy=request.validation_policy,
        evaluation_policy=request.evaluation_policy,
        champion_version=request.champion_version,
        decision_reference=request.decision_reference,
        decided_at_unix_ms=request.decided_at_unix_ms,
        reason=request.reason,
        horizon_ms=request.horizon_ms,
        model_version_prefix=request.model_version_prefix,
        training_policy_version=request.training_policy_version,
        minimum_test_scored_observations=request.minimum_test_scored_observations,
    )


def _request_document_from_values(
    *,
    feature_jsonl_path: str,
    observer_database_path: str,
    context_corpus_path: str,
    destination_path: str,
    future_path_label_version: int,
    counterfactual_base_quantity: float,
    validation_policy: FastChronologicalValidationPolicy,
    evaluation_policy: FastForecastEvaluationPolicy,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    horizon_ms: int,
    model_version_prefix: str,
    training_policy_version: str,
    minimum_test_scored_observations: int,
) -> dict[str, object]:
    return {
        "feature_jsonl_path": feature_jsonl_path,
        "observer_database_path": observer_database_path,
        "context_corpus_path": context_corpus_path,
        "destination_path": destination_path,
        "future_path_label_version": future_path_label_version,
        "counterfactual_base_quantity": _encode_numeric(
            counterfactual_base_quantity
        ),
        "validation_policy": _validation_policy_document(validation_policy),
        "evaluation_policy": _evaluation_policy_document(evaluation_policy),
        "champion_version": champion_version,
        "decision_reference": decision_reference,
        "decided_at_unix_ms": decided_at_unix_ms,
        "reason": reason,
        "horizon_ms": horizon_ms,
        "model_version_prefix": model_version_prefix,
        "training_policy_version": training_policy_version,
        "minimum_test_scored_observations": minimum_test_scored_observations,
    }


def _validation_policy_document(
    policy: FastChronologicalValidationPolicy,
) -> dict[str, object]:
    return {
        "version": policy.version,
        "folds": [
            {
                "name": fold.name,
                "training_started_at_unix_ms": (
                    fold.training_started_at_unix_ms
                ),
                "training_ended_at_unix_ms": (
                    fold.training_ended_at_unix_ms
                ),
                "validation_started_at_unix_ms": (
                    fold.validation_started_at_unix_ms
                ),
                "validation_ended_at_unix_ms": (
                    fold.validation_ended_at_unix_ms
                ),
                "test_started_at_unix_ms": fold.test_started_at_unix_ms,
                "test_ended_at_unix_ms": fold.test_ended_at_unix_ms,
            }
            for fold in policy.folds
        ],
    }


def _evaluation_policy_document(
    policy: FastForecastEvaluationPolicy,
) -> dict[str, object]:
    return {
        "version": policy.version,
        "partition": policy.partition.value,
        "probability_bucket_count": policy.probability_bucket_count,
        "liquidity_capacity_quote_boundaries": [
            _encode_numeric(value)
            for value in policy.liquidity_capacity_quote_boundaries
        ],
        "round_trip_cost_bps_boundaries": [
            _encode_numeric(value)
            for value in policy.round_trip_cost_bps_boundaries
        ],
        "binary_log_loss_clip_epsilon": _encode_numeric(
            policy.binary_log_loss_clip_epsilon
        ),
    }


def _decode_validation_policy(
    value: object,
) -> FastChronologicalValidationPolicy:
    if not isinstance(value, dict) or frozenset(value) != _VALIDATION_POLICY_KEYS:
        raise ValueError("validation policy fields are incompatible")
    raw_folds = value["folds"]
    if not isinstance(raw_folds, list) or not raw_folds:
        raise ValueError("validation policy folds must be a non-empty array")
    folds: list[FastChronologicalFold] = []
    for raw in raw_folds:
        if not isinstance(raw, dict) or frozenset(raw) != _FOLD_KEYS:
            raise ValueError("validation fold fields are incompatible")
        folds.append(
            FastChronologicalFold(
                name=_text(raw["name"], "fold name"),
                training_started_at_unix_ms=_integer(
                    raw["training_started_at_unix_ms"],
                    "training_started_at_unix_ms",
                ),
                training_ended_at_unix_ms=_integer(
                    raw["training_ended_at_unix_ms"],
                    "training_ended_at_unix_ms",
                ),
                validation_started_at_unix_ms=_integer(
                    raw["validation_started_at_unix_ms"],
                    "validation_started_at_unix_ms",
                ),
                validation_ended_at_unix_ms=_integer(
                    raw["validation_ended_at_unix_ms"],
                    "validation_ended_at_unix_ms",
                ),
                test_started_at_unix_ms=_integer(
                    raw["test_started_at_unix_ms"],
                    "test_started_at_unix_ms",
                ),
                test_ended_at_unix_ms=_integer(
                    raw["test_ended_at_unix_ms"],
                    "test_ended_at_unix_ms",
                ),
            )
        )
    return FastChronologicalValidationPolicy(
        version=_text(value["version"], "validation policy version"),
        folds=tuple(folds),
    )


def _decode_evaluation_policy(
    value: object,
) -> FastForecastEvaluationPolicy:
    if not isinstance(value, dict) or frozenset(value) != _EVALUATION_POLICY_KEYS:
        raise ValueError("evaluation policy fields are incompatible")
    try:
        partition = FastForecastEvaluationPartition(value["partition"])
    except (TypeError, ValueError) as exc:
        raise ValueError("evaluation partition is incompatible") from exc
    liquidity = value["liquidity_capacity_quote_boundaries"]
    costs = value["round_trip_cost_bps_boundaries"]
    if not isinstance(liquidity, list) or not isinstance(costs, list):
        raise ValueError("evaluation policy boundaries must be arrays")
    return FastForecastEvaluationPolicy(
        version=_text(value["version"], "evaluation policy version"),
        partition=partition,
        probability_bucket_count=_integer(
            value["probability_bucket_count"],
            "probability_bucket_count",
        ),
        liquidity_capacity_quote_boundaries=tuple(
            _decode_numeric(item, "liquidity boundary") for item in liquidity
        ),
        round_trip_cost_bps_boundaries=tuple(
            _decode_numeric(item, "cost boundary") for item in costs
        ),
        binary_log_loss_clip_epsilon=_decode_numeric(
            value["binary_log_loss_clip_epsilon"],
            "binary_log_loss_clip_epsilon",
        ),
    )


def _capture_sources(
    *,
    feature_path: Path,
    database_path: Path,
    context_path: Path,
) -> _SourceSnapshot:
    wal_path = Path(str(database_path) + "-wal")
    return _SourceSnapshot(
        feature_jsonl_sha256=_sha256_file_stable(feature_path),
        observer_database_sha256=_sha256_file_stable(database_path),
        observer_database_wal_sha256=(
            _sha256_file_stable(wal_path) if wal_path.is_file() else None
        ),
        context_corpus_file_sha256=_sha256_file_stable(context_path),
    )


def _resolve_source(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"first champion source file is missing: {value}")
    return path


def _resolve_destination(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _evaluation_file_name(report: FastForecastEvaluationReport) -> str:
    return f"evaluation-{report.target.value}@{report.horizon_ms}ms.json"


def _report_entry_document(
    value: FastFirstChampionEvaluationEvidenceEntry,
) -> dict[str, object]:
    return {
        "target": value.target,
        "horizon_ms": value.horizon_ms,
        "file_name": value.file_name,
        "file_sha256": value.file_sha256,
        "validation_run_fingerprint_sha256": (
            value.validation_run_fingerprint_sha256
        ),
        "evaluation_report_fingerprint_sha256": (
            value.evaluation_report_fingerprint_sha256
        ),
        "test_scored_observation_count": (
            value.test_scored_observation_count
        ),
        "test_target_unavailable_count": (
            value.test_target_unavailable_count
        ),
    }


def _report_entry_from_document(
    value: object,
) -> FastFirstChampionEvaluationEvidenceEntry:
    if not isinstance(value, dict) or frozenset(value) != _REPORT_ENTRY_KEYS:
        raise ValueError(
            "first champion evaluation report manifest entry is invalid"
        )
    return FastFirstChampionEvaluationEvidenceEntry(
        target=_text(value["target"], "target"),
        horizon_ms=_integer(value["horizon_ms"], "horizon_ms"),
        file_name=_text(value["file_name"], "file_name"),
        file_sha256=_text(value["file_sha256"], "file_sha256"),
        validation_run_fingerprint_sha256=_text(
            value["validation_run_fingerprint_sha256"],
            "validation_run_fingerprint_sha256",
        ),
        evaluation_report_fingerprint_sha256=_text(
            value["evaluation_report_fingerprint_sha256"],
            "evaluation_report_fingerprint_sha256",
        ),
        test_scored_observation_count=_integer(
            value["test_scored_observation_count"],
            "test_scored_observation_count",
        ),
        test_target_unavailable_count=_integer(
            value["test_target_unavailable_count"],
            "test_target_unavailable_count",
        ),
    )


def _manifest_document(
    value: FastFirstChampionArtifactManifest,
) -> dict[str, object]:
    return {
        "schema_name": value.schema_name,
        "schema_version": value.schema_version,
        "request_fingerprint_sha256": value.request_fingerprint_sha256,
        "request_file_sha256": value.request_file_sha256,
        "feature_jsonl_sha256": value.feature_jsonl_sha256,
        "observer_database_sha256": value.observer_database_sha256,
        "observer_database_wal_sha256": (
            value.observer_database_wal_sha256
        ),
        "context_corpus_file_sha256": value.context_corpus_file_sha256,
        "context_fingerprint_sha256": value.context_fingerprint_sha256,
        "training_bundle_fingerprint_sha256": (
            value.training_bundle_fingerprint_sha256
        ),
        "champion_fingerprint_sha256": value.champion_fingerprint_sha256,
        "champion_file_sha256": value.champion_file_sha256,
        "evaluation_reports": [
            _report_entry_document(item) for item in value.evaluation_reports
        ],
        "artifact_fingerprint_sha256": value.artifact_fingerprint_sha256,
    }


def _encode_numeric(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("request numeric value must be int or float")
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise ValueError("request float must be finite")
    return {"$float": value.hex()}


def _decode_numeric(value: object, name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{name} boolean is forbidden")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"{name} raw JSON float is forbidden; tagged float is required"
        )
    if not isinstance(value, dict) or frozenset(value) != {"$float"}:
        raise ValueError(f"{name} must be an integer or exact tagged float")
    raw = value["$float"]
    if not isinstance(raw, str):
        raise ValueError(f"{name} tagged float must be text")
    try:
        decoded = float.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"{name} tagged float is malformed") from exc
    if not math.isfinite(decoded):
        raise ValueError(f"{name} tagged float must be finite")
    return decoded


def _load_canonical(payload: str, *, label: str) -> dict[str, object]:
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"{label} must be non-empty text")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(f"{label} must contain exactly one trailing newline")
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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_file_stable(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"source is not an existing file: {path}")
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("source changed while fingerprinting")
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_empty(name: str, value: object) -> None:
    _text(value, name)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: object) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_positive_numeric(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name} must be positive and finite")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _require_leaf_name(name: str, value: object) -> None:
    _require_non_empty(name, value)
    assert isinstance(value, str)
    if Path(value).name != value or value in {".", ".."}:
        raise ValueError(f"{name} must be a leaf file name")
