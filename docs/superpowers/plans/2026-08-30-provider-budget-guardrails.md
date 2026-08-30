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

- [ ] **Step 1: Add a transport-backed test that configures a budget of 1, lets the first RPC reach the test server, then asserts the second call fails locally and the server saw exactly one request.**
- [ ] **Step 2: Add a test asserting provider Debug/usage telemetry contains no API key.**
- [ ] **Step 3: Commit tests only.**
- [ ] **Step 4: Open a draft PR and use exact-head CI as RED evidence; Rust must fail because the budget API does not yet exist while repository safety remains green.**

### Task 2: Helius request budget GREEN

**Files:**
- Modify: `crates/shreks-providers/src/helius.rs`.

**Interfaces:**
- Add an internal atomic request counter shared by cloned providers.
- `with_request_budget(max_requests: u64) -> Self` rejects zero by construction choice in runtime config; provider method stores a positive ceiling.
- `request_usage() -> HeliusRequestUsage` returns non-secret `{ attempted, limit: Option<u64>, remaining: Option<u64>, exhausted }`.
- `post_rpc` reserves before HTTP transport; exhausted reservation returns `ProviderErrorKind::RateLimited` or the repository's existing rate-limit-equivalent kind without network I/O.

- [ ] **Step 1: Implement minimal shared atomic budget state and reservation.**
- [ ] **Step 2: Run exact-head CI and confirm provider tests turn GREEN.**
- [ ] **Step 3: Commit the implementation.**

### Task 3: Paper-evidence configuration RED/GREEN

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/config.rs`.
- Modify: `crates/shreks-observer/tests/paper_evidence_binary.rs` and/or existing runtime-config tests.
- Modify: `.env.example`.

**Interfaces:**
- Add `holder_refresh: Duration` from required `SHREKS_PAPER_HOLDER_REFRESH_SECONDS`.
- Add `helius_max_requests_per_process: u64` from required `SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS`.

- [ ] **Step 1: Add failing config tests for missing, zero, and invalid values plus successful parsing.**
- [ ] **Step 2: Implement strict parsing with no production defaults.**
- [ ] **Step 3: Update `.env.example` with blank explicit values and comments describing them as operational cost guardrails.**
- [ ] **Step 4: Verify Rust tests on exact head.**

### Task 4: Holder freshness RED/GREEN

**Files:**
- Modify: `crates/shreks-storage/src/...` exact file containing holder-distribution persistence/read methods.
- Modify: `crates/shreks-observer/src/safety_evidence.rs`.
- Modify: existing safety-evidence/storage tests.

**Interfaces:**
- Add storage read method returning the latest holder-distribution observation timestamp for a candidate.
- Extend `SafetyEvidenceCollector::collect_candidate` with a freshness boundary or add a backwards-compatible `collect_candidate_with_policy` API used by paper evidence.
- Fresh evidence suppresses only holder-distribution provider calls; mint-state and quote semantics stay unchanged.

- [ ] **Step 1: Add a failing storage/collector test showing fresh holder evidence produces zero distribution-provider calls.**
- [ ] **Step 2: Add a complementary stale-evidence test showing the provider is called.**
- [ ] **Step 3: Implement the smallest storage query and collector branch.**
- [ ] **Step 4: Run focused Rust tests and exact-head CI.**

### Task 5: Wire budget + freshness into paper runtime

**Files:**
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/main.rs`.
- Modify: `crates/shreks-observer/src/bin/shreks-paper-evidence/cycle.rs`.
- Modify: runtime tests.

**Interfaces:**
- Construct Helius with `.with_request_budget(config.helius_max_requests_per_process)`.
- Compute `holder_refresh_after_unix_ms = as_of_unix_ms - config.holder_refresh.as_millis()` using checked conversion.
- Pass the boundary to evidence collection.
- Log non-secret request usage totals/exhaustion per cycle.

- [ ] **Step 1: Add failing runtime/cycle tests for freshness boundary propagation and budget configuration.**
- [ ] **Step 2: Wire the configuration and telemetry.**
- [ ] **Step 3: Verify all focused tests and exact-head CI.**

### Task 6: Observer-side optional Helius ceiling

**Files:**
- Modify: `crates/shreks-providers/src/config.rs`.
- Modify: `crates/shreks-observer/src/runtime.rs`.
- Modify: provider/runtime config tests.
- Modify: `.env.example`.

**Interfaces:**
- Parse optional positive `SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS`.
- When present, construct the observer Helius provider with the same request-budget implementation.
- Absence preserves compatibility; production deployment must set it before services are restarted.

- [ ] **Step 1: Add failing parsing/wiring tests.**
- [ ] **Step 2: Implement optional parsing and provider construction.**
- [ ] **Step 3: Verify provider/runtime tests and exact-head CI.**

### Task 7: Source-of-truth and operations update

**Files:**
- Modify: `SHREKS_MASTER_SOURCE_OF_TRUTH.md` if present at repo root.
- Modify: `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`.

**Interfaces:**
- Add explicit provider-consumption/cost burden as required operational health evidence.
- State that budget exhaustion is fail-closed and cannot satisfy FL1.5.
- State that metered full-program realtime ingestion must be measured and bounded before 24/7 production; paid infrastructure is never silently assumed.

- [ ] **Step 1: Update durable architecture documentation without changing live authority.**
- [ ] **Step 2: Verify docs contain no secrets and acceptance rules remain stricter, not weaker.**

### Task 8: Final verification and PR readiness

**Files:** no new production scope.

- [ ] **Step 1: Confirm exact PR head contains only intended guardrail/docs/test changes.**
- [ ] **Step 2: Require all four exact-head CI gates GREEN: repository safety, Rust, Python, ARM64 release build.**
- [ ] **Step 3: Review diff for provider authority, DB semantics, strategy, signing, PAPER/LIVE authority drift.**
- [ ] **Step 4: Only after GREEN, merge through the normal sealed-release path. Do not restart production services until the release is deployed and explicit host budgets are configured.**

## Self-review

- Spec coverage: request budget, holder deduplication, telemetry, fail-closed semantics, secret protection, no realtime-topology change are each mapped to tasks.
- Placeholder scan: no TODO/TBD steps.
- Type consistency: paper config fields and Helius budget API are named consistently across tasks.
