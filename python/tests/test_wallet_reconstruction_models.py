from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from shreks_brain.wallets import (
    WalletActionKind,
    WalletObservation,
    WalletObservationEvidence,
    WalletTradeEpisode,
    WalletTradeEpisodeState,
    WalletTradeEvidenceQuality,
    WalletTradeFindingCode,
    WalletTradeReconstruction,
)


def observation(**overrides: object) -> WalletObservation:
    values = dict(
        provider="helius", wallet="wallet-a", candidate_mint="mint-a",
        action=WalletActionKind.BUY, evidence=WalletObservationEvidence.DIRECT,
        signature="sig-a", event_index=0, slot=2**64 - 1,
        observed_at_unix_ms=100, occurred_at_unix_ms=90,
        candidate_token_delta_raw=100,
        counter_asset_mint="So11111111111111111111111111111111111111112",
        counter_asset_delta_raw=-1_000, venue="pump_swap", counterparty=None,
    )
    values.update(overrides)
    return WalletObservation(**values)


def closed_episode(**overrides: object) -> WalletTradeEpisode:
    values = dict(
        wallet="wallet-a", candidate_mint="mint-a", episode_index=0,
        state=WalletTradeEpisodeState.CLOSED,
        evidence_quality=WalletTradeEvidenceQuality.DIRECT,
        opened_at_unix_ms=100, last_observed_at_unix_ms=200, closed_at_unix_ms=200,
        counter_asset_mint="SOL", total_bought_quantity_raw=100,
        total_sold_quantity_raw=100, remaining_quantity_raw=0,
        total_entry_cost_counter_raw=1_000, total_exit_proceeds_counter_raw=1_300,
        estimated_realized_pnl_counter_raw=300, estimated_return_pct=30.0,
        trade_observation_ids=("helius:sig-a:0", "helius:sig-b:0"), findings=(),
    )
    values.update(overrides)
    return WalletTradeEpisode(**values)


def test_d1_mirror_and_reconstruction_vocabularies_are_stable() -> None:
    assert tuple(value.value for value in WalletActionKind) == (
        "buy", "sell", "transfer", "liquidity_event", "creator_action", "other"
    )
    assert tuple(value.value for value in WalletObservationEvidence) == ("direct", "inferred")
    assert tuple(value.value for value in WalletTradeEpisodeState) == ("OPEN", "CLOSED", "UNRESOLVED")
    assert tuple(value.value for value in WalletTradeEvidenceQuality) == ("DIRECT", "MIXED", "INFERRED")
    assert tuple(value.value for value in WalletTradeFindingCode) == (
        "BUY_ECONOMICS_INCOMPLETE", "SELL_ECONOMICS_INCOMPLETE",
        "BUY_DELTA_DIRECTION_INVALID", "SELL_DELTA_DIRECTION_INVALID",
        "SELL_WITHOUT_KNOWN_ENTRY", "SELL_EXCEEDS_KNOWN_INVENTORY",
        "COUNTER_ASSET_CHANGED", "NON_TRADE_INVENTORY_CHANGE", "OPEN_POSITION",
    )


def test_wallet_observation_preserves_full_width_values_and_is_immutable() -> None:
    row = observation(candidate_token_delta_raw=-(2**100), counter_asset_delta_raw=2**100)
    assert row.slot == 2**64 - 1
    assert row.candidate_token_delta_raw == -(2**100)
    with pytest.raises(FrozenInstanceError):
        row.wallet = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [("provider", " "), ("wallet", ""), ("candidate_mint", ""), ("signature", ""),
     ("event_index", -1), ("slot", -1), ("observed_at_unix_ms", -1),
     ("occurred_at_unix_ms", -1), ("counter_asset_mint", " "),
     ("venue", ""), ("counterparty", " ")],
)
def test_wallet_observation_rejects_invalid_structure(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        observation(**{field: value})


def test_counter_asset_delta_requires_counter_asset_mint() -> None:
    with pytest.raises(ValueError, match="requires counter_asset_mint"):
        observation(counter_asset_mint=None, counter_asset_delta_raw=-100)


def test_episode_state_controls_estimated_outcome_fields() -> None:
    assert closed_episode().estimated_realized_pnl_counter_raw == 300
    with pytest.raises(ValueError, match="OPEN/UNRESOLVED"):
        closed_episode(
            state=WalletTradeEpisodeState.OPEN, closed_at_unix_ms=None,
            total_sold_quantity_raw=90, remaining_quantity_raw=10,
        )
    with pytest.raises(ValueError, match="requires estimated outcome"):
        closed_episode(estimated_realized_pnl_counter_raw=None, estimated_return_pct=None)
    with pytest.raises(ValueError, match="finite"):
        closed_episode(estimated_return_pct=math.inf)


def test_reconstruction_requires_contiguous_matching_episodes() -> None:
    report = WalletTradeReconstruction(
        wallet="wallet-a", candidate_mint="mint-a", as_of_unix_ms=300,
        episodes=(closed_episode(),), findings=(), halted_on_uncertain_inventory=False,
    )
    assert report.episodes[0].episode_index == 0
    with pytest.raises(ValueError, match="contiguous"):
        WalletTradeReconstruction(
            wallet="wallet-a", candidate_mint="mint-a", as_of_unix_ms=300,
            episodes=(closed_episode(episode_index=1),), findings=(),
            halted_on_uncertain_inventory=False,
        )
