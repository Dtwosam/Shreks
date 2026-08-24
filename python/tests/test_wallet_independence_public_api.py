from __future__ import annotations

import inspect

import shreks_brain.wallets as wallets


EXPECTED_D4_API = (
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
    "WalletRelationshipDirection",
    "WalletRelationshipEvidenceQuality",
    "WalletRelationshipState",
    "WalletRelationshipEvidence",
    "WalletRelationshipPolicy",
    "WalletPairRelationship",
    "WalletRelationshipCluster",
    "WalletIndependenceAssessment",
    "assess_wallet_independence",
)


def test_wallet_public_api_is_exact_after_d4() -> None:
    assert wallets.__all__ == EXPECTED_D4_API


def test_d4_reducer_signature_is_exact_and_keyword_only() -> None:
    signature = inspect.signature(wallets.assess_wallet_independence)
    assert tuple(signature.parameters) == (
        "wallets",
        "evidence",
        "as_of_unix_ms",
        "policy",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )


def test_d4_public_symbols_remain_research_only() -> None:
    d4_text = " ".join(EXPECTED_D4_API[15:]).lower()
    for forbidden in (
        "providerclient",
        "sqlite",
        "tradeintent",
        "paperfill",
        "signer",
        "transaction",
        "execution",
        "live",
        "rank",
        "smartwallet",
    ):
        assert forbidden not in d4_text
