from __future__ import annotations

import inspect

import shreks_brain.features as features


SEALED_B2_PREFIX = (
    "ANCHOR_1M_MAX_AGE_MS",
    "ANCHOR_1M_MIN_AGE_MS",
    "ANCHOR_5M_MAX_AGE_MS",
    "ANCHOR_5M_MIN_AGE_MS",
    "ANCHOR_15M_MAX_AGE_MS",
    "ANCHOR_15M_MIN_AGE_MS",
    "FEATURE_SCHEMA_VERSION",
    "FeatureInputs",
    "FeatureVector",
    "MarketFeaturePoint",
    "build_feature_vector",
)

D5_SUFFIX = (
    "WALLET_FEATURE_SCHEMA_VERSION",
    "WalletHistoricalStrengthState",
    "WalletFeaturePolicy",
    "WalletFeatureInputs",
    "WalletStrengthAssessment",
    "WalletFeatureVector",
    "build_wallet_feature_vector",
)


def test_d5_feature_public_api_is_exact_and_preserves_b2() -> None:
    assert features.__all__ == SEALED_B2_PREFIX + D5_SUFFIX
    assert features.FEATURE_SCHEMA_VERSION == "b2-v1"
    assert features.WALLET_FEATURE_SCHEMA_VERSION == "d5-wallet-v1"
    signature = inspect.signature(features.build_wallet_feature_vector)
    assert tuple(signature.parameters) == ("inputs",)


def test_d5_public_surface_stays_research_only() -> None:
    text = " ".join(D5_SUFFIX).lower()
    for forbidden in (
        "tradeintent",
        "signer",
        "transaction",
        "submission",
        "position_size",
        "live",
        "providerclient",
        "sqlite",
    ):
        assert forbidden not in text
