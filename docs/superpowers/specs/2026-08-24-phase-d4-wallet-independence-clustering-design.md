# Phase D4 Wallet Independence / Clustering Heuristics Design

**Base:** sealed D3 head `de9c0e578b99295b65c3593909ed35225e067380`.

## Goal

Add a pure point-in-time relationship layer that prevents strongly linked wallet behavior from being counted as many independent confirmations while preserving uncertainty when relationship evidence is incomplete or contradictory.

Absence of link evidence is not proof of independence.

## Scope

D4 extends `shreks_brain.wallets` and consumes only caller-supplied relationship evidence. It performs no provider, RPC, SQLite, wall-clock, balance, transaction-history, graph-service, or external-attribution reads.

D4 adds immutable relationship evidence/policy/output models, pairwise LINKED / INDEPENDENT / CONFLICTING / UNKNOWN states, conservative coordination components, and an upper bound on independent groups after strong link evidence is collapsed.

D4 adds no wallet ranking, smart-wallet label, D5 feature, provider ingestion, setup/score/decision/risk change, signer, transaction submission, or live-money authority.

## Models

### `WalletRelationshipDirection`

- `LINKED`
- `INDEPENDENT`

The direction describes what one evidence item supports; it is not treated as factual attribution.

### `WalletRelationshipEvidenceQuality`

- `DIRECT`
- `INFERRED`

This vocabulary is intentionally separate from D1 observation classification.

### `WalletRelationshipEvidence`

```python
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
```

IDs, wallets, and reason codes are non-empty; self-pairs are invalid; time is non-negative; confidence is finite `0..1`. Local `observed_at_unix_ms` is the availability clock.

### `WalletRelationshipPolicy`

```python
@dataclass(frozen=True, slots=True)
class WalletRelationshipPolicy:
    version: str
    direct_evidence_weight: float
    inferred_evidence_weight: float
    relationship_confidence_threshold: float
```

Require `0 <= inferred <= direct <= 1`, direct `> 0`, and threshold in `(0, 1]`. D4 ships no production policy values.

### `WalletRelationshipState`

- `LINKED`: weighted link evidence reaches threshold and weighted independence evidence does not.
- `INDEPENDENT`: weighted independence evidence reaches threshold and weighted link evidence does not.
- `CONFLICTING`: both directions reach threshold.
- `UNKNOWN`: neither direction reaches threshold.

A CONFLICTING pair remains explicit but is still treated as a coordination edge, because strong link evidence exists and D4 must fail conservatively against double-counting.

### `WalletPairRelationship`

```python
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
```

Pairs are canonical lexical unordered pairs. Missing directional evidence remains `None`, not zero.

### `WalletRelationshipCluster`

```python
@dataclass(frozen=True, slots=True)
class WalletRelationshipCluster:
    cluster_index: int
    wallets: tuple[str, ...]
    strongest_internal_link_confidence: float | None
    contains_conflicting_pair: bool
```

Every requested wallet appears in exactly one deterministic connected component, including singletons.

### `WalletIndependenceAssessment`

```python
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
```

`maximum_independent_group_count` is only an upper bound after strong known linkage is collapsed. Five wallets with no relationship evidence may still have a maximum count of five while every pair is UNKNOWN. Downstream code must not relabel that value as five proven independent wallets.

`all_pairs_independent_under_evidence` is true only when every possible pair is explicitly classified INDEPENDENT under the active policy, or fewer than two wallets exist.

## Evidence combination

Each evidence item is adjusted by provenance quality:

```text
adjusted_confidence = confidence * provenance_weight
```

For each canonical pair and each direction, D4 uses the **maximum** adjusted confidence. It never sums confidence and never uses complementary-probability accumulation because relationship clues may be correlated.

Ties are deterministic: DIRECT before INFERRED, then lexical `reason_code`, then lexical `evidence_id`.

## Point-in-time rules

`assess_wallet_independence` has exact signature:

```python
def assess_wallet_independence(
    *,
    wallets: tuple[str, ...],
    evidence: tuple[WalletRelationshipEvidence, ...],
    as_of_unix_ms: int,
    policy: WalletRelationshipPolicy,
) -> WalletIndependenceAssessment:
    ...
```

Rules:

- wallet input is a tuple of distinct non-empty strings,
- output wallet order is lexical regardless of input order,
- evidence input is a tuple of exact evidence objects,
- evidence endpoints must be in the requested wallet set,
- future local evidence is rejected,
- `evidence_id` values are unique within one assessment,
- evidence pair orientation does not affect results,
- zero-wallet and one-wallet assessments are valid.

## Pair enumeration

D4 emits one pair assessment for every possible unordered pair.

For `n` wallets:

```text
total_pair_count = n * (n - 1) // 2
```

Unobserved pairs are UNKNOWN. Pairs with only sub-threshold evidence are also UNKNOWN but retain evidence counts, so they remain distinguishable from unobserved pairs.

Pair-state counts must sum exactly to `total_pair_count`.

## Conservative clustering

A graph edge exists for LINKED or CONFLICTING pairs. Connected components over those edges form coordination clusters.

Transitivity is intentionally conservative: A linked to B and B linked to C places A/B/C in one component even without direct A/C link evidence.

`coordination_cluster_count` counts components with at least two wallets. `maximum_independent_group_count` is the total component count.

D4 never converts UNKNOWN pairs to INDEPENDENT just because they are in separate components.

## Determinism

Results are invariant to wallet input order, evidence input order, and pair orientation. Pair output is lexical by `(wallet_a, wallet_b)`. Cluster members and clusters are lexical and cluster indexes are contiguous from zero.

## Public API extension

D4 appends exactly these **nine** symbols after the sealed D3 fifteen-symbol prefix:

```text
WalletRelationshipDirection
WalletRelationshipEvidenceQuality
WalletRelationshipState
WalletRelationshipEvidence
WalletRelationshipPolicy
WalletPairRelationship
WalletRelationshipCluster
WalletIndependenceAssessment
assess_wallet_independence
```

## TDD / CI strategy

Use one design/plan commit, one combined RED contract, one focused GREEN candidate, concrete repairs only, then one atomic README/verification seal, exact diff audit, and one final exact-head CI. Keep the PR draft and unmerged.

D4 proves conservative relationship-evidence mechanics only. It does not prove that wallet independence predicts profitable trades; D5 and later unseen evaluation own that question.
