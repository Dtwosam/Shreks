# Zero-Cost Direct Solana Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move FL1 broad Pump/PumpSwap observation and lifecycle verification off metered providers onto free public Solana RPC while preserving event-level Fast Lane economics, truthful provenance, and fail-closed supervision.

**Architecture:** Add a first-class `SolanaPublic` provider identity, reuse the existing standard-Solana bounded realtime parser/subscription machinery against the official public WSS endpoint, and reuse/generalize the standard read-only RPC adapter against the official public HTTPS endpoint. Production `shreks-observe` uses only this public source for broad FL1 collection/verification; Helius/Chainstack/Alchemy credentials are ignored by the observer broad lane. Directly supervise realtime-forwarder termination so the first causal failure is retained.

**Tech Stack:** Rust, Tokio, tokio-tungstenite, reqwest, rusqlite/SQLite WAL, existing Shreks Fast Lane/provider abstractions, GitHub Actions ARM64 release build.

**Spec:** `docs/superpowers/specs/2026-08-30-zero-cost-direct-solana-capture-design.md`

## Global Constraints

- LIVE TRADING remains disabled.
- No strategy, score, action, sizing, risk, signing, wallet, PAPER, SHADOW, LIVE, or FL2 authority changes.
- Preserve direct event-level Pump/PumpSwap economics required by FL1; do not replace them with DEX Screener polling, candles, or aggregates.
- Production observer broad realtime must not use Helius, Chainstack, Alchemy, or paid PumpPortal trade subscriptions.
- Never restore the global `PUMP_AMM_PROGRAM_ID` subscription.
- Preserve truthful source provenance; public Solana rows serialize as `solana_public`.
- No database migration: existing provider columns are textual.
- Public Solana endpoint failures remain fail-closed and visible; no silent paid fallback.
- Production observer and paper-evidence remain stopped until exact-head CI, merge, seal, release, deployment, and physical acceptance complete.

---

### Task 1: Add truthful Solana-public provider identity

**Files:**
- Modify: `crates/shreks-core/src/lib.rs`
- Modify: `crates/shreks-storage/src/fast_lane.rs`
- Modify: `crates/shreks-storage/src/pump_swap_fast_lane.rs` if it has its own provider decoder
- Modify: `crates/shreks-observer/src/fast_event_normalizer.rs`
- Modify: `crates/shreks-observer/src/runtime.rs`
- Test: existing core/storage/observer Fast Lane tests plus a focused new/extended provider-provenance test

**Interfaces:**
- Produces: `ProviderId::SolanaPublic`, `ProviderId::as_str() == "solana_public"`.
- All raw/canonical provider validation and decoding must accept the new identity.

- [ ] **Step 1: Write failing tests** asserting `SolanaPublic` serialization and Fast Lane storage round-trip, plus normalizer/runtime acceptance of the provider.
- [ ] **Step 2: Run exact focused Rust tests and capture RED** caused only by the missing enum/decoder support.
- [ ] **Step 3: Implement the minimal enum/string/decoder/validator changes.**
- [ ] **Step 4: Run the focused tests and existing Fast Lane suites GREEN.**
- [ ] **Step 5: Commit** as `feat: add Solana public provider provenance`.

### Task 2: Generalize the standard read-only Solana RPC adapter

**Files:**
- Modify: `crates/shreks-providers/src/solana_rpc.rs`
- Test: existing/new `crates/shreks-providers/tests/*solana_rpc*.rs`

**Interfaces:**
- Produces: `StandardSolanaRpcProvider::solana_public() -> Result<Self, ProviderError>`.
- Public endpoint: `https://api.mainnet.solana.com`.
- Public provider supports only the existing read-only FL1 calls: `getTransaction` and `getAccountInfo` with confirmed/jsonParsed semantics.

- [ ] **Step 1: Write failing tests** for public constructor, `SolanaPublic` mint parsing provenance, request validation provenance, and redacted Debug/error behavior.
- [ ] **Step 2: Run focused provider tests and capture RED.**
- [ ] **Step 3: Refactor hard-coded Chainstack request/provider messages into provider-parameterized helpers and add the public constructor.** Use a conservative public pacing interval at or below 4 requests/sec.
- [ ] **Step 4: Run provider tests GREEN**, including existing Chainstack compatibility tests.
- [ ] **Step 5: Commit** as `feat: add zero-cost Solana public RPC adapter`.

### Task 3: Move bounded broad realtime to Solana public WSS

**Files:**
- Modify: `crates/shreks-providers/src/bounded_pump_realtime.rs`
- Test: `crates/shreks-providers/tests/bounded_pump_realtime_stream.rs`
- Test: existing subscription-plan/reconciliation/failover tests

**Interfaces:**
- Produces: `BoundedPumpRealtimeLogStreamConfig::solana_public()` using `wss://api.mainnet.solana.com`.
- `for_provider_endpoint` accepts `SolanaPublic` in addition to existing provider identities for tests/backward compatibility.
- Subscription plan remains exactly Pump program + bounded verified PumpSwap pools.

- [ ] **Step 1: Write failing tests** for public constructor/provenance and confirm global AMM remains forbidden.
- [ ] **Step 2: Run focused bounded-realtime tests and capture RED.**
- [ ] **Step 3: Add `SolanaPublic` support without changing parser economics, reconciliation, unsubscribe semantics, or pool cap behavior.**
- [ ] **Step 4: Run all bounded realtime provider tests GREEN.**
- [ ] **Step 5: Commit** as `feat: add zero-cost Solana public realtime source`.

### Task 4: Make observer runtime zero-cost by construction

**Files:**
- Modify: `crates/shreks-observer/src/runtime.rs`
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Modify: `.env.example` comments/observer budget semantics if necessary
- Test: `crates/shreks-observer/tests/runtime_config.rs`
- Test: `crates/shreks-observer/tests/bounded_realtime_runtime_wiring.rs`
- Test: `crates/shreks-observer/tests/observer_v2_runtime.rs`

**Interfaces:**
- `free_observe_provider_plan` uses `SolanaPublic` for chain, transactions, and realtime broad FL1 lanes.
- `build_lifecycle_observer` constructs one public standard Solana provider for chain + transaction verification.
- `build_pump_realtime_configs` returns only one public bounded realtime config.
- Presence of `HELIUS_API_KEY` alone does not force the observer Helius HTTP budget because the observer no longer constructs Helius.
- PumpSwap tracking age/count remain mandatory for normal observer runtime.

- [ ] **Step 1: Write source/runtime RED tests** that require SolanaPublic-only production wiring and reject Helius/Chainstack/Alchemy construction in the broad observer lane.
- [ ] **Step 2: Add config RED tests** proving Helius key presence does not require observer Helius budget while missing/invalid PumpSwap scope still fails closed.
- [ ] **Step 3: Run focused observer tests and capture RED.**
- [ ] **Step 4: Replace production broad provider construction with SolanaPublic only**, leaving keyed provider config available to unrelated binaries.
- [ ] **Step 5: Run focused observer/runtime tests GREEN.**
- [ ] **Step 6: Commit** as `fix: move FL1 broad observer traffic off metered providers`.

### Task 5: Preserve the primary realtime failure in supervision

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Test: new/extended observer runtime supervision test

**Interfaces:**
- Forwarder task returns `Result<(), ProviderError>` instead of swallowing errors.
- `run_observation_with_realtime` selects the forwarder handle alongside publisher/writer/normalizer.
- On forwarder failure, sibling tasks are stopped and the returned process error preserves the provider/kind/message that caused the forwarder to exit.

- [ ] **Step 1: Write a failing supervision test/source contract** proving forwarder termination is directly supervised rather than only logged.
- [ ] **Step 2: Capture RED.**
- [ ] **Step 3: Implement minimal direct supervision and primary-error propagation.**
- [ ] **Step 4: Run observer tests GREEN.**
- [ ] **Step 5: Commit** as `fix: preserve realtime primary failure`.

### Task 6: Full verification and scope audit

**Files:**
- No new production scope beyond Tasks 1-5.

- [ ] **Step 1: Run/require repository-safety CI.**
- [ ] **Step 2: Run/require full Rust workspace CI.**
- [ ] **Step 3: Run/require full Python CI.**
- [ ] **Step 4: Run/require native ARM64 release-build/bundle verification.**
- [ ] **Step 5: Audit the exact diff** for no signing, `RuntimeMode::Live`, trade-intent, schema migration, strategy/risk/PAPER/LIVE authority, global PumpSwap AMM subscription, or broad keyed-provider production subscription.
- [ ] **Step 6: Open a non-draft PR against `main`** with the physical 5k-credit/3-minute evidence and explicit zero-cost acceptance requirements.

### Task 7: Stacked ready-row canonicalization repair

**Files:**
- Branch from the exact GREEN Task 6 head after transport PR is stable.
- Modify: `crates/shreks-storage/src/conflict_quarantine.rs` and/or focused readiness query module
- Modify: `crates/shreks-observer/src/fast_event_normalizer.rs`
- Test: `crates/shreks-observer/tests/fast_event_normalizer.rs`
- Test: storage Fast Lane/conflict tests

**Interfaces:**
- Old unresolved raw evidence remains durable and is never deleted/skipped permanently.
- A ready recent Pump/PumpSwap row with verified decimals/lifecycle mapping must be able to normalize even when older pending rows are unresolved.
- Deterministic canonical identity and sequence rules remain unchanged.

- [ ] **Step 1: Write a regression test** with more than the current 8x scan frontier of unresolved historical rows followed by a ready recent row; assert the ready row normalizes.
- [ ] **Step 2: Capture RED** demonstrating current frontier starvation.
- [ ] **Step 3: Implement a readiness-aware bounded query/scheduling rule** rather than increasing the scan multiplier without bound.
- [ ] **Step 4: Prove old unresolved rows remain pending and become normalizable once their prerequisites arrive.**
- [ ] **Step 5: Run focused + full Rust tests GREEN and commit.**
- [ ] **Step 6: Require exact-head four-gate CI for the stacked canonicalization head.**

### Task 8: Merge, seal, deploy, and zero-cost physical acceptance

- [ ] **Step 1: Merge transport first, then retarget/reverify canonicalization against merged `main`.**
- [ ] **Step 2: Require fresh merged-main four-gate CI.**
- [ ] **Step 3: Create byte-identical `seal:` commit and require seal CI.**
- [ ] **Step 4: Verify immutable ARM64 release/tag/assets.**
- [ ] **Step 5: Deploy through the verified release manager only.**
- [ ] **Step 6: Run a 3-minute physical sanity interval** with paper-evidence stopped; require exact process identity, unchanged restart count, raw/canonical progress, zero integrity/conflict violations, `solana_public` provenance, and no Helius/Chainstack/Alchemy observer usage.
- [ ] **Step 7: Only after sanity passes, run representative FL1.5** and retain public-source latency, event rate, CPU/RAM/storage/network evidence.
- [ ] **Step 8: Keep FL2 BLOCKED and LIVE DISABLED until FL1.5 passes.**
