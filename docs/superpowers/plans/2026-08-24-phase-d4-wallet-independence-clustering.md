# Phase D4 Wallet Independence / Clustering Heuristics Verification Record

**Base:** sealed D3 head `de9c0e578b99295b65c3593909ed35225e067380`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-d4-wallet-independence-clustering-design.md`.

## Implemented scope

D4 adds only deterministic, point-in-time wallet relationship research mechanics in Python:

- immutable relationship direction, evidence-quality, pair-state, evidence, policy, pair, cluster, and assessment models,
- exact nine-symbol public API extension after the sealed D3 fifteen-symbol prefix,
- exact local evidence availability checks and future-evidence rejection,
- canonical lexical unordered wallet pairs,
- DIRECT/INFERRED provenance weighting through caller-supplied versioned policy,
- strongest-only directional confidence aggregation rather than summing potentially correlated clues,
- deterministic DIRECT/lexical reason/evidence-id tie breaking,
- explicit `LINKED`, `INDEPENDENT`, `CONFLICTING`, and `UNKNOWN` pair states,
- deterministic conservative connected components over `LINKED` and `CONFLICTING` edges,
- explicit singleton components and a maximum independent-group upper bound,
- all-pairs-independent truth only when every possible pair is explicitly `INDEPENDENT` under the active evidence/policy.

D4 performs no provider/RPC/SQLite/wall-clock/balance/transaction-history/graph-service reads and adds no ownership attribution, wallet ranking, smart-wallet label, D5 feature, B/C trading-policy change, signer, transaction submission, or live-money authority.

## TDD evidence

### RED

The combined D4 contract was committed as `ffbe376751fa84748774d2d52ebc8cb9dd55a1fa` after the design/plan commit `83712799d3906f2393a0f11d002a3adf88123b82`.

CI `32743336064` behaved exactly as intended:

- repository safety: GREEN,
- Rust tests and workspace metadata: GREEN,
- Python: RED during collection because the D4 public relationship symbols did not yet exist.

The RED commit also proactively changed the sealed D3 public-API guard from exact package size to an exact fifteen-symbol predecessor prefix. That test-only maintenance preserves D3 symbol order/boundary while allowing the intentional D4 API extension; no D3 production code changed.

### GREEN

Implementation commit `340be80fbb19bd8dcdeabf8a17421851596150ff` added only:

- `python/src/shreks_brain/wallets/relationship_models.py`,
- `python/src/shreks_brain/wallets/independence.py`,
- the nine-symbol extension in `python/src/shreks_brain/wallets/__init__.py`.

CI `32744072083` is GREEN across repository safety, Python tests (`1553 passed`), Rust tests, and workspace metadata validation. No implementation repair commit was required.

## Integrity properties proven

- no evidence remains `UNKNOWN`, never silently `INDEPENDENT`,
- missing directional confidence remains `None`, never zero,
- inferred relationship evidence can be down-weighted without changing its raw provenance,
- multiple potentially correlated clues cannot manufacture confidence by summation,
- exact directional ties resolve deterministically by DIRECT provenance, then lexical reason code, then lexical evidence ID,
- reversed pair orientation and shuffled wallet/evidence input do not change the assessment,
- duplicate evidence IDs, out-of-scope endpoints, duplicate requested wallets, and future evidence fail closed,
- strong link plus strong independence remains explicit `CONFLICTING`,
- `CONFLICTING` still forms a conservative coordination edge so strong linkage cannot be double-counted,
- transitive LINKED/CONFLICTING connectivity collapses coordinated components without rewriting unobserved transitive pairs,
- `maximum_independent_group_count` is component count only and is not proof that those groups are actually independent,
- `all_pairs_independent_under_evidence` is true only when every possible pair is explicitly independent, or fewer than two wallets exist.

## Scope boundaries

D4 does not claim common ownership, beneficial ownership, control, identity, or profitability. Relationship evidence remains caller-supplied and heuristic. The layer does not feed setup/score/decision/risk logic and does not authorize execution.

D5 must decide whether and how wallet quality plus D4 independence evidence becomes a wallet-derived research feature, and later unseen evaluation must prove whether that feature adds post-cost value.

## Final seal procedure

The final D4 documentation commit appends README semantics and replaces this implementation plan with this verification record. After that commit, tracked D4 content is frozen. The sealed head must then pass an exact D3 -> D4 diff audit and one fresh exact-head CI run with repository safety, Python, Rust, and workspace metadata all GREEN. The eventual final D4 SHA/run are recorded only in draft PR metadata, not back-written into tracked docs.
