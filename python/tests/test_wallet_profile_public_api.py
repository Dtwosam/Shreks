import shreks_brain.wallets as wallets


EXPECTED_D3_PREFIX = (
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


def test_wallet_public_api_preserves_exact_d3_prefix() -> None:
    assert wallets.__all__[: len(EXPECTED_D3_PREFIX)] == EXPECTED_D3_PREFIX
