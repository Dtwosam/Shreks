# Phase D4 Wallet Independence / Clustering Heuristics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic point-in-time wallet relationship assessments that conservatively collapse strong coordination evidence without treating missing linkage evidence as proof of independence.

**Architecture:** Extend `shreks_brain.wallets` with immutable relationship models and one pure reducer. The reducer enumerates every wallet pair, applies explicit direct/inferred provenance weights, takes the strongest weighted evidence independently in each direction, classifies pair state, then forms deterministic connected components from strong link/conflict edges.

**Tech Stack:** Python 3.12+, stdlib only, immutable dataclasses, `StrEnum`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-d4-wallet-independence-clustering-design.md`

## Global Constraints

- Base exactly sealed D3 head `de9c0e578b99295b65c3593909ed35225e067380`.
- D4 remains pure Python research logic under `shreks_brain.wallets`.
- No provider/RPC/SQLite/wall-clock/transaction-history/graph-service reads inside D4.
- Absence of link evidence is never proof of independence.
- Future local evidence fails closed.
- Relationship confidences are never summed across potentially correlated clues.
- CONFLICTING strong evidence is a conservative coordination edge.
- No production relationship policy or threshold is shipped.
- No wallet ranking, smart-wallet label, D5 feature, B/C trading change, signer, transaction submission, or live-money authority.
- TDD RED -> exact failure -> GREEN.
- Minimize CI churn: one combined RED, one focused GREEN, one final exact-head seal.

---

### Task 1: Combined D4 RED contract

**Files:**
- Create: `python/tests/test_wallet_relationship_models.py`
- Create: `python/tests/test_wallet_independence.py`
- Create: `python/tests/test_wallet_independence_public_api.py`

**Interfaces:**
- Consumes: sealed D3 wallet package only.
- Produces: the exact D4 model, reducer, and public-API contract before production symbols exist.

- [ ] **Step 1: Add model/policy RED tests**

Require exact enum values:

```python
WalletRelationshipDirection.LINKED.value == "LINKED"
WalletRelationshipDirection.INDEPENDENT.value == "INDEPENDENT"
WalletRelationshipEvidenceQuality.DIRECT.value == "DIRECT"
WalletRelationshipEvidenceQuality.INFERRED.value == "INFERRED"
WalletRelationshipState.LINKED.value == "LINKED"
WalletRelationshipState.INDEPENDENT.value == "INDEPENDENT"
WalletRelationshipState.CONFLICTING.value == "CONFLICTING"
WalletRelationshipState.UNKNOWN.value == "UNKNOWN"
```

Pin policy fixture:

```python
WalletRelationshipPolicy(
    version="d4-test-v1",
    direct_evidence_weight=1.0,
    inferred_evidence_weight=0.5,
    relationship_confidence_threshold=0.7,
)
```

Require finite weights, reject bools, enforce `0 <= inferred <= direct <= 1`, direct `> 0`, and threshold in `(0, 1]`.

Pin evidence fixture:

```python
WalletRelationshipEvidence(
    evidence_id="ev-1",
    wallet_a="wallet-a",
    wallet_b="wallet-b",
    observed_at_unix_ms=1_000,
    direction=WalletRelationshipDirection.LINKED,
    evidence_quality=WalletRelationshipEvidenceQuality.DIRECT,
    confidence=0.9,
    reason_code="shared-funding-path",
)
```

Require non-empty strings, distinct endpoints, non-negative time, valid enums, finite `0..1` confidence, and immutable dataclasses.

Validate output-model invariants: canonical pair order, count reconciliation, directional confidence/reason presence together, deterministic cluster indexes/member order, assessment pair/state counts, cluster partition, and maximum group count.

- [ ] **Step 2: Add core pair-state RED tests**

Use `threshold=0.7`, direct weight `1.0`, inferred weight `0.5`.

Require:

1. zero wallets => zero pairs/clusters/groups and `all_pairs_independent_under_evidence=True`;
2. one wallet => one singleton cluster, zero pairs, maximum groups `1`;
3. two wallets with no evidence => UNKNOWN, unobserved pair `1`, maximum groups `2`, all-pairs-independent false;
4. direct LINKED confidence `0.9` => weighted link `0.9`, LINKED, one two-wallet cluster, maximum groups `1`;
5. inferred LINKED raw `0.9` => weighted `0.45`, UNKNOWN under threshold;
6. direct INDEPENDENT `0.8` only => INDEPENDENT with two singleton clusters;
7. strong link and strong independence => CONFLICTING and still one coordination component;
8. sub-threshold evidence is UNKNOWN but `evidence_pair_count=1` and `unobserved_pair_count=0`;
9. missing direction confidence remains `None`, never zero.

- [ ] **Step 3: Add strongest-evidence/determinism RED tests**

Require:

1. multiple evidence items in one direction use maximum adjusted confidence, not sum;
2. two inferred `0.6` link clues remain `0.3`, not `0.6`;
3. exact numeric ties prefer DIRECT provenance, then lexical reason code, then lexical evidence ID for strongest-reason metadata;
4. reversed evidence endpoint order yields the same canonical pair;
5. wallet input order and evidence input order do not change the assessment;
6. duplicate `evidence_id` raises `ValueError`;
7. evidence endpoint outside requested wallets raises `ValueError`;
8. future evidence raises `ValueError`.

- [ ] **Step 4: Add conservative clustering RED tests**

Require:

1. A-B LINKED and B-C LINKED => one `("a", "b", "c")` component even without A-C evidence;
2. A-B CONFLICTING and B-C INDEPENDENT => A/B cluster plus C singleton;
3. pair states remain explicit after transitive clustering;
4. `coordination_cluster_count` counts only multi-wallet components;
5. maximum independent group count equals total component count;
6. all-pairs-independent is true only when every possible pair is explicitly INDEPENDENT under policy.

- [ ] **Step 5: Add exact public API RED test**

Require the sealed D3 fifteen-symbol API as exact prefix followed by exactly:

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

Also pin exact keyword-only reducer parameter order `wallets, evidence, as_of_unix_ms, policy` and reject trading/execution/provider/storage vocabulary from the D4 symbol names.

- [ ] **Step 6: Commit RED tests only**

Expected CI:

- repository safety GREEN,
- Rust/workspace GREEN,
- Python RED during collection because D4 public symbols do not exist.

---

### Task 2: Immutable D4 relationship models

**Files:**
- Create: `python/src/shreks_brain/wallets/relationship_models.py`
- Modify: `python/src/shreks_brain/wallets/__init__.py`
- Test: `python/tests/test_wallet_relationship_models.py`
- Test: `python/tests/test_wallet_independence_public_api.py`

**Interfaces:**
- Produces all eight D4 model/enums before reducer wiring: `WalletRelationshipDirection`, `WalletRelationshipEvidenceQuality`, `WalletRelationshipState`, `WalletRelationshipEvidence`, `WalletRelationshipPolicy`, `WalletPairRelationship`, `WalletRelationshipCluster`, `WalletIndependenceAssessment`.

- [ ] **Step 1: Implement enums and policy**

Use `StrEnum`; implement the exact values in Task 1. Implement frozen/slots policy validation exactly from global constraints.

- [ ] **Step 2: Implement evidence model**

Implement the exact design fields and fail-closed validation. Do not canonicalize endpoints by mutation; the reducer owns canonical pair normalization.

- [ ] **Step 3: Implement pair model**

Require `wallet_a < wallet_b`, non-negative counts, `direct + inferred == evidence_count`, finite optional confidences in `0..1`, confidence/reason-code presence pairs, and `observed_through_unix_ms is None` exactly when `evidence_count == 0`.

Require UNKNOWN for evidence-free pairs. Pair state itself may still be UNKNOWN when sub-threshold evidence exists.

- [ ] **Step 4: Implement cluster model**

Require non-negative contiguous-ready index, non-empty lexical unique wallet tuple, optional finite `0..1` strongest-link confidence, and boolean conflict marker. Singleton clusters must have no internal link confidence and cannot claim internal conflict.

- [ ] **Step 5: Implement assessment model**

Require lexical unique wallet tuple, pair/state count reconciliation, `evidence_pair_count + unobserved_pair_count == total_pair_count`, pair relationships matching every possible pair exactly once in lexical order, clusters forming an exact non-overlapping partition of wallets, cluster indexes contiguous from zero, coordination-cluster count and maximum-group count consistent with clusters, and all-pairs-independent consistent with pair states.

---

### Task 3: Pure D4 pair reducer and clustering

**Files:**
- Create: `python/src/shreks_brain/wallets/independence.py`
- Modify: `python/src/shreks_brain/wallets/__init__.py`
- Test: `python/tests/test_wallet_independence.py`

**Interfaces:**
- Consumes: D4 models/policy.
- Produces: `assess_wallet_independence(...) -> WalletIndependenceAssessment`.

- [ ] **Step 1: Validate and normalize inputs**

Implement exact keyword-only signature from the design. Require tuples, distinct non-empty wallets, exact evidence objects, unique evidence IDs, in-scope evidence endpoints, and no future local evidence. Sort wallet output lexically and canonicalize evidence pair endpoints lexically.

- [ ] **Step 2: Compute directional strongest evidence**

For each evidence row:

```python
weight = (
    policy.direct_evidence_weight
    if row.evidence_quality is WalletRelationshipEvidenceQuality.DIRECT
    else policy.inferred_evidence_weight
)
adjusted = row.confidence * weight
```

Track the strongest LINKED and INDEPENDENT row independently for each pair. Compare candidates by:

```python
(
    adjusted_confidence,
    evidence_quality is WalletRelationshipEvidenceQuality.DIRECT,
    negative_lexical_reason_tie_break_via_explicit_comparison,
    negative_lexical_id_tie_break_via_explicit_comparison,
)
```

Implement ties explicitly so higher adjusted confidence wins; at equality DIRECT wins; then lexically smaller reason code; then lexically smaller evidence ID.

Never add confidences.

- [ ] **Step 3: Enumerate and classify every pair**

For every lexical unordered pair, compute evidence counts, last local observation time, optional strongest directional confidence/reason, and state:

```python
link_strong = link_confidence is not None and link_confidence >= threshold
independent_strong = (
    independence_confidence is not None
    and independence_confidence >= threshold
)

if link_strong and independent_strong:
    state = WalletRelationshipState.CONFLICTING
elif link_strong:
    state = WalletRelationshipState.LINKED
elif independent_strong:
    state = WalletRelationshipState.INDEPENDENT
else:
    state = WalletRelationshipState.UNKNOWN
```

- [ ] **Step 4: Build conservative components**

Use a deterministic union-find over requested wallets. Union LINKED and CONFLICTING pairs only. Build lexical member tuples, sort components by tuple, and assign contiguous indexes.

For each component, inspect internal pair assessments to compute maximum available strong link confidence and whether any internal pair is CONFLICTING. Singletons carry `None`/`False`.

- [ ] **Step 5: Build aggregate assessment**

Compute all pair/state/evidence counts directly from pair objects. `coordination_cluster_count` counts component size > 1. `maximum_independent_group_count = len(clusters)`. `all_pairs_independent_under_evidence` is true iff total pairs is zero or every pair state is INDEPENDENT.

- [ ] **Step 6: Wire public API**

Append the exact nine D4 symbols to the sealed D3 prefix without reordering predecessor names.

- [ ] **Step 7: Run focused + full GREEN**

Run:

```bash
python -m pytest \
  python/tests/test_wallet_relationship_models.py \
  python/tests/test_wallet_independence.py \
  python/tests/test_wallet_independence_public_api.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected all GREEN.

- [ ] **Step 8: Commit implementation only**

Commit:

```text
python/src/shreks_brain/wallets/__init__.py
python/src/shreks_brain/wallets/relationship_models.py
python/src/shreks_brain/wallets/independence.py
```

If a sealed predecessor API-size test conflicts with the intentional D4 extension, repair only that test to preserve its exact predecessor prefix and boundary contract, then rerun full GREEN.

---

### Task 4: Documentation and immutable D4 seal

**Files:**
- Modify: `README.md` append-only
- Replace: `docs/superpowers/plans/2026-08-24-phase-d4-wallet-independence-clustering.md` with verification record

**Interfaces:**
- Consumes verified D4 implementation/CI evidence.
- Produces final documented frozen D4 head.

- [ ] **Step 1: Append README D4 semantics**

Document pair states, maximum-not-proven independent group count, strongest-only confidence combination, point-in-time rules, conservative conflict clustering, and no D5/trading/live authority. README must be additions-only relative to sealed D3.

- [ ] **Step 2: Replace plan with verification record**

Record sealed D3 base, accepted RED commit/run, implementation candidate/repairs, accepted GREEN run/test count, proven integrity properties, final diff expectations, and seal procedure. Do not put final eventual D4 SHA/run in tracked docs.

- [ ] **Step 3: Freeze tracked branch**

After the atomic docs commit, make no further tracked D4 writes.

- [ ] **Step 4: Audit exact D3 -> D4 diff**

Expected core files:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-d4-wallet-independence-clustering.md
docs/superpowers/specs/2026-08-24-phase-d4-wallet-independence-clustering-design.md
python/src/shreks_brain/wallets/__init__.py
python/src/shreks_brain/wallets/relationship_models.py
python/src/shreks_brain/wallets/independence.py
python/tests/test_wallet_relationship_models.py
python/tests/test_wallet_independence.py
python/tests/test_wallet_independence_public_api.py
```

Allow only narrowly documented predecessor public-API compatibility-test maintenance if required. No predecessor production logic may change.

- [ ] **Step 5: Run one fresh exact-head seal CI**

Require repository safety, Python, Rust tests, and workspace metadata all GREEN on the frozen exact head.

- [ ] **Step 6: Update draft PR metadata only**

Record final D4 SHA, exact-head CI run, exact diff audit, and predecessor compatibility repair if any. Leave PR draft and unmerged.
