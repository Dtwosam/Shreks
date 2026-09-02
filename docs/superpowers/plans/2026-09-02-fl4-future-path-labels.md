# FL4 Future-Path Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, point-in-time-safe multi-horizon future-path labels over canonical FastEvents and persist them as versioned derived research evidence.

**Architecture:** A pure `shreks-core` labeler consumes an immutable decision point, strictly ordered future observations, explicit stream coverage, and validated horizons. `shreks-storage` adds migration 16 plus exact/idempotent persistence and bounded future-event reads; no strategy or execution authority consumes these labels in FL4.

**Tech Stack:** Rust, rusqlite/SQLite, existing Fast Lane domain/storage contracts, GitHub Actions canonical four-gate CI.

**Spec:** `docs/superpowers/specs/2026-09-02-fl4-future-path-labels-design.md`

## Global Constraints

- Use canonical `observed_at_unix_ms` as the future-information clock.
- Missing future capture/economic evidence remains explicit unknown; never substitute zero/current constants.
- Complete no-trade and incomplete capture are different outcomes.
- Labels never enter `FastMarketState` or grant strategy/PAPER/signing/submission/LIVE authority.
- Final completion requires exact-head and merged-main Repository safety, Rust, Python, and native ARM64 release verification.

---

### Task 1: Pure future-path labeling contract

**Files:**
- Create: `crates/shreks-core/tests/fast_lane_future_path_labels.rs`
- Create: `crates/shreks-core/src/fast_lane/future_path.rs`
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`

**Interfaces:**
- Consumes: `FastEvent`, `FastEventId`, `FastMarketKey`.
- Produces: `FuturePathDecision`, `FuturePathObservation`, `FuturePathCoverage`, `FuturePathCompleteness`, `FuturePathLabel`, `FuturePathLabelError`, `label_future_paths`, `FUTURE_PATH_LABEL_VERSION`, `DEFAULT_FUTURE_PATH_HORIZONS_MS`.

- [ ] **Step 1: Write the failing test**

Create tests that construct a decision at canonical observation time 1_000 ms and future observations exactly at/inside/outside 250/500/1_000 ms horizons. Assert boundary inclusion, endpoint return, MFE/MAE, peak/trough timing, no-trade vs incomplete status, reversal timing, and optional economic annotations. Add separate assertions that an event with earlier occurrence time but later observation time is future information.

- [ ] **Step 2: Run RED**

Run the canonical Rust workspace test job on the exact commit. Expected: compile failure because FL4 public types/functions do not exist.

- [ ] **Step 3: Implement the minimal pure labeler**

Implement the types and validator described by the spec. Important formulas:

```text
return_bps = (future_price / decision_price - 1) * 10_000
cost_adjusted_return_bps = (future_exit_net_quote / decision_entry_total_quote - 1) * 10_000
```

For each complete horizon, scan the ordered prefix `observed_at_unix_ms <= decision_at + horizon`. Incomplete horizons must not expose path metrics. Complete horizons with zero observations set `no_trade_events=true` and leave endpoint/path metrics unknown.

- [ ] **Step 4: Run GREEN**

Run the exact FL4 core test plus full Rust workspace. Expected: all pass.

- [ ] **Step 5: Commit**

Commit core implementation and tests together after GREEN.

---

### Task 2: Durable versioned FL4 labels

**Files:**
- Create: `crates/shreks-storage/migrations/0016_fast_future_path_labels.sql`
- Create: `crates/shreks-storage/src/future_path_labels.rs`
- Create: `crates/shreks-storage/tests/fl4_future_path_labels.rs`
- Modify: `crates/shreks-storage/src/lib.rs`

**Interfaces:**
- Consumes: `FuturePathDecision`, `FuturePathCoverage`, `FuturePathLabel`.
- Produces: `record_future_path_label`, `future_path_labels_for_decision`, schema version 16.

- [ ] **Step 1: Write the failing storage test**

Assert schema version 16, exact label round-trip, exact duplicate idempotence, conflicting same-key write rejection, nullable optional metrics, and decision FastEvent foreign-key provenance.

- [ ] **Step 2: Run RED**

Run the storage test. Expected: failure because migration/table/API do not exist.

- [ ] **Step 3: Add migration and storage module**

Use primary key `(decision_signature, decision_ordinal, horizon_ms, label_version)`. Keep optional fields nullable. Exact duplicates return `false`; conflicting duplicate content returns `StorageError::InvalidData`. Do not update existing label rows.

- [ ] **Step 4: Run GREEN**

Run storage tests and full Rust workspace.

- [ ] **Step 5: Commit**

Commit migration, module registration, and tests.

---

### Task 3: Canonical future-event retrieval and end-to-end generation

**Files:**
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/future_path_labels.rs`
- Create: `crates/shreks-storage/tests/fl4_future_path_generation.rs`

**Interfaces:**
- Consumes: canonical FastEvent journal and existing conflict-quarantine behavior.
- Produces: bounded future-event retrieval after a decision sequence through a requested canonical observation boundary, plus a storage-backed label-generation helper.

- [ ] **Step 1: Write the failing integration test**

Persist canonical decision/future events including a late-arrival case. Assert generation excludes events at/before the decision observation clock, includes exact horizon boundaries, preserves sequence order, and rejects ambiguous/quarantined canonical markets.

- [ ] **Step 2: Run RED**

Expected: helper/API absent.

- [ ] **Step 3: Implement bounded retrieval and generation**

Use canonical sequence and `observed_at_unix_ms`; never query by transaction occurrence time for label boundaries. Reuse existing replay/conflict checks rather than creating a second source-of-truth policy.

- [ ] **Step 4: Run GREEN**

Run focused integration tests plus full Rust workspace.

- [ ] **Step 5: Commit**

Commit only the bounded FL4 storage integration.

---

### Task 4: FL4 scope/proof closure

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-fl4-future-path-labels-design.md`
- Modify: `docs/superpowers/plans/2026-09-02-fl4-future-path-labels.md`

- [ ] **Step 1: Audit the PR diff**

Confirm no PAPER authority, strategy scoring, signing/submission, LIVE authorization, provider fallback, or deploy/release topology files changed.

- [ ] **Step 2: Run exact-head four-gate CI**

Require all four canonical jobs GREEN on one exact head SHA.

- [ ] **Step 3: Guarded merge**

Merge using the exact reviewed head SHA only.

- [ ] **Step 4: Run fresh merged-main four-gate CI**

Require all four jobs GREEN on the merge commit before declaring FL4 complete.

- [ ] **Step 5: Record proof state**

Update the merged PR body with exact head, exact-head run, merge SHA, merged-main run, scope audit, and the statement that LIVE remains disabled.
