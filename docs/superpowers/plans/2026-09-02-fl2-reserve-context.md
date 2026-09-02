# FL2 Reserve Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make authoritative Pump and PumpSwap reserve evidence part of deterministic, replayable `FastEvent`/`FastMarketState` without changing provider, strategy, PAPER, signing, submission, or LIVE authority.

**Architecture:** Keep immutable raw evidence as the reserve source of truth. Add a venue-typed reserve context to `FastEvent`, populate it during source normalization from the already-selected immutable evidence, reconstruct the same context during database replay from the referenced raw evidence, and expose the latest context in `FastMarketSnapshot`. Do not duplicate reserves into `fast_events`; source-derived replay has proved sufficient. Pump graduation lifecycle state is a separate point-in-time input keyed by its durable detection clock because lifecycle and trade streams do not share one authoritative total sequence.

**Tech Stack:** Rust, rusqlite, existing Shreks Fast Lane domain/storage/observer modules, GitHub Actions CI.

**Spec:** Existing FL2 Fast Lane state/benchmark work plus SHREKS build-order requirement to derive liquidity/state features where authoritative evidence is available.

## Global Constraints

- Current raw provenance remains public Solana only for physical acceptance.
- No paid-provider fallback.
- No database authority weakening; canonical source-existence and contiguous-sequence protections remain intact.
- No strategy, transaction submission, signing, PAPER authority, LIVE authority, or release-topology change.
- Preserve canonical identity `(signature, ordinal)` and durable sequence semantics.
- Use observation time for trade-state application; lifecycle state uses its separately durable `detected_at_unix_ms` clock.
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

- [x] Write failing tests that require venue-typed reserve context, venue mismatch rejection, and latest-context snapshot exposure.
- [x] Run CI and require RED specifically because the new reserve API does not exist.
- [x] Implement the minimal core types and validation.
- [x] Run exact-head CI and require all four repository gates GREEN.

### Task 2: Source-derived canonical normalization and replay

**Files:**
- Modify: provider Pump/PumpSwap evidence-to-`FastEvent` conversion.
- Modify: storage replay reconstruction from immutable Pump/PumpSwap raw evidence.
- Test: storage replay plus provider normalization tests.

**Interfaces:**
- Consumes: immutable Pump/PumpSwap raw evidence plus verified decimals.
- Produces: canonical `FastEvent` values carrying exact reserve context both newly normalized and replayed.

- [x] Write failing storage/replay tests for exact Pump and PumpSwap reserve reconstruction.
- [x] Require authoritative RED.
- [x] Populate reserve context from already-selected raw source during normalization.
- [x] Reconstruct context from immutable referenced source evidence during replay; avoid duplicated schema state because source-derived replay is exact.
- [x] Prove idempotence/conflict/fork replay gates remain unchanged and require exact-head GREEN.

**Durable decision:** No migration 15 is needed for reserve persistence. `fast_events` continues to reference immutable raw evidence as durable authority. Reserve-aware replay reconstructs exact context from that evidence, so duplicating the same source truth into another canonical column would create avoidable divergence risk.

### Task 3: Lifecycle/migration state audit

**Files:**
- Inspect: `crates/shreks-storage/src/lifecycle.rs`
- Inspect: lifecycle schema/tests and current Fast Lane state consumer path.
- Modify: `FastMarketState` only where the existing lifecycle contract is decision-safe.
- Test: `crates/shreks-core/tests/fast_lane_lifecycle_state.rs`.

- [x] Determine whether lifecycle evidence has an authoritative observation/detection time and market mapping sufficient for point-in-time state.
- [x] TDD a separate lifecycle state input rather than smuggling migration state into trade events.
- [x] Keep lifecycle ordering independent of trade sequence because there is no shared durable total sequence.
- [x] Fail closed on market mismatch, backward lifecycle detection time, conflicting same-time lifecycle evidence, and snapshots that predate known lifecycle detection.
- [x] Require exact-head four-gate GREEN after lifecycle integration.

**Durable decision:** `TokenLifecycleEvent.detected_at_unix_ms` is the decision-safe lifecycle clock. `occurred_at_unix_ms` is useful historical evidence but does not replace detection time for point-in-time state. Lifecycle events are not assigned fabricated `FastEvent` sequences.

### Task 4: Final FL2 capacity benchmark and release gate

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-observe/fast_state_benchmark_cli.rs`.
- Test: `crates/shreks-observer/tests/fast_state_benchmark_cli.rs`.

- [x] TDD benchmark version 2 so the measured workload explicitly includes reserve-aware and lifecycle-aware FL2 state.
- [x] Make the deterministic benchmark checksum consume both reserve and lifecycle state so the final state shape cannot silently disappear.
- [x] Run `fast-state-benchmark` on the final reserve-aware software shape in CI tests.
- [ ] Merge with exact-head guard only after scope audit and all four gates GREEN.
- [ ] Require fresh merged-main four-gate CI.
- [ ] Create a byte-identical seal only after merged-main is GREEN.
- [ ] Publish immutable ARM64 release and deploy through the existing verified release workflow.
- [ ] Run the physical ARM64 benchmark on the exact sealed binary; report measured throughput/latency/RSS without inventing thresholds.

## Verification history

- Core reserve API: intentional RED followed by four-gate GREEN.
- Source-derived reserve replay: intentional RED followed by four-gate GREEN.
- Lifecycle state: intentional RED at `ece6778fce3bed329bac04b9876975039f2c70c7`, then four-gate GREEN at `efda2d6a9d4940c4a24bd0accf33f49d37ec6155`.
- Provider reserve normalization: intentional RED at `a5de91706d46fa7ef12d20b7e2a34e97c103f514`, then four-gate GREEN at `fbe96eddd565ff06b55bd8d80d1cd57e96b9680f`.
- Final benchmark contract: intentional RED at `2eb7d0b958f7fcadd133a9e3792540ae0847f8c0` because the command still reported benchmark version 1 without `state_shape`; benchmark version 2 implementation was four-gate GREEN at `d93013f0af0e11cfa4368878a0e2a21d609e203a`.

LIVE remains disabled. This plan does not authorize strategy, PAPER, signing, submission, or live-money changes.
