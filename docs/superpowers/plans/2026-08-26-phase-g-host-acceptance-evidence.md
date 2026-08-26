# Phase G Host Acceptance Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and seal a non-numbered Phase G host-acceptance evidence harness that turns the remaining physical-host exit gates into canonical, secret-safe before/after records without adding trading, lifecycle, wallet, or live authority.

**Architecture:** Add a focused `shreks_brain.host_acceptance` package. Pure models/codec define the immutable evidence contract, a read-only collector reuses sealed G1-G8 APIs and allowlisted host probes, a pure comparator proves monotonic/no-loss restart/reboot/restore continuity, and a small CLI writes canonical private evidence files. Physical destructive drills remain outside the harness and outside repository CI.

**Tech Stack:** Python 3.12 standard library; existing Shreks PAPER/G7/G8 APIs; pytest; Rust repository contract tests for runbook/authority boundaries.

**Spec:** `docs/superpowers/specs/2026-08-26-phase-g-host-acceptance-evidence-design.md`

## Global Constraints

- Base exactly sealed G8 `99c5de232eb36e6fdd7777d089453f16c03ef38a`.
- This is not G9; the supplied build order ends Phase G at G8.
- `LIVE TRADING: DISABLED` throughout.
- Do not modify provider adapters, DB schema/migrations, strategy/setup/scoring/risk thresholds, sizing/slippage, fill/exit/accounting, profitability/proof formulas, promotion/registry, wallet/signing/submission, or live-execution behavior.
- Routine capture and compare paths must not invoke `systemctl start|stop|restart|enable|disable`, reboot, shutdown, kill, package managers, network clients, or arbitrary shell commands.
- Secret file contents are never opened, hashed, printed, or persisted by the harness.
- Missing/failed required evidence never becomes PASS.
- Repository CI may prove harness mechanics only; physical host acceptance remains pending until executed on the dedicated server.
- Use TDD: every production behavior starts with a failing test and a committed RED state.

---

### Task 1: Canonical evidence models and codec

**Files:**
- Create: `python/tests/test_phase_g_host_acceptance_models.py`
- Create: `python/src/shreks_brain/host_acceptance/__init__.py`
- Create: `python/src/shreks_brain/host_acceptance/models.py`
- Create: `python/src/shreks_brain/host_acceptance/codec.py`

**Interfaces:**
- Produces `HOST_ACCEPTANCE_SCHEMA_VERSION = "phase-g-host-acceptance-v1"`.
- Produces exact enums `HostAcceptanceStage`, `HostCheckStatus`.
- Produces immutable `SystemdUnitObservation`, `PaperRecoveryObservation`, `RiskControlObservation`, `ReleaseObservation`, `ProtectedPathObservation`, `DashboardExposureObservation`, `BackupObservation`, `HostResourceObservation`, and `HostAcceptanceRecord`.
- Produces `encode_host_acceptance_record(record) -> str`, `decode_host_acceptance_record(payload) -> HostAcceptanceRecord`, and `fingerprint_host_acceptance_record(record) -> str`.

- [ ] **Step 1: Write the failing model/codec tests**

Tests must define exact enum values, exact field validation, required unit ordering, no NaN/non-finite values, canonical UTF-8 JSON, exact-key decoding, canonical round trip, fingerprint validation, and overall PASS semantics. Include explicit tests that unknown keys/statuses/stages, malformed SHA-256 values, duplicate unit names, duplicate protected-path roles, and a required FAIL/UNAVAILABLE observation are rejected or keep overall status non-passing.

- [ ] **Step 2: Run full CI and verify RED**

Expected Python failure: `ModuleNotFoundError: No module named 'shreks_brain.host_acceptance'`. Rust and repository safety must stay GREEN.

- [ ] **Step 3: Implement minimal models and codec**

Use frozen dataclasses with slots, exact enum/type validation, canonical sorted JSON with `allow_nan=False`, newline termination, strict exact-key decoding, and the zero-fingerprint canonicalization rule from the design. Do not add host I/O yet.

- [ ] **Step 4: Run full CI to GREEN**

All existing tests plus Task 1 tests must pass.

- [ ] **Step 5: Commit GREEN**

Commit message: `feat: add canonical Phase G host evidence contract`.

---

### Task 2: Read-only host evidence collector

**Files:**
- Create: `python/tests/test_phase_g_host_acceptance_collector.py`
- Create: `python/src/shreks_brain/host_acceptance/collector.py`
- Modify: `python/src/shreks_brain/host_acceptance/__init__.py`

**Interfaces:**
- Consumes sealed `ObserverPaperCampaignRuntimeConfig` and `preflight_observer_paper_campaign_runtime()`.
- Consumes sealed `load_operator_risk_control_state()`.
- Consumes sealed `verify_backup_bundle()`.
- Produces `HostAcceptanceCaptureConfig` with explicit absolute paths, stage, host label, expected release SHA, dashboard port, and PAPER interval.
- Produces `collect_host_acceptance_record(config, *, command_runner=..., clock_unix_ms=..., boot_id_reader=..., resource_reader=...) -> HostAcceptanceRecord`.

- [ ] **Step 1: Write the failing collector tests**

Use temporary real files/SQLite fixtures plus an injected command runner. Cover:

- exact release symlink under `/opt/shreks/releases` semantics through injected paths;
- expected release SHA mismatch is FAIL;
- all core + telemetry/dashboard/alerts/backup units/timers observed through `systemctl show` and `systemctl is-enabled` only;
- command runner receives no shell string and no lifecycle verb;
- sealed PAPER preflight returns run/candidate/manifest/ledger continuity fields without advancing a cycle;
- G7 state loads through sealed decoder and reason text is omitted;
- newest valid G8 completed bundle is selected using `verify_backup_bundle()` while malformed/unrelated directories are untouched;
- secret paths are stat-only: monkeypatch secret `Path.read_bytes/read_text/open` to fail if called;
- dashboard port passes for loopback-only listeners and fails on `0.0.0.0`, `[::]`, or non-loopback addresses;
- missing required artifact/unit/listener/backup becomes FAIL/UNAVAILABLE, never PASS;
- output record overall status is PASS only when all required checks pass.

- [ ] **Step 2: Run full CI and verify RED**

Expected Python failure: collector module/API missing. Rust and repository safety remain GREEN.

- [ ] **Step 3: Implement minimal collector**

Use no shell. Command construction is internal and allowlisted. Parse only the allowlisted `systemctl show` properties. Stat secret paths but never open them. Construct the sealed PAPER runtime config directly from explicit paths; call preflight with a sink that discards the status line. Use sealed G7/G8 loaders/verifiers. Host resource collection is observational and does not invent thresholds.

- [ ] **Step 4: Run full CI to GREEN**

All tests pass with no behavior changes outside the new package.

- [ ] **Step 5: Commit GREEN**

Commit message: `feat: collect read-only Phase G host evidence`.

---

### Task 3: Restart/reboot/restore continuity comparator

**Files:**
- Create: `python/tests/test_phase_g_host_acceptance_compare.py`
- Create: `python/src/shreks_brain/host_acceptance/compare.py`
- Modify: `python/src/shreks_brain/host_acceptance/__init__.py`

**Interfaces:**
- Produces `HostContinuityVerdict` with exact values `PASS` and `FAIL`.
- Produces immutable `HostContinuityFinding` and `HostContinuityAssessment`.
- Produces `compare_host_acceptance_records(before, after) -> HostContinuityAssessment`.
- Produces canonical assessment encoder/decoder if an assessment is persisted by Task 4.

- [ ] **Step 1: Write failing comparator tests**

Cover:

- both records must independently be overall PASS;
- release SHA/run ID/candidate version/campaign fingerprint unchanged;
- after cycle time and ledger time cannot decrease;
- ledger entry count cannot decrease;
- every before processed intent key remains after;
- exact G7 revision/halt/kill/fingerprint continuity;
- `AFTER_PROCESS_RESTART` requires same boot ID;
- `AFTER_REBOOT` requires different boot ID;
- `AFTER_RESTORE_DRILL` does not impose boot-ID relation but retains all PAPER/G7 checks;
- an unexpected stage transition fails;
- comparator returns explicit findings rather than throwing for an ordinary continuity failure;
- no profitability or live-state decision is produced.

- [ ] **Step 2: Run full CI and verify RED**

Expected failure: comparator module/API missing only.

- [ ] **Step 3: Implement minimal pure comparator**

No filesystem, subprocess, network, trading, or service-control imports. Treat any violation as a deterministic FAIL finding. Keep ordering stable for canonical output.

- [ ] **Step 4: Run full CI to GREEN**

All tests pass.

- [ ] **Step 5: Commit GREEN**

Commit message: `feat: prove Phase G host continuity`.

---

### Task 4: Secret-safe CLI and physical-host runbook

**Files:**
- Create: `python/tests/test_phase_g_host_acceptance_runtime.py`
- Create: `python/src/shreks_brain/host_acceptance/runtime.py`
- Modify: `python/src/shreks_brain/host_acceptance/__init__.py`
- Create: `crates/shreks-observer/tests/phase_g_host_acceptance_runbook.rs`
- Create: `deploy/systemd/PHASE_G_HOST_ACCEPTANCE.md`

**Interfaces:**
- CLI `capture` consumes explicit paths and writes one private canonical evidence file.
- CLI `compare BEFORE AFTER --output FILE` validates canonical inputs and writes one private canonical assessment file.
- No lifecycle command exists in the parser.

- [ ] **Step 1: Write failing Python CLI tests**

Cover exact parser commands, required arguments, private atomic output mode `0600`, canonical records, nonzero exit for FAIL/UNAVAILABLE capture, nonzero exit for failed comparison, no secret value in stdout/stderr/output, and rejection of unknown/lifecycle-like subcommands.

- [ ] **Step 2: Write failing Rust runbook/authority contract**

Require the runbook to document:

- exact sealed G8 base and that this is a non-numbered Phase-G exit slice;
- installation/execution from the exact verified release;
- baseline -> process restart -> after capture -> compare;
- baseline -> host reboot -> after capture -> compare;
- G8 verified backup + isolated restore drill -> capture -> compare;
- G6 retry/delivery and G7 control drills referenced to their existing runbooks;
- secret values never copied into evidence;
- routine harness has no lifecycle authority;
- no physical-host PASS may be claimed from CI alone;
- rollback/release provenance evidence;
- `LIVE TRADING: DISABLED` and F7 remains separately gated.

The Rust test must also scan `python/src/shreks_brain/host_acceptance` for forbidden imports/markers covering wallet/signing/submission/live execution and for generated lifecycle command verbs in runtime/collector code.

- [ ] **Step 3: Run full CI and verify RED**

Python fails only on missing runtime; Rust fails only on missing runbook/authority evidence.

- [ ] **Step 4: Implement runtime CLI and runbook**

Use `argparse`, exact positive/absolute validation, canonical decoders, atomic temp-file + `os.replace`, `0600` output, and structured failure output that contains error type/reason code but not secret contents. Do not introduce a service/timer for the harness.

- [ ] **Step 5: Run full CI to GREEN**

All Python, Rust/workspace, and repository safety gates pass.

- [ ] **Step 6: Commit GREEN**

Commit message: `feat: add Phase G host acceptance operator workflow`.

---

### Task 5: Audit, freeze, and repository seal

**Files:**
- Modify only at seal: `docs/superpowers/plans/2026-08-26-phase-g-host-acceptance-evidence.md`

- [ ] **Step 1: Select frozen all-green behavior SHA**

Record exact CI and exact Python test cardinality.

- [ ] **Step 2: Compare sealed G8 -> frozen acceptance behavior**

Audit every changed file. Prove no provider adapter, DB schema/migration, strategy/setup/scoring/risk threshold, sizing/slippage, execution/accounting, profitability/proof, promotion/registry, wallet/signing/submission, live-enable, or existing G1-G8 authority drift.

- [ ] **Step 3: Replace this plan with the verification record in one docs-only commit**

The record must distinguish repository-sealed harness mechanics from still-pending physical-host evidence.

- [ ] **Step 4: Prove frozen -> seal is exactly one commit / one file / zero behind**

The sole file must be this verification record.

- [ ] **Step 5: Run exact-seal CI**

Require the exact frozen Python test cardinality plus Rust/workspace and repository safety GREEN.

- [ ] **Step 6: Update PR #50 with frozen/seal evidence**

Keep it open, draft, and unmerged.

- [ ] **Step 7: Re-fetch PR metadata**

Prove state `open`, `draft=true`, `merged=false`, head exactly the seal SHA.

## Physical-host evidence retained after repository seal

The repository seal must not mark Phase G physically complete. Remaining host execution must include at least:

1. exact sealed release deployed through the G2 path on the dedicated Linux host;
2. passing baseline host-acceptance capture;
3. actual process-kill/restart drill and passing continuity comparison;
4. actual server reboot and passing continuity comparison;
5. dashboard reachable only through the intended private/TLS path;
6. real G6 notification delivery/retry evidence;
7. real G7 halt and kill-control propagation evidence;
8. production-shaped G8 backup plus isolated restore drill and passing continuity comparison;
9. rollback to a prior verified release and forward recovery evidence;
10. continued PAPER/proof evidence sufficient for the separate profitability gates.

Only then can the Phase-G exit criterion be described as host-proven. F7 tiny-capital live remains separately disabled until every prior live-readiness/proof gate is satisfied.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
