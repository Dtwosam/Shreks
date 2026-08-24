from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shreks_brain.decision import DecisionAction, DecisionPolicy
from shreks_brain.features import (
    FEATURE_SCHEMA_VERSION,
    WALLET_FEATURE_SCHEMA_VERSION,
    FeatureVector,
    WalletFeatureVector,
)
from shreks_brain.regime import RegimeAssessment
from shreks_brain.research import (
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchOutcomeLabel,
    ResearchSnapshotInputs,
)
from shreks_brain.scoring import ScorePolicy
from shreks_brain.setups import (
    FIRST_PULLBACK_SETUP_NAME,
    FRESH_LAUNCH_SETUP_NAME,
    GRADUATION_BREAKOUT_SETUP_NAME,
    FirstPullbackPolicy,
    FreshLaunchPolicy,
    GraduationBreakoutPolicy,
    GraduationContext,
    PullbackContext,
)


BACKTEST_REPLAY_SCHEMA_VERSION = "e1-replay-v1"


class ReplaySetupKind(StrEnum):
    FRESH_LAUNCH_CONTINUATION = FRESH_LAUNCH_SETUP_NAME
    GRADUATION_BREAKOUT = GRADUATION_BREAKOUT_SETUP_NAME
    FIRST_PULLBACK = FIRST_PULLBACK_SETUP_NAME


@dataclass(frozen=True, slots=True)
class ReplayDecisionInput:
    candidate_mint: str
    market_features: FeatureVector
    wallet_features: WalletFeatureVector
    regime: RegimeAssessment
    setup_kind: ReplaySetupKind
    graduation_context: GraduationContext | None
    pullback_context: PullbackContext | None

    def __post_init__(self) -> None:
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        if type(self.market_features) is not FeatureVector:
            raise ValueError("market_features must be a FeatureVector")
        if type(self.wallet_features) is not WalletFeatureVector:
            raise ValueError("wallet_features must be a WalletFeatureVector")
        if type(self.regime) is not RegimeAssessment:
            raise ValueError("regime must be a RegimeAssessment")
        if not isinstance(self.setup_kind, ReplaySetupKind):
            raise ValueError("setup_kind must be a ReplaySetupKind")
        if self.graduation_context is not None and type(self.graduation_context) is not GraduationContext:
            raise ValueError("graduation_context must be a GraduationContext or None")
        if self.pullback_context is not None and type(self.pullback_context) is not PullbackContext:
            raise ValueError("pullback_context must be a PullbackContext or None")

        if self.market_features.schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("market feature schema must equal sealed B2 schema")
        if self.wallet_features.schema_version != WALLET_FEATURE_SCHEMA_VERSION:
            raise ValueError("wallet feature schema must equal sealed D5 schema")
        if self.wallet_features.candidate_mint != self.candidate_mint:
            raise ValueError("wallet candidate mint must match replay candidate")

        as_of = self.market_features.as_of_unix_ms
        if self.wallet_features.as_of_unix_ms != as_of:
            raise ValueError("wallet feature as_of must match market feature as_of")
        if self.regime.as_of_unix_ms != as_of:
            raise ValueError("regime as_of must match market feature as_of")
        if self.market_features.source_observed_at_unix_ms > as_of:
            raise ValueError("market source observation cannot be after replay as_of")
        expected_age = as_of - self.market_features.source_observed_at_unix_ms
        if self.market_features.source_age_ms != expected_age:
            raise ValueError("market source_age_ms must reconcile to source/as_of")

        if self.setup_kind is ReplaySetupKind.FRESH_LAUNCH_CONTINUATION:
            if self.graduation_context is not None or self.pullback_context is not None:
                raise ValueError("Fresh Launch replay cannot carry graduation or pullback context")
            return

        if self.setup_kind is ReplaySetupKind.GRADUATION_BREAKOUT:
            if self.pullback_context is not None:
                raise ValueError("graduation replay cannot carry pullback context")
            graduation = self.graduation_context
            if graduation is None:
                return
            if graduation.mint != self.candidate_mint:
                raise ValueError("graduation candidate mint must match replay candidate")
            if graduation.detected_at_unix_ms > as_of:
                raise ValueError("future local graduation evidence is not allowed in replay")
            return

        if self.graduation_context is not None:
            raise ValueError("first pullback replay cannot carry graduation context")
        pullback = self.pullback_context
        if pullback is not None and pullback.trough_at_unix_ms > self.market_features.source_observed_at_unix_ms:
            raise ValueError("pullback trough cannot be later than market source observation")


@dataclass(frozen=True, slots=True)
class ReplayOutcomeBundle:
    candidate_mint: str
    as_of_unix_ms: int
    outcomes: tuple[ResearchOutcomeLabel, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        if not isinstance(self.outcomes, tuple) or not all(
            type(value) is ResearchOutcomeLabel for value in self.outcomes
        ):
            raise ValueError("outcomes must be a tuple of ResearchOutcomeLabel values")
        if len(self.outcomes) != len(RESEARCH_OUTCOME_HORIZONS_SECONDS):
            raise ValueError("outcomes must contain exactly seven approved horizons")
        horizons = tuple(value.horizon_seconds for value in self.outcomes)
        if horizons != RESEARCH_OUTCOME_HORIZONS_SECONDS:
            raise ValueError("outcomes must use canonical horizon order")
        if any(
            value.baseline_observed_at_unix_ms != self.as_of_unix_ms
            for value in self.outcomes
        ):
            raise ValueError("every outcome baseline must equal bundle as_of_unix_ms")


@dataclass(frozen=True, slots=True)
class ReplayPolicySet:
    version: str
    fresh_launch_policy: FreshLaunchPolicy | None
    graduation_breakout_policy: GraduationBreakoutPolicy | None
    first_pullback_policy: FirstPullbackPolicy | None
    score_policy: ScorePolicy
    decision_policy: DecisionPolicy

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        _require_optional_exact_type(
            "fresh_launch_policy", self.fresh_launch_policy, FreshLaunchPolicy
        )
        _require_optional_exact_type(
            "graduation_breakout_policy",
            self.graduation_breakout_policy,
            GraduationBreakoutPolicy,
        )
        _require_optional_exact_type(
            "first_pullback_policy", self.first_pullback_policy, FirstPullbackPolicy
        )
        if (
            self.fresh_launch_policy is None
            and self.graduation_breakout_policy is None
            and self.first_pullback_policy is None
        ):
            raise ValueError("at least one setup policy must be configured")
        if type(self.score_policy) is not ScorePolicy:
            raise ValueError("score_policy must be a ScorePolicy")
        if type(self.decision_policy) is not DecisionPolicy:
            raise ValueError("decision_policy must be a DecisionPolicy")
        if self.score_policy.required_feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("score policy must require the sealed B2 feature schema")
        if self.decision_policy.required_score_policy_version != self.score_policy.version:
            raise ValueError("decision score policy requirement must match supplied score policy")


@dataclass(frozen=True, slots=True)
class ReplayRun:
    schema_version: str
    policy_set_version: str
    score_policy_version: str
    decision_policy_version: str
    snapshots: tuple[ResearchSnapshotInputs, ...]
    reject_count: int
    watch_count: int
    enter_count: int
    min_as_of_unix_ms: int
    max_as_of_unix_ms: int

    def __post_init__(self) -> None:
        if self.schema_version != BACKTEST_REPLAY_SCHEMA_VERSION:
            raise ValueError("schema_version must equal e1-replay-v1")
        for name in (
            "policy_set_version",
            "score_policy_version",
            "decision_policy_version",
        ):
            _require_non_empty_string(name, getattr(self, name))
        if not isinstance(self.snapshots, tuple) or not all(
            type(value) is ResearchSnapshotInputs for value in self.snapshots
        ):
            raise ValueError("snapshots must be a tuple of ResearchSnapshotInputs values")
        if not self.snapshots:
            raise ValueError("snapshots must be non-empty")

        identities = tuple(
            (value.market_features.as_of_unix_ms, value.candidate_mint)
            for value in self.snapshots
        )
        if tuple(sorted(identities)) != identities:
            raise ValueError("snapshots must be sorted by as_of and candidate mint")
        if len(set(identities)) != len(identities):
            raise ValueError("snapshots must have unique replay identities")
        if any(value.score.policy_version != self.score_policy_version for value in self.snapshots):
            raise ValueError("snapshot score policy version must match ReplayRun")
        if any(value.decision.policy_version != self.decision_policy_version for value in self.snapshots):
            raise ValueError("snapshot decision policy version must match ReplayRun")

        for name in ("reject_count", "watch_count", "enter_count"):
            _require_non_negative_int(name, getattr(self, name))
        actual_reject = sum(
            value.decision.action is DecisionAction.REJECT for value in self.snapshots
        )
        actual_watch = sum(
            value.decision.action is DecisionAction.WATCH for value in self.snapshots
        )
        actual_enter = sum(
            value.decision.action is DecisionAction.ENTER for value in self.snapshots
        )
        if any(
            value.decision.action
            not in (DecisionAction.REJECT, DecisionAction.WATCH, DecisionAction.ENTER)
            for value in self.snapshots
        ):
            raise ValueError("ReplayRun accepts only pre-entry decisions")
        if (
            self.reject_count,
            self.watch_count,
            self.enter_count,
        ) != (actual_reject, actual_watch, actual_enter):
            raise ValueError("replay action counts must reconcile to snapshots")

        _require_non_negative_int("min_as_of_unix_ms", self.min_as_of_unix_ms)
        _require_non_negative_int("max_as_of_unix_ms", self.max_as_of_unix_ms)
        actual_min = min(value.market_features.as_of_unix_ms for value in self.snapshots)
        actual_max = max(value.market_features.as_of_unix_ms for value in self.snapshots)
        if (self.min_as_of_unix_ms, self.max_as_of_unix_ms) != (actual_min, actual_max):
            raise ValueError("replay timestamp bounds must match snapshots")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_exact_type(name: str, value: object, expected: type[object]) -> None:
    if value is not None and type(value) is not expected:
        raise ValueError(f"{name} must be {expected.__name__} or None")
