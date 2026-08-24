from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from shreks_brain.decision import TradeDecision
from shreks_brain.features import FeatureVector, WalletFeatureVector
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
