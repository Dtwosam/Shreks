import shreks_brain.wallets as wallets


def test_wallet_public_api_is_exact_after_d3() -> None:
    assert wallets.__all__ == (
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
        "WalletEpisodeProfileContext",
        "WalletProfile",
        "WalletProfilePolicy",
        "WalletRegimeProfile",
        "build_wallet_profile",
    )
