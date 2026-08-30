# Provider Budget Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound confirmed Helius request amplification and suppress unnecessary repeated holder-distribution probes without weakening evidence or trading safety semantics.

**Architecture:** Add a request-count budget inside the Helius adapter, explicit production configuration in observer/paper-evidence runtimes, and SQLite-backed holder-evidence freshness suppression in the safety collector. Keep the current realtime topology unchanged in this PR and explicitly leave the WebSocket-firehose redesign to the next isolated change.

**Tech Stack:** Rust, Tokio, reqwest, rusqlite-backed `ShreksDb`, systemd environment configuration, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-30-provider-budget-guardrails-design.md`

## Global Constraints

- LIVE TRADING remains disabled.
- FL1.5 remains HOLD until physical-host acceptance passes.
- No provider key or endpoint may be logged, committed, or emitted in evidence.
- No strategy, PAPER decision policy, signing, wallet, canonical-event, or FL2 authority changes.
- Paid infrastructure must not become a hidden runtime requirement.
- TDD: tests land and fail before production behavior is implemented.

---

### Task 1: Helius request budget RED

**Files:**
- Modify: `crates/shreks-providers/tests/helius_adapter.rs` or the existing Helius provider test file containing HTTP transport tests.
- Modify later: `crates/shreks-providers/src/helius.rs`.

**Interfaces:**
- Produces desired constructor/builder behavior: `HeliusProvider::new(...).with_request_budget(max_requests)`.
- Produces telemetry behavior: bounded request count and remaining count without exposing credentials.

- [x] **Step 1: Add a transport-backed test that configures a budget of 1, lets the first RPC reach the test server, then asserts the second call fails locally and the server saw exactly one request.**
- [x] **Step 2: Add a test asserting provider Debug/usage telemetry contains no API key.**
- [x] **Step 3: Commit tests only.**
- [x] **Step 4: Open a draft PR and use exact-head CI as RED evidence; Rust must fail because the budget API does not yet exist while repository safety remains green.**

### Task 2: Helius request budget GREEN

**Files:**
- Modify: `crates/shreks-providers/src/helius.rs`.

**Interfaces:**
- Add an internal atomic request counter shared by cloned providers.
- `with_request_budget(max_requests: u64)` rejects zero and stores a positive ceiling.
- `request_usage() -> HeliusRequestUsage` returns non-secret `{ attempted, limit: Option<u64>, remaining: Option<u64>, exhausted }`.
- `post_rpc` reserves before HTTP transport; exhausted reservation returns `ProviderErrorKind::RateLimited` without network I/O.

- [x] **Step 1: Implement minimal shared atomic budget state and reservation.**
- [x] **Step 2: Run exact-head CI and confirm provider tests turn GREEN.**
- [x] **Step 3: Commit the implementation.**

### Task 3: Paper-evidence configuration RED/GREEN

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/config.rs`.
- Modify: `crates/shreks-observer/tests/paper_evidence_binary.rs` and runtime-config tests.
- Modify: `.env.example`.

**Interfaces:**
- Add `holder_refresh: Duration` from required `SHREKS_PAPER_HOLDER_REFRESH_SECONDS`.
- Add `helius_max_requests_per_process: u64` from required `SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS`.

- [x] **Step 1: Add failing config tests for missing, zero, and invalid values plus successful parsing.**
- [x] **Step 2: Implement strict parsing with no production defaults.**
- [x] **Step 3: Update `.env.example` with blank explicit values and comments describing them as operational cost guardrails.**
- [x] **Step 4: Verify Rust tests on exact head.**

### Task 4: Holder freshness RED/GREEN

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/candidate_store.rs`.
- Modify: `crates/shreks-observer/src/safety_evidence.rs`.
- Modify: existing safety-evidence/candidate-store tests.

**Interfaces:**
- Add a read-only holder-distribution freshness query over the existing durable table; do not change schema.
- Keep `SafetyEvidenceCollector::collect_candidate` backward-compatible and add a holder-probe control used only by paper evidence.
- Fresh evidence suppresses only holder-distribution provider calls; mint-state and quote semantics stay unchanged.

- [x] **Step 1: Add a failing storage/collector test showing fresh holder evidence produces zero distribution-provider calls.**
- [x] **Step 2: Add a complementary stale-evidence test showing the provider is called.**
- [x] **Step 3: Implement the smallest read-only query and collector branch.**
- [x] **Step 4: Repair the schema-validation boundary so candidate-only readers are not forced to require holder tables.**
- [x] **Step 5: Run focused Rust tests and exact-head CI.**

### Task 5: Wire budget + freshness into paper runtime

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/main.rs`.
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/cycle.rs`.
- Modify: runtime tests.

**Interfaces:**
- Construct Helius with `.with_request_budget(config.helius_max_requests_per_process)`.
- Compute the holder freshness boundary from `as_of_unix_ms` and `holder_refresh`, failing safe toward collection if conversion cannot be represented.
- Suppress only the holder lane when durable evidence is fresh.
- Log non-secret request usage totals/exhaustion per cycle.

- [x] **Step 1: Add failing runtime/cycle tests for freshness boundary propagation and budget configuration.**
- [x] **Step 2: Wire the configuration and telemetry.**
- [x] **Step 3: Verify all focused tests and exact-head CI.**

### Task 6: Observer-side required Helius HTTP ceiling

**Files:**
- Modify: `crates/shreks-providers/src/config.rs`.
- Modify: `crates/shreks-observer/src/runtime.rs`.
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`.
- Modify: provider/runtime config tests.
- Modify: `.env.example`.

**Interfaces:**
- Parse `SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS` as a positive integer.
- Require it whenever `HELIUS_API_KEY` is enabled in `ObserverRuntimeConfig`; Helius-free Chainstack/Alchemy plans remain valid without it.
- Fail closed again inside raw observer-builder entry points so direct `ProviderConfig` callers cannot bypass the runtime-config gate.
- Apply the same request-budget implementation to both Helius HTTP construction paths.
- Do not apply or claim this ceiling for WebSocket push consumption.

- [x] **Step 1: Add failing parsing tests showing Helius-enabled observer startup requires the ceiling while Helius-free operation remains valid.**
- [x] **Step 2: Implement parsing and runtime fail-closed validation.**
- [x] **Step 3: Add a second RED wiring test requiring both Helius HTTP builders to apply the ceiling.**
- [x] **Step 4: Implement bounded provider construction in both builders.**
- [x] **Step 5: Expose the blank required key in `.env.example` with an explicit HTTP-vs-WebSocket distinction.**
- [ ] **Step 6: Confirm exact-head Rust/ARM64 CI GREEN after the complete branch documentation state is committed.**

### Task 7: Source-of-truth and operations update

**Files:**
- Modify: `SHREKS_MASTER_SOURCE_OF_TRUTH.md`.
- Modify: `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`.

**Interfaces:**
- Add explicit provider-consumption/cost burden as required operational health evidence.
- State that HTTP request-budget exhaustion is fail-closed and cannot satisfy FL1.5.
- State that per-process budgets reset on restart and cannot be treated as monthly/cross-process ledgers or bypassed by restart.
- State that metered full-program realtime ingestion must be measured and bounded before 24/7 production; paid infrastructure is never silently assumed.
- Keep protected database/WAL evidence reads under the `shreks` service identity.

- [x] **Step 1: Update durable architecture documentation without changing live authority.**
- [ ] **Step 2: Update FL1.5 physical-host acceptance and repair the protected DB/WAL metadata-read commands.**
- [ ] **Step 3: Verify docs contain no secrets and acceptance rules remain stricter, not weaker.**

### Task 8: Final verification and PR readiness

**Files:** no new production scope.

- [ ] **Step 1: Confirm exact PR head contains only intended guardrail/docs/test changes.**
- [ ] **Step 2: Require all four exact-head CI gates GREEN: repository safety, Rust, Python, ARM64 release build.**
- [ ] **Step 3: Review diff for provider authority, DB semantics, strategy, signing, PAPER/LIVE authority drift.**
- [ ] **Step 4: Only after GREEN, merge through the normal sealed-release path. Do not restart production services; complete the separate realtime-firehose redesign before production reactivation.**

## Self-review

- Spec coverage: request budget, holder deduplication, telemetry, fail-closed semantics, secret protection, and the explicit realtime-topology boundary are mapped to tasks.
- Placeholder scan: no TODO/TBD steps.
- Type consistency: paper config fields, observer config field, and Helius budget API are named consistently across tasks.
- Safety consistency: LIVE remains disabled; FL1.5 remains HOLD; HTTP ceilings are not represented as total realtime/provider spend ceilings.
