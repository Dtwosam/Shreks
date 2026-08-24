from __future__ import annotations

import inspect

import shreks_brain.wallets as wallets

EXPECTED = (
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


def test_public_api_is_exact_and_research_only() -> None:
    assert wallets.__all__ == EXPECTED
    public_text = " ".join(EXPECTED).lower()
    for forbidden in (
        "sqlite", "providerclient", "signer", "transaction", "tradeintent",
        "paperfill", "decision", "execution", "live",
    ):
        assert forbidden not in public_text
    signature = inspect.signature(wallets.reconstruct_wallet_trades)
    assert tuple(signature.parameters) == (
        "wallet", "candidate_mint", "observations", "as_of_unix_ms"
    )
