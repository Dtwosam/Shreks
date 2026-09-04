from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_deterministic_lifecycle import (
    decode_fast_deterministic_comparison_catalog,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastOfflineLongerRunnerContinuation,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineWalletCohortEvidence,
    FastOfflineWalletCohortEvidencePayload,
    FastOfflineWalletCohortSideSummary,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.observer_campaign import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
)
from shreks_brain.paper import PaperFillPolicy, create_paper_ledger
from shreks_brain.regime import MarketRegime
from shreks_brain.research.fast_training_features import (
    read_fast_training_feature_jsonl,
    read_fast_training_feature_parquet,
)
from shreks_brain.risk import RiskPolicy

from .artifact import (
    FastDeterministicCampaignArtifactManifest,
    write_fast_deterministic_campaign_artifact,
)
from .input_assembly import (
    FastDeterministicComparisonExecutionPolicy,
    FastDeterministicComparisonPointInTimeContext,
)
from .risk_context import FastDeterministicCampaignRiskEnvironment


FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME = (
    "shreks.fast_deterministic_campaign_request"
)
FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION = 2

_REQUEST_FIELDS = (
    "observer_database_path",
    "feature_parquet_path",
    "comparison_catalog_path",
    "champion_path",
    "entry_authority_binary_path",
    "candidate_binary_path",
    "destination_path",
    "execution_policy",
    "contexts",
    "paper_run_id_prefix",
    "assessment_version",
    "starting_cash_usd",
    "starting_ledger_as_of_unix_ms",
    "fill_policy",
    "risk_policy",
    "position_policy",
    "evaluation_policy",
)
_REQUEST_FIELDS_V2 = (
    "observer_database_path",
    "feature_jsonl_path",
    "comparison_catalog_path",
    "champion_path",
    "entry_authority_binary_path",
    "candidate_binary_path",
    "destination_path",
    "execution_policy",
    "contexts",
    "paper_run_id_prefix",
    "assessment_version",
    "starting_cash_usd",
    "starting_ledger_as_of_unix_ms",
    "fill_policy",
    "risk_policy",
    "position_policy",
    "evaluation_policy",
)
_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "request",
        "request_fingerprint_sha256",
    }
)

_DATACLASS_TYPES = (
    FastDeterministicComparisonExecutionPolicy,
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
    FastDeterministicComparisonPointInTimeContext,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuoteAsset,
    FastOfflineWalletCohortEvidence,
    FastOfflineWalletCohortEvidencePayload,
    FastOfflineWalletCohortSideSummary,
    FastOfflineLongerRunnerEvidence,
    FastOfflineLongerRunnerProtective,
    FastOfflineLongerRunnerContinuation,
    FastDeterministicCampaignRiskEnvironment,
    PaperFillPolicy,
    RiskPolicy,
    FastPaperPositionActionPolicy,
    TradingEvaluationPolicy,
)
_DATACLASS_BY_NAME = {value.__name__: value for value in _DATACLASS_TYPES}
_DATACLASS_NAME_BY_TYPE = {value: value.__name__ for value in _DATACLASS_TYPES}

_ENUM_TYPES = (
    ObserverPaperQuotePurpose,
    MarketRegime,
)
_ENUM_BY_NAME = {value.__name__: value for value in _ENUM_TYPES}
_ENUM_NAME_BY_TYPE = {value: value.__name__ for value in _ENUM_TYPES}


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignRequest:
    schema_name: str
    schema_version: int
    observer_database_path: str
    feature_parquet_path: str
    comparison_catalog_path: str
    champion_path: str
    entry_authority_binary_path: str
    candidate_binary_path: str
    destination_path: str
    execution_policy: FastDeterministicComparisonExecutionPolicy
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...]
    paper_run_id_prefix: str
    assessment_version: str
    starting_cash_usd: float
    starting_ledger_as_of_unix_ms: int
    fill_policy: PaperFillPolicy
    risk_policy: RiskPolicy
    position_policy: FastPaperPositionActionPolicy
    evaluation_policy: TradingEvaluationPolicy
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME:
            raise ValueError("unsupported deterministic campaign request schema_name")
        if self.schema_version != FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported deterministic campaign request schema_version")

        for name in (
            "observer_database_path",
            "feature_parquet_path",
            "comparison_catalog_path",
            "champion_path",
            "entry_authority_binary_path",
            "candidate_binary_path",
            "destination_path",
            "paper_run_id_prefix",
            "assessment_version",
        ):
            _require_non_empty_string(name, getattr(self, name))

        if type(self.execution_policy) is not FastDeterministicComparisonExecutionPolicy:
            raise ValueError(
                "execution_policy must be exact FastDeterministicComparisonExecutionPolicy"
            )
        if (
            not isinstance(self.contexts, tuple)
            or not self.contexts
            or not all(
                type(value) is FastDeterministicComparisonPointInTimeContext
                for value in self.contexts
            )
        ):
            raise ValueError(
                "contexts must be a non-empty tuple of exact point-in-time contexts"
            )
        _require_positive_finite("starting_cash_usd", self.starting_cash_usd)
        _require_non_negative_int(
            "starting_ledger_as_of_unix_ms",
            self.starting_ledger_as_of_unix_ms,
        )
        if type(self.fill_policy) is not PaperFillPolicy:
            raise ValueError("fill_policy must be exact PaperFillPolicy")
        if type(self.risk_policy) is not RiskPolicy:
            raise ValueError("risk_policy must be exact RiskPolicy")
        if type(self.position_policy) is not FastPaperPositionActionPolicy:
            raise ValueError(
                "position_policy must be exact FastPaperPositionActionPolicy"
            )
        if type(self.evaluation_policy) is not TradingEvaluationPolicy:
            raise ValueError(
                "evaluation_policy must be exact TradingEvaluationPolicy"
            )
        _require_sha256(
            "request_fingerprint_sha256",
            self.request_fingerprint_sha256,
        )

        if self.evaluation_policy.starting_equity_usd != self.starting_cash_usd:
            raise ValueError(
                "evaluation starting equity must equal PAPER starting cash"
            )
        for index, context in enumerate(self.contexts):
            if (
                context.risk_environment.trading_capital_usd
                != self.starting_cash_usd
            ):
                raise ValueError(
                    f"risk trading capital must equal PAPER starting cash at context {index}"
                )
            if self.starting_ledger_as_of_unix_ms > context.evaluated_at_unix_ms:
                raise ValueError(
                    f"starting ledger time cannot follow context evaluation at context {index}"
                )


@dataclass(frozen=True, slots=True)
class FastDeterministicCampaignJsonlRequest:
    schema_name: str
    schema_version: int
    observer_database_path: str
    feature_jsonl_path: str
    comparison_catalog_path: str
    champion_path: str
    entry_authority_binary_path: str
    candidate_binary_path: str
    destination_path: str
    execution_policy: FastDeterministicComparisonExecutionPolicy
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...]
    paper_run_id_prefix: str
    assessment_version: str
    starting_cash_usd: float
    starting_ledger_as_of_unix_ms: int
    fill_policy: PaperFillPolicy
    risk_policy: RiskPolicy
    position_policy: FastPaperPositionActionPolicy
    evaluation_policy: TradingEvaluationPolicy
    request_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME:
            raise ValueError("unsupported deterministic campaign request schema_name")
        if (
            self.schema_version
            != FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported deterministic campaign JSONL request schema_version"
            )
        for name in (
            "observer_database_path",
            "feature_jsonl_path",
            "comparison_catalog_path",
            "champion_path",
            "entry_authority_binary_path",
            "candidate_binary_path",
            "destination_path",
            "paper_run_id_prefix",
            "assessment_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        if Path(self.feature_jsonl_path).suffix != ".jsonl":
            raise ValueError("feature_jsonl_path must end with .jsonl")
        _validate_request_economic_fields(
            execution_policy=self.execution_policy,
            contexts=self.contexts,
            starting_cash_usd=self.starting_cash_usd,
            starting_ledger_as_of_unix_ms=self.starting_ledger_as_of_unix_ms,
            fill_policy=self.fill_policy,
            risk_policy=self.risk_policy,
            position_policy=self.position_policy,
            evaluation_policy=self.evaluation_policy,
        )
        _require_sha256(
            "request_fingerprint_sha256",
            self.request_fingerprint_sha256,
        )


def build_fast_deterministic_campaign_request(
    *,
    observer_database_path: str,
    feature_parquet_path: str,
    comparison_catalog_path: str,
    champion_path: str,
    entry_authority_binary_path: str,
    candidate_binary_path: str,
    destination_path: str,
    execution_policy: FastDeterministicComparisonExecutionPolicy,
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...],
    paper_run_id_prefix: str,
    assessment_version: str,
    starting_cash_usd: float,
    starting_ledger_as_of_unix_ms: int,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicCampaignRequest:
    values = {
        "observer_database_path": observer_database_path,
        "feature_parquet_path": feature_parquet_path,
        "comparison_catalog_path": comparison_catalog_path,
        "champion_path": champion_path,
        "entry_authority_binary_path": entry_authority_binary_path,
        "candidate_binary_path": candidate_binary_path,
        "destination_path": destination_path,
        "execution_policy": execution_policy,
        "contexts": contexts,
        "paper_run_id_prefix": paper_run_id_prefix,
        "assessment_version": assessment_version,
        "starting_cash_usd": starting_cash_usd,
        "starting_ledger_as_of_unix_ms": starting_ledger_as_of_unix_ms,
        "fill_policy": fill_policy,
        "risk_policy": risk_policy,
        "position_policy": position_policy,
        "evaluation_policy": evaluation_policy,
    }
    material = _request_material_from_values(values)
    return FastDeterministicCampaignRequest(
        schema_name=FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME,
        schema_version=FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION,
        **values,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def build_fast_deterministic_campaign_jsonl_request(
    *,
    observer_database_path: str,
    feature_jsonl_path: str,
    comparison_catalog_path: str,
    champion_path: str,
    entry_authority_binary_path: str,
    candidate_binary_path: str,
    destination_path: str,
    execution_policy: FastDeterministicComparisonExecutionPolicy,
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...],
    paper_run_id_prefix: str,
    assessment_version: str,
    starting_cash_usd: float,
    starting_ledger_as_of_unix_ms: int,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicCampaignJsonlRequest:
    values = {
        "observer_database_path": observer_database_path,
        "feature_jsonl_path": feature_jsonl_path,
        "comparison_catalog_path": comparison_catalog_path,
        "champion_path": champion_path,
        "entry_authority_binary_path": entry_authority_binary_path,
        "candidate_binary_path": candidate_binary_path,
        "destination_path": destination_path,
        "execution_policy": execution_policy,
        "contexts": contexts,
        "paper_run_id_prefix": paper_run_id_prefix,
        "assessment_version": assessment_version,
        "starting_cash_usd": starting_cash_usd,
        "starting_ledger_as_of_unix_ms": starting_ledger_as_of_unix_ms,
        "fill_policy": fill_policy,
        "risk_policy": risk_policy,
        "position_policy": position_policy,
        "evaluation_policy": evaluation_policy,
    }
    material = _request_material_from_values(
        values,
        schema_version=FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION,
        request_fields=_REQUEST_FIELDS_V2,
    )
    return FastDeterministicCampaignJsonlRequest(
        schema_name=FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME,
        schema_version=FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION,
        **values,
        request_fingerprint_sha256=_sha256_canonical(material),
    )


def encode_fast_deterministic_campaign_request(
    request: FastDeterministicCampaignRequest | FastDeterministicCampaignJsonlRequest,
) -> str:
    if type(request) is FastDeterministicCampaignRequest:
        request_fields = _REQUEST_FIELDS
        schema_version = FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION
    elif type(request) is FastDeterministicCampaignJsonlRequest:
        request_fields = _REQUEST_FIELDS_V2
        schema_version = FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION
    else:
        raise ValueError(
            "request must be an exact deterministic campaign request"
        )
    values = {
        name: getattr(request, name)
        for name in request_fields
    }
    material = _request_material_from_values(
        values,
        schema_version=schema_version,
        request_fields=request_fields,
    )
    expected = _sha256_canonical(material)
    if request.request_fingerprint_sha256 != expected:
        raise ValueError(
            "deterministic campaign request fingerprint mismatch"
        )
    return _canonical(
        {
            **material,
            "request_fingerprint_sha256": (
                request.request_fingerprint_sha256
            ),
        }
    )


def decode_fast_deterministic_campaign_request(
    payload: str,
) -> FastDeterministicCampaignRequest:
    if not isinstance(payload, str) or not payload:
        raise ValueError(
            "deterministic campaign request payload must be non-empty text"
        )
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "deterministic campaign request is malformed JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError(
            "deterministic campaign request must be a JSON object"
        )
    if payload != _canonical(document):
        raise ValueError(
            "deterministic campaign request must use canonical JSON"
        )
    if frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "deterministic campaign request has unknown or missing top-level fields"
        )
    if document["schema_name"] != FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME:
        raise ValueError(
            "unsupported deterministic campaign request schema_name"
        )
    schema_version = document["schema_version"]
    if schema_version == FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION:
        request_fields = _REQUEST_FIELDS
        request_type = FastDeterministicCampaignRequest
    elif schema_version == FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION:
        request_fields = _REQUEST_FIELDS_V2
        request_type = FastDeterministicCampaignJsonlRequest
    else:
        raise ValueError(
            "unsupported deterministic campaign request schema_version"
        )

    raw_request = document["request"]
    if not isinstance(raw_request, dict):
        raise ValueError(
            "deterministic campaign request body must be an object"
        )
    if frozenset(raw_request) != frozenset(request_fields):
        raise ValueError(
            "deterministic campaign request body has unknown or missing fields"
        )

    decoded = {
        name: _decode_value(raw_request[name])
        for name in request_fields
    }
    try:
        request = request_type(
            schema_name=document["schema_name"],
            schema_version=document["schema_version"],
            **decoded,
            request_fingerprint_sha256=document[
                "request_fingerprint_sha256"
            ],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"deterministic campaign request content is incompatible: {exc}"
        ) from exc

    material = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "request": raw_request,
    }
    if request.request_fingerprint_sha256 != _sha256_canonical(material):
        raise ValueError(
            "deterministic campaign request fingerprint mismatch"
        )
    return request


def run_fast_deterministic_campaign_request_file(
    request_path: str | Path,
) -> FastDeterministicCampaignArtifactManifest:
    source = Path(request_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(
            "deterministic campaign request path must identify an existing file"
        )
    request = decode_fast_deterministic_campaign_request(
        source.read_text(encoding="utf-8")
    )
    base = source.parent

    observer_database_path = _resolve_source_path(
        base,
        request.observer_database_path,
        "observer_database_path",
    )
    if type(request) is FastDeterministicCampaignRequest:
        feature_source_path = _resolve_source_path(
            base,
            request.feature_parquet_path,
            "feature_parquet_path",
        )
        feature_dataset = read_fast_training_feature_parquet(
            feature_source_path
        )
    else:
        feature_source_path = _resolve_source_path(
            base,
            request.feature_jsonl_path,
            "feature_jsonl_path",
        )
        feature_dataset = read_fast_training_feature_jsonl(
            feature_source_path
        )
    comparison_catalog_path = _resolve_source_path(
        base,
        request.comparison_catalog_path,
        "comparison_catalog_path",
    )
    champion_path = _resolve_source_path(
        base,
        request.champion_path,
        "champion_path",
    )
    entry_authority_binary_path = _resolve_source_path(
        base,
        request.entry_authority_binary_path,
        "entry_authority_binary_path",
    )
    candidate_binary_path = _resolve_source_path(
        base,
        request.candidate_binary_path,
        "candidate_binary_path",
    )
    destination = _resolve_path(base, request.destination_path)

    if len(feature_dataset.records) != len(request.contexts):
        raise ValueError(
            "request context population does not match FL8.1 feature population"
        )
    earliest_decision = min(
        value.decision_observed_at_unix_ms
        for value in feature_dataset.records
    )
    if request.starting_ledger_as_of_unix_ms > earliest_decision:
        raise ValueError(
            "starting PAPER ledger time cannot follow the earliest FL8.1 decision"
        )

    catalog = decode_fast_deterministic_comparison_catalog(
        comparison_catalog_path.read_text(encoding="utf-8")
    )
    starting_ledger = create_paper_ledger(
        request.starting_cash_usd,
        request.starting_ledger_as_of_unix_ms,
    )

    return write_fast_deterministic_campaign_artifact(
        database_path=observer_database_path,
        feature_dataset=feature_dataset,
        catalog=catalog,
        champion_path=champion_path,
        execution_policy=request.execution_policy,
        contexts=request.contexts,
        entry_authority_binary_path=entry_authority_binary_path,
        candidate_binary_path=candidate_binary_path,
        paper_run_id_prefix=request.paper_run_id_prefix,
        assessment_version=request.assessment_version,
        starting_ledger=starting_ledger,
        fill_policy=request.fill_policy,
        risk_policy=request.risk_policy,
        position_policy=request.position_policy,
        evaluation_policy=request.evaluation_policy,
        destination=destination,
    )


def _request_material_from_values(
    values: dict[str, object],
    *,
    schema_version: int = FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION,
    request_fields: tuple[str, ...] = _REQUEST_FIELDS,
) -> dict[str, object]:
    if frozenset(values) != frozenset(request_fields):
        raise ValueError(
            "deterministic campaign request material field set is invalid"
        )
    if schema_version not in {
        FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_VERSION,
        FAST_DETERMINISTIC_CAMPAIGN_JSONL_REQUEST_SCHEMA_VERSION,
    }:
        raise ValueError(
            "deterministic campaign request material schema version is unsupported"
        )
    return {
        "schema_name": FAST_DETERMINISTIC_CAMPAIGN_REQUEST_SCHEMA_NAME,
        "schema_version": schema_version,
        "request": {
            name: _encode_value(values[name])
            for name in request_fields
        },
    }


def _validate_request_economic_fields(
    *,
    execution_policy: FastDeterministicComparisonExecutionPolicy,
    contexts: tuple[FastDeterministicComparisonPointInTimeContext, ...],
    starting_cash_usd: float,
    starting_ledger_as_of_unix_ms: int,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> None:
    if type(execution_policy) is not FastDeterministicComparisonExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastDeterministicComparisonExecutionPolicy"
        )
    if (
        not isinstance(contexts, tuple)
        or not contexts
        or not all(
            type(value) is FastDeterministicComparisonPointInTimeContext
            for value in contexts
        )
    ):
        raise ValueError(
            "contexts must be a non-empty tuple of exact point-in-time contexts"
        )
    _require_positive_finite("starting_cash_usd", starting_cash_usd)
    _require_non_negative_int(
        "starting_ledger_as_of_unix_ms",
        starting_ledger_as_of_unix_ms,
    )
    if type(fill_policy) is not PaperFillPolicy:
        raise ValueError("fill_policy must be exact PaperFillPolicy")
    if type(risk_policy) is not RiskPolicy:
        raise ValueError("risk_policy must be exact RiskPolicy")
    if type(position_policy) is not FastPaperPositionActionPolicy:
        raise ValueError(
            "position_policy must be exact FastPaperPositionActionPolicy"
        )
    if type(evaluation_policy) is not TradingEvaluationPolicy:
        raise ValueError(
            "evaluation_policy must be exact TradingEvaluationPolicy"
        )
    if evaluation_policy.starting_equity_usd != starting_cash_usd:
        raise ValueError(
            "evaluation starting equity must equal PAPER starting cash"
        )
    for index, context in enumerate(contexts):
        if context.risk_environment.trading_capital_usd != starting_cash_usd:
            raise ValueError(
                f"risk trading capital must equal PAPER starting cash at context {index}"
            )
        if starting_ledger_as_of_unix_ms > context.evaluated_at_unix_ms:
            raise ValueError(
                f"starting ledger time cannot follow context evaluation at context {index}"
            )


def _encode_value(value: object) -> object:
    value_type = type(value)
    if isinstance(value, Enum):
        enum_name = _ENUM_NAME_BY_TYPE.get(value_type)
        if enum_name is None:
            raise ValueError(
                f"unsupported deterministic campaign request enum type: {value_type.__name__}"
            )
        return {
            "$enum": enum_name,
            "value": value.value,
        }

    dataclass_name = _DATACLASS_NAME_BY_TYPE.get(value_type)
    if dataclass_name is not None:
        if not is_dataclass(value):
            raise ValueError(
                "registered deterministic campaign request dataclass is malformed"
            )
        return {
            "$type": dataclass_name,
            "fields": {
                field.name: _encode_value(getattr(value, field.name))
                for field in fields(value)
            },
        }

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "deterministic campaign request floats must be finite"
            )
        return {"$float": value.hex()}
    if isinstance(value, tuple):
        return {
            "$tuple": [_encode_value(item) for item in value]
        }
    if isinstance(value, frozenset):
        encoded = [_encode_value(item) for item in value]
        encoded.sort(key=_canonical)
        return {"$frozenset": encoded}
    raise ValueError(
        f"unsupported deterministic campaign request value type: {value_type.__name__}"
    )


def _decode_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise ValueError(
            "raw JSON float is not allowed; deterministic campaign request floats must use a tagged encoding"
        )
    if isinstance(value, list):
        raise ValueError(
            "raw JSON arrays are not allowed in deterministic campaign request values"
        )
    if not isinstance(value, dict):
        raise ValueError(
            "deterministic campaign request value has unsupported JSON type"
        )

    keys = frozenset(value)
    if keys == {"$float"}:
        encoded = value["$float"]
        if not isinstance(encoded, str):
            raise ValueError(
                "deterministic campaign request float tag is malformed"
            )
        try:
            decoded = float.fromhex(encoded)
        except ValueError as exc:
            raise ValueError(
                "deterministic campaign request float value is malformed"
            ) from exc
        if not math.isfinite(decoded):
            raise ValueError(
                "deterministic campaign request floats must be finite"
            )
        return decoded

    if keys == {"$tuple"}:
        items = value["$tuple"]
        if not isinstance(items, list):
            raise ValueError(
                "deterministic campaign request tuple tag is malformed"
            )
        return tuple(_decode_value(item) for item in items)

    if keys == {"$frozenset"}:
        items = value["$frozenset"]
        if not isinstance(items, list):
            raise ValueError(
                "deterministic campaign request frozenset tag is malformed"
            )
        decoded = tuple(_decode_value(item) for item in items)
        try:
            return frozenset(decoded)
        except TypeError as exc:
            raise ValueError(
                "deterministic campaign request frozenset contains an unhashable value"
            ) from exc

    if keys == {"$enum", "value"}:
        enum_name = value["$enum"]
        if not isinstance(enum_name, str):
            raise ValueError(
                "deterministic campaign request enum type is malformed"
            )
        enum_type = _ENUM_BY_NAME.get(enum_name)
        if enum_type is None:
            raise ValueError(
                "unknown deterministic campaign request enum type"
            )
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "deterministic campaign request enum value is invalid"
            ) from exc

    if keys == {"$type", "fields"}:
        type_name = value["$type"]
        field_values = value["fields"]
        if not isinstance(type_name, str):
            raise ValueError(
                "deterministic campaign request dataclass type is malformed"
            )
        dataclass_type = _DATACLASS_BY_NAME.get(type_name)
        if dataclass_type is None:
            raise ValueError(
                "unknown deterministic campaign request dataclass type"
            )
        if not isinstance(field_values, dict):
            raise ValueError(
                "deterministic campaign request dataclass fields are malformed"
            )
        expected = {field.name for field in fields(dataclass_type)}
        if set(field_values) != expected:
            raise ValueError(
                "deterministic campaign request dataclass has unknown or missing fields"
            )
        decoded_fields = {
            name: _decode_value(field_values[name])
            for name in expected
        }
        try:
            return dataclass_type(**decoded_fields)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"deterministic campaign request {type_name} invariants rejected content: {exc}"
            ) from exc

    raise ValueError(
        "deterministic campaign request value contains an unknown type tag"
    )


def _resolve_source_path(base: Path, value: str, name: str) -> Path:
    path = _resolve_path(base, value)
    if not path.is_file():
        raise ValueError(f"{name} must resolve to an existing file")
    return path


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_finite(name: str, value: object) -> None:
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
