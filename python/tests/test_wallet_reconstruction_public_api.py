from __future__ import annotations

import inspect

import shreks_brain.wallets as wallets

EXPECTED_D2_PREFIX = (
    "WalletActionKind",
    "WalletObservation",
    "WalletObservationEvidence",
    "WalletTradeEpisode",
    "WalletTradeEpisodeState",
    "WalletTradeEvidenceQuality",
    "WalletTradeFinding",
    "WalletTradeFindingCode",
    "WalletTradeReconstruction",
    "reconstruct_wallet_trades",
)


def test_public_api_preserves_d2_prefix_and_research_only() -> None:
    assert wallets.__all__[: len(EXPECTED_D2_PREFIX)] == EXPECTED_D2_PREFIX
    public_text = " ".join(wallets.__all__).lower()
    for forbidden in (
        "sqlite", "providerclient", "signer", "transaction", "tradeintent",
        "paperfill", "decision", "execution", "live",
    ):
        assert forbidden not in public_text
    signature = inspect.signature(wallets.reconstruct_wallet_trades)
    assert tuple(signature.parameters) == (
        "wallet", "candidate_mint", "observations", "as_of_unix_ms"
    )
