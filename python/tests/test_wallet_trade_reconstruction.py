from __future__ import annotations

from dataclasses import replace

import pytest

from shreks_brain.wallets import (
    WalletActionKind,
    WalletObservation,
    WalletObservationEvidence,
    WalletTradeEpisodeState,
    WalletTradeEvidenceQuality,
    WalletTradeFindingCode,
    reconstruct_wallet_trades,
)

SOL = "So11111111111111111111111111111111111111112"
USDC = "USDC111111111111111111111111111111111111111"


def obs(signature: str, observed: int, action: WalletActionKind,
        candidate_delta: int | None, counter_delta: int | None, *,
        counter_mint: str | None = SOL,
        evidence: WalletObservationEvidence = WalletObservationEvidence.DIRECT,
        occurred: int | None = None, event_index: int = 0,
        wallet: str = "wallet-a", mint: str = "mint-a") -> WalletObservation:
    return WalletObservation(
        provider="helius", wallet=wallet, candidate_mint=mint, action=action,
        evidence=evidence, signature=signature, event_index=event_index, slot=100,
        observed_at_unix_ms=observed, occurred_at_unix_ms=occurred,
        candidate_token_delta_raw=candidate_delta, counter_asset_mint=counter_mint,
        counter_asset_delta_raw=counter_delta, venue="pump_swap", counterparty=None,
    )


def run(*rows: WalletObservation, as_of: int = 10_000):
    return reconstruct_wallet_trades("wallet-a", "mint-a", tuple(rows), as_of)


def test_clean_direct_round_trip_computes_estimated_closed_outcome() -> None:
    result = run(
        obs("buy", 100, WalletActionKind.BUY, 100, -1_000),
        obs("sell", 200, WalletActionKind.SELL, -100, 1_300),
    )
    episode = result.episodes[0]
    assert not result.halted_on_uncertain_inventory and result.findings == ()
    assert episode.state is WalletTradeEpisodeState.CLOSED
    assert episode.evidence_quality is WalletTradeEvidenceQuality.DIRECT
    assert episode.total_bought_quantity_raw == episode.total_sold_quantity_raw == 100
    assert episode.total_entry_cost_counter_raw == 1_000
    assert episode.total_exit_proceeds_counter_raw == 1_300
    assert episode.estimated_realized_pnl_counter_raw == 300
    assert episode.estimated_return_pct == pytest.approx(30.0)


def test_partial_exits_wait_for_zero_inventory_and_do_not_invent_cost_allocation() -> None:
    result = run(
        obs("buy", 100, WalletActionKind.BUY, 100, -1_000),
        obs("sell-1", 200, WalletActionKind.SELL, -40, 600),
        obs("sell-2", 300, WalletActionKind.SELL, -60, 700),
    )
    episode = result.episodes[0]
    assert episode.state is WalletTradeEpisodeState.CLOSED
    assert episode.total_exit_proceeds_counter_raw == 1_300
    assert episode.estimated_realized_pnl_counter_raw == 300


def test_multiple_legs_close_then_new_buy_starts_second_open_episode() -> None:
    result = run(
        obs("buy-1", 100, WalletActionKind.BUY, 60, -600),
        obs("buy-2", 110, WalletActionKind.BUY, 40, -500),
        obs("sell-1", 200, WalletActionKind.SELL, -50, 700),
        obs("sell-2", 210, WalletActionKind.SELL, -50, 600),
        obs("buy-3", 300, WalletActionKind.BUY, 10, -100),
    )
    first, second = result.episodes
    assert first.episode_index == 0 and first.state is WalletTradeEpisodeState.CLOSED
    assert first.estimated_realized_pnl_counter_raw == 200
    assert second.episode_index == 1 and second.state is WalletTradeEpisodeState.OPEN
    assert second.remaining_quantity_raw == 10
    assert second.estimated_realized_pnl_counter_raw is None
    assert result.findings[-1].code is WalletTradeFindingCode.OPEN_POSITION


@pytest.mark.parametrize(
    ("entry_evidence", "exit_evidence", "quality"),
    [
        (WalletObservationEvidence.DIRECT, WalletObservationEvidence.DIRECT, WalletTradeEvidenceQuality.DIRECT),
        (WalletObservationEvidence.INFERRED, WalletObservationEvidence.INFERRED, WalletTradeEvidenceQuality.INFERRED),
        (WalletObservationEvidence.DIRECT, WalletObservationEvidence.INFERRED, WalletTradeEvidenceQuality.MIXED),
    ],
)
def test_evidence_quality_is_provenance_not_wallet_score(entry_evidence, exit_evidence, quality) -> None:
    result = run(
        obs("buy", 100, WalletActionKind.BUY, 10, -100, evidence=entry_evidence),
        obs("sell", 200, WalletActionKind.SELL, -10, 110, evidence=exit_evidence),
    )
    assert result.episodes[0].evidence_quality is quality


def test_local_observation_time_controls_order_and_future_evidence_fails_closed() -> None:
    result = run(
        obs("sell", 200, WalletActionKind.SELL, -10, 110, occurred=50),
        obs("buy", 100, WalletActionKind.BUY, 10, -100, occurred=500),
    )
    assert result.episodes[0].trade_observation_ids == ("helius:buy:0", "helius:sell:0")
    with pytest.raises(ValueError, match="future local"):
        run(obs("future", 201, WalletActionKind.BUY, 10, -100, occurred=10), as_of=200)


def test_duplicates_are_idempotent_but_contradictory_identity_fails() -> None:
    later = obs("buy", 120, WalletActionKind.BUY, 10, -100)
    earlier = replace(later, observed_at_unix_ms=100)
    result = run(later, earlier, obs("sell", 200, WalletActionKind.SELL, -10, 110))
    assert result.episodes[0].total_bought_quantity_raw == 10
    assert result.episodes[0].opened_at_unix_ms == 100
    with pytest.raises(ValueError, match="contradicts"):
        run(later, replace(later, counter_asset_delta_raw=-101))


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ((obs("sell", 100, WalletActionKind.SELL, -10, 110),), WalletTradeFindingCode.SELL_WITHOUT_KNOWN_ENTRY),
        ((obs("buy", 100, WalletActionKind.BUY, 10, -100), obs("sell", 200, WalletActionKind.SELL, -11, 120)), WalletTradeFindingCode.SELL_EXCEEDS_KNOWN_INVENTORY),
        ((obs("buy", 100, WalletActionKind.BUY, None, -100),), WalletTradeFindingCode.BUY_ECONOMICS_INCOMPLETE),
        ((obs("sell", 100, WalletActionKind.SELL, None, 100),), WalletTradeFindingCode.SELL_ECONOMICS_INCOMPLETE),
        ((obs("buy", 100, WalletActionKind.BUY, -10, -100),), WalletTradeFindingCode.BUY_DELTA_DIRECTION_INVALID),
        ((obs("buy", 100, WalletActionKind.BUY, 10, -100), obs("sell", 200, WalletActionKind.SELL, 10, 100)), WalletTradeFindingCode.SELL_DELTA_DIRECTION_INVALID),
        ((obs("buy", 100, WalletActionKind.BUY, 10, -100), obs("buy-usdc", 200, WalletActionKind.BUY, 10, -100, counter_mint=USDC)), WalletTradeFindingCode.COUNTER_ASSET_CHANGED),
        ((obs("buy", 100, WalletActionKind.BUY, 10, -100), obs("transfer", 200, WalletActionKind.TRANSFER, -5, None, counter_mint=None)), WalletTradeFindingCode.NON_TRADE_INVENTORY_CHANGE),
    ],
)
def test_uncertain_inventory_halts_without_claiming_outcome(rows, code) -> None:
    result = run(*rows)
    assert result.halted_on_uncertain_inventory
    assert result.findings[-1].code is code
    assert result.episodes[-1].state is WalletTradeEpisodeState.UNRESOLVED
    assert result.episodes[-1].estimated_realized_pnl_counter_raw is None
    assert result.episodes[-1].estimated_return_pct is None


def test_non_trade_without_inventory_delta_is_ignored_but_halt_never_resumes() -> None:
    clean = run(
        obs("buy", 100, WalletActionKind.BUY, 10, -100),
        obs("meta", 150, WalletActionKind.CREATOR_ACTION, None, None, counter_mint=None),
        obs("sell", 200, WalletActionKind.SELL, -10, 110),
    )
    assert clean.episodes[0].state is WalletTradeEpisodeState.CLOSED
    halted = run(
        obs("sell-unknown", 100, WalletActionKind.SELL, -10, 110),
        obs("buy-later", 200, WalletActionKind.BUY, 10, -100),
        obs("sell-later", 300, WalletActionKind.SELL, -10, 120),
    )
    assert halted.halted_on_uncertain_inventory and len(halted.episodes) == 1
    assert "buy-later" not in " ".join(halted.episodes[0].trade_observation_ids)


def test_wallet_and_mint_mismatch_fail_structurally() -> None:
    with pytest.raises(ValueError, match="wallet"):
        run(obs("buy", 100, WalletActionKind.BUY, 10, -100, wallet="other"))
    with pytest.raises(ValueError, match="candidate_mint"):
        run(obs("buy", 100, WalletActionKind.BUY, 10, -100, mint="other"))
