from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType


FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME = (
    "shreks.fast_deterministic_lifecycle_results"
)
FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME = (
    "shreks.fast_deterministic_candidate_manifest"
)
FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION = 1
FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY = "fast_deterministic_lifecycle"

_ENTRY_KINDS = frozenset(
    {"IMPULSE_SCALP", "MICRO_PULLBACK", "PRE_GRADUATION", "GRADUATION_FLOW"}
)
_MANAGER_KINDS = frozenset({"WALLET_COHORT", "LONGER_RUNNER"})
_KIND_VERSIONS = {
    "IMPULSE_SCALP": 1,
    "MICRO_PULLBACK": 1,
    "PRE_GRADUATION": 1,
    "GRADUATION_FLOW": 1,
    "WALLET_COHORT": 1,
    "LONGER_RUNNER": 1,
}
_ACTIONS = frozenset({"BUY", "SKIP", "HOLD", "REDUCE", "SELL"})


@dataclass(frozen=True, slots=True)
class FastDeterministicLifecyclePolicy:
    version: int
    entry_baseline_kind: str
    manager_baseline_kind: str
    entry_target_exposure_fraction: float
    reduce_remaining_fraction: float

    def __post_init__(self) -> None:
        _require_positive_int("version", self.version)
        if self.entry_baseline_kind not in _ENTRY_KINDS:
            raise ValueError(
                "entry_baseline_kind must be an FL6.1-FL6.4 deterministic entry family"
            )
        if self.manager_baseline_kind not in _MANAGER_KINDS:
            raise ValueError(
                "manager_baseline_kind must be an FL6.5-FL6.6 deterministic manager"
            )
        _require_fraction(
            "entry_target_exposure_fraction",
            self.entry_target_exposure_fraction,
            minimum_open=True,
            maximum_open=False,
        )
        _require_fraction(
            "reduce_remaining_fraction",
            self.reduce_remaining_fraction,
            minimum_open=True,
            maximum_open=True,
        )


@dataclass(frozen=True, slots=True)
class FastDeterministicLifecycleDecision:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    posture: str
    component_kind: str
    component_version: int
    action: str
    current_exposure_fraction: float | None
    target_exposure_fraction: float

    def __post_init__(self) -> None:
        _require_non_empty_string("source_event_id", self.source_event_id)
        _require_non_empty_string("market_key", self.market_key)
        _require_positive_int("source_sequence", self.source_sequence)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if self.posture not in {"FLAT", "OPEN"}:
            raise ValueError("posture must be FLAT or OPEN")
        if self.component_kind not in _KIND_VERSIONS:
            raise ValueError("component_kind is unsupported")
        _require_positive_int("component_version", self.component_version)
        if self.component_version != _KIND_VERSIONS[self.component_kind]:
            raise ValueError(
                "component_version does not match declared deterministic baseline kind"
            )
        if self.action not in _ACTIONS:
            raise ValueError("action is unsupported")
        if self.current_exposure_fraction is not None:
            _require_fraction(
                "current_exposure_fraction",
                self.current_exposure_fraction,
                minimum_open=True,
                maximum_open=False,
            )
        _require_fraction(
            "target_exposure_fraction",
            self.target_exposure_fraction,
            minimum_open=False,
            maximum_open=False,
        )


@dataclass(frozen=True, slots=True)
class FastDeterministicLifecycleResults:
    schema_name: str
    schema_version: int
    policy: FastDeterministicLifecyclePolicy
    decisions: tuple[FastDeterministicLifecycleDecision, ...]
    batch_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME:
            raise ValueError("unsupported deterministic lifecycle schema_name")
        if self.schema_version != FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION:
            raise ValueError("unsupported deterministic lifecycle schema_version")
        if type(self.policy) is not FastDeterministicLifecyclePolicy:
            raise ValueError("policy must be exact FastDeterministicLifecyclePolicy")
        if not isinstance(self.decisions, tuple) or not self.decisions:
            raise ValueError("decisions must be a non-empty tuple")
        if not all(type(value) is FastDeterministicLifecycleDecision for value in self.decisions):
            raise ValueError(
                "decisions must contain exact FastDeterministicLifecycleDecision values"
            )
        _require_sha256("batch_fingerprint_sha256", self.batch_fingerprint_sha256)


@dataclass(frozen=True, slots=True)
class FastDeterministicComponentPolicy:
    kind: str
    parameters: Mapping[str, int | float]

    def __post_init__(self) -> None:
        if self.kind not in _KIND_VERSIONS:
            raise ValueError("component policy kind is unsupported")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("component policy parameters must be a mapping")
        copied: dict[str, int | float] = {}
        for name, value in self.parameters.items():
            _require_non_empty_string("component policy parameter name", name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("component policy parameters must be numeric")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("component policy parameters must be finite")
            copied[name] = value
        object.__setattr__(self, "parameters", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class FastDeterministicCandidateManifest:
    schema_name: str
    schema_version: int
    candidate_version: str
    strategy_family: str
    strategy_version: str
    lifecycle_policy: FastDeterministicLifecyclePolicy
    entry_policy: FastDeterministicComponentPolicy
    manager_policy: FastDeterministicComponentPolicy
    candidate_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_NAME:
            raise ValueError("unsupported deterministic candidate manifest schema_name")
        if self.schema_version != FAST_DETERMINISTIC_CANDIDATE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported deterministic candidate manifest schema_version")
        _require_non_empty_string("candidate_version", self.candidate_version)
        if self.strategy_family != FAST_DETERMINISTIC_CANDIDATE_STRATEGY_FAMILY:
            raise ValueError("unsupported deterministic candidate strategy_family")
        _require_non_empty_string("strategy_version", self.strategy_version)
        if type(self.lifecycle_policy) is not FastDeterministicLifecyclePolicy:
            raise ValueError("lifecycle_policy must be exact FastDeterministicLifecyclePolicy")
        if type(self.entry_policy) is not FastDeterministicComponentPolicy:
            raise ValueError("entry_policy must be exact FastDeterministicComponentPolicy")
        if type(self.manager_policy) is not FastDeterministicComponentPolicy:
            raise ValueError("manager_policy must be exact FastDeterministicComponentPolicy")
        _require_sha256(
            "candidate_fingerprint_sha256",
            self.candidate_fingerprint_sha256,
        )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_fraction(
    name: str,
    value: object,
    *,
    minimum_open: bool,
    maximum_open: bool,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")
    scalar = float(value)
    minimum_ok = scalar > 0.0 if minimum_open else scalar >= 0.0
    maximum_ok = scalar < 1.0 if maximum_open else scalar <= 1.0
    if not minimum_ok or not maximum_ok:
        raise ValueError(f"{name} is outside its permitted interval")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
