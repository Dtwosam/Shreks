from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
import math


class WalletRelationshipDirection(StrEnum):
    LINKED = "LINKED"
    INDEPENDENT = "INDEPENDENT"


class WalletRelationshipEvidenceQuality(StrEnum):
    DIRECT = "DIRECT"
    INFERRED = "INFERRED"


class WalletRelationshipState(StrEnum):
    LINKED = "LINKED"
    INDEPENDENT = "INDEPENDENT"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WalletRelationshipEvidence:
    evidence_id: str
    wallet_a: str
    wallet_b: str
    observed_at_unix_ms: int
    direction: WalletRelationshipDirection
    evidence_quality: WalletRelationshipEvidenceQuality
    confidence: float
    reason_code: str

    def __post_init__(self) -> None:
        _require_non_empty_string("evidence_id", self.evidence_id)
        _require_non_empty_string("wallet_a", self.wallet_a)
        _require_non_empty_string("wallet_b", self.wallet_b)
        if self.wallet_a == self.wallet_b:
            raise ValueError("wallet relationship evidence requires two distinct wallets")
        _require_non_negative_int("observed_at_unix_ms", self.observed_at_unix_ms)
        if not isinstance(self.direction, WalletRelationshipDirection):
            raise ValueError("direction must be a WalletRelationshipDirection")
        if not isinstance(self.evidence_quality, WalletRelationshipEvidenceQuality):
            raise ValueError(
                "evidence_quality must be a WalletRelationshipEvidenceQuality"
            )
        _require_probability("confidence", self.confidence)
        _require_non_empty_string("reason_code", self.reason_code)


@dataclass(frozen=True, slots=True)
class WalletRelationshipPolicy:
    version: str
    direct_evidence_weight: float
    inferred_evidence_weight: float
    relationship_confidence_threshold: float

    def __post_init__(self) -> None:
        _require_non_empty_string("version", self.version)
        direct = _require_probability(
            "direct_evidence_weight", self.direct_evidence_weight
        )
        inferred = _require_probability(
            "inferred_evidence_weight", self.inferred_evidence_weight
        )
        threshold = _require_probability(
            "relationship_confidence_threshold",
            self.relationship_confidence_threshold,
        )
        if direct <= 0.0:
            raise ValueError("direct_evidence_weight must be strictly positive")
        if inferred > direct:
            raise ValueError(
                "inferred_evidence_weight cannot exceed direct_evidence_weight"
            )
        if threshold <= 0.0:
            raise ValueError(
                "relationship_confidence_threshold must be strictly positive"
            )


@dataclass(frozen=True, slots=True)
class WalletPairRelationship:
    wallet_a: str
    wallet_b: str
    state: WalletRelationshipState
    evidence_count: int
    direct_evidence_count: int
    inferred_evidence_count: int
    link_confidence: float | None
    independence_confidence: float | None
    strongest_link_reason_code: str | None
    strongest_independence_reason_code: str | None
    observed_through_unix_ms: int | None

    def __post_init__(self) -> None:
        _require_non_empty_string("wallet_a", self.wallet_a)
        _require_non_empty_string("wallet_b", self.wallet_b)
        if self.wallet_a >= self.wallet_b:
            raise ValueError("wallet pair must be canonical with wallet_a < wallet_b")
        if not isinstance(self.state, WalletRelationshipState):
            raise ValueError("state must be a WalletRelationshipState")
        for name, value in (
            ("evidence_count", self.evidence_count),
            ("direct_evidence_count", self.direct_evidence_count),
            ("inferred_evidence_count", self.inferred_evidence_count),
        ):
            _require_non_negative_int(name, value)
        if self.direct_evidence_count + self.inferred_evidence_count != self.evidence_count:
            raise ValueError("evidence quality counts must reconcile to evidence_count")
        _require_optional_probability("link_confidence", self.link_confidence)
        _require_optional_probability(
            "independence_confidence", self.independence_confidence
        )
        _require_optional_non_empty_string(
            "strongest_link_reason_code", self.strongest_link_reason_code
        )
        _require_optional_non_empty_string(
            "strongest_independence_reason_code",
            self.strongest_independence_reason_code,
        )
        if (self.link_confidence is None) != (
            self.strongest_link_reason_code is None
        ):
            raise ValueError(
                "link confidence and strongest link reason must be present together"
            )
        if (self.independence_confidence is None) != (
            self.strongest_independence_reason_code is None
        ):
            raise ValueError(
                "independence confidence and strongest independence reason must be present together"
            )
        _require_optional_non_negative_int(
            "observed_through_unix_ms", self.observed_through_unix_ms
        )
        if self.evidence_count == 0:
            if self.observed_through_unix_ms is not None:
                raise ValueError(
                    "evidence-free pair cannot have observed_through_unix_ms"
                )
            if self.state is not WalletRelationshipState.UNKNOWN:
                raise ValueError("evidence-free pair must remain UNKNOWN")
            if self.link_confidence is not None or self.independence_confidence is not None:
                raise ValueError("evidence-free pair cannot have directional confidence")
        elif self.observed_through_unix_ms is None:
            raise ValueError("pair with evidence requires observed_through_unix_ms")


@dataclass(frozen=True, slots=True)
class WalletRelationshipCluster:
    cluster_index: int
    wallets: tuple[str, ...]
    strongest_internal_link_confidence: float | None
    contains_conflicting_pair: bool

    def __post_init__(self) -> None:
        _require_non_negative_int("cluster_index", self.cluster_index)
        if not isinstance(self.wallets, tuple) or not self.wallets:
            raise ValueError("wallets must be a non-empty tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.wallets):
            raise ValueError("cluster wallets must be non-empty strings")
        if tuple(sorted(set(self.wallets))) != self.wallets:
            raise ValueError("cluster wallets must be unique and in lexical order")
        _require_optional_probability(
            "strongest_internal_link_confidence",
            self.strongest_internal_link_confidence,
        )
        if not isinstance(self.contains_conflicting_pair, bool):
            raise ValueError("contains_conflicting_pair must be boolean")
        if len(self.wallets) == 1:
            if self.strongest_internal_link_confidence is not None:
                raise ValueError("singleton cluster cannot have internal link confidence")
            if self.contains_conflicting_pair:
                raise ValueError("singleton cluster cannot contain a conflicting pair")
        elif self.strongest_internal_link_confidence is None:
            raise ValueError("multi-wallet cluster requires internal link confidence")


@dataclass(frozen=True, slots=True)
class WalletIndependenceAssessment:
    as_of_unix_ms: int
    policy_version: str
    wallets: tuple[str, ...]
    total_pair_count: int
    evidence_pair_count: int
    unobserved_pair_count: int
    linked_pair_count: int
    independent_pair_count: int
    conflicting_pair_count: int
    unknown_pair_count: int
    coordination_cluster_count: int
    maximum_independent_group_count: int
    all_pairs_independent_under_evidence: bool
    pair_relationships: tuple[WalletPairRelationship, ...]
    clusters: tuple[WalletRelationshipCluster, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int("as_of_unix_ms", self.as_of_unix_ms)
        _require_non_empty_string("policy_version", self.policy_version)
        if not isinstance(self.wallets, tuple):
            raise ValueError("wallets must be a tuple")
        if not all(isinstance(value, str) and value.strip() for value in self.wallets):
            raise ValueError("wallets must contain non-empty strings")
        if tuple(sorted(set(self.wallets))) != self.wallets:
            raise ValueError("wallets must be unique and in lexical order")

        for name in (
            "total_pair_count",
            "evidence_pair_count",
            "unobserved_pair_count",
            "linked_pair_count",
            "independent_pair_count",
            "conflicting_pair_count",
            "unknown_pair_count",
            "coordination_cluster_count",
            "maximum_independent_group_count",
        ):
            _require_non_negative_int(name, getattr(self, name))
        if not isinstance(self.all_pairs_independent_under_evidence, bool):
            raise ValueError("all_pairs_independent_under_evidence must be boolean")

        expected_pair_count = len(self.wallets) * (len(self.wallets) - 1) // 2
        if self.total_pair_count != expected_pair_count:
            raise ValueError("total_pair_count must match wallet combinations")
        if self.evidence_pair_count + self.unobserved_pair_count != self.total_pair_count:
            raise ValueError("evidence/unobserved pair counts must reconcile")
        if (
            self.linked_pair_count
            + self.independent_pair_count
            + self.conflicting_pair_count
            + self.unknown_pair_count
            != self.total_pair_count
        ):
            raise ValueError("relationship state counts must reconcile to total_pair_count")

        if not isinstance(self.pair_relationships, tuple) or not all(
            isinstance(value, WalletPairRelationship)
            for value in self.pair_relationships
        ):
            raise ValueError(
                "pair_relationships must be a tuple of WalletPairRelationship values"
            )
        expected_pairs = tuple(combinations(self.wallets, 2))
        actual_pairs = tuple(
            (value.wallet_a, value.wallet_b) for value in self.pair_relationships
        )
        if actual_pairs != expected_pairs:
            raise ValueError(
                "pair_relationships must cover every wallet pair once in lexical order"
            )

        derived_evidence_pairs = sum(
            value.evidence_count > 0 for value in self.pair_relationships
        )
        derived_state_counts = {
            state: sum(value.state is state for value in self.pair_relationships)
            for state in WalletRelationshipState
        }
        if derived_evidence_pairs != self.evidence_pair_count:
            raise ValueError("evidence_pair_count must match pair_relationships")
        if self.unobserved_pair_count != self.total_pair_count - derived_evidence_pairs:
            raise ValueError("unobserved_pair_count must match pair_relationships")
        if derived_state_counts[WalletRelationshipState.LINKED] != self.linked_pair_count:
            raise ValueError("linked_pair_count must match pair_relationships")
        if (
            derived_state_counts[WalletRelationshipState.INDEPENDENT]
            != self.independent_pair_count
        ):
            raise ValueError("independent_pair_count must match pair_relationships")
        if (
            derived_state_counts[WalletRelationshipState.CONFLICTING]
            != self.conflicting_pair_count
        ):
            raise ValueError("conflicting_pair_count must match pair_relationships")
        if derived_state_counts[WalletRelationshipState.UNKNOWN] != self.unknown_pair_count:
            raise ValueError("unknown_pair_count must match pair_relationships")

        expected_all_independent = self.total_pair_count == 0 or all(
            value.state is WalletRelationshipState.INDEPENDENT
            for value in self.pair_relationships
        )
        if self.all_pairs_independent_under_evidence != expected_all_independent:
            raise ValueError(
                "all_pairs_independent_under_evidence must match pair states"
            )

        if not isinstance(self.clusters, tuple) or not all(
            isinstance(value, WalletRelationshipCluster) for value in self.clusters
        ):
            raise ValueError("clusters must be a tuple of WalletRelationshipCluster values")
        if tuple(cluster.cluster_index for cluster in self.clusters) != tuple(
            range(len(self.clusters))
        ):
            raise ValueError("cluster indexes must be contiguous from zero")
        cluster_wallet_tuples = tuple(cluster.wallets for cluster in self.clusters)
        if cluster_wallet_tuples != tuple(sorted(cluster_wallet_tuples)):
            raise ValueError("clusters must be in lexical component order")
        flattened = tuple(wallet for cluster in self.clusters for wallet in cluster.wallets)
        if tuple(sorted(flattened)) != self.wallets or len(flattened) != len(set(flattened)):
            raise ValueError("clusters must partition the assessment wallets exactly")
        derived_coordination_count = sum(len(cluster.wallets) > 1 for cluster in self.clusters)
        if self.coordination_cluster_count != derived_coordination_count:
            raise ValueError("coordination_cluster_count must match clusters")
        if self.maximum_independent_group_count != len(self.clusters):
            raise ValueError("maximum_independent_group_count must equal cluster count")


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_optional_non_empty_string(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_empty_string(name, value)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_non_negative_int(name: str, value: object | None) -> None:
    if value is not None:
        _require_non_negative_int(name, value)


def _require_probability(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return result


def _require_optional_probability(name: str, value: object | None) -> None:
    if value is not None:
        _require_probability(name, value)
