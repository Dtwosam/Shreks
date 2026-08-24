from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math


CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION = "e6-registry-v1"


class RegistryStatus(StrEnum):
    CHALLENGER = "CHALLENGER"
    CHAMPION = "CHAMPION"
    RETIRED = "RETIRED"


@dataclass(frozen=True, slots=True)
class RegistryEvaluationEvidence:
    schema_version: str
    policy_version: str
    evaluation_fingerprint_sha256: str
    trade_count: int
    net_pnl_usd: float
    net_expectancy_usd: float | None
    net_expectancy_pct: float | None
    profit_factor: float | None
    maximum_drawdown_usd: float
    maximum_drawdown_pct: float
    win_rate: float | None
    turnover_usd: float
    total_cost_usd: float
    brier_score: float | None
    expected_calibration_error: float | None

    def __post_init__(self) -> None:
        _require_non_empty_string("schema_version", self.schema_version)
        _require_non_empty_string("policy_version", self.policy_version)
        _require_sha256(
            "evaluation_fingerprint_sha256", self.evaluation_fingerprint_sha256
        )
        _require_non_negative_int("trade_count", self.trade_count)
        _require_finite("net_pnl_usd", self.net_pnl_usd)
        _require_optional_finite("net_expectancy_usd", self.net_expectancy_usd)
        _require_optional_finite("net_expectancy_pct", self.net_expectancy_pct)
        _require_optional_non_negative_finite("profit_factor", self.profit_factor)
        _require_non_negative_finite(
            "maximum_drawdown_usd", self.maximum_drawdown_usd
        )
        _require_percent("maximum_drawdown_pct", self.maximum_drawdown_pct)
        _require_optional_fraction("win_rate", self.win_rate)
        _require_non_negative_finite("turnover_usd", self.turnover_usd)
        _require_non_negative_finite("total_cost_usd", self.total_cost_usd)
        if (self.brier_score is None) != (self.expected_calibration_error is None):
            raise ValueError("calibration values must both be present or both be None")
        if self.brier_score is not None:
            _require_fraction("brier_score", self.brier_score)
            _require_fraction(
                "expected_calibration_error", self.expected_calibration_error
            )


@dataclass(frozen=True, slots=True)
class RegistryCandidate:
    schema_version: str
    candidate_version: str
    strategy_version: str
    model_version: str | None
    model_training_schema_version: str | None
    model_training_fingerprint_sha256: str | None
    feature_schema_version: str
    feature_columns: tuple[str, ...]
    training_started_at_unix_ms: int | None
    training_ended_at_unix_ms: int | None
    validation_schema_version: str | None
    validation_policy_version: str | None
    validation_run_fingerprint_sha256: str | None
    evaluation: RegistryEvaluationEvidence
    registered_at_unix_ms: int
    initial_status: RegistryStatus
    candidate_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must equal "
                f"{CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION}"
            )
        _require_non_empty_string("candidate_version", self.candidate_version)
        _require_non_empty_string("strategy_version", self.strategy_version)
        _require_non_empty_string("feature_schema_version", self.feature_schema_version)
        if not isinstance(self.feature_columns, tuple) or not self.feature_columns:
            raise ValueError("feature_columns must be a non-empty tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.feature_columns):
            raise ValueError("feature_columns must contain non-empty strings")
        if len(set(self.feature_columns)) != len(self.feature_columns):
            raise ValueError("feature_columns cannot contain duplicates")
        if type(self.evaluation) is not RegistryEvaluationEvidence:
            raise ValueError("evaluation must be exact RegistryEvaluationEvidence")
        _require_non_negative_int("registered_at_unix_ms", self.registered_at_unix_ms)
        if self.initial_status is not RegistryStatus.CHALLENGER:
            raise ValueError("initial_status must be CHALLENGER")
        _require_sha256("candidate_fingerprint_sha256", self.candidate_fingerprint_sha256)

        if (self.training_started_at_unix_ms is None) != (
            self.training_ended_at_unix_ms is None
        ):
            raise ValueError("training timestamps must both be present or both be absent")

        model_fields = (
            self.model_version,
            self.model_training_schema_version,
            self.model_training_fingerprint_sha256,
            self.training_started_at_unix_ms,
            self.training_ended_at_unix_ms,
            self.validation_schema_version,
            self.validation_policy_version,
            self.validation_run_fingerprint_sha256,
        )
        present_count = sum(value is not None for value in model_fields)
        if present_count not in (0, len(model_fields)):
            raise ValueError(
                "model provenance must be either fully present or fully absent"
            )
        if present_count == 0:
            return

        _require_non_empty_string("model_version", self.model_version)
        _require_non_empty_string(
            "model_training_schema_version", self.model_training_schema_version
        )
        _require_sha256(
            "model_training_fingerprint_sha256",
            self.model_training_fingerprint_sha256,
        )
        _require_non_negative_int(
            "training_started_at_unix_ms", self.training_started_at_unix_ms
        )
        _require_non_negative_int(
            "training_ended_at_unix_ms", self.training_ended_at_unix_ms
        )
        if self.training_started_at_unix_ms > self.training_ended_at_unix_ms:  # type: ignore[operator]
            raise ValueError("training timestamps must satisfy start <= end")
        _require_non_empty_string(
            "validation_schema_version", self.validation_schema_version
        )
        _require_non_empty_string(
            "validation_policy_version", self.validation_policy_version
        )
        _require_sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )


@dataclass(frozen=True, slots=True)
class RegistryStatusEvent:
    candidate_version: str
    from_status: RegistryStatus
    to_status: RegistryStatus
    decision_reference: str
    decided_at_unix_ms: int
    reason: str
    event_fingerprint_sha256: str

    def __post_init__(self) -> None:
        _require_non_empty_string("candidate_version", self.candidate_version)
        if type(self.from_status) is not RegistryStatus:
            raise ValueError("from_status must be a RegistryStatus")
        if type(self.to_status) is not RegistryStatus:
            raise ValueError("to_status must be a RegistryStatus")
        if self.from_status is self.to_status:
            raise ValueError("from_status and to_status must be different")
        _require_non_empty_string("decision_reference", self.decision_reference)
        _require_non_negative_int("decided_at_unix_ms", self.decided_at_unix_ms)
        _require_non_empty_string("reason", self.reason)
        _require_sha256("event_fingerprint_sha256", self.event_fingerprint_sha256)


@dataclass(frozen=True, slots=True)
class ChampionChallengerRegistry:
    schema_version: str
    candidates: tuple[RegistryCandidate, ...]
    status_events: tuple[RegistryStatusEvent, ...]
    registry_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must equal "
                f"{CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION}"
            )
        if not isinstance(self.candidates, tuple) or not all(
            type(value) is RegistryCandidate for value in self.candidates
        ):
            raise ValueError("candidates must be a tuple of RegistryCandidate values")
        if not isinstance(self.status_events, tuple) or not all(
            type(value) is RegistryStatusEvent for value in self.status_events
        ):
            raise ValueError("status_events must be a tuple of RegistryStatusEvent values")
        _require_sha256("registry_fingerprint_sha256", self.registry_fingerprint_sha256)

        versions = tuple(value.candidate_version for value in self.candidates)
        if versions != tuple(sorted(versions)):
            raise ValueError("candidates must be in candidate_version lexical order")
        if len(versions) != len(set(versions)):
            raise ValueError("candidate versions must be unique")
        if self.status_events != tuple(sorted(self.status_events, key=_event_sort_key)):
            raise ValueError("status_events must be in canonical order")

        by_version = {value.candidate_version: value for value in self.candidates}
        statuses = {
            value.candidate_version: value.initial_status for value in self.candidates
        }
        champion: str | None = None
        for event in self.status_events:
            candidate = by_version.get(event.candidate_version)
            if candidate is None:
                raise ValueError("status event candidate must exist in registry")
            if event.decided_at_unix_ms < candidate.registered_at_unix_ms:
                raise ValueError("status event cannot precede candidate registration")
            if statuses[event.candidate_version] is not event.from_status:
                raise ValueError("status event from_status must match reconstructed status")
            if event.to_status is RegistryStatus.CHAMPION:
                if champion is not None and champion != event.candidate_version:
                    raise ValueError("registry may contain at most one current champion")
                champion = event.candidate_version
            elif champion == event.candidate_version:
                champion = None
            statuses[event.candidate_version] = event.to_status

    def current_status(self, candidate_version: str) -> RegistryStatus:
        _require_non_empty_string("candidate_version", candidate_version)
        candidate = next(
            (value for value in self.candidates if value.candidate_version == candidate_version),
            None,
        )
        if candidate is None:
            raise KeyError(candidate_version)
        status = candidate.initial_status
        for event in self.status_events:
            if event.candidate_version == candidate_version:
                status = event.to_status
        return status

    def current_champion(self) -> RegistryCandidate | None:
        for candidate in self.candidates:
            if self.current_status(candidate.candidate_version) is RegistryStatus.CHAMPION:
                return candidate
        return None

    def challengers(self) -> tuple[RegistryCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if self.current_status(candidate.candidate_version) is RegistryStatus.CHALLENGER
        )


def _event_sort_key(event: RegistryStatusEvent) -> tuple[int, str, str]:
    return (
        event.decided_at_unix_ms,
        event.candidate_version,
        event.event_fingerprint_sha256,
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_finite(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_non_negative_finite(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0:  # type: ignore[operator]
        raise ValueError(f"{name} must be non-negative")


def _require_optional_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_finite(name, value)


def _require_optional_non_negative_finite(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_finite(name, value)


def _require_fraction(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 1:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 1]")


def _require_optional_fraction(name: str, value: object | None) -> None:
    if value is not None:
        _require_fraction(name, value)


def _require_percent(name: str, value: object) -> None:
    _require_finite(name, value)
    if value < 0 or value > 100:  # type: ignore[operator]
        raise ValueError(f"{name} must be within [0, 100]")


def _require_sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 hex digest")
