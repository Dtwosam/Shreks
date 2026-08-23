# Phase A10 Adaptive Path Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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
- Modify `crates/shreks-observer/tests/runtime.rs` — prove realtime wake does not trigger path sampling.
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

- [ ] **Step 1: Write the failing storage tests**

Tests must assert schema version 5 and exact cadence boundaries:

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

Also prove:
- first due = discovery + 30_000ms,
- `ensure_path_sampling` is idempotent across reopen,
- due rows are deterministic by `next_due_at_unix_ms, candidate_id`,
- zero limit returns empty,
- timestamp overflow returns `StorageError::InvalidData` without partial state.

- [ ] **Step 2: Run full CI and verify RED**

Run: GitHub Actions full CI.  
Expected: Rust fails only on missing schema-v5/path-sampling contracts; Python and repository safety remain green.

- [ ] **Step 3: Implement migration and typed cadence module**

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

`path_sampling_interval_seconds` must use the exact spec boundaries. `ensure_path_sampling` precomputes checked first due time before insert.

- [ ] **Step 4: Run full CI and verify GREEN**

Expected: Rust/Python/repository-safety all pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add adaptive path sampling schedule`

---

### Task 2: Restart-safe schedule advancement without catch-up bursts

**Files:**
- Modify: `crates/shreks-storage/src/path_sampling.rs`
- Extend: `crates/shreks-storage/tests/path_sampling.rs`

**Interfaces:**
- Consumes: `advance_path_sampling(candidate_id, sampled_at_unix_ms)` from Task 1.
- Produces: schedule advancement based on candidate age at actual sample time.

- [ ] **Step 1: Write failing advancement tests**

Prove:
- sampling at age 40s makes next due `sampled_at + 30s`, not discovery + missed intervals,
- sampling at age 6m advances by 60s,
- sampling at age 23h advances by 3600s only if the computed next due is still within lifecycle; once sampled at/after 24h status is completed with `next_due_at_unix_ms = NULL`,
- `sample_count` increments exactly once per successful advancement,
- completed schedules cannot become active again,
- advancement survives database restart.

- [ ] **Step 2: Verify RED**

Expected: missing/incomplete advancement behavior only.

- [ ] **Step 3: Implement transactional advancement**

Load candidate discovery time + current schedule in one transaction. Reject nonpositive candidate IDs and timestamps before discovery. Compute `age_ms = sampled_at - discovered_at`; if cadence returns `Some(seconds)`, checked-add `seconds*1000` to actual `sampled_at`; otherwise mark completed. Update only an active row.

- [ ] **Step 4: Verify GREEN**

Run full CI.

- [ ] **Step 5: Commit**

Commit message: `feat: advance adaptive path samples safely`

---

### Task 3: Schedule every durable candidate

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Extend: `crates/shreks-observer/tests/cycle.rs`
- Extend: `crates/shreks-observer/tests/pump_verification.rs`

**Interfaces:**
- Consumes: candidate IDs returned by `ShreksDb::upsert_candidate`.
- Produces: one idempotent active path-sampling row for both generic discoveries and verified Pump creations.

- [ ] **Step 1: Write failing observer tests**

After generic discovery, assert both seven official outcome rows and one path schedule exist. Repeat discovery and assert counts remain unchanged. Verify a verified Pump Create/CreateV2 candidate gets the same path schedule. A rejected Pump signal that never becomes a candidate gets no path schedule.

- [ ] **Step 2: Verify RED**

Expected: candidate/outcome records exist while path schedule is absent.

- [ ] **Step 3: Schedule immediately after candidate upsert**

At every existing call site that currently does:

```rust
let candidate_id = self.db.upsert_candidate(&candidate)?;
self.db.ensure_outcome_checkpoints(candidate_id, candidate.discovered_at_unix_ms)?;
```

add:

```rust
self.db.ensure_path_sampling(candidate_id, candidate.discovered_at_unix_ms)?;
```

Do not create new candidate identities.

- [ ] **Step 4: Verify GREEN**

Run full CI.

- [ ] **Step 5: Commit**

Commit message: `feat: schedule path observation for candidates`

---

### Task 4: Shared checkpoint-first revisit budget

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/tests/path_sampling.rs`

**Interfaces:**
- Consumes: `due_outcome_checkpoints`, `due_path_samples`, existing candidate-ID dedupe and market provider pacing.
- Produces: a single ordered revisit list of at most 16 distinct existing candidates.

- [ ] **Step 1: Write failing priority/budget tests**

Use deterministic fixtures to prove:
- 16 official due candidates -> zero adaptive-only candidates,
- 7 official due candidates + 20 adaptive due candidates -> 7 checkpoint candidates then up to 9 adaptive-only candidates,
- candidate due for both appears once,
- newly discovered candidate that is also revisit-due is observed once through normal new-candidate processing,
- adaptive-only revisit causes zero chain calls.

- [ ] **Step 2: Verify RED**

Expected: adaptive due rows are currently ignored.

- [ ] **Step 3: Implement shared revisit selection**

Replace the outcome-only revisit selection with a helper equivalent to:

```rust
const MARKET_REVISIT_CANDIDATE_LIMIT: usize = 16;

struct RevisitCandidate {
    candidate_id: i64,
    mint: String,
    path_sample_due: bool,
}
```

Load checkpoint-due candidates first in deterministic order, dedupe by candidate ID, then request adaptive rows only for remaining capacity and append unseen candidate IDs. Preserve checkpoint priority.

- [ ] **Step 4: Verify GREEN**

Run full CI.

- [ ] **Step 5: Commit**

Commit message: `feat: prioritize checkpoint and path revisits`

---

### Task 5: Advance schedule only after real adaptive evidence

**Files:**
- Modify: `crates/shreks-observer/src/lib.rs`
- Extend: `crates/shreks-observer/tests/path_sampling.rs`

**Interfaces:**
- Consumes: existing `observe_market_data` snapshot persistence and `advance_path_sampling`.
- Produces: adaptive schedule advancement iff at least one valid snapshot was stored during that path-due pass.

- [ ] **Step 1: Write failing evidence/failure tests**

Prove:
- path-due candidate with one valid snapshot advances and increments `sample_count`,
- provider error with no valid snapshot leaves schedule due,
- empty pair response leaves schedule due,
- one provider failing while another stores a valid snapshot advances once,
- adaptive revisit reuses DEX Screener/Meteora pacing,
- official checkpoint finalization still occurs from the same market pass,
- no rug/dead/exitability values are fabricated.

- [ ] **Step 2: Verify RED**

Expected: snapshots may store, but adaptive schedule is not yet advanced.

- [ ] **Step 3: Return stored-snapshot count from market observation**

Refactor the internal market-observation helper to return the number of valid snapshots stored for that candidate in the pass. Existing report totals remain unchanged. After a revisit marked `path_sample_due`, call `advance_path_sampling(candidate_id, sampled_at)` only when stored count > 0.

Use one `sampled_at = unix_time_ms()?` after provider calls; do not advance on synthetic/no-data success.

- [ ] **Step 4: Verify GREEN**

Run full CI.

- [ ] **Step 5: Commit**

Commit message: `feat: record adaptive path evidence`

---

### Task 6: Realtime isolation, restart regression, and operator docs

**Files:**
- Modify: `crates/shreks-observer/tests/runtime.rs`
- Extend: `crates/shreks-observer/tests/path_sampling.rs`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-23-phase-a10-adaptive-path-observation.md`

**Interfaces:**
- Consumes: completed adaptive sampling path.
- Produces: regression evidence and operator-visible semantics.

- [ ] **Step 1: Add realtime isolation regression**

With a one-hour full-cycle interval and an adaptive-due candidate, deliver a Pump realtime signal between cycles. Assert the signal is durably written but no adaptive market provider call occurs until the next full cycle.

- [ ] **Step 2: Add restart/backlog regression**

Create an active schedule, close/reopen SQLite after it becomes overdue, run one successful adaptive pass, and assert:
- same schedule row is reused,
- exactly one sample-count increment occurs,
- next due is based on actual sample time,
- no historical missed intervals are replayed.

- [ ] **Step 3: Verify regressions**

If existing behavior passes a regression without a production change, record that result rather than manufacturing a failure.

- [ ] **Step 4: Update README**

Document lifecycle cadence, checkpoint-first shared budget, best-effort semantics, restart/no-catch-up behavior, and that adaptive snapshots are ordinary `market_snapshots` used for path/MFE/MAE research.

- [ ] **Step 5: Run final full CI**

Expected: Rust tests, Python tests, workspace metadata validation, and repository safety all pass.

- [ ] **Step 6: Commit**

Commit message: `docs: complete adaptive path observation`

---

## Self-review

- **Spec coverage:** exact lifecycle cadence, 24h stop, shared 16-candidate revisit budget, checkpoint priority, candidate dedupe, market-only adaptive sampling, restart durability, no catch-up bursts, and no-data failure semantics each have a task/test.
- **Data model:** no duplicate market evidence table is introduced; path sampling reuses `market_snapshots` and therefore automatically feeds existing MFE/MAE computation.
- **Free-source discipline:** adaptive work fills unused revisit capacity and uses existing provider pacing. It cannot create an unbounded second polling loop.
- **Look-ahead discipline:** path snapshots are observations at their actual timestamps; official future labels remain separate outcome rows.
- **Type consistency:** Task 3–6 consume only types/methods defined in Task 1–2 or already present in the repository.
- **Placeholder scan:** no implementation-critical TBD/TODO placeholders.
