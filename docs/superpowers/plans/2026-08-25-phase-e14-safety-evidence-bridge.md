# Phase E14 Safety Evidence Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and replay enough point-in-time holder, authority, liquidity, and exit-route evidence to construct honest B1 `SafetyInputs` from real observer history without changing the default Phase-A observer or granting execution authority.

**Architecture:** Extend provider-neutral Rust evidence with a complete-holder-distribution snapshot, persist holder and read-only quote evidence in SQLite, expose an explicit opt-in safety evidence collector, then add an isolated Python read-only assembler that combines those rows with sealed E13 market evidence and delegates evaluation to sealed B1. Missing/truncated/provider-failed evidence remains unknown and therefore fail-closed.

**Tech Stack:** Rust workspace (`shreks-core`, `shreks-providers`, `shreks-storage`, `shreks-observer`), `reqwest`, `serde`, `serde_json`, `rusqlite`, Python 3.12, stdlib `sqlite3`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e14-safety-evidence-bridge-design.md`

## Global Constraints

- Base exactly on sealed E13 `892ace744535e81b8bbea543a1d47ef46a2173c7`.
- Do not modify B1 safety thresholds, reason ordering, or precedence.
- Do not modify B2 feature arithmetic.
- Do not add Jupiter to `free_observe_provider_plan` or `build_free_observer`.
- Quote failures remain unknown; only a successful normalized quote with `route_available=false` is explicit unavailable evidence.
- Holder concentration is usable only when the holder scan is complete.
- Creator concentration remains `None` until proven by a separate evidence path.
- No signing, submission, registry mutation, promotion, live-mode enablement, or Phase-F authority.
- Every task follows RED -> exact failure inspection -> minimal GREEN -> full repository CI.
- Keep the PR draft/unmerged; final seal is one verification-document-only commit after the immutable behavior head.

---

### Task 1: Provider-neutral holder distribution and Helius complete scan

**Files:**
- Modify: `crates/shreks-core/src/lib.rs`
- Modify: `crates/shreks-providers/src/lib.rs`
- Modify: `crates/shreks-providers/src/helius.rs`
- Create/Test: `crates/shreks-providers/tests/distribution.rs`

**Interfaces:**
- Produces `TokenDistributionRequest { mint, page_size, max_pages }` with strict positive bounds.
- Produces `TokenHolderDistribution` containing provider, mint, observed timestamp, account/owner/page counts, completeness, total raw balance, largest owner/raw balance, and optional complete concentration percentage.
- Produces `DistributionDataProvider::token_holder_distribution(&TokenDistributionRequest)`.
- Helius aggregates token-account raw balances by owner across page-number `getTokenAccounts` pagination.

- [ ] **Step 1: Write RED Rust tests for the normalized distribution contract and pure Helius page boundary.**

Tests must prove:

```rust
assert!(TokenDistributionRequest::new("Mint111", 1000, 10).is_ok());
assert!(TokenDistributionRequest::new("", 1000, 10).is_err());
assert!(TokenDistributionRequest::new("Mint111", 0, 10).is_err());
assert!(TokenDistributionRequest::new("Mint111", 1000, 0).is_err());
```

and result invariants: incomplete scans expose `top_holder_concentration_pct=None`; complete positive-balance scans expose a finite concentration in `[0,100]`; raw totals remain `u64`.

The Helius request helper contract is:

```rust
get_token_accounts_request(&request, page_number)
```

and must encode JSON-RPC `method="getTokenAccounts"`, exact mint, exact positive `page`, exact `limit`, and `displayOptions.showZeroBalance=false`.

The parser/aggregator test fixtures must prove:

- two token accounts owned by the same wallet are aggregated;
- a different wallet with the largest aggregate becomes `largest_owner`;
- zero-balance accounts do not change concentration;
- response mint mismatch fails;
- malformed raw amount fails;
- page-number continuation is deterministic;
- a short/empty page proves completion;
- reaching `max_pages` after a full page returns `complete=false` and no concentration;
- local observation time is retained.

- [ ] **Step 2: Commit RED and verify full CI fails only because the new types/trait/helpers are absent.**

- [ ] **Step 3: Add minimal core types and provider trait.**

Use raw `u64` token amounts in Rust. Do not use UI floating amounts for aggregation. Percentage calculation occurs only for a complete scan with positive total raw balance and validates finite `[0,100]` output.

- [ ] **Step 4: Implement Helius `getTokenAccounts` page parsing and owner aggregation.**

A page shorter than `page_size`, or an empty page, proves terminal completion. A full page at the `max_pages` budget leaves completeness unproven and must return `complete=false` with no concentration. Reuse the existing redacted `post_rpc` transport path so API keys cannot leak to errors/logs.

- [ ] **Step 5: Run full CI and commit GREEN.**

Expected: all existing Rust/Python/safety lanes GREEN plus the new distribution tests.

---

### Task 2: Append-only holder and quote persistence

**Files:**
- Create: `crates/shreks-storage/migrations/0008_safety_evidence.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: storage Rust tests

**Interfaces:**
- Produces `ShreksDb::insert_holder_distribution(candidate_id, &TokenHolderDistribution)`.
- Produces `ShreksDb::insert_exit_quote_snapshot(candidate_id, probe_policy_version, &QuoteSnapshot)`.
- Both operations are idempotent on semantic observation identity.

- [ ] **Step 1: Write RED storage migration/schema tests.**

Require schema version 8 and exact new tables/indexes. Test reopening a version-7 fixture migrates without altering existing rows.

- [ ] **Step 2: Write RED persistence tests.**

Holder tests prove total raw balance/largest-owner raw balance survive SQLite as decimal text, incomplete rows persist with null concentration, complete rows preserve concentration, duplicates do not multiply.

Quote tests prove exact input/output mints, input/output/minimum raw amounts, slippage, route availability, price-impact text, canonical route-label JSON, quote timestamp, and non-empty `probe_policy_version` survive restart. Invalid candidate ids/blank probe version/invalid evidence fail closed.

- [ ] **Step 3: Commit RED and inspect exact CI failure.**

- [ ] **Step 4: Add migration 0008 and storage methods.**

Use foreign keys to `token_candidates`, candidate/time indexes, and semantic unique constraints. Never persist signed transactions or provider credentials.

- [ ] **Step 5: Run full CI and commit GREEN.**

---

### Task 3: Explicit opt-in Rust safety evidence collector

**Files:**
- Create: `crates/shreks-observer/src/safety_evidence.rs`
- Modify: `crates/shreks-observer/src/lib.rs`
- Test: observer Rust tests

**Interfaces:**
- Produces `SafetyEvidenceProbe { probe_policy_version, distribution_request, quote_request }`.
- Produces `SafetyEvidenceCycleReport` with successful holder/quote persistence counts and structured provider-failure counts.
- Produces `SafetyEvidenceCollector` constructed explicitly from `ShreksDb`, distribution providers, and quote providers.
- `collect_candidate(candidate_id, candidate_mint, &SafetyEvidenceProbe)` is read-only with respect to providers and write-only to normalized evidence tables.

- [ ] **Step 1: Write RED collector tests with deterministic provider doubles.**

Prove:

- exact candidate mint must match both distribution request and quote input mint;
- successful distribution and quote each persist once;
- provider failures do not synthesize evidence rows;
- successful `route_available=false` quote is persisted as explicit evidence;
- mismatched provider result identity is rejected and not persisted;
- duplicate collection is idempotent;
- no trade intent/signature/submission type appears in the public API.

- [ ] **Step 2: Add a regression test that `free_observe_provider_plan` still excludes Jupiter and `build_free_observer` still has no safety collector by default.**

- [ ] **Step 3: Commit RED and inspect CI.**

- [ ] **Step 4: Implement the isolated collector.**

Do not change normal `Observer::run_cycle`. Do not add quote calls to Phase-A default runtime. The collector is invoked only by an explicit later proof/campaign caller.

- [ ] **Step 5: Run full CI and commit GREEN.**

---

### Task 4: Python read-only safety evidence assembler

**Files:**
- Create: `python/src/shreks_brain/observer_safety/models.py`
- Create: `python/src/shreks_brain/observer_safety/store.py`
- Create: `python/src/shreks_brain/observer_safety/assembler.py`
- Create later in Task 5: `python/src/shreks_brain/observer_safety/__init__.py`
- Create: `python/tests/test_observer_safety_models.py`
- Create: `python/tests/test_observer_safety_store.py`
- Create: `python/tests/test_observer_safety_assembler.py`

**Interfaces:**
- `ObserverSafetyProbeIdentity` records exact probe policy version, output mint, raw input amount, taker, and slippage.
- `ObserverSafetyEvidenceStore(path)` opens SQLite read-only and validates required columns.
- Store readers return latest mint/distribution/quote evidence at or before `as_of` with exact candidate/probe attribution.
- `build_safety_inputs(window, evidence_store, probe_identity, global_risk_halt)` returns sealed B1 `SafetyInputs`.
- `assess_observer_safety(...)` delegates to sealed `assess_safety`.

- [ ] **Step 1: Write RED immutable model/store tests.**

Prove missing database does not get created, missing required tables/columns fail closed, additive future columns are allowed, timestamps after `as_of` are never selected, incomplete holder rows expose concentration as `None`, and quote lookup requires exact probe identity.

- [ ] **Step 2: Commit RED, verify the missing package/store failure, then implement models/store only.**

- [ ] **Step 3: Run full CI and commit the first GREEN for Task 4.**

- [ ] **Step 4: Add RED assembler tests.**

A clean case must produce exactly:

```python
SafetyInputs(
    as_of_unix_ms=window.as_of_unix_ms,
    mint_authority_active=False,
    freeze_authority_active=False,
    liquidity_usd=window.current.liquidity_usd,
    top_holder_concentration_pct=<persisted complete value>,
    creator_concentration_pct=None,
    exit_quote_available=True,
    exit_price_impact_pct=<matching quote value>,
    execution_trap_detected=False,
    critical_data_observed_at_unix_ms=<oldest used evidence timestamp>,
    critical_data_contradictory=False,
    global_risk_halt=<explicit caller value>,
)
```

Also prove:

- no mint row => authorities `None` => B1 `INCOMPLETE` under default required policy;
- incomplete/no holder row => concentration `None` => `INCOMPLETE`;
- no exact matching quote => exit quote `None` => `INCOMPLETE`;
- explicit route-unavailable quote => `REJECT`;
- active authority => `REJECT`;
- stale oldest critical evidence => B1 `INCOMPLETE`;
- future evidence is invisible;
- caller `global_risk_halt=True` => `REJECT`;
- creator concentration stays `None` and is never guessed.

- [ ] **Step 5: Implement minimal assembler and evaluator wrapper.**

Import B1 public APIs; do not duplicate threshold logic. Derive authority booleans only from presence/absence of authority addresses in a real mint-state row. Parse persisted quote price impact strictly into percentage points; malformed/non-finite values fail closed.

- [ ] **Step 6: Run full CI and commit GREEN.**

---

### Task 5: Public API, authority audit, verification seal

**Files:**
- Create: `python/src/shreks_brain/observer_safety/__init__.py`
- Create: `python/tests/test_observer_safety_public_api.py`
- Replace plan with verification record: `docs/superpowers/plans/2026-08-25-phase-e14-safety-evidence-bridge.md`

**Interfaces:**
- Export only evidence/read/assembly types and functions.
- Public imports must not load paper execution, registry promotion, signing, submission, or live-execution packages.

- [ ] **Step 1: Write RED exact-`__all__` and authority-firewall tests.**

- [ ] **Step 2: Commit RED, verify exact failure, add export-only `__init__.py`, run full CI, and freeze the resulting SHA as E14 behavior head.**

- [ ] **Step 3: Compare sealed E13 -> E14 behavior head.**

Audit every changed file. Expected scope is E14 docs/tests; provider-neutral core distribution types; Helius distribution adapter; storage migration/persistence; isolated observer safety collector; isolated Python `observer_safety` package. No B1 evaluator changes, no B2 arithmetic changes, no paper/live executor changes, no registry/promotion changes.

- [ ] **Step 4: Replace this plan with a verification record containing all RED/GREEN anchors, CI run ids/counts, exact public API, scope audit, and authority statement.**

- [ ] **Step 5: Commit only that document as `docs: seal E14 verification record`.**

- [ ] **Step 6: Verify behavior-head -> seal is exactly one commit / one file, then require fresh exact-seal full CI GREEN.**

- [ ] **Step 7: Update the stacked draft PR body with immutable behavior/seal metadata and leave it draft/unmerged.**
