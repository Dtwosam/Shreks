from dataclasses import FrozenInstanceError
import math

import pytest

from shreks_brain.regime import MarketRegime
from shreks_brain.wallets import (
    WalletEpisodeProfileContext,
    WalletProfile,
    WalletProfilePolicy,
    WalletRegimeProfile,
)


def _policy(**overrides: object) -> WalletProfilePolicy:
    values: dict[str, object] = {
        "version": "d3-test-v1",
        "direct_episode_weight": 1.0,
        "mixed_episode_weight": 0.5,
        "inferred_episode_weight": 0.25,
        "full_confidence_effective_sample_size": 10.0,
    }
    values.update(overrides)
    return WalletProfilePolicy(**values)  # type: ignore[arg-type]


def _context(**overrides: object) -> WalletEpisodeProfileContext:
    values: dict[str, object] = {
        "wallet": "wallet-a",
        "candidate_mint": "mint-a",
        "episode_index": 0,
        "observed_at_unix_ms": 2_000,
        "context_version": "ctx-v1",
        "entry_quality_pct": 80.0,
        "entry_delay_from_candidate_discovery_ms": 300,
        "max_drawdown_pct": 12.5,
        "rug_exposed": False,
        "regime": MarketRegime.NORMAL,
    }
    values.update(overrides)
    return WalletEpisodeProfileContext(**values)  # type: ignore[arg-type]


def _empty_profile(**overrides: object) -> WalletProfile:
    values: dict[str, object] = {
        "wallet": "wallet-a",
        "as_of_unix_ms": 10_000,
        "policy_version": "d3-test-v1",
        "context_version": None,
        "reconstruction_count": 0,
        "episode_count": 0,
        "closed_episode_count": 0,
        "open_episode_count": 0,
        "unresolved_episode_count": 0,
        "halted_reconstruction_count": 0,
        "direct_closed_episode_count": 0,
        "mixed_closed_episode_count": 0,
        "inferred_closed_episode_count": 0,
        "effective_closed_sample_size": 0.0,
        "evidence_sample_confidence": 0.0,
        "confidence_weighted_median_return_pct": None,
        "confidence_weighted_win_rate": None,
        "confidence_weighted_median_hold_ms": None,
        "aggregate_pnl_counter_asset_mint": None,
        "aggregate_realized_pnl_counter_raw": None,
        "entry_quality_sample_count": 0,
        "confidence_weighted_median_entry_quality_pct": None,
        "entry_timing_sample_count": 0,
        "confidence_weighted_median_entry_delay_ms": None,
        "drawdown_sample_count": 0,
        "confidence_weighted_median_max_drawdown_pct": None,
        "rug_exposure_sample_count": 0,
        "confidence_weighted_rug_exposure_rate": None,
        "regime_sample_count": 0,
        "regime_profiles": (),
    }
    values.update(overrides)
    return WalletProfile(**values)  # type: ignore[arg-type]


def test_profile_policy_is_immutable_and_keeps_explicit_weights() -> None:
    policy = _policy()
    assert policy.direct_episode_weight == 1.0
    assert policy.mixed_episode_weight == 0.5
    assert policy.inferred_episode_weight == 0.25
    assert policy.full_confidence_effective_sample_size == 10.0
    with pytest.raises(FrozenInstanceError):
        policy.version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direct_episode_weight", 0.0),
        ("direct_episode_weight", 1.1),
        ("mixed_episode_weight", -0.1),
        ("inferred_episode_weight", -0.1),
        ("direct_episode_weight", math.inf),
        ("mixed_episode_weight", math.nan),
        ("inferred_episode_weight", True),
        ("full_confidence_effective_sample_size", 0.0),
        ("full_confidence_effective_sample_size", math.inf),
    ],
)
def test_profile_policy_rejects_invalid_numeric_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _policy(**{field: value})


def test_profile_policy_requires_monotonic_evidence_weights() -> None:
    with pytest.raises(ValueError, match="inferred.*mixed.*direct"):
        _policy(direct_episode_weight=0.5, mixed_episode_weight=0.75)
    with pytest.raises(ValueError, match="inferred.*mixed.*direct"):
        _policy(mixed_episode_weight=0.25, inferred_episode_weight=0.5)


def test_episode_context_is_immutable_and_preserves_unknowns() -> None:
    context = _context(
        entry_quality_pct=None,
        entry_delay_from_candidate_discovery_ms=None,
        max_drawdown_pct=None,
        rug_exposed=None,
        regime=None,
    )
    assert context.entry_quality_pct is None
    assert context.rug_exposed is None
    with pytest.raises(FrozenInstanceError):
        context.context_version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", [-0.01, 100.01, math.inf, math.nan, True])
def test_episode_context_rejects_invalid_entry_quality(value: object) -> None:
    with pytest.raises(ValueError):
        _context(entry_quality_pct=value)


@pytest.mark.parametrize("value", [-0.01, 100.01, math.inf, math.nan, True])
def test_episode_context_rejects_invalid_drawdown(value: object) -> None:
    with pytest.raises(ValueError):
        _context(max_drawdown_pct=value)


def test_episode_context_rejects_invalid_delay_rug_and_regime() -> None:
    with pytest.raises(ValueError):
        _context(entry_delay_from_candidate_discovery_ms=-1)
    with pytest.raises(ValueError):
        _context(rug_exposed=1)
    with pytest.raises(ValueError):
        _context(regime="NORMAL")


def test_regime_profile_requires_metrics_to_match_effective_sample() -> None:
    with pytest.raises(ValueError):
        WalletRegimeProfile(
            regime=MarketRegime.NORMAL,
            closed_episode_count=1,
            effective_sample_size=0.0,
            confidence_weighted_median_return_pct=5.0,
            confidence_weighted_win_rate=1.0,
        )

    profile = WalletRegimeProfile(
        regime=MarketRegime.NORMAL,
        closed_episode_count=1,
        effective_sample_size=0.0,
        confidence_weighted_median_return_pct=None,
        confidence_weighted_win_rate=None,
    )
    assert profile.closed_episode_count == 1


def test_wallet_profile_reconciles_episode_and_evidence_counts() -> None:
    with pytest.raises(ValueError, match="episode state counts"):
        _empty_profile(episode_count=2, closed_episode_count=1)

    with pytest.raises(ValueError, match="closed evidence counts"):
        _empty_profile(
            episode_count=1,
            closed_episode_count=1,
            direct_closed_episode_count=0,
        )


def test_wallet_profile_rejects_partial_raw_pnl_identity() -> None:
    with pytest.raises(ValueError, match="aggregate raw PnL"):
        _empty_profile(aggregate_pnl_counter_asset_mint="SOL")
    with pytest.raises(ValueError, match="aggregate raw PnL"):
        _empty_profile(aggregate_realized_pnl_counter_raw=10)


def test_wallet_profile_does_not_allow_context_metric_without_samples() -> None:
    with pytest.raises(ValueError, match="entry quality"):
        _empty_profile(confidence_weighted_median_entry_quality_pct=50.0)
    with pytest.raises(ValueError, match="rug exposure"):
        _empty_profile(confidence_weighted_rug_exposure_rate=0.5)


def test_wallet_profile_requires_regime_profiles_in_fixed_unique_order() -> None:
    normal = WalletRegimeProfile(
        regime=MarketRegime.NORMAL,
        closed_episode_count=1,
        effective_sample_size=1.0,
        confidence_weighted_median_return_pct=5.0,
        confidence_weighted_win_rate=1.0,
    )
    hot = WalletRegimeProfile(
        regime=MarketRegime.HOT,
        closed_episode_count=1,
        effective_sample_size=1.0,
        confidence_weighted_median_return_pct=10.0,
        confidence_weighted_win_rate=1.0,
    )
    with pytest.raises(ValueError, match="regime_profiles"):
        _empty_profile(
            context_version="ctx-v1",
            regime_sample_count=2,
            regime_profiles=(normal, hot),
        )


def test_empty_wallet_profile_is_valid_and_immutable() -> None:
    profile = _empty_profile()
    assert profile.evidence_sample_confidence == 0.0
    assert profile.confidence_weighted_median_return_pct is None
    with pytest.raises(FrozenInstanceError):
        profile.wallet = "changed"  # type: ignore[misc]
