# Phase G Host Acceptance Evidence Design

**Base:** sealed G8 `99c5de232eb36e6fdd7777d089453f16c03ef38a`  
**Branch:** `feat/phase-g-host-acceptance-evidence`

**LIVE TRADING: DISABLED.**

## Status and scope

The supplied build order ends Phase G at G8. There is no approved G9. G1-G8 repository behavior is sealed, but their verification records explicitly retain physical-host gates that repository CI cannot prove: installed release provenance, real systemd supervision, process restart, host reboot, private listener exposure, alert delivery/retry, durable backup availability, restore drill behavior, and continuity of authoritative PAPER/safety state.

This slice is therefore a **non-numbered Phase G exit-evidence harness**. It does not add a new trading feature. It converts the remaining real-host exit gates into canonical, secret-safe evidence that can be captured on the dedicated Linux host and compared before/after operational drills.

Repository CI can seal the harness mechanics. It cannot claim that a physical host passed until the harness is executed there around the required drills.

## Goals

1. Produce one canonical immutable host-evidence record from read-only observations of the sealed G1-G8 system.
2. Prove routine restart and reboot continuity without inventing financial formulas or requiring exact equality of state that may legitimately advance while PAPER runs.
3. Verify exact release provenance, core/independent unit health, sealed PAPER preflight, G7 risk-control continuity, G8 backup validity, and dashboard loopback exposure.
4. Record protected-file metadata without reading or emitting secret contents.
5. Keep routine capture free of `systemctl start/stop/restart`, reboot, shutdown, trade, promotion, wallet, signer, transaction, or live-enable authority.
6. Keep destructive actions such as process-kill, reboot, restore installation, and service restart as separate operator/host procedures. The evidence harness observes before and after; it does not cause them.

## Non-goals

- No G9 feature.
- No daemon, timer, web endpoint, Telegram command, or auto-remediation loop.
- No provider, strategy, setup, scoring, risk-threshold, sizing, slippage, fill, exit, accounting, profitability, proof, promotion, or registry changes.
- No wallet/private-key access.
- No transaction construction/signing/submission.
- No live enablement.
- No secret-value capture.
- No hidden minimum CPU/RAM/disk thresholds. Resource values are evidence unless an existing sealed contract already defines a pass/fail rule.
- No claim that repository CI proves a VPS reboot or physical restore.

## Package layout

Create `python/src/shreks_brain/host_acceptance/`:

- `models.py` — exact immutable evidence/check/continuity models and enums.
- `codec.py` — canonical JSON encoder/decoder and evidence fingerprinting.
- `collector.py` — read-only collection from injected host command/filesystem probes plus sealed PAPER/G7/G8 APIs.
- `compare.py` — continuity evaluation between two canonical evidence records.
- `runtime.py` — explicit CLI for `capture` and `compare`; no lifecycle commands.
- `__init__.py` — narrow public API.

Tests live in:

- `python/tests/test_phase_g_host_acceptance_models.py`
- `python/tests/test_phase_g_host_acceptance_collector.py`
- `python/tests/test_phase_g_host_acceptance_compare.py`
- `python/tests/test_phase_g_host_acceptance_runtime.py`
- `crates/shreks-observer/tests/phase_g_host_acceptance_runbook.rs`

Operator procedure:

- `deploy/systemd/PHASE_G_HOST_ACCEPTANCE.md`

No existing trading or deployment implementation file needs to change.

## Evidence schema

Schema version: `phase-g-host-acceptance-v1`.

### `HostAcceptanceStage`

Exact values:

- `BASELINE`
- `AFTER_PROCESS_RESTART`
- `AFTER_REBOOT`
- `AFTER_RESTORE_DRILL`

### `HostCheckStatus`

Exact values:

- `PASS`
- `FAIL`
- `UNAVAILABLE`

`UNAVAILABLE` is never promoted to `PASS` by the collector or comparator.

### `SystemdUnitObservation`

For each required unit, record only allowlisted systemd metadata:

- `unit_name`
- `required`
- `active_state`
- `sub_state`
- `enabled_state`
- `n_restarts`
- `exec_main_status`
- `active_enter_timestamp`
- `check_status`

Core required units:

- `shreks-observe.service`
- `shreks-paper-evidence.service`
- `shreks-paper-campaign.service`
- `shreks.target`

Independent Phase-G units/timers required for full host exit evidence:

- `shreks-telemetry.timer`
- `shreks-dashboard.service`
- `shreks-alerts.timer`
- `shreks-backup.timer`

The collector uses only `systemctl show` and `systemctl is-enabled` for these observations. It never calls lifecycle verbs.

A unit observation is `PASS` only when its sealed role requires it active/enabled and the observed metadata satisfies that exact role. Failure/command error becomes `FAIL` or `UNAVAILABLE`; no inferred success.

### `PaperRecoveryObservation`

Derived by constructing the existing `ObserverPaperCampaignRuntimeConfig` from explicit absolute paths and calling sealed `preflight_observer_paper_campaign_runtime()`.

Record:

- `paper_run_id`
- `candidate_version`
- `campaign_manifest_fingerprint_sha256`
- `last_cycle_at_unix_ms`
- `ledger_as_of_unix_ms`
- `ledger_entry_count`
- sorted `processed_intent_keys`
- sorted currently managed/open position IDs
- `preflight_status`

The collector does not execute a PAPER cycle.

### `RiskControlObservation`

Load through sealed `load_operator_risk_control_state()` and record:

- schema version
- revision
- halt-new-entries
- kill-switch-active
- updated timestamp
- last command
- last source
- SHA-256 of canonical state-file bytes
- check status

The reason text is not required in the acceptance record because it may contain operator context and is unnecessary for continuity proof.

### `ReleaseObservation`

The caller must provide the expected sealed release SHA. The collector records:

- expected SHA
- resolved `/opt/shreks/current` target
- target directory name
- current target is a symlink under `/opt/shreks/releases`
- `RELEASE_MANIFEST.json` exists as a regular non-symlink file
- manifest-byte SHA-256
- target directory name equals expected SHA
- check status

This is a provenance check, not a reimplementation of sealed G2 release-manager validation. G2 remains the authority that verifies/stages/activates release bundles.

### `ProtectedPathObservation`

For required protected runtime paths, record metadata only:

- logical role
- path
- exists
- regular file/directory
- symlink flag
- numeric mode
- owner UID
- group GID
- byte size for regular files
- check status where an exact sealed permission rule exists

Never read or hash secret-file contents. Secret roles include at least dashboard password and Telegram bot token. Non-secret immutable/runtime evidence may be hashed only when needed by an existing sealed contract.

### `DashboardExposureObservation`

Caller provides the configured dashboard port. The collector invokes a read-only listener probe and requires every TCP listener for that port to bind only loopback (`127.0.0.1` or `::1`). Public/wildcard binding is `FAIL`. No listener is `FAIL` for a full host-acceptance capture because G5 is required by the Phase-G exit criterion.

The command runner is injectable in tests and must be invoked without a shell.

### `BackupObservation`

The collector examines only completed directories under the explicit backup root, newest first, and calls sealed `verify_backup_bundle()` until it finds the newest valid completed bundle. It records:

- whether a verified bundle exists
- bundle directory name/path
- bundle creation timestamp
- paper run ID
- campaign manifest fingerprint
- manifest file SHA-256
- check status

Malformed/unrelated directories are never deleted or modified.

### `HostResourceObservation`

Record read-only host facts required for operational evidence:

- boot ID
- uptime seconds
- load average where available
- total/free/available memory bytes where available
- filesystem total/free bytes for `/var/lib/shreks`

These are observations, not new safety thresholds. Missing data is explicit.

### `HostAcceptanceRecord`

Contains:

- schema version
- capture stage
- captured-at Unix milliseconds
- host identifier hash derived from an explicit caller-supplied non-secret host label (not hostname by default)
- release observation
- systemd observations
- PAPER recovery observation
- G7 control observation
- G8 backup observation
- dashboard exposure observation
- protected-path observations
- resource observation
- overall status
- evidence fingerprint SHA-256

`overall_status=PASS` only if every required check is `PASS`. Any required `FAIL`/`UNAVAILABLE` keeps the record non-passing. Resource observations without sealed thresholds do not manufacture failure or success beyond successful collection.

## Canonical encoding

Use the repository's existing strict pattern:

- exact dataclass keys;
- exact enum strings;
- UTF-8 only;
- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`;
- newline-terminated canonical record;
- decoder rejects unknown/missing keys, NaN/Infinity, invalid enum values, and non-canonical encodings;
- evidence fingerprint is SHA-256 over the canonical document with the fingerprint field temporarily set to 64 lowercase zeroes.

Output writes use private atomic replace with file mode `0600`. The only filesystem mutation owned by the harness is its explicit evidence output file.

## Host command boundary

Production command runner may invoke only these read-only commands:

- `systemctl show <allowlisted-unit> ...`
- `systemctl is-enabled <allowlisted-unit>`
- `ss -ltnH` for dashboard listener evidence

No shell, `sudo`, `journalctl`, lifecycle verb, reboot/shutdown, package manager, network client, or arbitrary command execution is exposed through the public API.

Tests use an injected command runner and must prove a lifecycle command cannot be generated by normal capture or compare paths.

## Continuity comparison

`compare_host_acceptance_records(before, after)` returns an immutable `HostContinuityAssessment` with explicit findings and a verdict.

Common requirements:

- both records independently validate/canonical-decode;
- exact expected release SHA remains unchanged unless the comparator is explicitly invoked for a deployment/rollback continuity case in a later approved extension;
- paper run ID unchanged;
- candidate version unchanged;
- campaign manifest fingerprint unchanged;
- `after.last_cycle_at_unix_ms >= before.last_cycle_at_unix_ms`;
- `after.ledger_as_of_unix_ms >= before.ledger_as_of_unix_ms`;
- `after.ledger_entry_count >= before.ledger_entry_count`;
- every `before.processed_intent_key` remains present after;
- G7 risk-control state fingerprint/revision/halt/kill values remain exactly unchanged for restart/reboot/restore drills unless a future explicit comparator policy says otherwise;
- both records must have required overall status `PASS`.

Stage-specific boot proof:

- `AFTER_PROCESS_RESTART`: boot ID must be unchanged.
- `AFTER_REBOOT`: boot ID must differ.
- `AFTER_RESTORE_DRILL`: no boot-ID relation is required, but authoritative PAPER/G7 continuity checks still apply.

The comparator does **not** require exact ledger/state equality because a healthy PAPER process may advance between captures. It proves monotonic/no-loss properties and relies on the sealed PAPER preflight/accounting invariants for internal consistency.

No continuity verdict proves profitability.

## CLI

`python -m shreks_brain.host_acceptance.runtime capture ...`

Required explicit arguments include:

- stage
- output path
- non-secret host label
- expected release SHA
- observer DB path
- E11 path
- campaign manifest path
- G7 risk-control path
- backup root
- dashboard port
- existing positive PAPER interval value needed only to construct the sealed runtime config

Optional explicit paths include G6 alert state and other protected/read-side artifacts when deployed.

`capture` exits zero only when it produced a canonical record whose required checks all pass. It still writes a canonical FAIL/UNAVAILABLE record on an observed acceptance failure when safe to do so, so failure evidence is retained.

`python -m shreks_brain.host_acceptance.runtime compare BEFORE AFTER --output ASSESSMENT`

`compare` is offline/read-only with respect to authoritative Shreks state and exits zero only for a passing continuity assessment.

There is deliberately no `restart`, `reboot`, `restore-install`, `start`, `stop`, `kill`, `resume`, `enable-live`, `buy`, or `sell` command.

## Operator drill sequence

The runbook separates observation from destructive host actions:

1. Deploy an exact sealed release through G2's verified path.
2. Capture `BASELINE` evidence.
3. Perform the process-restart drill using the documented host procedure; capture `AFTER_PROCESS_RESTART`; compare.
4. Perform the host reboot through the operator/cloud control plane; capture `AFTER_REBOOT`; compare.
5. Verify an actual G8 backup, restore it into isolated staging, perform the documented manual restore drill on a non-live host/sandbox, capture `AFTER_RESTORE_DRILL`; compare.
6. Exercise G6 delivery/retry and G7 halt/kill propagation using their existing runbooks and retain their evidence.
7. Only after all physical-host gates pass may Phase G be described as host-proven. F7 remains separately gated by the full profitability/proof/live-readiness requirements.

The harness itself never performs steps 3-5's destructive actions.

## Security and profitability boundary

- Secret values never enter evidence files.
- The collector never opens wallet/private-key/seed files.
- No transaction authority is imported.
- No live mode is enabled.
- No numeric trading/risk/profitability threshold is added.
- A host-acceptance PASS means the production-operations layer behaved consistently; it does not mean the strategy has positive expectancy.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
