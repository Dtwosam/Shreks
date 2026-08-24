# Phase A10 Observer V2 — Verification Record

**Status:** implementation complete; final seal CI pending at time of this commit  
**Base:** sealed E5 `8f8454a982d41a7f5710c66f27690ef8c080bf41`  
**PR:** #29 `Phase A10: Observer V2 high-resolution lifecycle capture`

## Purpose

A10 upgrades the read-only Rust observer so the standardized A9 1m/5m/15m/30m/1h/4h/24h outcomes are backed by dense token-path evidence rather than checkpoint-only observations. It does not add trading authority and does not claim profitability.

The default `shreks-observe` process now runs two coordinated loops against separate SQLite WAL connections to the same database:

- the existing `Observer` retains Pump realtime lifecycle verification and Helius chain/transaction observation;
- the A10 `HighResolutionSampler` owns public DEX Screener discovery plus adaptive DEX Screener/Meteora market-path sampling.

This split avoids duplicating public discovery/market requests while leaving the mature Pump verification implementation untouched.

## Delivered behavior

### Adaptive high-resolution sampling

`SamplingPolicy::default_v1()` applies explicit age bands:

- through 15m: 10s;
- through 1h: 30s;
- through 4h: 60s;
- through 24h: 300s.

ACTIVE/HOT observations shorten cadence while preserving a 5-second floor. Total market-provider failure applies bounded exponential backoff. Provider request pacing remains authoritative and uses the existing free-tier `ProviderConfig` budgets.

### Full path preservation

The registry preserves first/latest/high/low representative prices and their timestamps. The locked regression path `100 -> 400 -> 60` preserves:

- high = 400;
- low = 60;
- MFE = +300%;
- MAE = -40%;
- the corresponding peak/trough timestamps.

All normalized provider/pair snapshots are persisted; representative selection affects only operational path state and scheduling. The authoritative A9 checkpoint implementation still derives MFE/MAE from persisted snapshots, so no second outcome formula was introduced.

### Candidate neutrality and retention

The sampler consumes no REJECT/WATCH/ENTER decision. Every discovered candidate is retained independently of later strategy action through the 24h research horizon plus 10-minute grace. Missing/provider-failed observations are not converted to zero and do not delete candidate state.

### Restart safety

Active sampler state is encoded deterministically in the existing `ingestion_checkpoints` table under the versioned `observer_v2_registry_v1` stream. Restore validates the full registry and fails closed on corrupt state. Market snapshots remain the research truth; registry state is only scheduler/path operational state.

### Runtime ownership

The final binary wiring intentionally does **not** call `build_free_observer`. Public DEX Screener discovery/market and Meteora market sampling belong to V2. The legacy observer is constructed with `Observer::new` and receives Helius chain/transaction providers only when configured, plus the existing Pump realtime channel.

Shutdown/error handling is coupled: Ctrl-C stops both loops, and an unexpected exit from either loop signals the other. The sampler's normal shutdown path flushes its registry before return. The Pump forwarder is aborted/joined after the observation loops stop.

## TDD evidence

### Task 1 — scheduler/registry/path state

**RED:** `8ea6c49f7face58cf0e505ef79aee18804ad1b29`  
**CI:** `32783259327`  
**Expected failure:** Rust could not read missing `src/bin/observer_v2/sampling.rs`. Python and repository safety were green.

A test-fixture timestamp typo was corrected in `b1fc41280fff449a6df11e41eb709af5c9c2824c` before implementation; it did not change the RED cause.

**GREEN:** `21dc263dce5a45a8f89ad43f63c1e9a57dde2923`  
**CI:** `32783605323`  
**Result:** Rust workspace GREEN, Python GREEN, repository safety GREEN.

### Task 2 — finite sampler + SQLite/A9 integration

**RED:** `b0382faea02ff6ad96a564999c3c824f60d399c6`  
**CI:** `32783845484`  
**Expected failure:** Rust could not read missing `src/bin/observer_v2/sampler.rs`. Python and repository safety were green.

**GREEN:** `5816e32bd45dabb0fab6ede8f187f070f5f98425`  
**CI:** `32784155279`  
**Result:** Rust workspace GREEN, Python GREEN, repository safety GREEN.

Integration coverage proves discovery persistence/seven A9 checkpoints, pre-checkpoint re-sampling, hot-path cadence changes, multi-provider snapshot persistence, partial-provider success, all-provider failure backoff, A9 finalization from dense snapshots, and registry restoration across a new SQLite connection.

### Task 3 — default runtime wiring

**RED:** `5c0575f092246382fa31c80e1b93da90dc3b7089`  
**CI:** `32784481502`  
**Expected failure:** exactly one A10 runtime assertion failed because `HighResolutionSampler` was not yet wired into `shreks-observe`; the observe-only firewall test passed. Python and repository safety were green.

**GREEN:** `75d5450d9ae26c9ff75118552c26b1fbc83a4bb7`  
**CI:** `32784668443`  
**Result:** Rust workspace GREEN, repository safety GREEN, Python **1812 passed in 5.93s**.

## Scope audit

Cumulative comparison from sealed E5 `8f8454a982d41a7f5710c66f27690ef8c080bf41` to behavior head `75d5450d9ae26c9ff75118552c26b1fbc83a4bb7` contains exactly these eight files:

1. `crates/shreks-observer/src/bin/observer_v2/sampler.rs`
2. `crates/shreks-observer/src/bin/observer_v2/sampling.rs`
3. `crates/shreks-observer/src/bin/shreks-observe.rs`
4. `crates/shreks-observer/tests/observer_v2_runtime.rs`
5. `crates/shreks-observer/tests/observer_v2_sampler.rs`
6. `crates/shreks-observer/tests/observer_v2_sampling.rs`
7. `docs/superpowers/plans/2026-08-24-phase-a10-observer-v2.md`
8. `docs/superpowers/specs/2026-08-24-phase-a10-observer-v2-design.md`

No Python strategy/risk/learning/evaluation behavior changed. No storage migration was added. No trade intent, quote execution, signing, submission, promotion, or live-mode authority was introduced.

## Profitability boundary

A10 improves the evidence available to later learning/evaluation by preserving intra-window pumps, dumps, timing, liquidity/volume/flow changes, and all discovered candidates—including rejected and untraded candidates. That can reduce false conclusions caused by sparse labels, but it is not itself evidence of positive expectancy.

Real money remains disabled. E6-E8 retain model registry, shadow/challenger, and promotion authority under the existing source-of-truth gates.

## Final seal procedure

This verification record is the only tracked change after the fully green behavior head. The final A10 SHA is frozen only after exact-head CI on this documentation commit reports:

- Rust workspace GREEN;
- Python GREEN;
- repository safety GREEN;
- PR #29 head exactly equal to the sealed SHA.
