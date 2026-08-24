from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import pytest

from shreks_brain.wallets import (
    WalletIndependenceAssessment,
    WalletPairRelationship,
    WalletRelationshipCluster,
    WalletRelationshipDirection,
    WalletRelationshipEvidence,
    WalletRelationshipEvidenceQuality,
    WalletRelationshipPolicy,
    WalletRelationshipState,
)


def policy(**changes: object) -> WalletRelationshipPolicy:
    values: dict[str, object] = {
        "version": "d4-test-v1",
        "direct_evidence_weight": 1.0,
        "inferred_evidence_weight": 0.5,
        "relationship_confidence_threshold": 0.7,
    }
    values.update(changes)
    return WalletRelationshipPolicy(**values)  # type: ignore[arg-type]


def evidence(**changes: object) -> WalletRelationshipEvidence:
    values: dict[str, object] = {
        "evidence_id": "ev-1",
        "wallet_a": "wallet-a",
        "wallet_b": "wallet-b",
        "observed_at_unix_ms": 1_000,
        "direction": WalletRelationshipDirection.LINKED,
        "evidence_quality": WalletRelationshipEvidenceQuality.DIRECT,
        "confidence": 0.9,
        "reason_code": "shared-funding-path",
    }
    values.update(changes)
    return WalletRelationshipEvidence(**values)  # type: ignore[arg-type]


def test_relationship_enum_values_are_stable() -> None:
    assert WalletRelationshipDirection.LINKED.value == "LINKED"
    assert WalletRelationshipDirection.INDEPENDENT.value == "INDEPENDENT"
    assert WalletRelationshipEvidenceQuality.DIRECT.value == "DIRECT"
    assert WalletRelationshipEvidenceQuality.INFERRED.value == "INFERRED"
    assert tuple(state.value for state in WalletRelationshipState) == (
        "LINKED",
        "INDEPENDENT",
        "CONFLICTING",
        "UNKNOWN",
    )


def test_relationship_models_are_immutable() -> None:
    row = evidence()
    with pytest.raises(FrozenInstanceError):
        row.confidence = 0.1  # type: ignore[misc]
    p = policy()
    with pytest.raises(FrozenInstanceError):
        p.version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", ""),
        ("direct_evidence_weight", 0.0),
        ("direct_evidence_weight", -0.1),
        ("direct_evidence_weight", 1.1),
        ("direct_evidence_weight", True),
        ("direct_evidence_weight", math.inf),
        ("inferred_evidence_weight", -0.1),
        ("inferred_evidence_weight", 1.1),
        ("inferred_evidence_weight", True),
        ("inferred_evidence_weight", math.nan),
        ("relationship_confidence_threshold", 0.0),
        ("relationship_confidence_threshold", 1.1),
        ("relationship_confidence_threshold", True),
        ("relationship_confidence_threshold", math.inf),
    ],
)
def test_relationship_policy_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        policy(**{field: value})


def test_relationship_policy_requires_inferred_weight_not_above_direct() -> None:
    with pytest.raises(ValueError):
        policy(direct_evidence_weight=0.4, inferred_evidence_weight=0.5)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_id", ""),
        ("wallet_a", ""),
        ("wallet_b", ""),
        ("observed_at_unix_ms", -1),
        ("observed_at_unix_ms", True),
        ("direction", "LINKED"),
        ("evidence_quality", "DIRECT"),
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("confidence", True),
        ("confidence", math.nan),
        ("reason_code", ""),
    ],
)
def test_relationship_evidence_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        evidence(**{field: value})


def test_relationship_evidence_rejects_self_pair() -> None:
    with pytest.raises(ValueError):
        evidence(wallet_b="wallet-a")


def test_pair_model_requires_canonical_order_and_reconciled_counts() -> None:
    with pytest.raises(ValueError):
        WalletPairRelationship(
            wallet_a="b",
            wallet_b="a",
            state=WalletRelationshipState.UNKNOWN,
            evidence_count=0,
            direct_evidence_count=0,
            inferred_evidence_count=0,
            link_confidence=None,
            independence_confidence=None,
            strongest_link_reason_code=None,
            strongest_independence_reason_code=None,
            observed_through_unix_ms=None,
        )
    with pytest.raises(ValueError):
        WalletPairRelationship(
            wallet_a="a",
            wallet_b="b",
            state=WalletRelationshipState.UNKNOWN,
            evidence_count=2,
            direct_evidence_count=1,
            inferred_evidence_count=0,
            link_confidence=0.2,
            independence_confidence=None,
            strongest_link_reason_code="x",
            strongest_independence_reason_code=None,
            observed_through_unix_ms=100,
        )


def test_pair_model_preserves_missing_directional_evidence() -> None:
    row = WalletPairRelationship(
        wallet_a="a",
        wallet_b="b",
        state=WalletRelationshipState.UNKNOWN,
        evidence_count=0,
        direct_evidence_count=0,
        inferred_evidence_count=0,
        link_confidence=None,
        independence_confidence=None,
        strongest_link_reason_code=None,
        strongest_independence_reason_code=None,
        observed_through_unix_ms=None,
    )
    assert row.link_confidence is None
    assert row.independence_confidence is None


def test_pair_model_requires_confidence_and_reason_together() -> None:
    with pytest.raises(ValueError):
        WalletPairRelationship(
            wallet_a="a",
            wallet_b="b",
            state=WalletRelationshipState.UNKNOWN,
            evidence_count=1,
            direct_evidence_count=1,
            inferred_evidence_count=0,
            link_confidence=0.4,
            independence_confidence=None,
            strongest_link_reason_code=None,
            strongest_independence_reason_code=None,
            observed_through_unix_ms=100,
        )


def test_singleton_cluster_cannot_claim_internal_link() -> None:
    with pytest.raises(ValueError):
        WalletRelationshipCluster(
            cluster_index=0,
            wallets=("a",),
            strongest_internal_link_confidence=0.9,
            contains_conflicting_pair=False,
        )


def test_assessment_rejects_non_reconciled_pair_counts() -> None:
    pair = WalletPairRelationship(
        wallet_a="a",
        wallet_b="b",
        state=WalletRelationshipState.UNKNOWN,
        evidence_count=0,
        direct_evidence_count=0,
        inferred_evidence_count=0,
        link_confidence=None,
        independence_confidence=None,
        strongest_link_reason_code=None,
        strongest_independence_reason_code=None,
        observed_through_unix_ms=None,
    )
    with pytest.raises(ValueError):
        WalletIndependenceAssessment(
            as_of_unix_ms=100,
            policy_version="v1",
            wallets=("a", "b"),
            total_pair_count=1,
            evidence_pair_count=0,
            unobserved_pair_count=1,
            linked_pair_count=1,
            independent_pair_count=0,
            conflicting_pair_count=0,
            unknown_pair_count=0,
            coordination_cluster_count=0,
            maximum_independent_group_count=2,
            all_pairs_independent_under_evidence=False,
            pair_relationships=(pair,),
            clusters=(
                WalletRelationshipCluster(0, ("a",), None, False),
                WalletRelationshipCluster(1, ("b",), None, False),
            ),
        )
