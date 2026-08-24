from __future__ import annotations

from dataclasses import dataclass
import math

from shreks_brain.regime import MarketRegime


@dataclass(frozen=True, slots=True)
class WalletProfilePolicy:
    version: str
    direct_episode_weight: float
    mixed_episode_weight: float
    inferred_episode_weight: float
    full_confidence_effective_sample_size: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        direct = _require_finite_number("direct_episode_weight", self.direct_episode_weight)
        mixed = _require_finite_number("mixed_episode_weight", self.mixed_episode_weight)
        inferred = _require_finite_number("inferred_episode_weight", self.inferred_episode_weight)
        full = _require_finite_number(
            "full_confidence_effective_sample_size",
            self.full_confidence_effective_sample_size,
        )
        if not 0.0 < direct <= 1.0:
            raise ValueError("direct_episode_weight must be in (0, 1]")
        if not 0.0 <= mixed <= 1.0:
            raise ValueError("mixed_episode_weight must be in [0, 1]")
        if not 0.0 <= inferred <= 1.0:
            raise ValueError("inferred_episode_weight must be in [0, 1]")
        if not inferred <= mixed <= direct:
            raise ValueError(
                "evidence weights must satisfy inferred <= mixed <= direct"
            )
        if full <= 0.0:
            raise ValueError(
                "full_confidence_effective_sample_size must be strictly positive"
            )


@dataclass(frozen=True, slots=True)
class WalletEpisodeProfileContext:
    wallet: str
    candidate_mint: str
    episode_index: int
    observed_at_unix_ms: int
    context_version: str
    entry_quality_pct: float | None
    entry_delay_from_candidate_discovery_ms: int | None
    max_drawdown_pct: float | None
    rug_exposed: bool | None
    regime: MarketRegime | None

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet", self.wallet)
        _require_non_empty_string("candidate_mint", self.candidate_mint)
        _require_non_negative_int("episode_index", self.episode_index)
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        _require_non_empty_string("context_version", self.context_version)
        _require_optional_percentage("entry_quality_pct", self.entry_quality_pct)
        if self.entry_delay_from_candidate_discovery_ms is not None:
            _require_non_negative_int(
                "entry_delay_from_candidate_discovery_ms",
                self.entry_delay_from_candidate_discovery_ms,
            )
        _require_optional_percentage("max_drawdown_pct", self.max_drawdown_pct)
        if self.rug_exposed is not None and not isinstance(self.rug_exposed, bool):
            raise ValueError("rug_exposed must be boolean or None")
        if self.regime is not None and not isinstance(self.regime, MarketRegime):
            raise ValueError("regime must be a MarketRegime or None")


@dataclass(frozen=True, slots=True)
class WalletRegimeProfile:
    regime: MarketRegime
    closed_episode_count: int
    effective_sample_size: float
    confidence_weighted_median_return_pct: float | None
    confidence_weighted_win_rate: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.regime, MarketRegime):
            raise ValueError("regime must be a MarketRegime")
        _require_non_negative_int("closed_episode_count", self.closed_episode_count)
        effective = _require_non_negative_finite_number(
            "effective_sample_size", self.effective_sample_size
        )
        _require_optional_finite_number(
            "confidence_weighted_median_return_pct",
            self.confidence_weighted_median_return_pct,
        )
        _require_optional_rate(
            "confidence_weighted_win_rate", self.confidence_weighted_win_rate
        )
        if effective > float(self.closed_episode_count):
            raise ValueError(
                "effective_sample_size cannot exceed closed_episode_count"
            )
        if effective == 0.0:
            if (
                self.confidence_weighted_median_return_pct is not None
                or self.confidence_weighted_win_rate is not None
            ):
                raise ValueError(
                    "regime metrics require a positive effective sample size"
                )
        else:
            if self.closed_episode_count == 0:
                raise ValueError(
                    "positive effective_sample_size requires closed episodes"
                )
            if (
                self.confidence_weighted_median_return_pct is None
                or self.confidence_weighted_win_rate is None
            ):
                raise ValueError(
                    "positive effective sample size requires regime return and win metrics"
                )


@dataclass(frozen=True, slots=True)
class WalletProfile:
    wallet: str
    as_of_unix_ms: int
    policy_version: str
    context_version: str | None
    reconstruction_count: int
    episode_count: int
    closed_episode_count: int
    open_episode_count: int
    unresolved_episode_count: int
    halted_reconstruction_count: int
    direct_closed_episode_count: int
    mixed_closed_episode_count: int
    inferred_closed_episode_count: int
    effective_closed_sample_size: float
    evidence_sample_confidence: float
    confidence_weighted_median_return_pct: float | None
    confidence_weighted_win_rate: float | None
    confidence_weighted_median_hold_ms: float | None
    aggregate_pnl_counter_asset_mint: str | None
    aggregate_realized_pnl_counter_raw: int | None
    entry_quality_sample_count: int
    confidence_weighted_median_entry_quality_pct: float | None
    entry_timing_sample_count: int
    confidence_weighted_median_entry_delay_ms: float | None
    drawdown_sample_count: int
    confidence_weighted_median_max_drawdown_pct: float | None
    rug_exposure_sample_count: int
    confidence_weighted_rug_exposure_rate: float | None
    regime_sample_count: int
    regime_profiles: tuple[WalletRegimeProfile, ...]

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet", self.wallet)
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("policy_version", self.policy_version)
        if self.context_version is not None:
            _require_non_empty_string("context_version", self.context_version)

        count_fields = (
            "reconstruction_count",
            "episode_count",
            "closed_episode_count",
            "open_episode_count",
            "unresolved_episode_count",
            "halted_reconstruction_count",
            "direct_closed_episode_count",
            "mixed_closed_episode_count",
            "inferred_closed_episode_count",
            "entry_quality_sample_count",
            "entry_timing_sample_count",
            "drawdown_sample_count",
            "rug_exposure_sample_count",
            "regime_sample_count",
        )
        for name in count_fields:
            _require_non_negative_int(name, getattr(self, name))

        if (
            self.closed_episode_count
            + self.open_episode_count
            + self.unresolved_episode_count
            != self.episode_count
        ):
            raise ValueError("episode state counts must reconcile to episode_count")
        if (
            self.direct_closed_episode_count
            + self.mixed_closed_episode_count
            + self.inferred_closed_episode_count
            != self.closed_episode_count
        ):
            raise ValueError(
                "closed evidence counts must reconcile to closed_episode_count"
            )
        if self.halted_reconstruction_count > self.reconstruction_count:
            raise ValueError(
                "halted_reconstruction_count cannot exceed reconstruction_count"
            )

        effective = _require_non_negative_finite_number(
            "effective_closed_sample_size", self.effective_closed_sample_size
        )
        _require_rate("evidence_sample_confidence", self.evidence_sample_confidence)
        _require_optional_finite_number(
            "confidence_weighted_median_return_pct",
            self.confidence_weighted_median_return_pct,
        )
        _require_optional_rate(
            "confidence_weighted_win_rate", self.confidence_weighted_win_rate
        )
        _require_optional_non_negative_finite_number(
            "confidence_weighted_median_hold_ms",
            self.confidence_weighted_median_hold_ms,
        )
        if effective > float(self.closed_episode_count):
            raise ValueError(
                "effective_closed_sample_size cannot exceed closed_episode_count"
            )
        if effective == 0.0:
            if self.evidence_sample_confidence != 0.0:
                raise ValueError(
                    "zero effective closed sample requires zero evidence confidence"
                )
            if any(
                value is not None
                for value in (
                    self.confidence_weighted_median_return_pct,
                    self.confidence_weighted_win_rate,
                    self.confidence_weighted_median_hold_ms,
                )
            ):
                raise ValueError(
                    "core weighted metrics require a positive effective closed sample"
                )
        else:
            if self.closed_episode_count == 0:
                raise ValueError(
                    "positive effective_closed_sample_size requires closed episodes"
                )
            if self.evidence_sample_confidence <= 0.0:
                raise ValueError(
                    "positive effective closed sample requires positive evidence confidence"
                )
            if any(
                value is None
                for value in (
                    self.confidence_weighted_median_return_pct,
                    self.confidence_weighted_win_rate,
                    self.confidence_weighted_median_hold_ms,
                )
            ):
                raise ValueError(
                    "positive effective closed sample requires all core weighted metrics"
                )

        raw_pnl_pair = (
            self.aggregate_pnl_counter_asset_mint is not None,
            self.aggregate_realized_pnl_counter_raw is not None,
        )
        if raw_pnl_pair[0] != raw_pnl_pair[1]:
            raise ValueError(
                "aggregate raw PnL requires both counter asset mint and raw value"
            )
        if self.aggregate_pnl_counter_asset_mint is not None:
            if self.closed_episode_count == 0:
                raise ValueError("aggregate raw PnL requires closed episodes")
            _require_non_empty_string(
                "aggregate_pnl_counter_asset_mint",
                self.aggregate_pnl_counter_asset_mint,
            )
            _require_int(
                "aggregate_realized_pnl_counter_raw",
                self.aggregate_realized_pnl_counter_raw,
            )

        self._validate_optional_metric(
            "entry quality",
            self.entry_quality_sample_count,
            self.confidence_weighted_median_entry_quality_pct,
            percentage=True,
        )
        self._validate_optional_metric(
            "entry timing",
            self.entry_timing_sample_count,
            self.confidence_weighted_median_entry_delay_ms,
            non_negative=True,
        )
        self._validate_optional_metric(
            "drawdown",
            self.drawdown_sample_count,
            self.confidence_weighted_median_max_drawdown_pct,
            percentage=True,
        )
        self._validate_optional_metric(
            "rug exposure",
            self.rug_exposure_sample_count,
            self.confidence_weighted_rug_exposure_rate,
            rate=True,
        )

        if not isinstance(self.regime_profiles, tuple) or not all(
            isinstance(value, WalletRegimeProfile)
            for value in self.regime_profiles
        ):
            raise ValueError(
                "regime_profiles must be a tuple of WalletRegimeProfile values"
            )
        regime_order = {
            MarketRegime.HOT: 0,
            MarketRegime.NORMAL: 1,
            MarketRegime.WEAK: 2,
            MarketRegime.DEAD: 3,
        }
        regimes = tuple(item.regime for item in self.regime_profiles)
        if len(set(regimes)) != len(regimes) or tuple(
            sorted(regimes, key=regime_order.__getitem__)
        ) != regimes:
            raise ValueError(
                "regime_profiles must be unique and in HOT/NORMAL/WEAK/DEAD order"
            )
        if sum(item.closed_episode_count for item in self.regime_profiles) != self.regime_sample_count:
            raise ValueError(
                "regime_profiles closed counts must reconcile to regime_sample_count"
            )

        for name, value in (
            ("entry_quality_sample_count", self.entry_quality_sample_count),
            ("entry_timing_sample_count", self.entry_timing_sample_count),
            ("drawdown_sample_count", self.drawdown_sample_count),
            ("rug_exposure_sample_count", self.rug_exposure_sample_count),
            ("regime_sample_count", self.regime_sample_count),
        ):
            if value > self.closed_episode_count:
                raise ValueError(f"{name} cannot exceed closed_episode_count")

        any_context_evidence = (
            self.entry_quality_sample_count
            + self.entry_timing_sample_count
            + self.drawdown_sample_count
            + self.rug_exposure_sample_count
            + self.regime_sample_count
            > 0
        )
        if any_context_evidence and self.context_version is None:
            raise ValueError("context metrics require context_version")

    def _validate_optional_metric(
        self,
        label: str,
        sample_count: int,
        value: float | None,
        *,
        percentage: bool = False,
        non_negative: bool = False,
        rate: bool = False,
    ) -> None:
        if value is not None and sample_count == 0:
            raise ValueError(f"{label} metric requires a non-zero sample count")
        if percentage:
            _require_optional_percentage(label, value)
        elif non_negative:
            _require_optional_non_negative_finite_number(label, value)
        elif rate:
            _require_optional_rate(label, value)
        else:
            _require_optional_finite_number(label, value)


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")


def _require_finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _require_non_negative_finite_number(name: str, value: object) -> float:
    result = _require_finite_number(name, value)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _require_optional_finite_number(name: str, value: object | None) -> None:
    if value is not None:
        _require_finite_number(name, value)


def _require_optional_non_negative_finite_number(
    name: str, value: object | None
) -> None:
    if value is not None:
        _require_non_negative_finite_number(name, value)


def _require_percentage(name: str, value: object) -> None:
    result = _require_finite_number(name, value)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{name} must be between 0 and 100")


def _require_optional_percentage(name: str, value: object | None) -> None:
    if value is not None:
        _require_percentage(name, value)


def _require_rate(name: str, value: object) -> None:
    result = _require_finite_number(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def _require_optional_rate(name: str, value: object | None) -> None:
    if value is not None:
        _require_rate(name, value)
