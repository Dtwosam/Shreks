from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.decision import DecisionAction, TradeDecision
from shreks_brain.features import (
    FEATURE_SCHEMA_VERSION,
    WALLET_FEATURE_SCHEMA_VERSION,
    FeatureVector,
    WalletFeatureVector,
)
from shreks_brain.regime import RegimeAssessment
from shreks_brain.scoring import ScoreAssessment


RESEARCH_DATASET_SCHEMA_VERSION = "d6-research-v1"
RESEARCH_OUTCOME_HORIZONS_SECONDS = (
    60,
    300,
    900,
    1800,
    3600,
    14_400,
    86_400,
)


class ResearchOutcomeLabelStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class ResearchExitability(StrEnum):
    EXITABLE = "EXITABLE"
    NOT_EXITABLE = "NOT_EXITABLE"


@dataclass(frozen=True, slots=True)
class ResearchOutcomeLabel:
    horizon_seconds: int
    baseline_observed_at_unix_ms: int
    due_at_unix_ms: int
    status: ResearchOutcomeLabelStatus
    checkpoint_observed_at_unix_ms: int | None
    completed_at_unix_ms: int | None
    return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    liquidity_change_pct: float | None
    volume_m5_change_pct: float | None
    buys_m5_change: int | None
    sells_m5_change: int | None
    rug_or_dead_pool: bool | None
    exitability: ResearchExitability | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.horizon_seconds, bool)
            or not isinstance(self.horizon_seconds, int)
            or self.horizon_seconds not in RESEARCH_OUTCOME_HORIZONS_SECONDS
        ):
            raise ValueError("horizon_seconds must be an approved research horizon")
        _require_non_negative_int(
            "baseline_observed_at_unix_ms", self.baseline_observed_at_unix_ms
        )
        _require_non_negative_int("due_at_unix_ms", self.due_at_unix_ms)
        expected_due = (
            self.baseline_observed_at_unix_ms + self.horizon_seconds * 1_000
        )
        if self.due_at_unix_ms != expected_due:
            raise ValueError(
                "due_at_unix_ms must equal baseline_observed_at_unix_ms plus horizon"
            )
        if not isinstance(self.status, ResearchOutcomeLabelStatus):
            raise ValueError("status must be a ResearchOutcomeLabelStatus")

        _require_optional_non_negative_int(
            "checkpoint_observed_at_unix_ms", self.checkpoint_observed_at_unix_ms
        )
        _require_optional_non_negative_int(
            "completed_at_unix_ms", self.completed_at_unix_ms
        )
        for name in (
            "return_pct",
            "mfe_pct",
            "mae_pct",
            "liquidity_change_pct",
            "volume_m5_change_pct",
        ):
            _require_optional_finite_number(name, getattr(self, name))
        for name in ("buys_m5_change", "sells_m5_change"):
            _require_optional_int(name, getattr(self, name))
        if self.rug_or_dead_pool is not None and not isinstance(
            self.rug_or_dead_pool, bool
        ):
            raise ValueError("rug_or_dead_pool must be bool or None")
        if self.exitability is not None and not isinstance(
            self.exitability, ResearchExitability
        ):
            raise ValueError("exitability must be a ResearchExitability or None")

        if self.status is ResearchOutcomeLabelStatus.PENDING:
            future_values = (
                self.checkpoint_observed_at_unix_ms,
                self.completed_at_unix_ms,
                self.return_pct,
                self.mfe_pct,
                self.mae_pct,
                self.liquidity_change_pct,
                self.volume_m5_change_pct,
                self.buys_m5_change,
                self.sells_m5_change,
                self.rug_or_dead_pool,
                self.exitability,
            )
            if any(value is not None for value in future_values):
                raise ValueError("PENDING label cannot contain future outcome evidence")
            return

        if (
            self.checkpoint_observed_at_unix_ms is None
            or self.completed_at_unix_ms is None
            or self.return_pct is None
        ):
            raise ValueError(
                "COMPLETED label requires checkpoint/completion timestamps and return_pct"
            )
        if self.checkpoint_observed_at_unix_ms < self.due_at_unix_ms:
            raise ValueError(
                "checkpoint_observed_at_unix_ms cannot be earlier than due_at_unix_ms"
            )
        if self.completed_at_unix_ms < self.checkpoint_observed_at_unix_ms:
            raise ValueError(
                "completed_at_unix_ms cannot be earlier than checkpoint observation"
            )


@dataclass(frozen=True, slots=True)
class ResearchSnapshotInputs:
    candidate_mint: str
    market_features: FeatureVector
    wallet_features: WalletFeatureVector
    regime: RegimeAssessment
    score: ScoreAssessment
    decision: TradeDecision
    outcomes: tuple[ResearchOutcomeLabel, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_mint, str) or not self.candidate_mint.strip():
            raise ValueError("candidate_mint must be a non-empty string")
        for name, value, expected in (
            ("market_features", self.market_features, FeatureVector),
            ("wallet_features", self.wallet_features, WalletFeatureVector),
            ("regime", self.regime, RegimeAssessment),
            ("score", self.score, ScoreAssessment),
            ("decision", self.decision, TradeDecision),
        ):
            if type(value) is not expected:
                raise ValueError(f"{name} must be an exact {expected.__name__}")

        if self.market_features.schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("market feature schema must equal sealed b2-v1")
        if self.wallet_features.schema_version != WALLET_FEATURE_SCHEMA_VERSION:
            raise ValueError("wallet feature schema must equal sealed d5-wallet-v1")
        if (
            self.wallet_features.candidate_mint != self.candidate_mint
            or self.decision.mint != self.candidate_mint
        ):
            raise ValueError("candidate mint must agree across D6 snapshot evidence")

        as_of = self.market_features.as_of_unix_ms
        if any(
            value != as_of
            for value in (
                self.wallet_features.as_of_unix_ms,
                self.regime.as_of_unix_ms,
                self.score.as_of_unix_ms,
                self.decision.as_of_unix_ms,
            )
        ):
            raise ValueError("all D6 evidence must share the exact as_of_unix_ms")
        if self.score.source_observed_at_unix_ms != self.market_features.source_observed_at_unix_ms:
            raise ValueError("score source timestamp must match market feature source")
        if (
            self.score.feature_schema_version != self.market_features.schema_version
            or self.decision.feature_schema_version != self.market_features.schema_version
        ):
            raise ValueError("score and decision feature schema must match market feature schema")
        if not (
            self.market_features.safety_decision
            == self.score.safety_decision
            == self.decision.safety_decision
        ):
            raise ValueError("safety decision must agree across market, score, and decision")
        if self.decision.score_policy_version != self.score.policy_version:
            raise ValueError("score policy version must agree between score and decision")
        if self.decision.setup_name != self.score.setup_name:
            raise ValueError("setup name must agree between score and decision")
        if self.decision.setup_policy_version != self.score.setup_policy_version:
            raise ValueError("setup policy version must agree between score and decision")
        if self.decision.setup_state != self.score.setup_state:
            raise ValueError("setup state must agree between score and decision")
        if self.score.regime_policy_version != self.regime.policy_version:
            raise ValueError("regime policy version must agree between score and regime")
        if not (
            self.score.market_regime == self.regime.regime == self.decision.market_regime
        ):
            raise ValueError("market regime must agree across regime, score, and decision")
        if self.score.total_score != self.decision.total_score:
            raise ValueError("total score must agree between score and decision")
        if self.decision.action not in (
            DecisionAction.REJECT,
            DecisionAction.WATCH,
            DecisionAction.ENTER,
        ):
            raise ValueError("decision action must be REJECT, WATCH, or ENTER")

        if not isinstance(self.outcomes, tuple) or not all(
            type(value) is ResearchOutcomeLabel for value in self.outcomes
        ):
            raise ValueError("outcomes must be a tuple of ResearchOutcomeLabel values")
        if len(self.outcomes) != len(RESEARCH_OUTCOME_HORIZONS_SECONDS):
            raise ValueError("outcomes must contain exactly seven research horizons")
        horizons = tuple(value.horizon_seconds for value in self.outcomes)
        if (
            len(set(horizons)) != len(horizons)
            or set(horizons) != set(RESEARCH_OUTCOME_HORIZONS_SECONDS)
        ):
            raise ValueError("outcome horizon set must contain each approved horizon once")
        if horizons != RESEARCH_OUTCOME_HORIZONS_SECONDS:
            raise ValueError("outcome order must follow canonical ascending horizon order")
        if any(value.baseline_observed_at_unix_ms != as_of for value in self.outcomes):
            raise ValueError("every outcome baseline must equal the decision as_of_unix_ms")


@dataclass(frozen=True, slots=True)
class ResearchDatasetManifest:
    schema_version: str
    row_count: int
    min_as_of_unix_ms: int
    max_as_of_unix_ms: int
    dataset_fingerprint_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_DATASET_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must equal {RESEARCH_DATASET_SCHEMA_VERSION}"
            )
        _require_positive_int("row_count", self.row_count)
        _require_non_negative_int("min_as_of_unix_ms", self.min_as_of_unix_ms)
        _require_non_negative_int("max_as_of_unix_ms", self.max_as_of_unix_ms)
        if self.min_as_of_unix_ms > self.max_as_of_unix_ms:
            raise ValueError("manifest timestamp range must satisfy min <= max")
        digest = self.dataset_fingerprint_sha256
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or digest.lower() != digest
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(
                "dataset_fingerprint_sha256 must be a lowercase 64-character hex digest"
            )


def _require_non_negative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_positive_int(name: str, value: int) -> None:
    _require_non_negative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _require_optional_non_negative_int(name: str, value: int | None) -> None:
    if value is None:
        return
    _require_non_negative_int(name, value)


def _require_optional_int(name: str, value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer or None")


def _require_optional_finite_number(
    name: str, value: float | int | None
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number or None")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number or None")
