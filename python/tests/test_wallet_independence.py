from __future__ import annotations

import pytest

from shreks_brain.wallets import (
    WalletRelationshipDirection,
    WalletRelationshipEvidence,
    WalletRelationshipEvidenceQuality,
    WalletRelationshipPolicy,
    WalletRelationshipState,
    assess_wallet_independence,
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


def ev(
    evidence_id: str,
    wallet_a: str,
    wallet_b: str,
    *,
    direction: WalletRelationshipDirection = WalletRelationshipDirection.LINKED,
    quality: WalletRelationshipEvidenceQuality = WalletRelationshipEvidenceQuality.DIRECT,
    confidence: float = 0.9,
    reason: str = "link-signal",
    observed_at: int = 1_000,
) -> WalletRelationshipEvidence:
    return WalletRelationshipEvidence(
        evidence_id=evidence_id,
        wallet_a=wallet_a,
        wallet_b=wallet_b,
        observed_at_unix_ms=observed_at,
        direction=direction,
        evidence_quality=quality,
        confidence=confidence,
        reason_code=reason,
    )


def assess(
    wallets: tuple[str, ...],
    evidence: tuple[WalletRelationshipEvidence, ...] = (),
    *,
    as_of: int = 10_000,
    p: WalletRelationshipPolicy | None = None,
):
    return assess_wallet_independence(
        wallets=wallets,
        evidence=evidence,
        as_of_unix_ms=as_of,
        policy=p or policy(),
    )


def pair(result, wallet_a: str, wallet_b: str):
    canonical = tuple(sorted((wallet_a, wallet_b)))
    return next(
        row
        for row in result.pair_relationships
        if (row.wallet_a, row.wallet_b) == canonical
    )


def test_empty_and_single_wallet_assessments_are_deterministic() -> None:
    empty = assess(())
    assert empty.wallets == ()
    assert empty.total_pair_count == 0
    assert empty.pair_relationships == ()
    assert empty.clusters == ()
    assert empty.maximum_independent_group_count == 0
    assert empty.all_pairs_independent_under_evidence is True

    single = assess(("wallet-a",))
    assert single.wallets == ("wallet-a",)
    assert single.total_pair_count == 0
    assert tuple(cluster.wallets for cluster in single.clusters) == (("wallet-a",),)
    assert single.coordination_cluster_count == 0
    assert single.maximum_independent_group_count == 1
    assert single.all_pairs_independent_under_evidence is True


def test_no_evidence_is_unknown_not_independent() -> None:
    result = assess(("wallet-b", "wallet-a"))
    assert result.wallets == ("wallet-a", "wallet-b")
    row = pair(result, "wallet-a", "wallet-b")
    assert row.state is WalletRelationshipState.UNKNOWN
    assert row.evidence_count == 0
    assert row.link_confidence is None
    assert row.independence_confidence is None
    assert result.evidence_pair_count == 0
    assert result.unobserved_pair_count == 1
    assert result.unknown_pair_count == 1
    assert result.maximum_independent_group_count == 2
    assert result.all_pairs_independent_under_evidence is False


def test_strong_direct_link_collapses_pair_into_one_component() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (ev("ev-1", "wallet-a", "wallet-b", confidence=0.9),),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.state is WalletRelationshipState.LINKED
    assert row.link_confidence == pytest.approx(0.9)
    assert row.independence_confidence is None
    assert result.linked_pair_count == 1
    assert result.coordination_cluster_count == 1
    assert result.maximum_independent_group_count == 1
    assert tuple(cluster.wallets for cluster in result.clusters) == (
        ("wallet-a", "wallet-b"),
    )
    assert result.clusters[0].strongest_internal_link_confidence == pytest.approx(0.9)


def test_inferred_link_is_weighted_and_can_remain_unknown() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (
            ev(
                "ev-1",
                "wallet-a",
                "wallet-b",
                quality=WalletRelationshipEvidenceQuality.INFERRED,
                confidence=0.9,
            ),
        ),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.link_confidence == pytest.approx(0.45)
    assert row.state is WalletRelationshipState.UNKNOWN
    assert result.evidence_pair_count == 1
    assert result.unobserved_pair_count == 0


def test_strong_independence_evidence_keeps_separate_components() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (
            ev(
                "ev-1",
                "wallet-a",
                "wallet-b",
                direction=WalletRelationshipDirection.INDEPENDENT,
                confidence=0.8,
                reason="distinct-provenance",
            ),
        ),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.state is WalletRelationshipState.INDEPENDENT
    assert row.link_confidence is None
    assert row.independence_confidence == pytest.approx(0.8)
    assert result.independent_pair_count == 1
    assert result.maximum_independent_group_count == 2
    assert result.all_pairs_independent_under_evidence is True


def test_strong_evidence_in_both_directions_is_conflicting_and_clusters() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (
            ev("link", "wallet-a", "wallet-b", confidence=0.85),
            ev(
                "independent",
                "wallet-a",
                "wallet-b",
                direction=WalletRelationshipDirection.INDEPENDENT,
                confidence=0.8,
                reason="distinct-provenance",
            ),
        ),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.state is WalletRelationshipState.CONFLICTING
    assert result.conflicting_pair_count == 1
    assert result.maximum_independent_group_count == 1
    assert result.clusters[0].contains_conflicting_pair is True


def test_relationship_confidences_use_maximum_not_sum() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (
            ev(
                "ev-1",
                "wallet-a",
                "wallet-b",
                quality=WalletRelationshipEvidenceQuality.INFERRED,
                confidence=0.9,
                reason="signal-a",
            ),
            ev(
                "ev-2",
                "wallet-a",
                "wallet-b",
                quality=WalletRelationshipEvidenceQuality.INFERRED,
                confidence=0.9,
                reason="signal-b",
            ),
        ),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.evidence_count == 2
    assert row.link_confidence == pytest.approx(0.45)
    assert row.state is WalletRelationshipState.UNKNOWN


def test_strongest_evidence_tie_prefers_direct_then_lexical_metadata() -> None:
    result = assess(
        ("wallet-a", "wallet-b"),
        (
            ev(
                "inferred-a",
                "wallet-a",
                "wallet-b",
                quality=WalletRelationshipEvidenceQuality.INFERRED,
                confidence=0.8,
                reason="a-inferred",
            ),
            ev(
                "direct-z",
                "wallet-a",
                "wallet-b",
                quality=WalletRelationshipEvidenceQuality.DIRECT,
                confidence=0.4,
                reason="z-direct",
            ),
        ),
        p=policy(relationship_confidence_threshold=0.3),
    )
    row = pair(result, "wallet-a", "wallet-b")
    assert row.link_confidence == pytest.approx(0.4)
    assert row.strongest_link_reason_code == "z-direct"

    lexical = assess(
        ("wallet-a", "wallet-b"),
        (
            ev("z-id", "wallet-a", "wallet-b", confidence=0.8, reason="z-reason"),
            ev("b-id", "wallet-a", "wallet-b", confidence=0.8, reason="a-reason"),
            ev("a-id", "wallet-a", "wallet-b", confidence=0.8, reason="a-reason"),
        ),
    )
    assert pair(lexical, "wallet-a", "wallet-b").strongest_link_reason_code == "a-reason"


def test_orientation_and_input_order_do_not_change_result() -> None:
    first = assess(
        ("c", "a", "b"),
        (
            ev("ab", "a", "b", confidence=0.9),
            ev("bc", "b", "c", confidence=0.8),
        ),
    )
    second = assess(
        ("b", "c", "a"),
        (
            ev("bc", "c", "b", confidence=0.8),
            ev("ab", "b", "a", confidence=0.9),
        ),
    )
    assert first == second


def test_transitive_linkage_forms_one_conservative_component() -> None:
    result = assess(
        ("a", "b", "c"),
        (
            ev("ab", "a", "b", confidence=0.9),
            ev("bc", "b", "c", confidence=0.8),
        ),
    )
    assert pair(result, "a", "c").state is WalletRelationshipState.UNKNOWN
    assert tuple(cluster.wallets for cluster in result.clusters) == (("a", "b", "c"),)
    assert result.maximum_independent_group_count == 1
    assert result.coordination_cluster_count == 1


def test_conflicting_edge_clusters_but_independent_pair_does_not() -> None:
    result = assess(
        ("a", "b", "c"),
        (
            ev("ab-link", "a", "b", confidence=0.9),
            ev(
                "ab-independent",
                "a",
                "b",
                direction=WalletRelationshipDirection.INDEPENDENT,
                confidence=0.8,
            ),
            ev(
                "bc-independent",
                "b",
                "c",
                direction=WalletRelationshipDirection.INDEPENDENT,
                confidence=0.9,
            ),
        ),
    )
    assert pair(result, "a", "b").state is WalletRelationshipState.CONFLICTING
    assert pair(result, "b", "c").state is WalletRelationshipState.INDEPENDENT
    assert tuple(cluster.wallets for cluster in result.clusters) == (("a", "b"), ("c",))
    assert result.maximum_independent_group_count == 2


def test_all_pairs_independent_requires_every_pair_to_be_explicitly_independent() -> None:
    partial = assess(
        ("a", "b", "c"),
        (
            ev("ab", "a", "b", direction=WalletRelationshipDirection.INDEPENDENT, confidence=0.9),
            ev("ac", "a", "c", direction=WalletRelationshipDirection.INDEPENDENT, confidence=0.9),
        ),
    )
    assert partial.all_pairs_independent_under_evidence is False
    assert pair(partial, "b", "c").state is WalletRelationshipState.UNKNOWN

    complete = assess(
        ("a", "b", "c"),
        (
            ev("ab", "a", "b", direction=WalletRelationshipDirection.INDEPENDENT, confidence=0.9),
            ev("ac", "a", "c", direction=WalletRelationshipDirection.INDEPENDENT, confidence=0.9),
            ev("bc", "b", "c", direction=WalletRelationshipDirection.INDEPENDENT, confidence=0.9),
        ),
    )
    assert complete.independent_pair_count == 3
    assert complete.all_pairs_independent_under_evidence is True
    assert complete.maximum_independent_group_count == 3


def test_duplicate_evidence_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="evidence_id"):
        assess(
            ("a", "b"),
            (
                ev("same", "a", "b"),
                ev("same", "a", "b", confidence=0.8),
            ),
        )


def test_evidence_outside_wallet_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="requested wallet"):
        assess(("a", "b"), (ev("ev-1", "a", "c"),))


def test_future_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="future"):
        assess(("a", "b"), (ev("ev-1", "a", "b", observed_at=10_001),), as_of=10_000)


def test_duplicate_wallet_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="distinct"):
        assess(("a", "a"))
