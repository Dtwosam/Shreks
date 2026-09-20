from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
import hashlib
import json
import math

from shreks_brain.decision import DecisionPolicy, SetupDecisionRule
from shreks_brain.exits import ExitPolicy, TakeProfitLevel
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.paper_loop import PaperLoopState
from shreks_brain.paper_validation import (
    PaperCheckpointError,
    decode_paper_checkpoint,
    encode_paper_checkpoint,
)
from shreks_brain.regime import RecentStrategyPerformance, RegimePolicy
from shreks_brain.registry import RegistryCandidate
from shreks_brain.registry.codec import compute_candidate_fingerprint
from shreks_brain.registry.models import RegistryEvaluationEvidence, RegistryStatus
from shreks_brain.risk import RiskPolicy
from shreks_brain.safety import SafetyPolicy
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import FreshLaunchPolicy

from .assembler import ObserverFreshLaunchPolicyBundle
from .coordinator import ObserverPaperCampaignSelectionPolicy
from .models import (
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperQuotePurpose,
    ObserverPaperRiskEnvironment,
    ObserverRegimeReadPolicy,
)


OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION = (
    "g1c-paper-campaign-runtime-manifest-v1"
)
OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2 = (
    "g1c-paper-campaign-runtime-manifest-v2"
)
OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION = (
    "g1c-paper-quote-usd-valuation-v1"
)


class ObserverPaperCampaignRuntimeManifestError(ValueError):
    """Raised when a G1C PAPER runtime manifest cannot be trusted exactly."""


class ObserverPaperQuoteUsdValuationMode(Enum):
    EXACT_MARKET_RATIO = "exact_market_ratio"


@dataclass(frozen=True, slots=True)
class ObserverPaperQuoteUsdValuationPolicy:
    version: str
    mode: ObserverPaperQuoteUsdValuationMode

    def __post_init__(self) -> None:
        if self.version != OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION:
            raise ObserverPaperCampaignRuntimeManifestError(
                "unsupported quote USD valuation policy version"
            )
        if type(self.mode) is not ObserverPaperQuoteUsdValuationMode:
            raise ObserverPaperCampaignRuntimeManifestError(
                "quote USD valuation mode must be exact"
            )


@dataclass(frozen=True, slots=True)
class ObserverPaperCampaignRuntimeManifest:
    schema_version: str
    paper_run_id: str
    candidate: RegistryCandidate
    initial_state: PaperLoopState
    policy_bundle: ObserverFreshLaunchPolicyBundle
    risk_environment: ObserverPaperRiskEnvironment
    selection_policy: ObserverPaperCampaignSelectionPolicy
    recent_performance: RecentStrategyPerformance | None
    global_risk_halt: bool
    manifest_fingerprint_sha256: str
    quote_usd_valuation_policy: ObserverPaperQuoteUsdValuationPolicy | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in (
            OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
            OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
        ):
            raise ObserverPaperCampaignRuntimeManifestError(
                "unsupported paper campaign runtime manifest schema version"
            )
        if (
            self.schema_version
            == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
        ):
            if self.quote_usd_valuation_policy is not None:
                raise ObserverPaperCampaignRuntimeManifestError(
                    "legacy v1 manifest must not carry quote USD valuation policy"
                )
        else:
            if (
                type(self.quote_usd_valuation_policy)
                is not ObserverPaperQuoteUsdValuationPolicy
            ):
                raise ObserverPaperCampaignRuntimeManifestError(
                    "v2 manifest requires exact quote USD valuation policy"
                )
        _require_non_empty_string("paper_run_id", self.paper_run_id)
        _require_exact_type("candidate", self.candidate, RegistryCandidate)
        _require_exact_type("initial_state", self.initial_state, PaperLoopState)
        _require_exact_type(
            "policy_bundle", self.policy_bundle, ObserverFreshLaunchPolicyBundle
        )
        if (
            self.schema_version
            == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
            and self.policy_bundle.quote_asset.usd_per_token != 1.0
        ):
            raise ObserverPaperCampaignRuntimeManifestError(
                "v2 dynamic valuation requires quote_asset.usd_per_token "
                "to remain the non-authoritative 1.0 compatibility sentinel"
            )
        _require_exact_type(
            "risk_environment",
            self.risk_environment,
            ObserverPaperRiskEnvironment,
        )
        _require_exact_type(
            "selection_policy",
            self.selection_policy,
            ObserverPaperCampaignSelectionPolicy,
        )
        if self.recent_performance is not None:
            _require_exact_type(
                "recent_performance",
                self.recent_performance,
                RecentStrategyPerformance,
            )
        if type(self.global_risk_halt) is not bool:
            raise ObserverPaperCampaignRuntimeManifestError(
                "global_risk_halt must be a boolean"
            )
        _require_sha256(
            "manifest_fingerprint_sha256", self.manifest_fingerprint_sha256
        )
        _require_candidate_fingerprint(self.candidate)
        if self.candidate.strategy_version != self.policy_bundle.fresh_launch_policy.version:
            raise ObserverPaperCampaignRuntimeManifestError(
                "candidate strategy attribution must match Fresh Launch policy"
            )
        if (
            self.candidate.feature_schema_version
            != self.policy_bundle.score_policy.required_feature_schema_version
        ):
            raise ObserverPaperCampaignRuntimeManifestError(
                "candidate feature attribution must match bundled score policy"
            )


_DATACLASS_TYPES = (
    RegistryCandidate,
    RegistryEvaluationEvidence,
    ObserverFreshLaunchPolicyBundle,
    ObserverMarketReadPolicy,
    SafetyPolicy,
    ObserverSafetyProbeIdentity,
    ObserverRegimeReadPolicy,
    RegimePolicy,
    FreshLaunchPolicy,
    ScorePolicy,
    DecisionPolicy,
    SetupDecisionRule,
    RiskPolicy,
    ExitPolicy,
    TakeProfitLevel,
    ObserverPaperQuoteAsset,
    ObserverPaperQuoteIdentity,
    ObserverPaperRiskEnvironment,
    ObserverPaperCampaignSelectionPolicy,
    RecentStrategyPerformance,
    ObserverPaperQuoteUsdValuationPolicy,
)
_DATACLASS_BY_NAME = {item.__name__: item for item in _DATACLASS_TYPES}
_DATACLASS_NAME_BY_TYPE = {item: item.__name__ for item in _DATACLASS_TYPES}

_ENUM_TYPES = (
    RegistryStatus,
    ObserverPaperQuotePurpose,
    ObserverPaperQuoteUsdValuationMode,
)
_ENUM_BY_NAME = {item.__name__: item for item in _ENUM_TYPES}
_ENUM_NAME_BY_TYPE = {item: item.__name__ for item in _ENUM_TYPES}

_TOP_LEVEL_FIELDS_V1 = {
    "schema_version",
    "paper_run_id",
    "candidate",
    "initial_state_checkpoint",
    "policy_bundle",
    "risk_environment",
    "selection_policy",
    "recent_performance",
    "global_risk_halt",
    "manifest_fingerprint_sha256",
}
_TOP_LEVEL_FIELDS_V2 = _TOP_LEVEL_FIELDS_V1 | {"quote_usd_valuation_policy"}


def build_observer_paper_campaign_runtime_manifest(
    *,
    paper_run_id: str,
    candidate: RegistryCandidate,
    initial_state: PaperLoopState,
    policy_bundle: ObserverFreshLaunchPolicyBundle,
    risk_environment: ObserverPaperRiskEnvironment,
    selection_policy: ObserverPaperCampaignSelectionPolicy,
    recent_performance: RecentStrategyPerformance | None,
    global_risk_halt: bool,
) -> ObserverPaperCampaignRuntimeManifest:
    draft = ObserverPaperCampaignRuntimeManifest(
        schema_version=OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
        paper_run_id=paper_run_id,
        candidate=candidate,
        initial_state=initial_state,
        policy_bundle=policy_bundle,
        risk_environment=risk_environment,
        selection_policy=selection_policy,
        recent_performance=recent_performance,
        global_risk_halt=global_risk_halt,
        manifest_fingerprint_sha256="0" * 64,
    )
    fingerprint = _manifest_fingerprint(draft)
    return replace(draft, manifest_fingerprint_sha256=fingerprint)


def build_observer_paper_campaign_runtime_manifest_v2(
    *,
    paper_run_id: str,
    candidate: RegistryCandidate,
    initial_state: PaperLoopState,
    policy_bundle: ObserverFreshLaunchPolicyBundle,
    risk_environment: ObserverPaperRiskEnvironment,
    selection_policy: ObserverPaperCampaignSelectionPolicy,
    recent_performance: RecentStrategyPerformance | None,
    global_risk_halt: bool,
    quote_usd_valuation_policy: ObserverPaperQuoteUsdValuationPolicy,
) -> ObserverPaperCampaignRuntimeManifest:
    draft = ObserverPaperCampaignRuntimeManifest(
        schema_version=OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2,
        paper_run_id=paper_run_id,
        candidate=candidate,
        initial_state=initial_state,
        policy_bundle=policy_bundle,
        risk_environment=risk_environment,
        selection_policy=selection_policy,
        recent_performance=recent_performance,
        global_risk_halt=global_risk_halt,
        manifest_fingerprint_sha256="0" * 64,
        quote_usd_valuation_policy=quote_usd_valuation_policy,
    )
    fingerprint = _manifest_fingerprint(draft)
    return replace(draft, manifest_fingerprint_sha256=fingerprint)


def encode_observer_paper_campaign_runtime_manifest(
    manifest: ObserverPaperCampaignRuntimeManifest,
) -> bytes:
    if type(manifest) is not ObserverPaperCampaignRuntimeManifest:
        raise ObserverPaperCampaignRuntimeManifestError(
            "manifest must be an exact ObserverPaperCampaignRuntimeManifest"
        )
    expected = _manifest_fingerprint(manifest)
    if expected != manifest.manifest_fingerprint_sha256:
        raise ObserverPaperCampaignRuntimeManifestError(
            "manifest fingerprint does not match manifest content"
        )
    return _canonical_json(_manifest_document(manifest, include_fingerprint=True))


def decode_observer_paper_campaign_runtime_manifest(
    payload: bytes | str,
) -> ObserverPaperCampaignRuntimeManifest:
    raw = _payload_bytes(payload)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            "runtime manifest is not valid UTF-8 JSON"
        ) from error
    if not isinstance(value, dict):
        raise ObserverPaperCampaignRuntimeManifestError(
            "runtime manifest must be a JSON object"
        )
    schema_version = _string(value.get("schema_version"), "schema_version")
    if schema_version == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION:
        expected_fields = _TOP_LEVEL_FIELDS_V1
    elif schema_version == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2:
        expected_fields = _TOP_LEVEL_FIELDS_V2
    else:
        raise ObserverPaperCampaignRuntimeManifestError(
            "unsupported paper campaign runtime manifest schema version"
        )
    document = _exact_dict(value, expected_fields, "runtime manifest")

    paper_run_id = _string(document["paper_run_id"], "paper_run_id")
    candidate = _decode_exact_type(
        document["candidate"], RegistryCandidate, "candidate"
    )
    _require_candidate_fingerprint(candidate)
    initial_state = _decode_initial_state_checkpoint(
        document["initial_state_checkpoint"]
    )
    policy_bundle = _decode_exact_type(
        document["policy_bundle"],
        ObserverFreshLaunchPolicyBundle,
        "policy_bundle",
    )
    risk_environment = _decode_exact_type(
        document["risk_environment"],
        ObserverPaperRiskEnvironment,
        "risk_environment",
    )
    selection_policy = _decode_exact_type(
        document["selection_policy"],
        ObserverPaperCampaignSelectionPolicy,
        "selection_policy",
    )

    raw_recent = document["recent_performance"]
    recent_performance = (
        None
        if raw_recent is None
        else _decode_exact_type(
            raw_recent,
            RecentStrategyPerformance,
            "recent_performance",
        )
    )
    global_risk_halt = _bool(document["global_risk_halt"], "global_risk_halt")
    quote_usd_valuation_policy = (
        None
        if schema_version
        == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
        else _decode_exact_type(
            document["quote_usd_valuation_policy"],
            ObserverPaperQuoteUsdValuationPolicy,
            "quote_usd_valuation_policy",
        )
    )
    fingerprint = _string(
        document["manifest_fingerprint_sha256"],
        "manifest_fingerprint_sha256",
    )

    try:
        manifest = ObserverPaperCampaignRuntimeManifest(
            schema_version=schema_version,
            paper_run_id=paper_run_id,
            candidate=candidate,
            initial_state=initial_state,
            policy_bundle=policy_bundle,
            risk_environment=risk_environment,
            selection_policy=selection_policy,
            recent_performance=recent_performance,
            global_risk_halt=global_risk_halt,
            manifest_fingerprint_sha256=fingerprint,
            quote_usd_valuation_policy=quote_usd_valuation_policy,
        )
    except ObserverPaperCampaignRuntimeManifestError:
        raise
    except (TypeError, ValueError) as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"runtime manifest invariants rejected content: {error}"
        ) from error

    expected_fingerprint = _manifest_fingerprint(manifest)
    if expected_fingerprint != manifest.manifest_fingerprint_sha256:
        raise ObserverPaperCampaignRuntimeManifestError(
            "manifest fingerprint does not match persisted content"
        )

    canonical = encode_observer_paper_campaign_runtime_manifest(manifest)
    if canonical != raw:
        raise ObserverPaperCampaignRuntimeManifestError(
            "runtime manifest payload is not canonical"
        )
    return manifest


def _manifest_fingerprint(manifest: ObserverPaperCampaignRuntimeManifest) -> str:
    return hashlib.sha256(
        _canonical_json(_manifest_document(manifest, include_fingerprint=False))
    ).hexdigest()


def _manifest_document(
    manifest: ObserverPaperCampaignRuntimeManifest,
    *,
    include_fingerprint: bool,
) -> dict[str, object]:
    try:
        checkpoint = encode_paper_checkpoint(
            manifest.paper_run_id,
            0,
            manifest.initial_state,
            manifest.initial_state.last_cycle_at_unix_ms,
        ).decode("utf-8")
    except (PaperCheckpointError, UnicodeDecodeError) as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"initial paper state cannot be encoded safely: {error}"
        ) from error

    result: dict[str, object] = {
        "schema_version": manifest.schema_version,
        "paper_run_id": manifest.paper_run_id,
        "candidate": _encode_value(manifest.candidate),
        "initial_state_checkpoint": checkpoint,
        "policy_bundle": _encode_value(manifest.policy_bundle),
        "risk_environment": _encode_value(manifest.risk_environment),
        "selection_policy": _encode_value(manifest.selection_policy),
        "recent_performance": _encode_value(manifest.recent_performance),
        "global_risk_halt": manifest.global_risk_halt,
    }
    if (
        manifest.schema_version
        == OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION_V2
    ):
        result["quote_usd_valuation_policy"] = _encode_value(
            manifest.quote_usd_valuation_policy
        )
    if include_fingerprint:
        result["manifest_fingerprint_sha256"] = manifest.manifest_fingerprint_sha256
    return result


def _decode_initial_state_checkpoint(value: object) -> PaperLoopState:
    checkpoint_payload = _string(value, "initial_state_checkpoint")
    try:
        record = decode_paper_checkpoint(checkpoint_payload)
    except PaperCheckpointError as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"initial_state_checkpoint is invalid: {error}"
        ) from error
    if record.sequence != 0:
        raise ObserverPaperCampaignRuntimeManifestError(
            "initial_state_checkpoint sequence must be zero"
        )
    if record.created_at_unix_ms != record.state.last_cycle_at_unix_ms:
        raise ObserverPaperCampaignRuntimeManifestError(
            "initial_state_checkpoint must be anchored at initial state time"
        )
    return record.state


def _encode_value(value: object) -> object:
    value_type = type(value)
    if isinstance(value, Enum):
        enum_name = _ENUM_NAME_BY_TYPE.get(value_type)
        if enum_name is None:
            raise ObserverPaperCampaignRuntimeManifestError(
                f"unsupported runtime manifest enum type: {value_type.__name__}"
            )
        return {"$enum": enum_name, "value": value.value}

    if value is None or isinstance(value, (bool, int, str)):
        return value

    dataclass_name = _DATACLASS_NAME_BY_TYPE.get(value_type)
    if dataclass_name is not None:
        if not is_dataclass(value):
            raise ObserverPaperCampaignRuntimeManifestError(
                "registered runtime manifest dataclass is malformed"
            )
        return {
            "$type": dataclass_name,
            "fields": {
                field.name: _encode_value(getattr(value, field.name))
                for field in fields(value)
            },
        }

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObserverPaperCampaignRuntimeManifestError(
                "runtime manifest floats must be finite"
            )
        return {"$float": value.hex()}
    if isinstance(value, tuple):
        return {"$tuple": [_encode_value(item) for item in value]}

    raise ObserverPaperCampaignRuntimeManifestError(
        f"unsupported runtime manifest value type: {value_type.__name__}"
    )


def _decode_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise ObserverPaperCampaignRuntimeManifestError(
            "raw JSON floats are not allowed in tagged runtime manifest values"
        )
    if isinstance(value, list):
        raise ObserverPaperCampaignRuntimeManifestError(
            "raw JSON arrays are not allowed in tagged runtime manifest values"
        )
    if not isinstance(value, dict):
        raise ObserverPaperCampaignRuntimeManifestError(
            "runtime manifest value has unsupported JSON type"
        )

    keys = set(value)
    if keys == {"$float"}:
        encoded = value["$float"]
        if not isinstance(encoded, str):
            raise ObserverPaperCampaignRuntimeManifestError(
                "malformed runtime manifest float tag"
            )
        try:
            decoded = float.fromhex(encoded)
        except ValueError as error:
            raise ObserverPaperCampaignRuntimeManifestError(
                "malformed runtime manifest float value"
            ) from error
        if not math.isfinite(decoded):
            raise ObserverPaperCampaignRuntimeManifestError(
                "runtime manifest floats must be finite"
            )
        return decoded

    if keys == {"$tuple"}:
        items = value["$tuple"]
        if not isinstance(items, list):
            raise ObserverPaperCampaignRuntimeManifestError(
                "malformed runtime manifest tuple tag"
            )
        return tuple(_decode_value(item) for item in items)

    if keys == {"$enum", "value"}:
        enum_name = value["$enum"]
        if not isinstance(enum_name, str) or enum_name not in _ENUM_BY_NAME:
            raise ObserverPaperCampaignRuntimeManifestError(
                "unknown runtime manifest enum type"
            )
        enum_type = _ENUM_BY_NAME[enum_name]
        try:
            return enum_type(value["value"])
        except (TypeError, ValueError) as error:
            raise ObserverPaperCampaignRuntimeManifestError(
                "invalid runtime manifest enum value"
            ) from error

    if keys == {"$type", "fields"}:
        type_name = value["$type"]
        raw_fields = value["fields"]
        if not isinstance(type_name, str) or type_name not in _DATACLASS_BY_NAME:
            raise ObserverPaperCampaignRuntimeManifestError(
                "unknown runtime manifest dataclass type"
            )
        if not isinstance(raw_fields, dict):
            raise ObserverPaperCampaignRuntimeManifestError(
                "malformed runtime manifest dataclass fields"
            )
        dataclass_type = _DATACLASS_BY_NAME[type_name]
        expected_fields = {field.name for field in fields(dataclass_type)}
        if set(raw_fields) != expected_fields:
            raise ObserverPaperCampaignRuntimeManifestError(
                f"runtime manifest {type_name} field set is malformed"
            )
        decoded_fields = {
            name: _decode_value(raw_fields[name]) for name in expected_fields
        }
        try:
            return dataclass_type(**decoded_fields)
        except (TypeError, ValueError) as error:
            raise ObserverPaperCampaignRuntimeManifestError(
                f"runtime manifest {type_name} invariants rejected content: {error}"
            ) from error

    raise ObserverPaperCampaignRuntimeManifestError(
        "runtime manifest value contains malformed type tag"
    )


def _decode_exact_type(value: object, expected_type: type, label: str):
    decoded = _decode_value(value)
    if type(decoded) is not expected_type:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must decode to exact {expected_type.__name__} type"
        )
    return decoded


def _exact_dict(value: object, expected_fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} field set is malformed"
        )
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            "runtime manifest cannot be canonicalized"
        ) from error


def _payload_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise ObserverPaperCampaignRuntimeManifestError(
        "runtime manifest payload must be bytes or text"
    )


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must be a non-empty string"
        )
    return value


def _bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must be a boolean"
        )
    return value


def _require_non_empty_string(label: str, value: object) -> None:
    _string(value, label)


def _require_exact_type(label: str, value: object, expected_type: type) -> None:
    if type(value) is not expected_type:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must be an exact {expected_type.__name__}"
        )


def _require_sha256(label: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must be a 64-character sha256"
        )
    try:
        int(value, 16)
    except ValueError as error:
        raise ObserverPaperCampaignRuntimeManifestError(
            f"{label} must be hexadecimal sha256"
        ) from error


def _require_candidate_fingerprint(candidate: RegistryCandidate) -> None:
    actual = compute_candidate_fingerprint(candidate)
    if actual != candidate.candidate_fingerprint_sha256:
        raise ObserverPaperCampaignRuntimeManifestError(
            "candidate fingerprint does not match candidate content"
        )
