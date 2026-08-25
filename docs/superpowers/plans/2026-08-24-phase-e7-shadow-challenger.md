# Phase E7 Shadow Challenger Verification Record

## Scope

Phase E7 adds a deterministic, shadow-only challenger path under `shreks_brain.shadow`.

It validates frozen E6/E3 provenance, evaluates a registered model-backed challenger against an exact D6 point-in-time row, preserves deterministic safety/setup/regime gates, records baseline-versus-challenger divergence, and persists tamper-evident shadow decision evidence for later E8 comparison.

E7 does **not** execute trades, create trade intents, mutate registry status, promote a challenger, choose economic promotion thresholds, enable live money, sign transactions, or submit transactions.

Schema: `e7-shadow-v1`.

## Frozen base

- Phase E6 seal: `5933416fa7136ee7594f89baf97da469bedac171`
- E7 branch: `feat/phase-e7-shadow-challenger`
- PR: #31
- Design: `docs/superpowers/specs/2026-08-24-phase-e7-shadow-challenger-design.md`

## Implemented contract

Public E7 surface:

1. `SHADOW_CHALLENGER_SCHEMA_VERSION`
2. `ShadowDecisionPolicy`
3. `ShadowReasonCode`
4. `ShadowDecisionRecord`
5. `ShadowEvidenceLedger`
6. `ShadowEvidenceStore`
7. `evaluate_shadow_challenger`

### Decision semantics

The caller must supply an explicit, versioned `enter_min_probability`; E7 ships no production probability threshold default.

A registered challenger is accepted only when its E6 registry provenance aligns with the supplied E3 model. The D6 row must have the exact sealed physical shape/schema and must not predate candidate registration.

Decision precedence is fail-closed:

1. safety not `PASS` -> `REJECT`;
2. setup `BLOCKED` -> `REJECT`;
3. regime `DEAD` -> `REJECT`;
4. setup `WATCH` -> `WATCH`;
5. eligible setup with probability below threshold -> `WATCH`;
6. eligible setup with probability at/above threshold -> shadow `ENTER`.

The incumbent baseline action is preserved as audit evidence but is not allowed to suppress a challenger-only shadow `ENTER` when all deterministic gates pass. This allows later measurement of genuine challenger divergence without letting model probability override safety.

### Point-in-time firewall

The engine reuses sealed E3 pure-Python inference. Decision-feature fingerprints project only `RESEARCH_FEATURE_COLUMNS`.

Tests prove that radically mutating D6 future-label columns does not change:

- positive probability;
- challenger action;
- reason;
- decision-feature fingerprint;
- record fingerprint.

No future label is used as shadow decision evidence.

### Durable evidence

`ShadowEvidenceStore` persists canonical JSON with exact schema/field validation, independently recomputes record and ledger fingerprints on load, uses atomic fsync + replace writes, and rejects corrupt, unknown, forged, conflicting, or tampered evidence.

Decision identity is:

`(candidate_version, candidate_mint, as_of_unix_ms, shadow_policy_version)`.

Identical re-appends are byte-for-byte idempotent. Same-identity/different-content records fail closed. The public API exposes no deletion/history-rewrite path.

## TDD evidence

### Task 1 — contract and provenance firewall

**RED**

- head: `087ade04508c39ec7a9318d4fa3f4c672789e8b4`
- CI: `32787507532`
- expected Python result: two collection errors because `shreks_brain.shadow` did not yet exist
- Rust/workspace: GREEN
- repository safety: GREEN

**GREEN**

- head: `5f7f46a99c7498f9f524da0d303a21b58c93fa97`
- CI: `32787776091`
- Python: `1849 passed in 5.41s`
- Rust/workspace: GREEN
- repository safety: GREEN

A test-fixture correction was required before the final Task 1 green: the duplicate-identity fixture originally changed the reason while leaving probability/threshold values internally inconsistent, so model validation correctly rejected the forged record before ledger identity validation. The fixture was corrected to differ on valid material; production semantic validation was not weakened.

### Task 2 — pure shadow decision engine and leakage firewall

**RED**

- head: `a08604375181077ac8a4a6013832f14938d1b546`
- CI: `32788085609`
- expected Python result: two collection errors for missing `evaluate_shadow_challenger`
- repository safety: GREEN
- Rust/workspace: unaffected/green

**GREEN**

- head: `1ea77580e5b68342e4ee4f61fe12f19c6d319ca3`
- CI: `32788254452`
- Python: `1865 passed in 6.14s`
- Rust/workspace: GREEN
- repository safety: GREEN

This gate includes real E3 model inference, real E6 model-backed registration provenance, exact D6 physical rows, hard-gate precedence, baseline `WATCH` -> challenger shadow `ENTER` divergence, deterministic fingerprints, and future-label invariance.

### Task 3 — durable canonical shadow evidence store

**RED**

- head: `f633760cde66ca4ce6c832b941bbf68181129dbd`
- CI: `32788390778`
- expected Python result: one collection error for missing `ShadowEvidenceStore`
- repository safety: GREEN
- Rust/workspace: unaffected

**GREEN / behavior head**

- head: `92de4e9338056923a27a2a9b687e733110ef884c`
- CI: `32788513517`
- Python: `1873 passed in 5.91s`
- Rust/workspace: GREEN
- repository safety: GREEN

This gate covers canonical ordering, restart round-trip, parent creation, byte-for-byte idempotency, forged-record rejection, conflicting-identity rejection, corrupt/unknown/tampered state rejection, top-level ledger hash tampering, atomic writes, and absence of history-rewrite APIs.

## Cumulative scope audit

Comparison:

- base: frozen E6 `5933416fa7136ee7594f89baf97da469bedac171`
- behavior head: `92de4e9338056923a27a2a9b687e733110ef884c`

Result: 13 changed files, all in the allowed E7 scope:

- E7 design document;
- this E7 plan/verification document;
- `python/src/shreks_brain/shadow/__init__.py`;
- `python/src/shreks_brain/shadow/codec.py`;
- `python/src/shreks_brain/shadow/engine.py`;
- `python/src/shreks_brain/shadow/fingerprint.py`;
- `python/src/shreks_brain/shadow/models.py`;
- `python/src/shreks_brain/shadow/store.py`;
- `python/tests/test_shadow_engine.py`;
- `python/tests/test_shadow_leakage.py`;
- `python/tests/test_shadow_models.py`;
- `python/tests/test_shadow_public_api.py`;
- `python/tests/test_shadow_store.py`.

No existing E3 inference, E6 registry, safety/setup/decision/risk/paper execution, Rust observer/executor, or live-money path changed.

## Seal boundary

The behavior head is `92de4e9338056923a27a2a9b687e733110ef884c`.

The only permitted change after that head is this documentation verification record. The final seal is valid only if behavior-head -> seal-candidate comparison is docs-only and exact-head CI passes Python, Rust/workspace, and repository safety.

Final immutable seal SHA and final CI run ID are recorded on PR #31 after that exact-head gate. No tracked changes are allowed after the seal.

## Profitability and promotion boundary

E7 provides operational shadow evidence. It does not prove positive expectancy, profitability, or superiority over the incumbent, and it does not promote any model.

E8 owns explicit promotion-rule evaluation using unseen/post-cost evidence and must preserve the rule that challengers never self-promote. Live money remains disabled.