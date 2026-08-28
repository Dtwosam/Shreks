# FL1.5 Read-Only Runtime Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy an observation-only acceptance reporter that measures real FL1 Pump/PumpSwap ingestion counts, backlog, journal integrity, and latency from the production SQLite database without writes or network access.

**Architecture:** Add a standalone Rust binary under `shreks-observer` with a focused read-only report module. The module validates FL1 schema, runs deterministic SQLite queries for an explicit time window, computes latency percentiles in Rust, and emits stable `key=value` output. A separate operator runbook records host-only CPU/RAM/storage/reconnect evidence that the database cannot prove.

**Tech Stack:** Rust 2021, rusqlite 0.40.2, SQLite read-only connection flags, existing Shreks migrations/systemd/release conventions.

**Spec:** `docs/superpowers/specs/2026-08-28-fl1-readonly-runtime-acceptance-design.md`

## Global Constraints

- LIVE remains disabled.
- FL2 must not begin until real-host FL1.5 evidence is captured and reviewed.
- Reporter opens SQLite read-only and never creates a missing database.
- Reporter executes no migrations and performs no writes.
- Reporter makes no provider/network requests.
- Reporter has no strategy, PAPER, risk, wallet, signing, transaction, or submission authority.
- Database evidence must not be presented as CPU/RAM/reconnect evidence.
- Invalid timing or sequence evidence fails closed.

---

### Task 1: RED — Define read-only report contract

**Files:**
- Create: `crates/shreks-observer/tests/fast_lane_acceptance_report.rs`
- Create later in GREEN: `crates/shreks-observer/src/bin/shreks-fast-lane-acceptance/report.rs`

**Interfaces:**

```rust
pub struct LatencySummary {
    pub samples: u64,
    pub p50_ms: Option<i64>,
    pub p95_ms: Option<i64>,
    pub p99_ms: Option<i64>,
    pub max_ms: Option<i64>,
}

pub struct FastLaneAcceptanceReport {
    pub window_start_unix_ms: i64,
    pub as_of_unix_ms: i64,
    pub database_bytes: u64,
    pub wal_bytes: u64,
    pub pump_raw_events: u64,
    pub pumpswap_raw_events: u64,
    pub canonical_events: u64,
    pub pending_pump_events: u64,
    pub pending_pumpswap_events: u64,
    pub sequence_integrity_violations: u64,
    pub source_latency: LatencySummary,
    pub normalization_latency: LatencySummary,
    pub end_to_end_latency: LatencySummary,
}

pub struct FastLaneAcceptanceStore { /* read-only connection */ }

impl FastLaneAcceptanceStore {
    pub fn open(path: &Path) -> Result<Self, FastLaneAcceptanceError>;
    pub fn report(
        &self,
        window_start_unix_ms: i64,
        as_of_unix_ms: i64,
    ) -> Result<FastLaneAcceptanceReport, FastLaneAcceptanceError>;
}
```

- [ ] **Step 1: Write missing-database/read-only RED test**

Call `FastLaneAcceptanceStore::open` on a nonexistent path. Require an error and assert the path is still absent afterward.

- [ ] **Step 2: Write schema-validation RED test**

Create an empty SQLite file and require open to fail because `pump_trade_evidence`, `pump_swap_trade_evidence`, and `fast_events` with required timing/identity columns are missing.

- [ ] **Step 3: Write deterministic report RED fixture**

Initialize a schema-12 Shreks database, insert bounded Pump/PumpSwap raw rows and canonical rows with known timestamps, then assert exact window counts, current pending counts, file sizes, contiguous sequence status, and nearest-rank p50/p95/p99/max latency values.

- [ ] **Step 4: Write timing/window fail-closed RED tests**

Reject negative bounds, non-positive windows, source observation before chain occurrence, and canonical acceptance before source/occurrence.

- [ ] **Step 5: Prove RED**

Run `cargo test -p shreks-observer --test fast_lane_acceptance_report`. Expected failure: report module/API is missing; no unrelated failure is acceptable.

---

### Task 2: GREEN — Implement read-only acceptance store and exact metrics

**Files:**
- Create: `crates/shreks-observer/src/bin/shreks-fast-lane-acceptance/report.rs`

**Interfaces produced:** Task 1 interfaces.

- [ ] **Step 1: Open SQLite with read-only flags**

Use exactly:

```rust
Connection::open_with_flags(
    path,
    OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
)
```

Reject empty path and map missing/unopenable DB to a fail-closed acceptance error.

- [ ] **Step 2: Validate required schema**

Require the three FL1 tables and columns used by the report. Do not call `ShreksDb::open` because that path may create/migrate a database.

- [ ] **Step 3: Query exact window counts/backlog**

Use half-open `[start, end)` predicates. Raw tables use `observed_at_unix_ms`; canonical uses `observed_at_unix_ms`. Pending counts use LEFT JOIN on `(signature, ordinal)` over the full database.

- [ ] **Step 4: Query bounded report latency values**

Collect only latency integer values for rows in the explicit report window. Pump/PumpSwap source latency is `observed_at_unix_ms - timestamp_unix_seconds*1000`. Canonical normalization latency is `observed_at_unix_ms - source_observed_at_unix_ms`. Canonical end-to-end latency is `observed_at_unix_ms - occurred_at_unix_ms`.

Reject overflow and any negative latency before percentile calculation.

- [ ] **Step 5: Compute exact nearest-rank summaries**

Sort latency values ascending. For non-empty `n`, percentile rank is `ceil(p*n)` clamped to `[1,n]`; p50/p95/p99 and max are exact observed values. Empty summaries use `None` fields.

- [ ] **Step 6: Validate sequence integrity**

Read canonical sequences ordered ascending and count violations where the first sequence is not 1 or a later sequence is not exactly previous+1. Integer decode/overflow errors fail closed.

- [ ] **Step 7: Read DB/WAL metadata without mutation**

Use filesystem metadata for database bytes and `<db>-wal` when present; missing WAL is zero bytes.

- [ ] **Step 8: Run focused test GREEN then full Rust workspace**

Required focused and workspace PASS.

---

### Task 3: RED/GREEN — Add stable CLI output and authority guard

**Files:**
- Create: `crates/shreks-observer/src/bin/shreks-fast-lane-acceptance/main.rs`
- Create: `crates/shreks-observer/tests/fast_lane_acceptance_binary.rs`

**CLI:**

```text
shreks-fast-lane-acceptance <db-path> <window-start-unix-ms> <as-of-unix-ms>
```

- [ ] **Step 1: Write RED source/binary contract test**

Require the binary to parse exactly three arguments, call only the read-only report store, and print stable `key=value` fields. Reject source references to provider clients, wallet/signing, `TradeIntent`, PAPER execution, transaction submission, or `ShreksDb::open`.

- [ ] **Step 2: Implement minimal CLI**

Parse decimal i64 timestamps, generate one report, print stable fields including `none` for absent latency percentiles, and return non-zero on errors.

- [ ] **Step 3: Run focused binary tests GREEN**

Expected PASS.

---

### Task 4: RED/GREEN — Production acceptance runbook

**Files:**
- Create: `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`
- Create/modify tests only if the repository has runbook safety assertions that apply.

- [ ] **Step 1: Document immutable release execution**

Use the existing release/systemd deployment conventions. Run the reporter against the production DB with explicit start/end timestamps. Capture output to an operator-owned evidence file; do not redirect into the Shreks database directory if service permissions make that writable by runtime.

- [ ] **Step 2: Document host-only evidence**

Capture service status/restarts, CPU/RSS, memory/storage headroom, DB/WAL growth over the interval, and reconnect/provider logs. State explicitly that these are host measurements, not inferred from SQLite.

- [ ] **Step 3: Define fail/hold conditions**

Hold FL2 for any sequence violation, invalid timing row, unexplained persistent backlog, inability to observe Pump/PumpSwap traffic during a representative interval, resource saturation, or unstable reconnect behavior.

- [ ] **Step 4: Keep LIVE disabled**

The runbook must contain no signing key, transaction submission, LIVE enablement, or trading command.

---

### Task 5: Verification and merge gate

- [ ] **Step 1: Require full CI GREEN**

Required: Rust tests, Python tests, Repository safety, ARM64 release build.

- [ ] **Step 2: Diff audit**

Allowed: acceptance binary/module/tests/docs only. No strategy/PAPER/risk/executor/signing/LIVE changes.

- [ ] **Step 3: Merge exact GREEN head**

Squash merge only the exact tested head SHA.

- [ ] **Step 4: Run real-host acceptance**

After merged release is deployed, run the reporter and capture host metrics for the same interval. Do not claim FL1 complete from CI.

- [ ] **Step 5: FL2 gate**

Only after real-host evidence is reviewed and acceptable may the project create an FL2 implementation branch.
