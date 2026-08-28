# FL1 Realtime Provider Failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep FL1 Pump/PumpSwap ingestion available when Helius quota is exhausted by adding an Alchemy Solana WebSocket fallback, truthful source provenance, and fail-closed realtime health.

**Architecture:** Preserve the existing single bounded Pump/PumpSwap ingestion channel and canonical normalization path. Add Alchemy as a second standard-Solana WebSocket source, carry the actual `ProviderId` with each realtime envelope, and rotate providers after bounded connection failures instead of retrying one provider forever. Helius remains primary; Alchemy is secondary when configured. If every configured realtime source is unavailable, the realtime task exits so the observer fails closed and systemd health reflects the outage.

**Tech Stack:** Rust, Tokio, tokio-tungstenite, SQLite/WAL, GitHub Actions CI.

**Spec:** `SHREKS_BUILD_ORDER.md` FL1/FL1.5 production acceptance gate and `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`.

## Global Constraints

- Solana only V1.
- Free external providers only V1.
- No secrets in source or GitHub.
- Paper and live share the decision path; this change does not add execution authority.
- Critical uncertainty fails closed.
- Do not advance to FL2 before FL1 production acceptance.
- LIVE remains disabled.
- TDD RED -> expected failure -> GREEN -> fresh verification.

---

### Task 1: Add truthful Alchemy provider identity and configuration

**Files:**
- Modify: `crates/shreks-core/src/lib.rs`
- Modify: `crates/shreks-providers/src/config.rs`
- Test: `crates/shreks-providers/tests/config.rs`
- Test: provider/core tests that assert stable provider strings

**Interfaces:**
- Produces: `ProviderId::Alchemy` with stable string `alchemy`.
- Produces: `ProviderConfig::alchemy_api_key()` / `alchemy_enabled()`.

- [ ] Write failing tests asserting `ALCHEMY_API_KEY` is optional, blank values disable it, and configured Alchemy appears only in the realtime provider plan.
- [ ] Run targeted Rust tests and verify RED for missing `ProviderId::Alchemy` / config methods.
- [ ] Add the enum variant and configuration plumbing without exposing key material in `Debug`.
- [ ] Run targeted tests to GREEN.
- [ ] Commit.

### Task 2: Make the standard-Solana realtime stream provider-aware and bounded

**Files:**
- Modify: `crates/shreks-providers/src/pump_realtime.rs`
- Test: `crates/shreks-providers/tests/pump_realtime_stream.rs`

**Interfaces:**
- Produces: provider-aware `PumpRealtimeLogStreamConfig` constructors for Helius and Alchemy.
- Produces: each `PumpRealtimeNotification` carries its actual `ProviderId`.
- Produces: a configurable maximum consecutive connection-attempt budget for tests and a production default that prevents infinite silent retry.

- [ ] Write a failing local-websocket test that proves an Alchemy-configured stream emits `ProviderId::Alchemy` while preserving the same two `logsSubscribe` requests.
- [ ] Write a failing test that points at an unavailable local endpoint and requires the stream to return `Unavailable` after the configured attempt budget instead of retrying forever.
- [ ] Run targeted tests and verify both failures are for missing behavior.
- [ ] Implement provider identity on config/notifications and bounded connect retries with existing exponential backoff.
- [ ] Run targeted tests to GREEN.
- [ ] Commit.

### Task 3: Add ordered Helius -> Alchemy failover

**Files:**
- Modify: `crates/shreks-providers/src/pump_realtime.rs`
- Test: `crates/shreks-providers/tests/pump_realtime_stream.rs`

**Interfaces:**
- Produces: a realtime failover source implementing `PumpRealtimeSignalSource` over an ordered list of provider configs.
- Helius remains first when configured; Alchemy is attempted after Helius exceeds its connection-attempt budget.
- If all configured sources fail, return a provider error so the existing forwarder/writer fail-closed chain stops the observer.

- [ ] Write a failing test with an unavailable primary endpoint and a working secondary local WebSocket; require an event from the secondary provider.
- [ ] Write a failing test where every endpoint is unavailable; require a returned error within a bounded timeout.
- [ ] Verify RED.
- [ ] Implement minimal ordered rotation and active-provider reset behavior.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 4: Preserve provider provenance through durable evidence and canonical FastEvents

**Files:**
- Modify: `crates/shreks-observer/src/runtime.rs`
- Modify: `crates/shreks-observer/src/fast_event_normalizer.rs`
- Modify: `crates/shreks-providers/src/pump_trade.rs`
- Modify: `crates/shreks-providers/src/pump_swap_trade.rs`
- Test: `crates/shreks-observer/tests/pump_realtime_evidence.rs`
- Test: fast-event normalization tests

**Interfaces:**
- Writer stores `notification.provider`, never hardcoded Helius.
- Normalizer accepts only the explicit FL1 realtime providers `{Helius, Alchemy}`.
- Pump/PumpSwap conversion functions receive the source provider and write it into `FastEvent`.

- [ ] Write failing tests that persist Alchemy raw evidence and require Alchemy canonical event provenance.
- [ ] Verify RED.
- [ ] Thread provider identity through writer and converter calls; replace `require_helius` with a narrow realtime-provider allowlist.
- [ ] Verify targeted GREEN.
- [ ] Commit.

### Task 5: Wire fallback into `shreks-observe` and document host-only configuration

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Modify: `.env.example`
- Modify: `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`
- Test: `crates/shreks-observer/tests/runtime_config.rs`
- Test: repository safety/config tests as applicable

**Interfaces:**
- Runtime constructs ordered realtime configs from available keys: Helius first, Alchemy second.
- No API key is logged.
- No fallback means no realtime task; configured-but-unavailable providers fail closed after bounded attempts.

- [ ] Write failing runtime/config tests for Helius-primary/Alchemy-secondary ordering and secret-redacted startup behavior.
- [ ] Verify RED.
- [ ] Wire the failover source into the existing forwarder/writer/normalizer task group.
- [ ] Add `ALCHEMY_API_KEY=` to `.env.example` and host-only setup notes without a real key.
- [ ] Update FL1.5 runbook to record which provider produced accepted evidence and to treat all-provider exhaustion as a hold.
- [ ] Verify targeted GREEN.
- [ ] Commit.

### Task 6: Full verification, review, merge, release, and production acceptance

**Files:** no new production behavior unless verification reveals a defect.

- [ ] Run full Rust tests, Python tests, repository safety, and ARM64 release build in CI.
- [ ] Audit the PR diff for no wallet/signing/execution/LIVE authority and no secret material.
- [ ] Merge only with exact-head green CI.
- [ ] Create the normal sealed release through the existing release path.
- [ ] Deploy through the existing manual `production-paper` workflow.
- [ ] Configure the Alchemy key only in `/etc/shreks/shreks.env` on the VPS.
- [ ] Re-run FL1.5 real-host acceptance and require Pump + PumpSwap traffic, canonical progress, zero sequence violations, healthy latency samples, stable restarts/resources, and truthful provider provenance.
- [ ] Keep FL2 blocked and LIVE disabled until that evidence passes.
