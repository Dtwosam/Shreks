# Phase A10 Adaptive Path Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** COMPLETE — implemented and regression-verified on `feat/phase-a-foundation`.

**Goal:** Persist budget-aware market observations between the official 1m/5m/15m/30m/1h/4h/24h outcome checkpoints so Shreks can study the path that led to each outcome.

**Architecture:** Add one restart-safe lifecycle sampling schedule per candidate in SQLite schema v5. The observer keeps one shared 16-candidate revisit budget per full cycle: official checkpoint-due candidates are selected first, then adaptive-only candidates fill unused capacity, and candidate IDs are deduplicated before provider calls. Adaptive observations reuse existing paced `MarketDataProvider` calls and normalized `market_snapshots`; schedule state advances only when at least one valid snapshot was actually persisted.

**Tech Stack:** Rust workspace, rusqlite 0.40.2 bundled SQLite/WAL, Tokio, existing `shreks-storage`, `shreks-observer`, `shreks-providers`, and GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-adaptive-path-observation-amendment.md`

## Global Constraints

- Solana only for V1.
- Free data/API/RPC sources only; no paid fallback.
- Official A9 checkpoints remain unchanged.
- In-between evidence uses existing normalized `market_snapshots`.
- V0 cadence is lifecycle-based: 30s, 60s, 120s, 300s, 900s, 3600s by approved age bands; stop at 24h.
- Revisit budget is 16 distinct existing candidates per full observer cycle, with official checkpoints first.
- Adaptive sampling never performs chain-state calls solely because a path sample is due.
- Realtime Pump wake-ups remain durable-write-only between full cycles.
- A failed/no-data market pass does not advance the adaptive schedule.
- Delayed samples advance from actual sample time; no catch-up burst.
- Single SQLite writer remains the observer.
- Live trading remains disabled.

## File map

- Create `crates/shreks-storage/migrations/0005_adaptive_path_sampling.sql` — durable one-row-per-candidate adaptive schedule.
- Create `crates/shreks-storage/src/path_sampling.rs` — cadence calculation, typed schedule records, due queries, advancement.
- Modify `crates/shreks-storage/src/lib.rs` — register migration/module and re-export schedule types/constants.
- Create `crates/shreks-storage/tests/path_sampling.rs` — schema/cadence/restart/advancement tests.
- Modify `crates/shreks-observer/src/lib.rs` — schedule candidates and merge checkpoint/adaptive revisit work.
- Create `crates/shreks-observer/tests/path_sampling.rs` — bounded orchestration, dedupe, pacing, no-chain, failure semantics.
- Add adaptive runtime/hardening regressions under `crates/shreks-observer/tests/` — prove realtime wake does not trigger path sampling and restart does not create catch-up bursts.
- Modify `README.md` — document path sampling semantics after implementation.

---

### Task 1: Schema v5 and deterministic lifecycle cadence

**Files:**
- Create: `crates/shreks-storage/migrations/0005_adaptive_path_sampling.sql`
- Create: `crates/shreks-storage/src/path_sampling.rs`
- Modify: `crates/shreks-storage/src/lib.rs`
- Create: `crates/shreks-storage/tests/path_sampling.rs`

**Interfaces:**
- Consumes: durable `token_candidates(id, discovered_at_unix_ms)`.
- Produces:
  - `PATH_CADENCE_VERSION: &str = "lifecycle_v0"`
  - `PathSamplingStatus::{Active, Completed}`
  - `PathSamplingRecord`
  - `DuePathSample { candidate_id, mint, due_at_unix_ms }`
  - `path_sampling_interval_seconds(age_ms: i64) -> Option<u32>`
  - `ShreksDb::ensure_path_sampling(candidate_id, discovered_at_unix_ms)`
  - `ShreksDb::path_sampling(candidate_id)`
  - `ShreksDb::due_path_samples(now_unix_ms, limit)`
  - `ShreksDb::advance_path_sampling(candidate_id, sampled_at_unix_ms)`

- [x] **Step 1: Write the failing storage tests**

Tests assert schema version 5 and exact cadence boundaries:

```rust
assert_eq!(path_sampling_interval_seconds(0), Some(30));
assert_eq!(path_sampling_interval_seconds(299_999), Some(30));
assert_eq!(path_sampling_interval_seconds(300_000), Some(60));
assert_eq!(path_sampling_interval_seconds(900_000), Some(120));
assert_eq!(path_sampling_interval_seconds(1_800_000), Some(300));
assert_eq!(path_sampling_interval_seconds(3_600_000), Some(900));
assert_eq!(path_sampling_interval_seconds(14_400_000), Some(3_600));
assert_eq!(path_sampling_interval_seconds(86_400_000), None);
```

Also proven:
- first due = discovery + 30_000ms,
- `ensure_path_sampling` is idempotent across reopen,
- due rows are deterministic by `next_due_at_unix_ms, candidate_id`,
- zero limit returns empty,
- timestamp overflow returns `StorageError::InvalidData` without partial state.

- [x] **Step 2: Run full CI and verify RED**

Verified: Rust failed only on missing schema-v5/path-sampling contracts while Python and repository safety remained green.

- [x] **Step 3: Implement migration and typed cadence module**

Migration shape:

```sql
CREATE TABLE candidate_path_sampling (
    candidate_id INTEGER PRIMARY KEY REFERENCES token_candidates(id) ON DELETE CASCADE,
    next_due_at_unix_ms INTEGER,
    last_sample_at_unix_ms INTEGER,
    sample_count INTEGER NOT NULL DEFAULT 0 CHECK(sample_count >= 0),
    status TEXT NOT NULL CHECK(status IN ('active', 'completed')),
    cadence_version TEXT NOT NULL
);
CREATE INDEX idx_candidate_path_sampling_due
ON candidate_path_sampling(status, next_due_at_unix_ms, candidate_id);
```

`path_sampling_interval_seconds` uses the exact spec boundaries. `ensure_path_sampling` precomputes checked first due time before insert.

- [x] **Step 4: Run full CI and verify GREEN**

Verified Rust/Python/repository-safety all pass.

- [x] **Step 5: Commit**

Implemented across the A10 storage commits.

---

### Task 2: Restart-safe schedule advancement without catch-up bursts

**Files:**
- Modify: `crates/shreks-storage/src/path_sampling.rs`
- Extend: `crates/shreks-storage/tests/path_sampling.rs`

**Interfaces:**
- Consumes: `advance_path_sampling(candidate_id, sampled_at_unix_ms)` from Task 1.
- Produces: schedule advancement based on candidate age at actual sample time.

- [x] **Step 1: Write failing advancement tests**

Proven:
- sampling at age 40s makes next due `sampled_at + 30s`, not discovery + missed intervals,
- sampling at age 6m advances by 60s,
- lifecycle stops at 24h,
- `sample_count` increments exactly once per successful advancement,
- completed schedules cannot become active again,
- advancement survives database restart.

- [x] **Step 2: Verify RED**

Verified missing advancement behavior only.

- [x] **Step 3: Implement transactional advancement**

Implemented with candidate discovery time + current schedule loaded transactionally, checked timestamp arithmetic, active-row-only update, and terminal lifecycle handling.

- [x] **Step 4: Verify GREEN**

Full CI passed.

- [x] **Step 5: Commit**

Implemented as `feat: advance adaptive path samples safely` and supporting storage commits.

---

### Task 3: Schedule every durable candidate

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Extend: `crates/shreks-observer/tests/cycle.rs`
- Extend: `crates/shreks-observer/tests/pump_verification.rs`

**Interfaces:**
- Consumes: candidate IDs returned by `ShreksDb::upsert_candidate`.
- Produces: one idempotent active path-sampling row for both generic discoveries and verified Pump creations.

- [x] **Step 1: Write failing observer tests**

Generic discovery, verified Pump creation, and rejected Pump behavior are covered.

- [x] **Step 2: Verify RED**

Verified candidate/outcome records existed while the adaptive schedule was absent.

- [x] **Step 3: Schedule immediately after candidate upsert**

Both durable candidate-creation paths now call `ensure_path_sampling` after official outcome scheduling.

- [x] **Step 4: Verify GREEN**

Full CI passed.

- [x] **Step 5: Commit**

Implemented as `feat: schedule path observation for candidates`.

---

### Task 4: Shared checkpoint-first revisit budget

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/tests/path_sampling.rs`

**Interfaces:**
- Consumes: `due_outcome_checkpoints`, `due_path_samples`, existing candidate-ID dedupe and market provider pacing.
- Produces: a single ordered revisit list of at most 16 distinct existing candidates.

- [x] **Step 1: Write failing priority/budget tests**

Proven:
- 16 official due candidates -> zero adaptive-only candidates,
- 7 official due candidates + 20 adaptive due candidates -> 7 checkpoint candidates then up to 9 adaptive-only candidates,
- candidate due for both appears once,
- newly rediscovered path-due candidate is observed once through normal processing,
- adaptive-only revisit causes zero chain calls.

- [x] **Step 2: Verify RED**

Verified adaptive due rows were ignored before implementation.

- [x] **Step 3: Implement shared revisit selection**

Implemented `MARKET_REVISIT_CANDIDATE_LIMIT = 16` and checkpoint-first `RevisitCandidate` selection with deterministic dedupe and adaptive spare-capacity fill.

- [x] **Step 4: Verify GREEN**

Full CI passed.

- [x] **Step 5: Commit**

Implemented as `feat: prioritize checkpoint and path revisits`.

---

### Task 5: Advance schedule only after real adaptive evidence

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Extend adaptive observer tests.

**Interfaces:**
- Consumes: existing `observe_market_data` snapshot persistence and `advance_path_sampling`.
- Produces: adaptive schedule advancement iff at least one new durable snapshot was stored during that path-due pass.

- [x] **Step 1: Write failing evidence/failure tests**

Proven:
- path-due candidate with one valid snapshot advances and increments `sample_count`,
- provider error with no valid snapshot leaves schedule due,
- empty pair response leaves schedule due,
- invalid/mismatched snapshots leave schedule due,
- a duplicate snapshot ignored by SQLite is not treated as new evidence,
- one provider failing while another stores a valid snapshot advances once,
- adaptive revisit reuses DEX Screener pacing,
- official checkpoint finalization still occurs from the same market pass,
- rediscovered due candidates can advance from their single normal market pass,
- no rug/dead/exitability values are fabricated by adaptive sampling.

- [x] **Step 2: Verify RED**

Verified positive evidence stored while schedule remained at `sample_count = 0`; negative/no-data cases already stayed due.

- [x] **Step 3: Return stored-snapshot count from market observation**

The observer now counts only newly inserted normalized snapshots as durable evidence. `insert_market_snapshot_if_new` distinguishes a fresh row from an idempotent duplicate. Path sampling advances at most once per candidate pass and only when new evidence count is positive.

- [x] **Step 4: Verify GREEN**

Full CI passed.

- [x] **Step 5: Commit**

Implemented across `feat: report new market evidence inserts` and `feat: advance adaptive sampling on durable evidence`.

---

### Task 6: Realtime isolation, restart regression, and operator docs

**Files:**
- Add adaptive runtime/hardening regression coverage under `crates/shreks-observer/tests/`.
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-a10-adaptive-path-observation.md`

**Interfaces:**
- Consumes: completed adaptive sampling path.
- Produces: regression evidence and operator-visible semantics.

- [x] **Step 1: Add realtime isolation regression**

With a one-hour full-cycle interval and an adaptive-due candidate, a Pump realtime signal is durably written without causing an adaptive market-provider call between cycles.

- [x] **Step 2: Add restart/backlog regression**

Regression proves:
- the same schedule row survives reopen,
- exactly one sample-count increment occurs,
- next due is based on actual sample time,
- no historical missed intervals are replayed,
- an immediate second restart/cycle does not issue another market request.

- [x] **Step 3: Verify regressions**

Existing architecture passed both regressions without a production change; no artificial change was introduced.

- [x] **Step 4: Update README**

README now documents lifecycle cadence, checkpoint-first shared budget, best-effort semantics, evidence-gated advancement, restart/no-catch-up behavior, realtime isolation, and reuse of ordinary `market_snapshots` for path/MFE/MAE research.

- [ ] **Step 5: Run final full CI**

Expected: Rust tests, Python tests, workspace metadata validation, and repository safety all pass.

- [ ] **Step 6: Commit**

Final documentation completion is committed once Step 5 is verified.

---

## Self-review

- **Spec coverage:** exact lifecycle cadence, 24h stop, shared 16-candidate revisit budget, checkpoint priority, candidate dedupe, market-only adaptive sampling, restart durability, no catch-up bursts, and no-data failure semantics each have tests.
- **Data model:** no duplicate market evidence table is introduced; path sampling reuses `market_snapshots` and therefore automatically feeds existing MFE/MAE computation.
- **Free-source discipline:** adaptive work fills unused revisit capacity and uses existing provider pacing. It cannot create an unbounded second polling loop.
- **Look-ahead discipline:** path snapshots are observations at their actual timestamps; official future labels remain separate outcome rows.
- **Type consistency:** Task 3–6 consume only types/methods defined in Task 1–2 or already present in the repository.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
