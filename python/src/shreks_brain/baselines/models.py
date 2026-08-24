from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.backtest import ReplayPolicySet, ReplayRun


BASELINE_SUITE_SCHEMA_VERSION = "e2-baselines-v1"
RESERVED_BASELINE_NAMES = frozenset({"v0", "zero_score_threshold"})


class BaselineKind(StrEnum):
    V0 = "V0"
    ZERO_SCORE_THRESHOLD = "ZERO_SCORE_THRESHOLD"
    THRESHOLD_DELTA = "THRESHOLD_DELTA"


@dataclass(frozen=True, slots=True)
class ThresholdDeltaBaselineSpec:
    name: str
    delta_points: float

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        if self.name in RESERVED_BASELINE_NAMES:
            raise ValueError("threshold baseline name is reserved")
        _require_finite_number("delta_points", self.delta_points)
        if self.delta_points == 0:
            raise ValueError("delta_points must be non-zero")
        if self.delta_points < -100 or self.delta_points > 100:
            raise ValueError("delta_points must be within [-100, 100]")


@dataclass(frozen=True, slots=True)
class BaselineSuitePolicy:
    version: str
    base_replay_policies: ReplayPolicySet
    threshold_variants: tuple[ThresholdDeltaBaselineSpec, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        if type(self.base_replay_policies) is not ReplayPolicySet:
            raise ValueError("base_replay_policies must be an exact ReplayPolicySet")
        if not isinstance(self.threshold_variants, tuple):
            raise ValueError("threshold_variants must be a tuple")
        if not all(
            type(value) is ThresholdDeltaBaselineSpec
            for value in self.threshold_variants
        ):
            raise ValueError(
                "threshold_variants must contain exact ThresholdDeltaBaselineSpec values"
            )
        names = tuple(value.name for value in self.threshold_variants)
        if len(set(names)) != len(names):
            raise ValueError("threshold_variants contain duplicate names")


@dataclass(frozen=True, slots=True)
class BaselineReplayResult:
    name: str
    kind: BaselineKind
    threshold_delta_points: float | None
    replay_policy_set_version: str
    replay: ReplayRun

    def __post_init__(self) -> None:
        _require_non_empty_string("name", self.name)
        if not isinstance(self.kind, BaselineKind):
            raise ValueError("kind must be a BaselineKind")
        if type(self.replay) is not ReplayRun:
            raise ValueError("replay must be an exact ReplayRun")
        _require_non_empty_string(
            "replay_policy_set_version", self.replay_policy_set_version
        )
        if self.replay_policy_set_version != self.replay.policy_set_version:
            raise ValueError("replay policy version must match replay.policy_set_version")

        if self.kind is BaselineKind.V0:
            if self.name != "v0":
                raise ValueError("v0 baseline name must be 'v0'")
            if self.threshold_delta_points is not None:
                raise ValueError("v0 baseline delta must be None")
            return

        if self.kind is BaselineKind.ZERO_SCORE_THRESHOLD:
            if self.name != "zero_score_threshold":
                raise ValueError(
                    "zero_score_threshold baseline name must be 'zero_score_threshold'"
                )
            if self.threshold_delta_points is not None:
                raise ValueError("zero_score_threshold baseline delta must be None")
            return

        if self.name in RESERVED_BASELINE_NAMES:
            raise ValueError("threshold baseline name is reserved")
        _require_finite_number("threshold delta", self.threshold_delta_points)
        assert self.threshold_delta_points is not None
        if self.threshold_delta_points == 0:
            raise ValueError("threshold delta must be non-zero")
        if self.threshold_delta_points < -100 or self.threshold_delta_points > 100:
            raise ValueError("threshold delta must be within [-100, 100]")


@dataclass(frozen=True, slots=True)
class BaselineSuite:
    schema_version: str
    policy_version: str
    results: tuple[BaselineReplayResult, ...]

    def __post_init__(self) -> None:
        if self.schema_version != BASELINE_SUITE_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {BASELINE_SUITE_SCHEMA_VERSION}"
            )
        _require_non_empty_string("policy_version", self.policy_version)
        if not isinstance(self.results, tuple) or not all(
            type(value) is BaselineReplayResult for value in self.results
        ):
            raise ValueError("results must be a tuple of exact BaselineReplayResult values")
        if len(self.results) < 2:
            raise ValueError("results must contain at least v0 and zero_score_threshold")

        names = tuple(value.name for value in self.results)
        if len(set(names)) != len(names):
            raise ValueError("results contain duplicate baseline names")

        first, second = self.results[0], self.results[1]
        if first.kind is not BaselineKind.V0 or first.name != "v0":
            raise ValueError("first result must be the v0 baseline")
        if (
            second.kind is not BaselineKind.ZERO_SCORE_THRESHOLD
            or second.name != "zero_score_threshold"
        ):
            raise ValueError("second result must be the zero_score_threshold baseline")

        threshold_results = self.results[2:]
        if any(
            value.kind is not BaselineKind.THRESHOLD_DELTA
            for value in threshold_results
        ):
            raise ValueError("results after zero_score_threshold must be threshold baselines")
        threshold_names = tuple(value.name for value in threshold_results)
        if threshold_names != tuple(sorted(threshold_names)):
            raise ValueError("threshold baseline result order must be lexical by name")

        expected_identities = _replay_identities(first.replay)
        if any(
            _replay_identities(value.replay) != expected_identities
            for value in self.results[1:]
        ):
            raise ValueError(
                "baseline replay population identities must match exactly"
            )


def _replay_identities(replay: ReplayRun) -> tuple[tuple[int, str], ...]:
    return tuple(
        (snapshot.market_features.as_of_unix_ms, snapshot.candidate_mint)
        for snapshot in replay.snapshots
    )


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_finite_number(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
