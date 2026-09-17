# FL9 V2 Discovery Request Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let FL9 V2 runtime-manifest discovery recover the five explicit non-manifest hydration assumptions from a preserved canonical V2 host request and its fingerprint-bound hydration policy, without reusing stale scoring authority.

**Architecture:** Add one historical-authority resolver inside the existing read-only discovery module. It strict-decodes the prior V2 request and referenced canonical hydration policy, proves the request binds the current frozen cohort and exact policy fingerprint, extracts only the five non-runtime assumptions, then delegates to the existing candidate discovery path. Existing explicit-input mode remains available and mutually exclusive.

**Tech Stack:** Python 3, existing Shreks canonical codecs/fingerprints, pytest, GitHub Actions canonical Python/Rust/repository-safety/ARM64 CI.

**Spec:** `docs/superpowers/specs/2026-09-17-fl9-v2-discovery-request-authority-design.md`

## Global Constraints

- Main/base SHA is `47332667144c40ff37dc4e05fb71ce32374d7d51` unless repository state changes before merge.
- No write path, SQLite access, provider/network calls, model fitting, PAPER execution, promotion, signing, submission, or LIVE authority may enter the discovery module.
- A prior V2 request is historical authority for the five non-manifest hydration assumptions only; it is never reused as the current scoring request.
- Runtime-derived hydration fields must continue to come only from each authenticated PAPER runtime manifest.
- Existing G8 backup verification and V2 quote-policy compatibility behavior must remain fail-closed.

---

### Task 1: RED contracts for prior-request authority

**Files:**
- Modify: `python/tests/test_fl9_v2_runtime_manifest_discovery.py`

**Interfaces:**
- Consumes: existing V2 host-request encoder/writer helpers and hydration-policy codec.
- Produces: failing tests that define `discover_fl9_v2_runtime_manifests_from_v2_request_authority(...)` and CLI authority-mode behavior.

- [ ] **Step 1: Add a fixture that writes a canonical prior V2 request whose hydration policy deliberately carries a quote mint incompatible with the current cohort but whose five non-manifest values are distinctive.**
- [ ] **Step 2: Add a test requiring request-authority discovery to produce a compatible candidate from a WSOL-compatible runtime manifest while preserving the prior request/policy fingerprints in `non_manifest_input_authority`.**
- [ ] **Step 3: Add tests proving tampered request bytes, current-cohort fingerprint mismatch, tampered/replaced policy bytes, and request/policy fingerprint mismatch fail closed.**
- [ ] **Step 4: Add CLI tests requiring `--v2-host-request-authority` to be mutually exclusive with explicit non-manifest flags and requiring all five explicit values when request authority is absent.**
- [ ] **Step 5: Push the RED commit and verify Python fails only because the new resolver/CLI mode is absent while unrelated canonical lanes remain green.**

### Task 2: Minimal request-authority resolver

**Files:**
- Modify: `python/src/shreks_brain/fl9_v2_runtime_manifest_discovery.py`
- Test: `python/tests/test_fl9_v2_runtime_manifest_discovery.py`

**Interfaces:**
- Consumes: `decode_fast_first_champion_v2_host_request`, `decode_fast_forecast_context_hydration_policy`, `fast_forecast_context_hydration_policy_fingerprint_sha256`, existing stable-file reader, and existing `discover_fl9_v2_runtime_manifests`.
- Produces: `discover_fl9_v2_runtime_manifests_from_v2_request_authority(...) -> dict[str, object]` plus request-authority provenance in the report.

- [ ] **Step 1: Stable-read and strict-decode the prior request.**
- [ ] **Step 2: Authenticate the current frozen cohort and require its artifact fingerprint to equal the request binding.**
- [ ] **Step 3: Stable-read and strict-decode the request-referenced hydration policy and require its computed fingerprint to equal the request binding.**
- [ ] **Step 4: Extract exactly `version`, `strategy_families`, `max_exit_quote_age_ms`, `execution_cost_policy_version`, and `expected_round_trip_cost_bps`; do not copy any runtime-derived field.**
- [ ] **Step 5: Delegate candidate evaluation to the existing discovery function and add bounded provenance under `non_manifest_input_authority`.**
- [ ] **Step 6: Update CLI parsing to support either request authority or the complete existing explicit-input set, never both/partial.**
- [ ] **Step 7: Run focused Python tests and push GREEN.**

### Task 3: Full verification and review

**Files:**
- Review only: complete branch diff.

**Interfaces:**
- Consumes: Task 2 implementation.
- Produces: merge-ready implementation evidence; no release authorization yet.

- [ ] **Step 1: Require branch/PR Python, Rust, repository-safety, and ARM64 lanes to pass.**
- [ ] **Step 2: Inspect the diff for any write/trading/privilege authority creep.**
- [ ] **Step 3: Confirm the stale request cannot be executed or republished by the new code path.**
- [ ] **Step 4: Merge only after exact-head PR CI is green, then require exact merged-main CI green.**
- [ ] **Step 5: Create a separate docs-only `seal:` commit only after merged-main implementation evidence is green; that later seal may authorize immutable release/deploy and read-only production discovery, never scoring.**
