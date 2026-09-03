from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
import string

from shreks_brain.fast_learning.models import (
    FastForecastBaselineArtifact,
    FastForecastTarget,
)


FAST_FORECAST_CHAMPION_SCHEMA_NAME = "shreks.fast_lane_forecast_champion"
FAST_FORECAST_CHAMPION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FastForecastChampionSelection:
    decision_reference: str
    decided_at_unix_ms: int
    reason: str

    def __post_init__(self) -> None:
        _non_empty("decision_reference", self.decision_reference)
        _non_negative_int("decided_at_unix_ms", self.decided_at_unix_ms)
        _non_empty("reason", self.reason)


@dataclass(frozen=True, slots=True)
class FastForecastChampionMember:
    member_key: str
    forecast_artifact: FastForecastBaselineArtifact
    validation_policy_version: str
    validation_run_fingerprint_sha256: str
    test_evaluation_policy_version: str
    test_evaluation_report_fingerprint_sha256: str
    test_scored_observation_count: int
    test_target_unavailable_count: int

    def __post_init__(self) -> None:
        if type(self.forecast_artifact) is not FastForecastBaselineArtifact:
            raise ValueError("forecast_artifact must be an exact FastForecastBaselineArtifact")
        expected_key = fast_forecast_champion_member_key(
            self.forecast_artifact.target,
            self.forecast_artifact.horizon_ms,
        )
        if self.member_key != expected_key:
            raise ValueError("member_key must be derived exactly from forecast target and horizon")
        _non_empty("validation_policy_version", self.validation_policy_version)
        _sha256(
            "validation_run_fingerprint_sha256",
            self.validation_run_fingerprint_sha256,
        )
        _non_empty("test_evaluation_policy_version", self.test_evaluation_policy_version)
        _sha256(
            "test_evaluation_report_fingerprint_sha256",
            self.test_evaluation_report_fingerprint_sha256,
        )
        _positive_int("test_scored_observation_count", self.test_scored_observation_count)
        _non_negative_int(
            "test_target_unavailable_count",
            self.test_target_unavailable_count,
        )


@dataclass(frozen=True, slots=True)
class FastForecastChampionArtifact:
    schema_name: str
    schema_version: int
    champion_version: str
    selection: FastForecastChampionSelection
    feature_schema_version: int
    training_bundle_fingerprint_sha256: str
    future_path_label_version: int
    members: tuple[FastForecastChampionMember, ...]
    champion_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_name != FAST_FORECAST_CHAMPION_SCHEMA_NAME:
            raise ValueError("forecast champion schema name is incompatible")
        if self.schema_version != FAST_FORECAST_CHAMPION_SCHEMA_VERSION:
            raise ValueError("forecast champion schema version is incompatible")
        _non_empty("champion_version", self.champion_version)
        if type(self.selection) is not FastForecastChampionSelection:
            raise ValueError("selection must be an exact FastForecastChampionSelection")
        _positive_int("feature_schema_version", self.feature_schema_version)
        _sha256(
            "training_bundle_fingerprint_sha256",
            self.training_bundle_fingerprint_sha256,
        )
        _positive_int("future_path_label_version", self.future_path_label_version)
        if not isinstance(self.members, tuple) or not self.members:
            raise ValueError("members must be a non-empty tuple")
        if not all(type(value) is FastForecastChampionMember for value in self.members):
            raise ValueError("members must contain exact FastForecastChampionMember values")
        keys = tuple(value.member_key for value in self.members)
        if keys != tuple(sorted(keys)):
            raise ValueError("members must be in canonical member_key order")
        if len(keys) != len(set(keys)):
            raise ValueError("champion contains duplicate target/horizon members")
        for member in self.members:
            artifact = member.forecast_artifact
            if artifact.feature_schema_version != self.feature_schema_version:
                raise ValueError("champion members must share one feature schema version")
            if (
                artifact.training_bundle_fingerprint_sha256
                != self.training_bundle_fingerprint_sha256
            ):
                raise ValueError("champion members must share one training bundle fingerprint")
            if artifact.future_path_label_version != self.future_path_label_version:
                raise ValueError("champion members must share one future-path label version")
        _sha256("champion_fingerprint_sha256", self.champion_fingerprint_sha256)

    def member_for(
        self,
        target: FastForecastTarget,
        horizon_ms: int,
    ) -> FastForecastChampionMember:
        key = fast_forecast_champion_member_key(target, horizon_ms)
        for member in self.members:
            if member.member_key == key:
                return member
        raise KeyError(key)


def fast_forecast_champion_member_key(
    target: FastForecastTarget,
    horizon_ms: int,
) -> str:
    if type(target) is not FastForecastTarget:
        raise ValueError("target must be an exact FastForecastTarget")
    _positive_int("horizon_ms", horizon_ms)
    return f"{target.value}@{horizon_ms}ms"


def fast_forecast_champion_fingerprint_sha256(
    champion: FastForecastChampionArtifact,
) -> str:
    if type(champion) is not FastForecastChampionArtifact:
        raise ValueError("champion must be an exact FastForecastChampionArtifact")
    payload = {
        field.name: getattr(champion, field.name)
        for field in fields(champion)
        if field.name != "champion_fingerprint_sha256"
    }
    encoded = json.dumps(
        _canonical_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("champion fingerprint cannot contain non-finite floats")
        return {"float_hex": value.hex()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in value.items()
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical_value(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(
        f"unsupported forecast champion fingerprint value: {type(value).__name__}"
    )


def _non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in string.hexdigits.lower() for character in value)
    ):
        raise ValueError(f"{name} must be a 64-character lowercase SHA-256 hex digest")
