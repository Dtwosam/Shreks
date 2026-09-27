from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicComparisonExecutionPolicy,
)
from shreks_brain.fast_deterministic_offline import (
    FastOfflineExecutionCostModel,
    FastOfflineExecutionLegCost,
)
from shreks_brain.observer_campaign import ObserverRegimeReadPolicy
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.regime import RegimePolicy
from shreks_brain.risk_control import load_operator_risk_control_state
from shreks_brain.safety import SafetyPolicy

from .models import FastPaperRuntimeManifest
from .shadow_service import FastPaperShadowServicePolicy


FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_NAME = (
    "shreks.fast_paper_shadow_buy_writer_policy"
)
FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_VERSION = 1

_TOP_KEYS = frozenset(
    {
        "schema_name",
        "schema_version",
        "market_read_policy",
        "regime_read_policy",
        "regime_policy",
        "safety_policy",
        "safety_probe_identity",
        "execution_economics_policies",
        "operator_risk_control_path",
        "entry_authority_binary_path",
        "entry_authority_binary_sha256",
        "day_started_at_unix_ms",
        "data_healthy",
        "execution_healthy",
        "global_risk_halt",
        "policy_fingerprint_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowBuyWriterPolicy:
    schema_name: str
    schema_version: int
    market_read_policy: ObserverMarketReadPolicy
    regime_read_policy: ObserverRegimeReadPolicy
    regime_policy: RegimePolicy
    safety_policy: SafetyPolicy
    safety_probe_identity: ObserverSafetyProbeIdentity
    execution_economics_policies: tuple[
        FastDeterministicComparisonExecutionPolicy, ...
    ]
    operator_risk_control_path: Path
    entry_authority_binary_path: Path
    entry_authority_binary_sha256: str
    day_started_at_unix_ms: int
    data_healthy: bool | None
    execution_healthy: bool | None
    global_risk_halt: bool
    policy_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_NAME:
            raise ValueError("BUY writer policy schema_name is incompatible")
        if self.schema_version != FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_VERSION:
            raise ValueError("BUY writer policy schema_version is incompatible")
        _require_exact(
            "market_read_policy",
            self.market_read_policy,
            ObserverMarketReadPolicy,
        )
        _require_exact(
            "regime_read_policy",
            self.regime_read_policy,
            ObserverRegimeReadPolicy,
        )
        _require_exact("regime_policy", self.regime_policy, RegimePolicy)
        _require_exact("safety_policy", self.safety_policy, SafetyPolicy)
        _require_exact(
            "safety_probe_identity",
            self.safety_probe_identity,
            ObserverSafetyProbeIdentity,
        )
        if (
            not isinstance(self.execution_economics_policies, tuple)
            or not self.execution_economics_policies
            or not all(
                type(value) is FastDeterministicComparisonExecutionPolicy
                for value in self.execution_economics_policies
            )
        ):
            raise ValueError(
                "execution_economics_policies must be a non-empty tuple of exact policies"
            )
        horizons = tuple(
            value.horizon_ms for value in self.execution_economics_policies
        )
        if horizons != tuple(sorted(horizons)):
            raise ValueError(
                "execution economics policies must use canonical horizon order"
            )
        if len(set(horizons)) != len(horizons):
            raise ValueError(
                "execution economics policies contain duplicate horizons"
            )
        _require_absolute_path(
            "operator_risk_control_path",
            self.operator_risk_control_path,
        )
        _require_absolute_path(
            "entry_authority_binary_path",
            self.entry_authority_binary_path,
        )
        _require_sha256(
            "entry_authority_binary_sha256",
            self.entry_authority_binary_sha256,
        )
        _require_non_negative_int(
            "day_started_at_unix_ms",
            self.day_started_at_unix_ms,
        )
        _require_optional_bool("data_healthy", self.data_healthy)
        _require_optional_bool(
            "execution_healthy",
            self.execution_healthy,
        )
        if type(self.global_risk_halt) is not bool:
            raise ValueError("global_risk_halt must be bool")
        _require_sha256(
            "policy_fingerprint_sha256",
            self.policy_fingerprint_sha256,
        )
        expected = _fingerprint(self)
        if self.policy_fingerprint_sha256 != expected:
            raise ValueError("BUY writer policy fingerprint mismatch")


def build_fast_paper_shadow_buy_writer_policy(
    *,
    market_read_policy: ObserverMarketReadPolicy,
    regime_read_policy: ObserverRegimeReadPolicy,
    regime_policy: RegimePolicy,
    safety_policy: SafetyPolicy,
    safety_probe_identity: ObserverSafetyProbeIdentity,
    execution_economics_policies: tuple[
        FastDeterministicComparisonExecutionPolicy, ...
    ],
    operator_risk_control_path: str | Path,
    entry_authority_binary_path: str | Path,
    entry_authority_binary_sha256: str,
    day_started_at_unix_ms: int,
    data_healthy: bool | None,
    execution_healthy: bool | None,
    global_risk_halt: bool,
) -> FastPaperShadowBuyWriterPolicy:
    ordered = tuple(
        sorted(
            execution_economics_policies,
            key=lambda value: value.horizon_ms,
        )
    )
    values = {
        "schema_name": FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_NAME,
        "schema_version": FAST_PAPER_SHADOW_BUY_WRITER_POLICY_SCHEMA_VERSION,
        "market_read_policy": market_read_policy,
        "regime_read_policy": regime_read_policy,
        "regime_policy": regime_policy,
        "safety_policy": safety_policy,
        "safety_probe_identity": safety_probe_identity,
        "execution_economics_policies": ordered,
        "operator_risk_control_path": Path(operator_risk_control_path),
        "entry_authority_binary_path": Path(entry_authority_binary_path),
        "entry_authority_binary_sha256": entry_authority_binary_sha256,
        "day_started_at_unix_ms": day_started_at_unix_ms,
        "data_healthy": data_healthy,
        "execution_healthy": execution_healthy,
        "global_risk_halt": global_risk_halt,
    }
    fingerprint = hashlib.sha256(
        _canonical(_material_from_values(values)).encode("utf-8")
    ).hexdigest()
    return FastPaperShadowBuyWriterPolicy(
        **values,
        policy_fingerprint_sha256=fingerprint,
    )


def write_fast_paper_shadow_buy_writer_policy(
    policy: FastPaperShadowBuyWriterPolicy,
    destination: str | Path,
) -> None:
    _require_exact(
        "policy",
        policy,
        FastPaperShadowBuyWriterPolicy,
    )
    _verify_policy_fingerprint(policy)
    path = Path(destination).expanduser()
    if path.exists() or path.is_symlink():
        raise FileExistsError("BUY writer policy destination already exists")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError(
            "BUY writer policy parent must be an existing regular non-symlink directory"
        )
    payload = (_canonical(_document(policy)) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
        published = True
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
        temporary.unlink()
        _fsync_directory(path.parent)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if published:
            path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise


def read_fast_paper_shadow_buy_writer_policy(
    source: str | Path,
) -> FastPaperShadowBuyWriterPolicy:
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError(
            "BUY writer policy source must be a regular non-symlink file"
        )
    payload = path.read_text(encoding="utf-8")
    if not payload.endswith("\n") or payload.endswith("\n\n"):
        raise ValueError(
            "BUY writer policy must have exactly one trailing newline"
        )
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("BUY writer policy is malformed JSON") from exc
    if not isinstance(document, dict) or frozenset(document) != _TOP_KEYS:
        raise ValueError(
            "BUY writer policy has unknown or missing fields"
        )
    if payload != _canonical(document) + "\n":
        raise ValueError("BUY writer policy must use canonical JSON")

    values = {
        "schema_name": document["schema_name"],
        "schema_version": document["schema_version"],
        "market_read_policy": _decode_market_read_policy(
            document["market_read_policy"]
        ),
        "regime_read_policy": _decode_regime_read_policy(
            document["regime_read_policy"]
        ),
        "regime_policy": _decode_regime_policy(
            document["regime_policy"]
        ),
        "safety_policy": _decode_safety_policy(
            document["safety_policy"]
        ),
        "safety_probe_identity": _decode_safety_probe_identity(
            document["safety_probe_identity"]
        ),
        "execution_economics_policies": _decode_execution_policies(
            document["execution_economics_policies"]
        ),
        "operator_risk_control_path": Path(
            _require_text(
                "operator_risk_control_path",
                document["operator_risk_control_path"],
            )
        ),
        "entry_authority_binary_path": Path(
            _require_text(
                "entry_authority_binary_path",
                document["entry_authority_binary_path"],
            )
        ),
        "entry_authority_binary_sha256": document[
            "entry_authority_binary_sha256"
        ],
        "day_started_at_unix_ms": document["day_started_at_unix_ms"],
        "data_healthy": document["data_healthy"],
        "execution_healthy": document["execution_healthy"],
        "global_risk_halt": document["global_risk_halt"],
        "policy_fingerprint_sha256": document[
            "policy_fingerprint_sha256"
        ],
    }
    try:
        return FastPaperShadowBuyWriterPolicy(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("BUY writer policy content is incompatible") from exc


def verify_fast_paper_shadow_buy_writer_policy_bindings(
    manifest: FastPaperRuntimeManifest,
    service_policy: FastPaperShadowServicePolicy,
    policy: FastPaperShadowBuyWriterPolicy,
) -> None:
    _require_exact("manifest", manifest, FastPaperRuntimeManifest)
    _require_exact(
        "service_policy",
        service_policy,
        FastPaperShadowServicePolicy,
    )
    _require_exact(
        "policy",
        policy,
        FastPaperShadowBuyWriterPolicy,
    )
    _verify_policy_fingerprint(policy)

    if manifest.quote_provider != "jupiter":
        raise ValueError(
            "BUY writer policy requires the persisted Jupiter quote authority"
        )
    regime = policy.regime_read_policy
    expected_regime = (
        service_policy.probe_policy_version,
        manifest.quote_mint,
        service_policy.entry_input_amount_raw,
        service_policy.taker,
        service_policy.slippage_bps,
    )
    actual_regime = (
        regime.entry_probe_policy_version,
        regime.quote_asset_mint,
        regime.entry_input_amount,
        regime.taker,
        regime.slippage_bps,
    )
    if actual_regime != expected_regime:
        raise ValueError(
            "BUY writer policy regime ENTRY identity does not match service policy"
        )

    probe = policy.safety_probe_identity
    expected_probe = (
        service_policy.probe_policy_version,
        manifest.quote_mint,
        service_policy.exit_input_amount_raw,
        service_policy.taker,
        service_policy.slippage_bps,
    )
    actual_probe = (
        probe.probe_policy_version,
        probe.output_mint,
        probe.input_amount,
        probe.taker,
        probe.slippage_bps,
    )
    if actual_probe != expected_probe:
        raise ValueError(
            "BUY writer policy safety EXIT identity does not match service policy"
        )

    expected_horizons = set(manifest.action_policy.horizons_ms)
    actual_horizons = {
        value.horizon_ms
        for value in policy.execution_economics_policies
    }
    if actual_horizons != expected_horizons:
        raise ValueError(
            "BUY writer policy execution economics horizon coverage does not match learned action policy"
        )

    binary = policy.entry_authority_binary_path
    if binary.is_symlink() or not binary.is_file():
        raise ValueError(
            "BUY writer policy entry authority binary must be a regular non-symlink file"
        )
    decision_binary = Path(manifest.decision_binary_path)
    if binary.parent != decision_binary.parent:
        raise ValueError(
            "BUY writer policy entry authority binary must be release-local beside decision binary"
        )
    actual_binary_sha = _sha256_file(binary)
    if actual_binary_sha != policy.entry_authority_binary_sha256:
        raise ValueError(
            "BUY writer policy entry authority binary SHA digest mismatch"
        )

    control = policy.operator_risk_control_path
    if control.is_symlink() or not control.is_file():
        raise ValueError(
            "BUY writer policy operator control path must be a regular non-symlink file"
        )
    load_operator_risk_control_state(control)


def _material_from_values(values: dict[str, object]) -> dict[str, object]:
    return {
        "schema_name": values["schema_name"],
        "schema_version": values["schema_version"],
        "market_read_policy": asdict(values["market_read_policy"]),
        "regime_read_policy": asdict(values["regime_read_policy"]),
        "regime_policy": asdict(values["regime_policy"]),
        "safety_policy": asdict(values["safety_policy"]),
        "safety_probe_identity": asdict(values["safety_probe_identity"]),
        "execution_economics_policies": [
            asdict(value)
            for value in values["execution_economics_policies"]
        ],
        "operator_risk_control_path": str(
            values["operator_risk_control_path"]
        ),
        "entry_authority_binary_path": str(
            values["entry_authority_binary_path"]
        ),
        "entry_authority_binary_sha256": values[
            "entry_authority_binary_sha256"
        ],
        "day_started_at_unix_ms": values["day_started_at_unix_ms"],
        "data_healthy": values["data_healthy"],
        "execution_healthy": values["execution_healthy"],
        "global_risk_halt": values["global_risk_halt"],
    }


def _material(policy: FastPaperShadowBuyWriterPolicy) -> dict[str, object]:
    return _material_from_values(
        {
            name: getattr(policy, name)
            for name in (
                "schema_name",
                "schema_version",
                "market_read_policy",
                "regime_read_policy",
                "regime_policy",
                "safety_policy",
                "safety_probe_identity",
                "execution_economics_policies",
                "operator_risk_control_path",
                "entry_authority_binary_path",
                "entry_authority_binary_sha256",
                "day_started_at_unix_ms",
                "data_healthy",
                "execution_healthy",
                "global_risk_halt",
            )
        }
    )


def _document(
    policy: FastPaperShadowBuyWriterPolicy,
) -> dict[str, object]:
    return {
        **_material(policy),
        "policy_fingerprint_sha256": policy.policy_fingerprint_sha256,
    }


def _fingerprint(policy: FastPaperShadowBuyWriterPolicy) -> str:
    return hashlib.sha256(
        _canonical(_material(policy)).encode("utf-8")
    ).hexdigest()


def _verify_policy_fingerprint(
    policy: FastPaperShadowBuyWriterPolicy,
) -> None:
    if policy.policy_fingerprint_sha256 != _fingerprint(policy):
        raise ValueError("BUY writer policy fingerprint mismatch")


def _decode_market_read_policy(value: object) -> ObserverMarketReadPolicy:
    raw = _exact_mapping(value, ObserverMarketReadPolicy, "market read policy")
    return ObserverMarketReadPolicy(
        version=raw["version"],
        source_priority=_string_tuple(
            raw["source_priority"],
            "market source_priority",
        ),
        max_current_age_ms=raw["max_current_age_ms"],
        local_range_lookback_ms=raw["local_range_lookback_ms"],
    )


def _decode_regime_read_policy(value: object) -> ObserverRegimeReadPolicy:
    raw = _exact_mapping(value, ObserverRegimeReadPolicy, "regime read policy")
    return ObserverRegimeReadPolicy(
        version=raw["version"],
        window_ms=raw["window_ms"],
        max_snapshot_age_ms=raw["max_snapshot_age_ms"],
        source_priority=_string_tuple(
            raw["source_priority"],
            "regime source_priority",
        ),
        entry_probe_policy_version=raw["entry_probe_policy_version"],
        quote_asset_mint=raw["quote_asset_mint"],
        entry_input_amount=raw["entry_input_amount"],
        taker=raw["taker"],
        slippage_bps=raw["slippage_bps"],
    )


def _decode_regime_policy(value: object) -> RegimePolicy:
    raw = _exact_mapping(value, RegimePolicy, "regime policy")
    return RegimePolicy(**raw)


def _decode_safety_policy(value: object) -> SafetyPolicy:
    raw = _exact_mapping(value, SafetyPolicy, "safety policy")
    return SafetyPolicy(**raw)


def _decode_safety_probe_identity(
    value: object,
) -> ObserverSafetyProbeIdentity:
    raw = _exact_mapping(
        value,
        ObserverSafetyProbeIdentity,
        "safety probe identity",
    )
    return ObserverSafetyProbeIdentity(**raw)


def _decode_execution_policies(
    value: object,
) -> tuple[FastDeterministicComparisonExecutionPolicy, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(
            "execution economics policies must be a non-empty list"
        )
    result = []
    for item in value:
        raw = _exact_mapping(
            item,
            FastDeterministicComparisonExecutionPolicy,
            "execution economics policy",
        )
        cost_raw = _exact_mapping(
            raw["cost_model"],
            FastOfflineExecutionCostModel,
            "execution cost model",
        )
        entry = FastOfflineExecutionLegCost(
            **_exact_mapping(
                cost_raw["entry"],
                FastOfflineExecutionLegCost,
                "entry execution cost",
            )
        )
        exit_cost = FastOfflineExecutionLegCost(
            **_exact_mapping(
                cost_raw["exit"],
                FastOfflineExecutionLegCost,
                "exit execution cost",
            )
        )
        cost_model = FastOfflineExecutionCostModel(
            version=cost_raw["version"],
            entry=entry,
            exit=exit_cost,
        )
        result.append(
            FastDeterministicComparisonExecutionPolicy(
                version=raw["version"],
                horizon_ms=raw["horizon_ms"],
                cost_model=cost_model,
                required_edge_bps=raw["required_edge_bps"],
                risk_margin_bps=raw["risk_margin_bps"],
            )
        )
    return tuple(result)


def _exact_mapping(
    value: object,
    model: type,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    expected = frozenset(field.name for field in fields(model))
    if frozenset(value) != expected:
        raise ValueError(f"{label} has unknown or missing fields")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON list")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise ValueError(f"{label} must contain strings")
    return result


def _sha256_file(path: Path) -> str:
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


def _reject_duplicate_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _require_exact(name: str, value: object, expected: type) -> None:
    if type(value) is not expected:
        raise ValueError(f"{name} must be exact {expected.__name__}")


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_absolute_path(name: str, value: object) -> None:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{name} must be an absolute Path")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_bool(name: str, value: object) -> None:
    if value is not None and type(value) is not bool:
        raise ValueError(f"{name} must be bool or None")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
