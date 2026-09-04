from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, TypeVar

from shreks_brain.fast_campaign_paper import (
    FastCampaignPaperEntryAuthority,
    FastCampaignPaperQuoteEvidence,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicComparisonCatalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineEntryExecution,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineExecutionTrade,
    FastOfflineGraduationFlowEvidence,
    FastOfflineImpulseScalpEvidence,
    FastOfflineLongerRunnerContinuation,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineMarketSnapshot,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
    FastOfflineWalletCohortEvidence,
    FastOfflineWalletCohortEvidencePayload,
    FastOfflineWalletCohortSideSummary,
)
from shreks_brain.paper import PaperQuoteState
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureDataset,
    FastTrainingFeatureRecord,
    FastTrainingLifecycleEvent,
    FastTrainingReserveContext,
    FastTrainingWindowSummary,
    read_fast_training_feature_parquet,
    write_fast_training_feature_parquet,
)

from .comparison import (
    FastDeterministicCandidatePaperAuthority,
    FastDeterministicComparisonEvidenceRow,
)
from .risk_context import FastDeterministicCampaignRiskEnvironment


FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_NAME = (
    "shreks.fast_deterministic_comparison_evidence_bundle"
)
FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION = 1

_FEATURE_FILE = "fast_training_features.parquet"
_EVIDENCE_FILE = "comparison_evidence.jsonl"
_MANIFEST_FILE = "manifest.json"
_BUNDLE_FILES = frozenset({_FEATURE_FILE, _EVIDENCE_FILE, _MANIFEST_FILE})

_MANIFEST_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "catalog_fingerprint_sha256",
        "row_count",
        "feature_logical_fingerprint_sha256",
        "feature_source_sha256",
        "feature_file_sha256",
        "evidence_logical_fingerprint_sha256",
        "evidence_file_sha256",
        "bundle_fingerprint_sha256",
    }
)
_SIDECAR_KEYS = frozenset(
    {
        "record_identity",
        "state_version",
        "evaluated_at_unix_ms",
        "quote",
        "market_regime",
        "risk_environment",
        "candidate_authorities",
        "impulse_scalp_evidence",
        "micro_pullback_evidence",
        "pre_graduation_evidence",
        "graduation_flow_evidence",
        "wallet_cohort_evidence",
        "longer_runner_evidence",
    }
)
_IDENTITY_KEYS = frozenset(
    {
        "decision_signature",
        "decision_ordinal",
        "decision_sequence",
        "mint",
        "quote_mint",
        "venue",
        "decision_observed_at_unix_ms",
    }
)


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonEvidenceBundleManifest:
    schema_name: str
    schema_version: int
    catalog_fingerprint_sha256: str
    row_count: int
    feature_logical_fingerprint_sha256: str
    feature_source_sha256: str
    feature_file_sha256: str
    evidence_logical_fingerprint_sha256: str
    evidence_file_sha256: str
    bundle_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_NAME:
            raise ValueError("unsupported comparison evidence bundle schema_name")
        if self.schema_version != FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported comparison evidence bundle schema_version")
        if (
            isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count <= 0
        ):
            raise ValueError("comparison evidence bundle row_count must be positive")
        for name in (
            "catalog_fingerprint_sha256",
            "feature_logical_fingerprint_sha256",
            "feature_source_sha256",
            "feature_file_sha256",
            "evidence_logical_fingerprint_sha256",
            "evidence_file_sha256",
            "bundle_fingerprint_sha256",
        ):
            _require_sha256(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class FastDeterministicComparisonEvidenceBundle:
    manifest: FastDeterministicComparisonEvidenceBundleManifest
    features: FastTrainingFeatureDataset
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not FastDeterministicComparisonEvidenceBundleManifest:
            raise ValueError(
                "manifest must be exact FastDeterministicComparisonEvidenceBundleManifest"
            )
        if type(self.features) is not FastTrainingFeatureDataset:
            raise ValueError("features must be exact FastTrainingFeatureDataset")
        if (
            not isinstance(self.rows, tuple)
            or len(self.rows) != self.manifest.row_count
            or not all(
                type(row) is FastDeterministicComparisonEvidenceRow
                for row in self.rows
            )
        ):
            raise ValueError(
                "rows must match manifest row_count and contain exact comparison rows"
            )
        _validate_population(self.features, self.rows)
        if (
            self.features.logical_fingerprint_sha256
            != self.manifest.feature_logical_fingerprint_sha256
        ):
            raise ValueError("bundle feature logical fingerprint mismatch")
        if self.features.source_sha256 != self.manifest.feature_source_sha256:
            raise ValueError("bundle feature source fingerprint mismatch")


def write_fast_deterministic_comparison_evidence_bundle(
    *,
    feature_dataset: FastTrainingFeatureDataset,
    catalog: FastDeterministicComparisonCatalog,
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...],
    destination: str | Path,
) -> FastDeterministicComparisonEvidenceBundleManifest:
    if type(feature_dataset) is not FastTrainingFeatureDataset:
        raise ValueError("feature_dataset must be exact FastTrainingFeatureDataset")
    if type(catalog) is not FastDeterministicComparisonCatalog:
        raise ValueError("catalog must be exact FastDeterministicComparisonCatalog")
    if (
        not isinstance(rows, tuple)
        or not rows
        or not all(
            type(row) is FastDeterministicComparisonEvidenceRow for row in rows
        )
    ):
        raise ValueError(
            "rows must be a non-empty tuple of exact comparison evidence rows"
        )
    _validate_population(feature_dataset, rows)
    _validate_catalog_authorities(catalog, rows)

    destination_path = Path(destination)
    if destination_path.exists():
        raise FileExistsError(
            "comparison evidence bundle destination already exists; bundles are immutable"
        )
    destination_path.mkdir(parents=True)

    feature_path = destination_path / _FEATURE_FILE
    evidence_path = destination_path / _EVIDENCE_FILE
    manifest_path = destination_path / _MANIFEST_FILE

    write_fast_training_feature_parquet(feature_dataset, feature_path)

    evidence_documents = tuple(_row_to_sidecar(row) for row in rows)
    evidence_bytes = b"".join(
        (_canonical(document) + "\n").encode("utf-8")
        for document in evidence_documents
    )
    evidence_path.write_bytes(evidence_bytes)

    feature_file_sha = _file_sha256(feature_path)
    evidence_file_sha = hashlib.sha256(evidence_bytes).hexdigest()
    evidence_logical_sha = _logical_evidence_sha256(evidence_documents)

    material = {
        "schema_name": FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION,
        "catalog_fingerprint_sha256": catalog.catalog_fingerprint_sha256,
        "row_count": len(rows),
        "feature_logical_fingerprint_sha256": (
            feature_dataset.logical_fingerprint_sha256
        ),
        "feature_source_sha256": feature_dataset.source_sha256,
        "feature_file_sha256": feature_file_sha,
        "evidence_logical_fingerprint_sha256": evidence_logical_sha,
        "evidence_file_sha256": evidence_file_sha,
    }
    bundle_fingerprint = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    manifest = FastDeterministicComparisonEvidenceBundleManifest(
        **material,
        bundle_fingerprint_sha256=bundle_fingerprint,
    )
    manifest_path.write_text(
        _canonical(_jsonable(manifest)) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_fast_deterministic_comparison_evidence_bundle(
    path: str | Path,
) -> FastDeterministicComparisonEvidenceBundle:
    source = Path(path)
    if not source.is_dir():
        raise ValueError("comparison evidence bundle path must be an existing directory")
    actual_files = frozenset(item.name for item in source.iterdir() if item.is_file())
    if actual_files != _BUNDLE_FILES:
        raise ValueError(
            "comparison evidence bundle has missing or unexpected files"
        )

    manifest_path = source / _MANIFEST_FILE
    raw_manifest = manifest_path.read_text(encoding="utf-8")
    try:
        manifest_document = json.loads(raw_manifest)
    except json.JSONDecodeError as exc:
        raise ValueError("comparison evidence bundle manifest is malformed JSON") from exc
    manifest_map = _require_dict(manifest_document, "bundle manifest")
    _require_exact_keys("bundle manifest", manifest_map, _MANIFEST_KEYS)
    if raw_manifest != _canonical(manifest_map) + "\n":
        raise ValueError("comparison evidence bundle manifest is not canonical")

    material = dict(manifest_map)
    claimed_bundle_fingerprint = material.pop("bundle_fingerprint_sha256")
    _require_sha256("bundle_fingerprint_sha256", claimed_bundle_fingerprint)
    expected_bundle_fingerprint = hashlib.sha256(
        _canonical(material).encode("utf-8")
    ).hexdigest()
    if claimed_bundle_fingerprint != expected_bundle_fingerprint:
        raise ValueError("comparison evidence bundle fingerprint mismatch")
    try:
        manifest = FastDeterministicComparisonEvidenceBundleManifest(
            **manifest_map
        )
    except TypeError as exc:
        raise ValueError("comparison evidence bundle manifest is invalid") from exc

    feature_path = source / _FEATURE_FILE
    evidence_path = source / _EVIDENCE_FILE
    if _file_sha256(feature_path) != manifest.feature_file_sha256:
        raise ValueError("comparison evidence feature file fingerprint mismatch")
    evidence_bytes = evidence_path.read_bytes()
    if hashlib.sha256(evidence_bytes).hexdigest() != manifest.evidence_file_sha256:
        raise ValueError("comparison evidence file fingerprint mismatch")

    features = read_fast_training_feature_parquet(feature_path)
    if features.logical_fingerprint_sha256 != manifest.feature_logical_fingerprint_sha256:
        raise ValueError("comparison evidence feature logical fingerprint mismatch")
    if features.source_sha256 != manifest.feature_source_sha256:
        raise ValueError("comparison evidence feature source fingerprint mismatch")
    if len(features.records) != manifest.row_count:
        raise ValueError("comparison evidence feature row count mismatch")

    evidence_documents = _read_canonical_jsonl(evidence_bytes)
    if len(evidence_documents) != manifest.row_count:
        raise ValueError("comparison evidence sidecar row count mismatch")
    if (
        _logical_evidence_sha256(evidence_documents)
        != manifest.evidence_logical_fingerprint_sha256
    ):
        raise ValueError("comparison evidence logical fingerprint mismatch")

    rows = tuple(
        _sidecar_to_row(record, document)
        for record, document in zip(features.records, evidence_documents, strict=True)
    )
    bundle = FastDeterministicComparisonEvidenceBundle(
        manifest=manifest,
        features=features,
        rows=rows,
    )
    return bundle


def _validate_population(
    feature_dataset: FastTrainingFeatureDataset,
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...],
) -> None:
    if len(feature_dataset.records) != len(rows):
        raise ValueError("comparison evidence population row count mismatch")
    for index, (record, row) in enumerate(
        zip(feature_dataset.records, rows, strict=True)
    ):
        if row.record != record:
            raise ValueError(
                f"comparison evidence feature/row population mismatch at row {index}"
            )


def _validate_catalog_authorities(
    catalog: FastDeterministicComparisonCatalog,
    rows: tuple[FastDeterministicComparisonEvidenceRow, ...],
) -> None:
    expected_versions = tuple(
        manifest.candidate_version for manifest in catalog.candidates
    )
    for index, row in enumerate(rows):
        actual_versions = tuple(
            authority.candidate_version for authority in row.candidate_authorities
        )
        if actual_versions != expected_versions:
            raise ValueError(
                f"comparison evidence candidate authority/catalog mismatch at row {index}"
            )


def _row_to_sidecar(
    row: FastDeterministicComparisonEvidenceRow,
) -> dict[str, object]:
    record = row.record
    return {
        "record_identity": {
            "decision_signature": record.decision_signature,
            "decision_ordinal": record.decision_ordinal,
            "decision_sequence": record.decision_sequence,
            "mint": record.mint,
            "quote_mint": record.quote_mint,
            "venue": record.venue,
            "decision_observed_at_unix_ms": record.decision_observed_at_unix_ms,
        },
        "state_version": row.state_version,
        "evaluated_at_unix_ms": row.evaluated_at_unix_ms,
        "quote": _jsonable(row.quote),
        "market_regime": row.market_regime.value,
        "risk_environment": _jsonable(row.risk_environment),
        "candidate_authorities": [
            _jsonable(value) for value in row.candidate_authorities
        ],
        "impulse_scalp_evidence": _jsonable(row.impulse_scalp_evidence),
        "micro_pullback_evidence": _jsonable(row.micro_pullback_evidence),
        "pre_graduation_evidence": _jsonable(row.pre_graduation_evidence),
        "graduation_flow_evidence": _jsonable(row.graduation_flow_evidence),
        "wallet_cohort_evidence": _jsonable(row.wallet_cohort_evidence),
        "longer_runner_evidence": _jsonable(row.longer_runner_evidence),
    }


def _sidecar_to_row(
    record: FastTrainingFeatureRecord,
    document: dict[str, Any],
) -> FastDeterministicComparisonEvidenceRow:
    _require_exact_keys("comparison evidence sidecar row", document, _SIDECAR_KEYS)
    identity = _require_dict(document["record_identity"], "record_identity")
    _require_exact_keys("record_identity", identity, _IDENTITY_KEYS)
    expected_identity = {
        "decision_signature": record.decision_signature,
        "decision_ordinal": record.decision_ordinal,
        "decision_sequence": record.decision_sequence,
        "mint": record.mint,
        "quote_mint": record.quote_mint,
        "venue": record.venue,
        "decision_observed_at_unix_ms": record.decision_observed_at_unix_ms,
    }
    if identity != expected_identity:
        raise ValueError("comparison evidence sidecar record identity mismatch")

    quote = _quote_from_wire(document["quote"])
    risk_environment = _risk_environment_from_wire(
        document["risk_environment"]
    )
    authorities_raw = document["candidate_authorities"]
    if not isinstance(authorities_raw, list) or not authorities_raw:
        raise ValueError("candidate_authorities must be a non-empty JSON array")
    authorities = tuple(
        _candidate_authority_from_wire(value) for value in authorities_raw
    )

    try:
        regime = MarketRegime(document["market_regime"])
    except (TypeError, ValueError) as exc:
        raise ValueError("comparison evidence market_regime is invalid") from exc

    return FastDeterministicComparisonEvidenceRow(
        record=record,
        impulse_scalp_evidence=_entry_evidence_from_wire(
            document["impulse_scalp_evidence"],
            FastOfflineImpulseScalpEvidence,
        ),
        micro_pullback_evidence=_entry_evidence_from_wire(
            document["micro_pullback_evidence"],
            FastOfflineMicroPullbackEvidence,
        ),
        pre_graduation_evidence=_entry_evidence_from_wire(
            document["pre_graduation_evidence"],
            FastOfflinePreGraduationEvidence,
        ),
        graduation_flow_evidence=_graduation_from_wire(
            document["graduation_flow_evidence"]
        ),
        wallet_cohort_evidence=_wallet_from_wire(
            document["wallet_cohort_evidence"]
        ),
        longer_runner_evidence=_longer_runner_from_wire(
            document["longer_runner_evidence"]
        ),
        state_version=_require_string(document["state_version"], "state_version"),
        evaluated_at_unix_ms=_require_int(
            document["evaluated_at_unix_ms"],
            "evaluated_at_unix_ms",
        ),
        quote=quote,
        market_regime=regime,
        risk_environment=risk_environment,
        candidate_authorities=authorities,
    )


TEntryEvidence = TypeVar(
    "TEntryEvidence",
    FastOfflineImpulseScalpEvidence,
    FastOfflineMicroPullbackEvidence,
    FastOfflinePreGraduationEvidence,
)


def _entry_evidence_from_wire(
    value: object,
    cls: type[TEntryEvidence],
) -> TEntryEvidence:
    raw = _require_dict(value, cls.__name__)
    _require_dataclass_keys(cls.__name__, raw, cls)
    return cls(execution=_entry_execution_from_wire(raw["execution"]))


def _entry_execution_from_wire(
    value: object,
) -> FastOfflineEntryExecution | None:
    if value is None:
        return None
    raw = _require_dict(value, "entry execution")
    _require_dataclass_keys("entry execution", raw, FastOfflineEntryExecution)
    return FastOfflineEntryExecution(
        cost_model=_cost_model_from_wire(raw["cost_model"]),
        trade=_trade_from_wire(raw["trade"]),
    )


def _cost_model_from_wire(value: object) -> FastOfflineExecutionCostModel:
    raw = _require_dict(value, "execution cost model")
    _require_dataclass_keys(
        "execution cost model",
        raw,
        FastOfflineExecutionCostModel,
    )
    return FastOfflineExecutionCostModel(
        version=_require_int(raw["version"], "cost model version"),
        entry=_leg_from_wire(raw["entry"]),
        exit=_leg_from_wire(raw["exit"]),
    )


def _leg_from_wire(value: object) -> FastOfflineExecutionLegCost:
    raw = _require_dict(value, "execution leg cost")
    _require_dataclass_keys(
        "execution leg cost",
        raw,
        FastOfflineExecutionLegCost,
    )
    return _construct_dataclass(FastOfflineExecutionLegCost, raw)


def _trade_from_wire(value: object) -> FastOfflineExecutionTrade:
    raw = _require_dict(value, "execution trade")
    _require_dataclass_keys("execution trade", raw, FastOfflineExecutionTrade)
    return _construct_dataclass(FastOfflineExecutionTrade, raw)


def _graduation_from_wire(value: object) -> FastOfflineGraduationFlowEvidence:
    raw = _require_dict(value, "graduation flow evidence")
    _require_dataclass_keys(
        "graduation flow evidence",
        raw,
        FastOfflineGraduationFlowEvidence,
    )
    return FastOfflineGraduationFlowEvidence(
        pre_snapshot=_snapshot_from_wire(raw["pre_snapshot"]),
        boost_context=raw["boost_context"],
        execution=_entry_execution_from_wire(raw["execution"]),
    )


def _snapshot_from_wire(value: object) -> FastOfflineMarketSnapshot:
    raw = _require_dict(value, "offline market snapshot")
    _require_dataclass_keys(
        "offline market snapshot",
        raw,
        FastOfflineMarketSnapshot,
    )
    reserve = _optional_dataclass_from_wire(
        raw["last_reserve_context"],
        FastTrainingReserveContext,
        "last_reserve_context",
    )
    lifecycle = _optional_dataclass_from_wire(
        raw["last_lifecycle_event"],
        FastTrainingLifecycleEvent,
        "last_lifecycle_event",
    )
    windows_raw = raw["windows"]
    if not isinstance(windows_raw, list) or not windows_raw:
        raise ValueError("offline market snapshot windows must be non-empty JSON array")
    windows = tuple(
        _required_dataclass_from_wire(
            item,
            FastTrainingWindowSummary,
            "window",
        )
        for item in windows_raw
    )
    return FastOfflineMarketSnapshot(
        mint=_require_string(raw["mint"], "snapshot mint"),
        quote_mint=_require_string(raw["quote_mint"], "snapshot quote_mint"),
        venue=_require_string(raw["venue"], "snapshot venue"),
        as_of_unix_ms=_require_int(raw["as_of_unix_ms"], "snapshot as_of_unix_ms"),
        last_sequence=raw["last_sequence"],
        last_price_quote=raw["last_price_quote"],
        last_reserve_context=reserve,
        last_lifecycle_event=lifecycle,
        windows=windows,
    )


def _wallet_from_wire(value: object) -> FastOfflineWalletCohortEvidence:
    raw = _require_dict(value, "wallet cohort evidence")
    _require_dataclass_keys(
        "wallet cohort evidence",
        raw,
        FastOfflineWalletCohortEvidence,
    )
    payload_value = raw["evidence"]
    if payload_value is None:
        return FastOfflineWalletCohortEvidence(evidence=None)
    payload = _require_dict(payload_value, "wallet cohort payload")
    _require_dataclass_keys(
        "wallet cohort payload",
        payload,
        FastOfflineWalletCohortEvidencePayload,
    )
    return FastOfflineWalletCohortEvidence(
        evidence=FastOfflineWalletCohortEvidencePayload(
            version=_require_int(payload["version"], "wallet evidence version"),
            wallet_feature_policy_version=_require_string(
                payload["wallet_feature_policy_version"],
                "wallet_feature_policy_version",
            ),
            profile_policy_version=payload["profile_policy_version"],
            relationship_policy_version=_require_string(
                payload["relationship_policy_version"],
                "relationship_policy_version",
            ),
            support=_wallet_side_from_wire(payload["support"]),
            exits=_wallet_side_from_wire(payload["exits"]),
            support_hold_horizon_wallet_weight=payload[
                "support_hold_horizon_wallet_weight"
            ],
            confidence_weighted_support_median_hold_ms=payload[
                "confidence_weighted_support_median_hold_ms"
            ],
        )
    )


def _wallet_side_from_wire(value: object) -> FastOfflineWalletCohortSideSummary:
    raw = _require_dict(value, "wallet cohort side")
    _require_dataclass_keys(
        "wallet cohort side",
        raw,
        FastOfflineWalletCohortSideSummary,
    )
    return _construct_dataclass(FastOfflineWalletCohortSideSummary, raw)


def _longer_runner_from_wire(value: object) -> FastOfflineLongerRunnerEvidence:
    raw = _require_dict(value, "longer runner evidence")
    _require_dataclass_keys(
        "longer runner evidence",
        raw,
        FastOfflineLongerRunnerEvidence,
    )
    protective_raw = _require_dict(
        raw["protective"],
        "longer runner protective",
    )
    _require_dataclass_keys(
        "longer runner protective",
        protective_raw,
        FastOfflineLongerRunnerProtective,
    )
    protective = _construct_dataclass(
        FastOfflineLongerRunnerProtective,
        protective_raw,
    )
    continuation_raw = raw["continuation"]
    continuation = (
        None
        if continuation_raw is None
        else _continuation_from_wire(continuation_raw)
    )
    return FastOfflineLongerRunnerEvidence(
        protective=protective,
        continuation=continuation,
    )


def _continuation_from_wire(
    value: object,
) -> FastOfflineLongerRunnerContinuation:
    raw = _require_dict(value, "longer runner continuation")
    _require_dataclass_keys(
        "longer runner continuation",
        raw,
        FastOfflineLongerRunnerContinuation,
    )
    values = dict(raw)
    values["current_exit_costs"] = _leg_from_wire(raw["current_exit_costs"])
    values["future_exit_costs"] = _leg_from_wire(raw["future_exit_costs"])
    try:
        return FastOfflineLongerRunnerContinuation(**values)
    except TypeError as exc:
        raise ValueError("longer runner continuation is invalid") from exc


def _quote_from_wire(value: object) -> FastCampaignPaperQuoteEvidence:
    raw = _require_dict(value, "campaign PAPER quote")
    _require_dataclass_keys(
        "campaign PAPER quote",
        raw,
        FastCampaignPaperQuoteEvidence,
    )
    values = dict(raw)
    try:
        values["state"] = PaperQuoteState(raw["state"])
        return FastCampaignPaperQuoteEvidence(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("campaign PAPER quote is invalid") from exc


def _risk_environment_from_wire(
    value: object,
) -> FastDeterministicCampaignRiskEnvironment:
    raw = _require_dict(value, "campaign risk environment")
    _require_dataclass_keys(
        "campaign risk environment",
        raw,
        FastDeterministicCampaignRiskEnvironment,
    )
    active_keys = raw["active_intent_keys"]
    if not isinstance(active_keys, list):
        raise ValueError("active_intent_keys must be a JSON array")
    values = dict(raw)
    values["active_intent_keys"] = frozenset(active_keys)
    try:
        return FastDeterministicCampaignRiskEnvironment(**values)
    except TypeError as exc:
        raise ValueError("campaign risk environment is invalid") from exc


def _candidate_authority_from_wire(
    value: object,
) -> FastDeterministicCandidatePaperAuthority:
    raw = _require_dict(value, "candidate PAPER authority")
    _require_dataclass_keys(
        "candidate PAPER authority",
        raw,
        FastDeterministicCandidatePaperAuthority,
    )
    entry_raw = _require_dict(raw["entry_authority"], "entry authority")
    _require_dataclass_keys(
        "entry authority",
        entry_raw,
        FastCampaignPaperEntryAuthority,
    )
    try:
        entry = FastCampaignPaperEntryAuthority(**entry_raw)
        return FastDeterministicCandidatePaperAuthority(
            candidate_version=_require_string(
                raw["candidate_version"],
                "candidate_version",
            ),
            entry_authority=entry,
        )
    except TypeError as exc:
        raise ValueError("candidate PAPER authority is invalid") from exc


def _optional_dataclass_from_wire(
    value: object,
    cls: type[Any],
    name: str,
) -> Any | None:
    if value is None:
        return None
    return _required_dataclass_from_wire(value, cls, name)


def _required_dataclass_from_wire(
    value: object,
    cls: type[Any],
    name: str,
) -> Any:
    raw = _require_dict(value, name)
    _require_dataclass_keys(name, raw, cls)
    return _construct_dataclass(cls, raw)


def _construct_dataclass(cls: type[Any], raw: dict[str, Any]) -> Any:
    try:
        return cls(**raw)
    except TypeError as exc:
        raise ValueError(f"{cls.__name__} is invalid") from exc


def _read_canonical_jsonl(raw: bytes) -> tuple[dict[str, Any], ...]:
    if not raw:
        raise ValueError("comparison evidence JSONL cannot be empty")
    documents: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.endswith(b"\n"):
            raise ValueError(
                f"comparison evidence JSONL line {line_number} is not newline terminated"
            )
        payload = line[:-1]
        if not payload:
            raise ValueError(
                f"comparison evidence JSONL line {line_number} is blank"
            )
        try:
            text = payload.decode("utf-8")
            document = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"comparison evidence JSONL line {line_number} is invalid"
            ) from exc
        raw_document = _require_dict(
            document,
            f"comparison evidence JSONL line {line_number}",
        )
        if text != _canonical(raw_document):
            raise ValueError(
                f"comparison evidence JSONL line {line_number} is not canonical"
            )
        documents.append(raw_document)
    return tuple(documents)


def _logical_evidence_sha256(
    documents: tuple[dict[str, Any], ...],
) -> str:
    if not documents:
        raise ValueError("comparison evidence documents cannot be empty")
    return hashlib.sha256(
        _canonical(list(documents)).encode("utf-8")
    ).hexdigest()


def _jsonable(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, frozenset):
        return [_jsonable(item) for item in sorted(value)]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _require_dataclass_keys(
    name: str,
    value: dict[str, Any],
    cls: type[Any],
) -> None:
    _require_exact_keys(
        name,
        value,
        frozenset(field.name for field in fields(cls)),
    )


def _require_exact_keys(
    name: str,
    value: dict[str, Any],
    expected: frozenset[str],
) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ValueError(
            f"{name} has unknown or missing fields: "
            f"missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _require_dict(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _require_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
