# Phase A10 Observer V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add adaptive high-resolution read-only token sampling to the existing Rust observe process so intra-window pumps/dumps and path extrema are preserved while the existing A9 checkpoint engine continues to own future labels.

**Architecture:** Keep the proven `Observer` library unchanged for Pump lifecycle/chain/checkpoint orchestration. Add focused support modules used by the existing `shreks-observe` binary: pure scheduling/registry/path state plus a finite high-resolution sampler engine. The binary runs the sampler and legacy Pump/chain observer against separate WAL connections to the same SQLite file.

**Tech Stack:** Rust 2021, Tokio, existing `shreks-core`, `shreks-providers`, `shreks-storage`, SQLite WAL through `ShreksDb`. No new paid provider or infrastructure dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-a10-observer-v2-design.md`

## Global Constraints

- Base exactly on sealed E5 `8f8454a982d41a7f5710c66f27690ef8c080bf41`.
- A10 is observe-only and must not create `TradeIntent`, sign, submit, promote, or enable live trading.
- Reuse existing `PairMarketData` normalization and `ShreksDb::insert_market_snapshot`.
- Reuse existing A9 checkpoint finalization; do not duplicate MFE/MAE outcome formulas.
- Track discovered candidates independently of REJECT/WATCH/ENTER decisions.
- Keep free-tier provider pacing explicit and fail/degrade safely.
- No migration is required for scheduler state; use versioned `ingestion_checkpoints` cursor state.
- Existing Pump realtime lifecycle handling remains on the current `Observer` path.

---

### Task 1: Adaptive scheduling, durable registry, and path state

**Files:**
- Create: `crates/shreks-observer/src/bin/observer_v2/sampling.rs`
- Create: `crates/shreks-observer/tests/observer_v2_sampling.rs`

**Interfaces:**
- `SamplingPolicy::default_v1() -> SamplingPolicy`
- `TrackedCandidate::new(candidate_id: i64, mint: String, discovered_at_unix_ms: i64) -> Result<TrackedCandidate, SamplingError>`
- `TrackedCandidate::record_sample(&mut self, summary: RepresentativeSample) -> Result<ActivityClass, SamplingError>`
- `TrackedCandidate::schedule_after_success(&mut self, now_unix_ms: i64, policy: &SamplingPolicy, activity: ActivityClass)`
- `TrackedCandidate::schedule_after_failure(&mut self, now_unix_ms: i64, policy: &SamplingPolicy)`
- `SamplingRegistry::register(...)`
- `SamplingRegistry::due_candidates(now_unix_ms: i64) -> Vec<TrackedCandidate>`
- `SamplingRegistry::expire(now_unix_ms: i64, policy: &SamplingPolicy)`
- `SamplingRegistry::encode() -> String`
- `SamplingRegistry::decode(&str) -> Result<SamplingRegistry, SamplingError>`
- `representative_sample(&[PairMarketData]) -> Option<RepresentativeSample>`

- [ ] Write RED tests for age bands: 10s through 15m, 30s through 1h, 60s through 4h, 300s through 24h.
- [ ] Write RED tests for ACTIVE/HOT boosts and 5-second floor.
- [ ] Write RED test that successive total-provider failures back off exponentially without exceeding the slow 300-second cadence.
- [ ] Write RED path test: prices `100 -> 400 -> 60` produce high `400`, low `60`, MFE `300%`, MAE `-40%`, with correct peak/trough timestamps.
- [ ] Write RED tests for deterministic representative-pair selection and invalid/non-finite/non-positive prices.
- [ ] Write RED registry round-trip/canonical-order/corruption tests.
- [ ] Write RED retention test through `24h + 10m` grace and prove no decision/action field exists in `TrackedCandidate`.
- [ ] Run Rust tests and verify failures are only missing A10 sampling surfaces.
- [ ] Implement the pure standard-library module with no provider/network/storage reads.
- [ ] Run full Rust workspace tests and require GREEN before Task 2.

### Task 2: Finite high-resolution sampler engine

**Files:**
- Create: `crates/shreks-observer/src/bin/observer_v2/sampler.rs`
- Create: `crates/shreks-observer/tests/observer_v2_sampler.rs`

**Interfaces:**
- `SamplerProvider { provider: Arc<dyn MarketDataProvider>, requests_per_second: u32 }`
- `HighResolutionSampler::new(db: ShreksDb, discovery: Option<Arc<dyn DiscoveryProvider>>, market: Vec<SamplerProvider>, policy: SamplingPolicy) -> HighResolutionSampler`
- `HighResolutionSampler::restore_registry(&mut self) -> Result<(), SamplerError>`
- `HighResolutionSampler::run_cycle_at(&mut self, now_unix_ms: i64) -> Result<SamplerCycleReport, SamplerError>`
- `HighResolutionSampler::run_until_shutdown<F>(&mut self, shutdown: F) -> Result<u64, SamplerError>`

Behavior:

- discovery runs on a 30-second operational cadence and validates source identity;
- every discovered candidate is idempotently upserted and receives A9 checkpoints;
- registry keeps candidates independent of trading decisions;
- due candidates are sampled in deterministic order;
- every returned normalized pair snapshot is written through `insert_market_snapshot`;
- representative path state is updated after persisted evidence;
- successful samples call `finalize_due_outcome_checkpoints`;
- at least one successful market provider counts as sample success;
- total market-provider failure triggers candidate backoff;
- provider health is updated on success/failure;
- registry is flushed after discovery changes and at a bounded periodic cadence;
- shutdown flushes registry.

- [ ] Write mock `DiscoveryProvider` and `MarketDataProvider` RED tests.
- [ ] Prove new discovery is persisted and receives seven checkpoints.
- [ ] Prove a candidate is re-sampled before any A9 checkpoint is due.
- [ ] Prove hot path observations shorten the next interval.
- [ ] Prove two providers' pair snapshots are all persisted while representative selection remains deterministic.
- [ ] Prove one-provider failure + one-provider success keeps the candidate alive and resets failure backoff.
- [ ] Prove all-provider failure backs off without deleting candidate state.
- [ ] Prove a fresh high-resolution sample can finalize an A9 checkpoint through the existing storage implementation.
- [ ] Prove registry restoration resumes candidate tracking after opening a new `ShreksDb` connection.
- [ ] Implement per-provider pacing; test constructors may disable wall-clock sleeps.
- [ ] Run full Rust workspace tests and require GREEN before Task 3.

### Task 3: Make `shreks-observe` run Observer V2 by default

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Test: existing Rust workspace plus source/firewall assertions in `crates/shreks-observer/tests/observer_v2_runtime.rs`

Runtime structure:

1. read existing `ObserverRuntimeConfig`;
2. open one `ShreksDb` for the legacy Pump/chain observer and one for the high-resolution sampler;
3. build the legacy observer with Helius chain/transaction provider only, preserving the Pump realtime channel when configured;
4. build sampler discovery with public DEX Screener and market providers with DEX Screener/Meteora according to `ProviderConfig`;
5. run legacy observer in a Tokio task;
6. run sampler until Ctrl-C and flush scheduler registry;
7. abort/join background tasks on shutdown;
8. print only non-secret runtime diagnostics.

- [ ] RED test/source assertion that runtime includes the V2 sampler and contains no trade/sign/submit/live authority.
- [ ] Replace the small binary entrypoint with dual-loop orchestration.
- [ ] Run full Rust workspace tests.
- [ ] Run full Python tests to ensure research/evaluation predecessors are unchanged.
- [ ] Run repository safety gate.

### Task 4: Verification and seal

**Files:**
- Replace this plan with an A10 verification record.
- Update PR #29 metadata only after final CI.

- [ ] Compare sealed E5 to A10 behavior head; allowed scope is A10 docs, observer support/tests, and the observe binary only unless a demonstrated defect requires more.
- [ ] Verify no Python strategy/risk/learning/evaluation behavior changed.
- [ ] Verify no live executor/signing path was introduced.
- [ ] Record RED/GREEN commit and CI evidence.
- [ ] Run exact-head CI on the final seal and freeze the SHA.
- [ ] After A10 is sealed, E6 may start; operational collector execution can proceed independently when free-provider runtime access is available.
