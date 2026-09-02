# FL2 Reserve Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make authoritative Pump and PumpSwap reserve evidence part of deterministic, replayable `FastEvent`/`FastMarketState` without changing provider, strategy, PAPER, signing, submission, or LIVE authority.

**Architecture:** Keep immutable raw evidence as the reserve source of truth. Add a venue-typed reserve context to `FastEvent`, populate it during normalization from the already-selected immutable source, reconstruct the same context during database replay by joining/re-reading the referenced raw evidence, and expose the latest context in `FastMarketSnapshot`. Do not duplicate reserves into `fast_events` unless tests prove source-derived replay cannot satisfy deterministic reconstruction.

**Tech Stack:** Rust, rusqlite, existing Shreks Fast Lane domain/storage/observer modules, GitHub Actions CI.

**Spec:** Existing FL2 Fast Lane state/benchmark work plus SHREKS build-order requirement to derive liquidity/state features where authoritative evidence is available.

## Global Constraints

- Current raw provenance remains public Solana only for physical acceptance.
- No paid-provider fallback.
- No database authority weakening; canonical source-existence and contiguous-sequence protections remain intact.
- No strategy, transaction submission, signing, PAPER authority, LIVE authority, or release-topology change.
- Preserve canonical identity `(signature, ordinal)` and durable sequence semantics.
- Use observation time for state application; no future leakage from chain occurrence timestamps.
- Exact raw reserve integers remain authoritative; normalized values are derived only from verified decimals.

---

### Task 1: Core reserve context and state exposure

**Files:**
- Modify: `crates/shreks-core/src/fast_lane/event.rs`
- Modify: `crates/shreks-core/src/fast_lane/state.rs`
- Modify: `crates/shreks-core/src/fast_lane/mod.rs`
- Modify: `crates/shreks-core/src/lib.rs`
- Test: `crates/shreks-core/tests/fast_lane_reserve_context.rs`

**Interfaces:**
- Produces: `FastReserveContext`, `FastEvent::with_reserve_context`, `FastMarketSnapshot::last_reserve_context`.

- [ ] Write failing tests that require venue-typed reserve context, venue mismatch rejection, and latest-context snapshot exposure.
- [ ] Run CI and require RED specifically because the new reserve API does not exist.
- [ ] Implement the minimal core types and validation.
- [ ] Run exact-head CI and require all four repository gates GREEN.

### Task 2: Source-derived canonical normalization and replay

**Files:**
- Modify: `crates/shreks-observer/src/fast_event_normalizer.rs`
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/pump_swap_fast_lane.rs`
- Test: `crates/shreks-storage/tests/fast_event_storage.rs`
- Test: `crates/shreks-storage/tests/fast_lane_fork_replay.rs`
- Test: observer normalization tests as applicable.

**Interfaces:**
- Consumes: immutable `PumpTradeEvidenceWrite` / `PumpSwapTradeEvidenceWrite` plus verified decimals.
- Produces: canonical `FastEvent` values carrying exact reserve context both live-normalized and replayed.

- [ ] Write failing storage/replay tests for exact Pump and PumpSwap reserve reconstruction.
- [ ] Require authoritative RED.
- [ ] Populate reserve context from already-selected raw source during normalization.
- [ ] Reconstruct context from immutable referenced source evidence during replay; avoid duplicated schema state if source-derived replay is exact.
- [ ] Prove idempotence/conflict/fork replay gates remain unchanged and require exact-head GREEN.

### Task 3: Lifecycle/migration state audit

**Files:**
- Inspect: `crates/shreks-storage/src/lifecycle.rs`
- Inspect: lifecycle schema/tests and current Fast Lane state consumer path.
- Modify only if deterministic observation-time application can be made without inventing ordering or identity semantics.

- [ ] Determine whether lifecycle evidence has an authoritative observation/detection time and market mapping sufficient for point-in-time state.
- [ ] If sufficient, TDD a separate lifecycle state input rather than smuggling migration state into trade events.
- [ ] If insufficient, document the exact missing contract and leave state fail-closed/unrepresented rather than guessing.

### Task 4: Final FL2 capacity benchmark and release gate

**Files:**
- Modify benchmark tests only if reserve-aware state changes its required synthetic workload.

- [ ] Run `fast-state-benchmark` on the final reserve-aware software shape in CI tests.
- [ ] Merge with exact-head guard only after scope audit and all four gates GREEN.
- [ ] Require fresh merged-main four-gate CI.
- [ ] Create a byte-identical seal only after merged-main is GREEN.
- [ ] Publish immutable ARM64 release and deploy through the existing verified release workflow.
- [ ] Run the physical ARM64 benchmark on the exact sealed binary; report measured throughput/latency/RSS without inventing thresholds.
