from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shreks_brain.features import (
    WALLET_FEATURE_SCHEMA_VERSION,
    WalletFeatureInputs,
    WalletFeaturePolicy,
    WalletFeatureVector,
    WalletHistoricalStrengthState,
    WalletStrengthAssessment,
)
from shreks_brain.wallets import (
    WalletActionKind,
    WalletObservation,
    WalletObservationEvidence,
    WalletRelationshipPolicy,
    assess_wallet_independence,
)

AS_OF = 10_000_000
MINT = "mint-a"


def _policy(**overrides: object) -> WalletFeaturePolicy:
    values: dict[str, object] = {
        "version": "d5-test-v1",
        "entry_window_ms": 300_000,
        "exit_window_ms": 300_000,
        "creator_activity_window_ms": 900_000,
        "minimum_effective_closed_sample_size": 5.0,
        "minimum_evidence_sample_confidence": 0.5,
        "minimum_median_return_pct": 10.0,
        "minimum_win_rate": 0.55,
        "maximum_rug_exposure_rate": 0.10,
        "maximum_median_drawdown_pct": 35.0,
    }
    values.update(overrides)
    return WalletFeaturePolicy(**values)  # type: ignore[arg-type]


def _empty_independence():
    return assess_wallet_independence(
        wallets=(),
        evidence=(),
        as_of_unix_ms=AS_OF,
        policy=WalletRelationshipPolicy(
            version="d4-test-v1",
            direct_evidence_weight=1.0,
            inferred_evidence_weight=0.5,
            relationship_confidence_threshold=0.7,
        ),
    )


def _observation(*, mint: str = MINT, observed_at: int = AS_OF) -> WalletObservation:
    return WalletObservation(
        provider="provider-a",
        wallet="wallet-a",
        candidate_mint=mint,
        action=WalletActionKind.OTHER,
        evidence=WalletObservationEvidence.DIRECT,
        signature=f"sig-{mint}-{observed_at}",
        event_index=0,
        slot=1,
        observed_at_unix_ms=observed_at,
        occurred_at_unix_ms=None,
        candidate_token_delta_raw=None,
        counter_asset_mint=None,
        counter_asset_delta_raw=None,
        venue=None,
        counterparty=None,
    )


def test_wallet_feature_policy_is_strict_and_immutable() -> None:
    policy = _policy()
    assert policy.version == "d5-test-v1"
    with pytest.raises(FrozenInstanceError):
        policy.entry_window_ms = 1  # type: ignore[misc]

    for field, value in (
        ("entry_window_ms", 0),
        ("exit_window_ms", -1),
        ("creator_activity_window_ms", True),
        ("minimum_effective_closed_sample_size", 0.0),
        ("minimum_evidence_sample_confidence", 0.0),
        ("minimum_evidence_sample_confidence", 1.1),
        ("minimum_median_return_pct", 0.0),
        ("minimum_win_rate", -0.1),
        ("minimum_win_rate", 1.1),
        ("maximum_rug_exposure_rate", 1.1),
        ("maximum_median_drawdown_pct", 100.1),
    ):
        with pytest.raises(ValueError):
            _policy(**{field: value})


def test_strength_state_values_and_assessment_invariants() -> None:
    assert WalletHistoricalStrengthState.STRONG.value == "STRONG"
    assert WalletHistoricalStrengthState.NOT_STRONG.value == "NOT_STRONG"
    assert WalletHistoricalStrengthState.UNKNOWN.value == "UNKNOWN"

    strong = WalletStrengthAssessment(
        wallet="wallet-a",
        state=WalletHistoricalStrengthState.STRONG,
        effective_closed_sample_size=5.0,
        evidence_sample_confidence=0.5,
        median_return_pct=20.0,
        win_rate=0.6,
        rug_exposure_rate=0.0,
        median_drawdown_pct=20.0,
        failed_checks=(),
        missing_checks=(),
    )
    assert strong.wallet == "wallet-a"
    with pytest.raises(FrozenInstanceError):
        strong.wallet = "wallet-b"  # type: ignore[misc]

    with pytest.raises(ValueError, match="STRONG"):
        WalletStrengthAssessment(
            wallet="wallet-a",
            state=WalletHistoricalStrengthState.STRONG,
            effective_closed_sample_size=5.0,
            evidence_sample_confidence=0.5,
            median_return_pct=20.0,
            win_rate=0.6,
            rug_exposure_rate=0.0,
            median_drawdown_pct=20.0,
            failed_checks=("win_rate",),
            missing_checks=(),
        )

    with pytest.raises(ValueError, match="UNKNOWN"):
        WalletStrengthAssessment(
            wallet="wallet-a",
            state=WalletHistoricalStrengthState.UNKNOWN,
            effective_closed_sample_size=5.0,
            evidence_sample_confidence=0.5,
            median_return_pct=20.0,
            win_rate=0.6,
            rug_exposure_rate=None,
            median_drawdown_pct=20.0,
            failed_checks=(),
            missing_checks=(),
        )


def test_empty_inputs_are_valid_and_preserve_b2_schema_separation() -> None:
    inputs = WalletFeatureInputs(
        as_of_unix_ms=AS_OF,
        candidate_mint=MINT,
        reconstructions=(),
        profiles=(),
        independence=_empty_independence(),
        observations=(),
        policy=_policy(),
    )
    assert inputs.candidate_mint == MINT
    assert WALLET_FEATURE_SCHEMA_VERSION == "d5-wallet-v1"


def test_input_rejects_future_or_wrong_candidate_observation() -> None:
    with pytest.raises(ValueError, match="future"):
        WalletFeatureInputs(
            as_of_unix_ms=AS_OF,
            candidate_mint=MINT,
            reconstructions=(),
            profiles=(),
            independence=_empty_independence(),
            observations=(_observation(observed_at=AS_OF + 1),),
            policy=_policy(),
        )

    with pytest.raises(ValueError, match="candidate"):
        WalletFeatureInputs(
            as_of_unix_ms=AS_OF,
            candidate_mint=MINT,
            reconstructions=(),
            profiles=(),
            independence=_empty_independence(),
            observations=(_observation(mint="mint-b"),),
            policy=_policy(),
        )


def test_wallet_feature_vector_rejects_impossible_weighted_count() -> None:
    assessment = WalletStrengthAssessment(
        wallet="wallet-a",
        state=WalletHistoricalStrengthState.STRONG,
        effective_closed_sample_size=5.0,
        evidence_sample_confidence=0.5,
        median_return_pct=20.0,
        win_rate=0.6,
        rug_exposure_rate=0.0,
        median_drawdown_pct=20.0,
        failed_checks=(),
        missing_checks=(),
    )
    with pytest.raises(ValueError, match="weighted"):
        WalletFeatureVector(
            schema_version="d5-wallet-v1",
            as_of_unix_ms=AS_OF,
            candidate_mint=MINT,
            wallet_feature_policy_version="d5-test-v1",
            profile_policy_version="d3-test-v1",
            profile_context_version="ctx-v1",
            relationship_policy_version="d4-test-v1",
            wallet_count=1,
            recent_entry_wallet_count=1,
            recent_exit_wallet_count=0,
            strong_wallet_count=1,
            unknown_strength_wallet_count=0,
            strong_entry_wallet_count=1,
            strong_exit_wallet_count=0,
            confidence_weighted_strong_entry_count=1.1,
            confidence_weighted_strong_exit_count=0.0,
            entry_quality_profile_sample_count=1,
            confidence_weighted_entry_median_return_pct=20.0,
            confidence_weighted_entry_win_rate=0.6,
            independently_strong_entry_wallet_count=1,
            strong_entry_all_pairs_independent_under_evidence=True,
            strong_entry_linked_pair_count=0,
            strong_entry_conflicting_pair_count=0,
            strong_entry_unknown_pair_count=0,
            strong_entry_coordination_cluster_count=0,
            strong_entry_max_independent_group_count_upper_bound=1,
            creator_deployer_action_observation_count=0,
            strength_assessments=(assessment,),
            missing_features=(),
        )
