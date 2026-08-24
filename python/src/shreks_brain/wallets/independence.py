from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .relationship_models import (
    WalletIndependenceAssessment,
    WalletPairRelationship,
    WalletRelationshipCluster,
    WalletRelationshipDirection,
    WalletRelationshipEvidence,
    WalletRelationshipEvidenceQuality,
    WalletRelationshipPolicy,
    WalletRelationshipState,
)


@dataclass(frozen=True, slots=True)
class _StrongestEvidence:
    adjusted_confidence: float
    row: WalletRelationshipEvidence


def assess_wallet_independence(
    *,
    wallets: tuple[str, ...],
    evidence: tuple[WalletRelationshipEvidence, ...],
    as_of_unix_ms: int,
    policy: WalletRelationshipPolicy,
) -> WalletIndependenceAssessment:
    normalized_wallets = _validate_and_normalize_inputs(
        wallets=wallets,
        evidence=evidence,
        as_of_unix_ms=as_of_unix_ms,
        policy=policy,
    )

    rows_by_pair: dict[tuple[str, str], list[WalletRelationshipEvidence]] = {}
    for row in evidence:
        pair = tuple(sorted((row.wallet_a, row.wallet_b)))
        rows_by_pair.setdefault(pair, []).append(row)

    pair_relationships = tuple(
        _build_pair_relationship(
            wallet_a=wallet_a,
            wallet_b=wallet_b,
            rows=rows_by_pair.get((wallet_a, wallet_b), ()),
            policy=policy,
        )
        for wallet_a, wallet_b in combinations(normalized_wallets, 2)
    )

    clusters = _build_clusters(
        wallets=normalized_wallets,
        pair_relationships=pair_relationships,
    )

    linked_pair_count = sum(
        row.state is WalletRelationshipState.LINKED for row in pair_relationships
    )
    independent_pair_count = sum(
        row.state is WalletRelationshipState.INDEPENDENT for row in pair_relationships
    )
    conflicting_pair_count = sum(
        row.state is WalletRelationshipState.CONFLICTING for row in pair_relationships
    )
    unknown_pair_count = sum(
        row.state is WalletRelationshipState.UNKNOWN for row in pair_relationships
    )
    evidence_pair_count = sum(row.evidence_count > 0 for row in pair_relationships)
    total_pair_count = len(pair_relationships)

    return WalletIndependenceAssessment(
        as_of_unix_ms=as_of_unix_ms,
        policy_version=policy.version,
        wallets=normalized_wallets,
        total_pair_count=total_pair_count,
        evidence_pair_count=evidence_pair_count,
        unobserved_pair_count=total_pair_count - evidence_pair_count,
        linked_pair_count=linked_pair_count,
        independent_pair_count=independent_pair_count,
        conflicting_pair_count=conflicting_pair_count,
        unknown_pair_count=unknown_pair_count,
        coordination_cluster_count=sum(len(cluster.wallets) > 1 for cluster in clusters),
        maximum_independent_group_count=len(clusters),
        all_pairs_independent_under_evidence=(
            total_pair_count == 0
            or independent_pair_count == total_pair_count
        ),
        pair_relationships=pair_relationships,
        clusters=clusters,
    )


def _validate_and_normalize_inputs(
    *,
    wallets: tuple[str, ...],
    evidence: tuple[WalletRelationshipEvidence, ...],
    as_of_unix_ms: int,
    policy: WalletRelationshipPolicy,
) -> tuple[str, ...]:
    if not isinstance(wallets, tuple):
        raise ValueError("wallets must be a tuple")
    if not all(isinstance(wallet, str) and wallet.strip() for wallet in wallets):
        raise ValueError("wallets must contain non-empty strings")
    if len(set(wallets)) != len(wallets):
        raise ValueError("wallets must contain distinct values")
    if isinstance(as_of_unix_ms, bool) or not isinstance(as_of_unix_ms, int) or as_of_unix_ms < 0:
        raise ValueError("as_of_unix_ms must be a non-negative integer")
    if type(policy) is not WalletRelationshipPolicy:
        raise ValueError("policy must be a WalletRelationshipPolicy")
    if not isinstance(evidence, tuple):
        raise ValueError("evidence must be a tuple")
    if not all(type(row) is WalletRelationshipEvidence for row in evidence):
        raise ValueError("evidence must contain WalletRelationshipEvidence values")

    normalized_wallets = tuple(sorted(wallets))
    requested = set(normalized_wallets)
    evidence_ids: set[str] = set()
    for row in evidence:
        if row.evidence_id in evidence_ids:
            raise ValueError("duplicate evidence_id in relationship evidence")
        evidence_ids.add(row.evidence_id)
        if row.wallet_a not in requested or row.wallet_b not in requested:
            raise ValueError("relationship evidence endpoint is not a requested wallet")
        if row.observed_at_unix_ms > as_of_unix_ms:
            raise ValueError("future relationship evidence is not allowed")

    return normalized_wallets


def _build_pair_relationship(
    *,
    wallet_a: str,
    wallet_b: str,
    rows: tuple[WalletRelationshipEvidence, ...] | list[WalletRelationshipEvidence],
    policy: WalletRelationshipPolicy,
) -> WalletPairRelationship:
    strongest_link: _StrongestEvidence | None = None
    strongest_independence: _StrongestEvidence | None = None

    for row in rows:
        adjusted = row.confidence * _evidence_weight(row, policy)
        candidate = _StrongestEvidence(adjusted_confidence=adjusted, row=row)
        if row.direction is WalletRelationshipDirection.LINKED:
            if _candidate_is_stronger(candidate, strongest_link):
                strongest_link = candidate
        elif row.direction is WalletRelationshipDirection.INDEPENDENT:
            if _candidate_is_stronger(candidate, strongest_independence):
                strongest_independence = candidate
        else:
            raise AssertionError("unexpected relationship direction")

    link_confidence = (
        None if strongest_link is None else strongest_link.adjusted_confidence
    )
    independence_confidence = (
        None
        if strongest_independence is None
        else strongest_independence.adjusted_confidence
    )
    link_strong = (
        link_confidence is not None
        and link_confidence >= policy.relationship_confidence_threshold
    )
    independence_strong = (
        independence_confidence is not None
        and independence_confidence >= policy.relationship_confidence_threshold
    )

    if link_strong and independence_strong:
        state = WalletRelationshipState.CONFLICTING
    elif link_strong:
        state = WalletRelationshipState.LINKED
    elif independence_strong:
        state = WalletRelationshipState.INDEPENDENT
    else:
        state = WalletRelationshipState.UNKNOWN

    return WalletPairRelationship(
        wallet_a=wallet_a,
        wallet_b=wallet_b,
        state=state,
        evidence_count=len(rows),
        direct_evidence_count=sum(
            row.evidence_quality is WalletRelationshipEvidenceQuality.DIRECT
            for row in rows
        ),
        inferred_evidence_count=sum(
            row.evidence_quality is WalletRelationshipEvidenceQuality.INFERRED
            for row in rows
        ),
        link_confidence=link_confidence,
        independence_confidence=independence_confidence,
        strongest_link_reason_code=(
            None if strongest_link is None else strongest_link.row.reason_code
        ),
        strongest_independence_reason_code=(
            None
            if strongest_independence is None
            else strongest_independence.row.reason_code
        ),
        observed_through_unix_ms=(
            None if not rows else max(row.observed_at_unix_ms for row in rows)
        ),
    )


def _evidence_weight(
    row: WalletRelationshipEvidence,
    policy: WalletRelationshipPolicy,
) -> float:
    if row.evidence_quality is WalletRelationshipEvidenceQuality.DIRECT:
        return policy.direct_evidence_weight
    if row.evidence_quality is WalletRelationshipEvidenceQuality.INFERRED:
        return policy.inferred_evidence_weight
    raise AssertionError("unexpected relationship evidence quality")


def _candidate_is_stronger(
    candidate: _StrongestEvidence,
    current: _StrongestEvidence | None,
) -> bool:
    if current is None:
        return True
    if candidate.adjusted_confidence != current.adjusted_confidence:
        return candidate.adjusted_confidence > current.adjusted_confidence

    candidate_direct = (
        candidate.row.evidence_quality is WalletRelationshipEvidenceQuality.DIRECT
    )
    current_direct = (
        current.row.evidence_quality is WalletRelationshipEvidenceQuality.DIRECT
    )
    if candidate_direct != current_direct:
        return candidate_direct
    if candidate.row.reason_code != current.row.reason_code:
        return candidate.row.reason_code < current.row.reason_code
    return candidate.row.evidence_id < current.row.evidence_id


def _build_clusters(
    *,
    wallets: tuple[str, ...],
    pair_relationships: tuple[WalletPairRelationship, ...],
) -> tuple[WalletRelationshipCluster, ...]:
    if not wallets:
        return ()

    parent = {wallet: wallet for wallet in wallets}

    def find(wallet: str) -> str:
        root = wallet
        while parent[root] != root:
            root = parent[root]
        while parent[wallet] != wallet:
            next_wallet = parent[wallet]
            parent[wallet] = root
            wallet = next_wallet
        return root

    def union(wallet_a: str, wallet_b: str) -> None:
        root_a = find(wallet_a)
        root_b = find(wallet_b)
        if root_a == root_b:
            return
        if root_a < root_b:
            parent[root_b] = root_a
        else:
            parent[root_a] = root_b

    for row in pair_relationships:
        if row.state in (
            WalletRelationshipState.LINKED,
            WalletRelationshipState.CONFLICTING,
        ):
            union(row.wallet_a, row.wallet_b)

    members_by_root: dict[str, list[str]] = {}
    for wallet in wallets:
        members_by_root.setdefault(find(wallet), []).append(wallet)

    component_wallets = tuple(
        sorted(tuple(sorted(members)) for members in members_by_root.values())
    )
    pair_by_key = {
        (row.wallet_a, row.wallet_b): row for row in pair_relationships
    }

    clusters: list[WalletRelationshipCluster] = []
    for cluster_index, members in enumerate(component_wallets):
        if len(members) == 1:
            clusters.append(
                WalletRelationshipCluster(
                    cluster_index=cluster_index,
                    wallets=members,
                    strongest_internal_link_confidence=None,
                    contains_conflicting_pair=False,
                )
            )
            continue

        internal_pairs = tuple(
            pair_by_key[(wallet_a, wallet_b)]
            for wallet_a, wallet_b in combinations(members, 2)
        )
        strong_link_confidences = tuple(
            row.link_confidence
            for row in internal_pairs
            if row.state
            in (
                WalletRelationshipState.LINKED,
                WalletRelationshipState.CONFLICTING,
            )
            and row.link_confidence is not None
        )
        if not strong_link_confidences:
            raise AssertionError("multi-wallet component requires a strong link edge")
        clusters.append(
            WalletRelationshipCluster(
                cluster_index=cluster_index,
                wallets=members,
                strongest_internal_link_confidence=max(strong_link_confidences),
                contains_conflicting_pair=any(
                    row.state is WalletRelationshipState.CONFLICTING
                    for row in internal_pairs
                ),
            )
        )

    return tuple(clusters)
