import pytest

from shreks_brain.regime import MarketRegime
from shreks_brain.wallets import (
    WalletEpisodeProfileContext,
    WalletProfilePolicy,
    WalletTradeEpisode,
    WalletTradeEpisodeState,
    WalletTradeEvidenceQuality,
    WalletTradeReconstruction,
    build_wallet_profile,
)

AS_OF = 10_000
WALLET = "wallet-a"


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


def _closed(
    mint: str,
    *,
    quality: WalletTradeEvidenceQuality = WalletTradeEvidenceQuality.DIRECT,
    return_pct: float = 30.0,
    pnl_raw: int = 300,
    counter_mint: str = "SOL",
    opened_at: int = 1_000,
    closed_at: int = 2_000,
    episode_index: int = 0,
) -> WalletTradeEpisode:
    return WalletTradeEpisode(
        wallet=WALLET,
        candidate_mint=mint,
        episode_index=episode_index,
        state=WalletTradeEpisodeState.CLOSED,
        evidence_quality=quality,
        opened_at_unix_ms=opened_at,
        last_observed_at_unix_ms=closed_at,
        closed_at_unix_ms=closed_at,
        counter_asset_mint=counter_mint,
        total_bought_quantity_raw=100,
        total_sold_quantity_raw=100,
        remaining_quantity_raw=0,
        total_entry_cost_counter_raw=1_000,
        total_exit_proceeds_counter_raw=1_000 + pnl_raw,
        estimated_realized_pnl_counter_raw=pnl_raw,
        estimated_return_pct=return_pct,
        trade_observation_ids=(f"{mint}:{episode_index}:buy", f"{mint}:{episode_index}:sell"),
        findings=(),
    )


def _open(mint: str) -> WalletTradeEpisode:
    return WalletTradeEpisode(
        wallet=WALLET,
        candidate_mint=mint,
        episode_index=0,
        state=WalletTradeEpisodeState.OPEN,
        evidence_quality=WalletTradeEvidenceQuality.DIRECT,
        opened_at_unix_ms=1_000,
        last_observed_at_unix_ms=2_000,
        closed_at_unix_ms=None,
        counter_asset_mint="SOL",
        total_bought_quantity_raw=100,
        total_sold_quantity_raw=0,
        remaining_quantity_raw=100,
        total_entry_cost_counter_raw=1_000,
        total_exit_proceeds_counter_raw=0,
        estimated_realized_pnl_counter_raw=None,
        estimated_return_pct=None,
        trade_observation_ids=(f"{mint}:0:buy",),
        findings=(),
    )


def _unresolved(mint: str) -> WalletTradeEpisode:
    return WalletTradeEpisode(
        wallet=WALLET,
        candidate_mint=mint,
        episode_index=0,
        state=WalletTradeEpisodeState.UNRESOLVED,
        evidence_quality=WalletTradeEvidenceQuality.MIXED,
        opened_at_unix_ms=1_000,
        last_observed_at_unix_ms=2_000,
        closed_at_unix_ms=None,
        counter_asset_mint="SOL",
        total_bought_quantity_raw=100,
        total_sold_quantity_raw=0,
        remaining_quantity_raw=100,
        total_entry_cost_counter_raw=1_000,
        total_exit_proceeds_counter_raw=0,
        estimated_realized_pnl_counter_raw=None,
        estimated_return_pct=None,
        trade_observation_ids=(f"{mint}:0:uncertain",),
        findings=(),
    )


def _reconstruction(
    mint: str,
    episode: WalletTradeEpisode,
    *,
    as_of: int = AS_OF,
    halted: bool = False,
    wallet: str = WALLET,
) -> WalletTradeReconstruction:
    return WalletTradeReconstruction(
        wallet=wallet,
        candidate_mint=mint,
        as_of_unix_ms=as_of,
        episodes=(episode,),
        findings=(),
        halted_on_uncertain_inventory=halted,
    )


def _context(
    mint: str,
    *,
    observed_at: int = 9_000,
    version: str = "ctx-v1",
    entry_quality_pct: float | None = 80.0,
    entry_delay_ms: int | None = 100,
    max_drawdown_pct: float | None = 10.0,
    rug_exposed: bool | None = False,
    regime: MarketRegime | None = MarketRegime.NORMAL,
    episode_index: int = 0,
) -> WalletEpisodeProfileContext:
    return WalletEpisodeProfileContext(
        wallet=WALLET,
        candidate_mint=mint,
        episode_index=episode_index,
        observed_at_unix_ms=observed_at,
        context_version=version,
        entry_quality_pct=entry_quality_pct,
        entry_delay_from_candidate_discovery_ms=entry_delay_ms,
        max_drawdown_pct=max_drawdown_pct,
        rug_exposed=rug_exposed,
        regime=regime,
    )


def test_empty_history_preserves_unknown_metrics() -> None:
    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(),
        contexts=(),
        policy=_policy(),
    )

    assert profile.reconstruction_count == 0
    assert profile.episode_count == 0
    assert profile.closed_episode_count == 0
    assert profile.effective_closed_sample_size == 0.0
    assert profile.evidence_sample_confidence == 0.0
    assert profile.confidence_weighted_median_return_pct is None
    assert profile.confidence_weighted_win_rate is None
    assert profile.confidence_weighted_median_hold_ms is None
    assert profile.aggregate_pnl_counter_asset_mint is None
    assert profile.aggregate_realized_pnl_counter_raw is None
    assert profile.context_version is None
    assert profile.regime_profiles == ()


def test_closed_history_uses_evidence_weights_for_core_metrics() -> None:
    direct = _reconstruction(
        "mint-a",
        _closed("mint-a", return_pct=30.0, pnl_raw=300, opened_at=1_000, closed_at=2_000),
    )
    mixed = _reconstruction(
        "mint-b",
        _closed(
            "mint-b",
            quality=WalletTradeEvidenceQuality.MIXED,
            return_pct=-10.0,
            pnl_raw=-100,
            opened_at=1_000,
            closed_at=4_000,
        ),
    )
    inferred = _reconstruction(
        "mint-c",
        _closed(
            "mint-c",
            quality=WalletTradeEvidenceQuality.INFERRED,
            return_pct=5.0,
            pnl_raw=50,
            opened_at=1_000,
            closed_at=3_000,
        ),
    )

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(mixed, inferred, direct),
        contexts=(),
        policy=_policy(),
    )

    assert profile.closed_episode_count == 3
    assert profile.direct_closed_episode_count == 1
    assert profile.mixed_closed_episode_count == 1
    assert profile.inferred_closed_episode_count == 1
    assert profile.effective_closed_sample_size == pytest.approx(1.75)
    assert profile.evidence_sample_confidence == pytest.approx(0.175)
    assert profile.confidence_weighted_median_return_pct == pytest.approx(30.0)
    assert profile.confidence_weighted_win_rate == pytest.approx(1.25 / 1.75)
    assert profile.confidence_weighted_median_hold_ms == pytest.approx(1_000.0)
    assert profile.aggregate_pnl_counter_asset_mint == "SOL"
    assert profile.aggregate_realized_pnl_counter_raw == 250


def test_open_unresolved_and_halted_history_remain_explicit() -> None:
    open_reconstruction = _reconstruction("mint-open", _open("mint-open"))
    unresolved_reconstruction = _reconstruction(
        "mint-uncertain", _unresolved("mint-uncertain"), halted=True
    )

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(open_reconstruction, unresolved_reconstruction),
        contexts=(),
        policy=_policy(),
    )

    assert profile.episode_count == 2
    assert profile.closed_episode_count == 0
    assert profile.open_episode_count == 1
    assert profile.unresolved_episode_count == 1
    assert profile.halted_reconstruction_count == 1
    assert profile.effective_closed_sample_size == 0.0
    assert profile.confidence_weighted_median_return_pct is None


def test_profile_requires_one_exact_as_of_reconstruction_per_candidate() -> None:
    episode = _closed("mint-a")

    wrong_as_of = _reconstruction("mint-a", episode, as_of=AS_OF - 1)
    with pytest.raises(ValueError, match="as_of"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(wrong_as_of,),
            contexts=(),
            policy=_policy(),
        )

    one = _reconstruction("mint-a", episode)
    two = _reconstruction("mint-a", episode)
    with pytest.raises(ValueError, match="duplicate.*candidate"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(one, two),
            contexts=(),
            policy=_policy(),
        )


def test_profile_rejects_wrong_wallet_and_future_episode_evidence() -> None:
    episode = _closed("mint-a")
    wrong_wallet = _reconstruction("mint-a", episode, wallet="wallet-b")
    with pytest.raises(ValueError, match="wallet"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(wrong_wallet,),
            contexts=(),
            policy=_policy(),
        )

    future_episode = _closed("mint-future", opened_at=9_500, closed_at=10_500)
    future_reconstruction = _reconstruction("mint-future", future_episode)
    with pytest.raises(ValueError, match="future"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(future_reconstruction,),
            contexts=(),
            policy=_policy(),
        )


def test_mixed_counter_assets_disable_raw_pnl_aggregation() -> None:
    sol = _reconstruction("mint-a", _closed("mint-a", counter_mint="SOL", pnl_raw=300))
    usdc = _reconstruction(
        "mint-b",
        _closed("mint-b", counter_mint="USDC", pnl_raw=200),
    )

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(sol, usdc),
        contexts=(),
        policy=_policy(),
    )

    assert profile.aggregate_pnl_counter_asset_mint is None
    assert profile.aggregate_realized_pnl_counter_raw is None


def test_zero_weight_closed_evidence_does_not_become_zero_performance() -> None:
    inferred = _reconstruction(
        "mint-a",
        _closed(
            "mint-a",
            quality=WalletTradeEvidenceQuality.INFERRED,
            return_pct=25.0,
            pnl_raw=250,
        ),
    )
    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(inferred,),
        contexts=(),
        policy=_policy(mixed_episode_weight=0.0, inferred_episode_weight=0.0),
    )

    assert profile.closed_episode_count == 1
    assert profile.effective_closed_sample_size == 0.0
    assert profile.evidence_sample_confidence == 0.0
    assert profile.confidence_weighted_median_return_pct is None
    assert profile.confidence_weighted_win_rate is None
    assert profile.confidence_weighted_median_hold_ms is None
    assert profile.aggregate_pnl_counter_asset_mint == "SOL"
    assert profile.aggregate_realized_pnl_counter_raw == 250


def test_optional_context_metrics_use_episode_evidence_weight_and_missingness() -> None:
    direct = _reconstruction("mint-a", _closed("mint-a", return_pct=30.0, pnl_raw=300))
    mixed = _reconstruction(
        "mint-b",
        _closed(
            "mint-b",
            quality=WalletTradeEvidenceQuality.MIXED,
            return_pct=-10.0,
            pnl_raw=-100,
        ),
    )
    inferred = _reconstruction(
        "mint-c",
        _closed(
            "mint-c",
            quality=WalletTradeEvidenceQuality.INFERRED,
            return_pct=5.0,
            pnl_raw=50,
        ),
    )

    contexts = (
        _context(
            "mint-b",
            entry_quality_pct=20.0,
            entry_delay_ms=300,
            max_drawdown_pct=30.0,
            rug_exposed=True,
            regime=MarketRegime.WEAK,
        ),
        _context(
            "mint-c",
            entry_quality_pct=None,
            entry_delay_ms=None,
            max_drawdown_pct=None,
            rug_exposed=None,
            regime=MarketRegime.NORMAL,
        ),
        _context(
            "mint-a",
            entry_quality_pct=80.0,
            entry_delay_ms=100,
            max_drawdown_pct=10.0,
            rug_exposed=False,
            regime=MarketRegime.NORMAL,
        ),
    )

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(mixed, inferred, direct),
        contexts=contexts,
        policy=_policy(),
    )

    assert profile.context_version == "ctx-v1"
    assert profile.entry_quality_sample_count == 2
    assert profile.confidence_weighted_median_entry_quality_pct == pytest.approx(80.0)
    assert profile.entry_timing_sample_count == 2
    assert profile.confidence_weighted_median_entry_delay_ms == pytest.approx(100.0)
    assert profile.drawdown_sample_count == 2
    assert profile.confidence_weighted_median_max_drawdown_pct == pytest.approx(10.0)
    assert profile.rug_exposure_sample_count == 2
    assert profile.confidence_weighted_rug_exposure_rate == pytest.approx(0.5 / 1.5)
    assert profile.regime_sample_count == 3
    assert tuple(item.regime for item in profile.regime_profiles) == (
        MarketRegime.NORMAL,
        MarketRegime.WEAK,
    )

    normal, weak = profile.regime_profiles
    assert normal.closed_episode_count == 2
    assert normal.effective_sample_size == pytest.approx(1.25)
    assert normal.confidence_weighted_median_return_pct == pytest.approx(30.0)
    assert normal.confidence_weighted_win_rate == pytest.approx(1.0)
    assert weak.closed_episode_count == 1
    assert weak.effective_sample_size == pytest.approx(0.5)
    assert weak.confidence_weighted_median_return_pct == pytest.approx(-10.0)
    assert weak.confidence_weighted_win_rate == pytest.approx(0.0)


def test_unknown_context_values_never_become_zero_or_false() -> None:
    reconstruction = _reconstruction("mint-a", _closed("mint-a"))
    unknown = _context(
        "mint-a",
        entry_quality_pct=None,
        entry_delay_ms=None,
        max_drawdown_pct=None,
        rug_exposed=None,
        regime=None,
    )

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=(reconstruction,),
        contexts=(unknown,),
        policy=_policy(),
    )

    assert profile.context_version == "ctx-v1"
    assert profile.entry_quality_sample_count == 0
    assert profile.confidence_weighted_median_entry_quality_pct is None
    assert profile.entry_timing_sample_count == 0
    assert profile.confidence_weighted_median_entry_delay_ms is None
    assert profile.drawdown_sample_count == 0
    assert profile.confidence_weighted_median_max_drawdown_pct is None
    assert profile.rug_exposure_sample_count == 0
    assert profile.confidence_weighted_rug_exposure_rate is None
    assert profile.regime_sample_count == 0
    assert profile.regime_profiles == ()


def test_context_must_uniquely_target_closed_history_in_time() -> None:
    closed = _reconstruction("mint-a", _closed("mint-a", closed_at=2_000))
    duplicate = _context("mint-a")
    with pytest.raises(ValueError, match="duplicate.*context"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(closed,),
            contexts=(duplicate, duplicate),
            policy=_policy(),
        )

    before_close = _context("mint-a", observed_at=1_999)
    with pytest.raises(ValueError, match="before.*closed"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(closed,),
            contexts=(before_close,),
            policy=_policy(),
        )

    future = _context("mint-a", observed_at=AS_OF + 1)
    with pytest.raises(ValueError, match="future"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(closed,),
            contexts=(future,),
            policy=_policy(),
        )

    open_reconstruction = _reconstruction("mint-open", _open("mint-open"))
    with pytest.raises(ValueError, match="CLOSED"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(open_reconstruction,),
            contexts=(_context("mint-open"),),
            policy=_policy(),
        )


def test_profile_rejects_mixed_context_versions() -> None:
    one = _reconstruction("mint-a", _closed("mint-a"))
    two = _reconstruction("mint-b", _closed("mint-b"))
    with pytest.raises(ValueError, match="context_version"):
        build_wallet_profile(
            wallet=WALLET,
            as_of_unix_ms=AS_OF,
            reconstructions=(one, two),
            contexts=(
                _context("mint-a", version="ctx-v1"),
                _context("mint-b", version="ctx-v2"),
            ),
            policy=_policy(),
        )


def test_regime_profiles_use_fixed_enum_order_not_input_order() -> None:
    regimes = (
        ("mint-dead", MarketRegime.DEAD),
        ("mint-hot", MarketRegime.HOT),
        ("mint-weak", MarketRegime.WEAK),
        ("mint-normal", MarketRegime.NORMAL),
    )
    reconstructions = tuple(
        _reconstruction(mint, _closed(mint, return_pct=float(index + 1)))
        for index, (mint, _) in enumerate(regimes)
    )
    contexts = tuple(_context(mint, regime=regime) for mint, regime in regimes)

    profile = build_wallet_profile(
        wallet=WALLET,
        as_of_unix_ms=AS_OF,
        reconstructions=reconstructions,
        contexts=contexts,
        policy=_policy(),
    )

    assert tuple(item.regime for item in profile.regime_profiles) == (
        MarketRegime.HOT,
        MarketRegime.NORMAL,
        MarketRegime.WEAK,
        MarketRegime.DEAD,
    )
