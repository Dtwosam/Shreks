# Phase G3 24/7 Supervision and Restart Proof Verification Record

## Result

Phase G3 repository behavior is frozen and verified as a supervision/recovery-only change stacked on sealed G2.

- Sealed G2 base: `f71f448f79f2257e081f80e4a3caf2d0dfc6c9e7`
- Frozen G3 behavior SHA: `4571d0f3b2e9f1cffd7ddcb4bf22b923e1197ef7`
- Frozen behavior CI: `32907544456`
- Frozen behavior Python result: **2315 passed in 9.90s**
- Frozen behavior Rust/workspace: **GREEN**
- Frozen behavior repository safety: **GREEN**

This verification record is the sole intended change after the frozen behavior SHA.

**LIVE TRADING: DISABLED.**

## Scope and authority audit

GitHub compare from sealed G2 `f71f448f79f2257e081f80e4a3caf2d0dfc6c9e7` to frozen G3 behavior `4571d0f3b2e9f1cffd7ddcb4bf22b923e1197ef7` reports:

- status: ahead
- commits: **10**
- changed files: **12**
- behind: **0**

Changed files:

1. `crates/shreks-observer/tests/systemd_units.rs`
2. `deploy/release/release_manager.py`
3. `deploy/systemd/README.md`
4. `deploy/systemd/shreks-observe.service`
5. `deploy/systemd/shreks-paper-campaign.service`
6. `deploy/systemd/shreks-paper-evidence.service`
7. `deploy/systemd/shreks.target`
8. `docs/superpowers/plans/2026-08-25-phase-g3-supervision-restart-proof.md`
9. `docs/superpowers/specs/2026-08-25-phase-g3-supervision-restart-proof-design.md`
10. `python/src/shreks_brain/observer_campaign/runtime.py`
11. `python/tests/test_g2_release_manager.py`
12. `python/tests/test_observer_campaign_runtime.py`

No strategy/setup/scoring implementation or threshold changed. No risk policy or sizing threshold changed. No provider implementation/configuration changed. No storage schema/migration changed. No trade-intent, execution-adapter, ledger/accounting/checkpoint-core, registry/promotion, transaction-construction, signing/submission, wallet, or live-enable file changed.

Production diff audit:

- `python/src/shreks_brain/observer_campaign/runtime.py` adds only a read-only recovery preflight that reuses the existing bootstrap/load-state path, structured PAPER `READY` output, and strict CLI argument routing. It does not execute a cycle, construct a trade intent, promote, sign, submit, or enable live mode.
- `deploy/release/release_manager.py` only replaces target-only health gating with read-only `systemctl is-active --quiet` checks for observer, paper evidence, paper campaign, and `shreks.target`; the same check gates rollback success.
- systemd service changes only add persistent-path mount requirements, writable-state prechecks, bounded restart limits, target membership, and the PAPER recovery preflight. No policy/economic override, wallet secret, signing/submission command, or live-mode command was added.
- `shreks.target` changes child membership from `Wants=` to `Requires=` and remains wanted by `multi-user.target` for host-boot startup.
- the remaining changes are tests, design documentation, and the operator runbook.

Authority remains PAPER/observe/supervision only.

## Task 1 — persistent-state and bounded systemd supervision

### RED

- RED commit: `ece4501a1420cceaff2981bf456503219709d2e3`
- RED CI: `32905558734`
- Python: GREEN
- Repository safety: GREEN
- Rust: failed only the four new systemd supervision assertions, including missing persistent-path requirements and required target membership.

### GREEN

Implementation was split across two repository commits while preserving one behavior checkpoint:

- first unit commit: `f7b75411e2981379f7ad4d0ac6722ef8221fc2ee`
- final Task 1 behavior SHA: `1c3fc3e7c12ef9d5f68c7497c5cbb8f176a1cde9`
- GREEN CI: `32905775529`
- Python: **2308 passed in 10.03s**
- Rust/workspace: GREEN
- Repository safety: GREEN

Verified contract:

- required mounts for `/var/lib/shreks`, `/etc/shreks`, and `/opt/shreks/current`;
- `/var/lib/shreks` must exist and be writable before each service starts;
- `Restart=on-failure`, `RestartSec=5s`;
- `StartLimitIntervalSec=300`, `StartLimitBurst=5`;
- all runtime services are members of `shreks.target`;
- target requires observer, evidence, and campaign services;
- target remains enabled through `multi-user.target` semantics.

## Task 2 — read-only PAPER recovery preflight

### RED

- RED commit: `2877a9b2788b313cf59b6854f818d98721e5d1dc`
- RED CI: `32905933715`
- Rust/workspace: GREEN
- Repository safety: GREEN
- Python: failed at collection only because `preflight_observer_paper_campaign_runtime` did not yet exist.

### GREEN

- GREEN commit: `86d86f37112cebf9f8bbdc9e69ac9c73c983bbe9`
- GREEN CI: `32906027725`
- Python: **2313 passed in 9.98s**
- Rust/workspace: GREEN
- Repository safety: GREEN

Verified preflight behavior:

- loads the same runtime configuration and sealed bootstrap/recovery path as the PAPER loop;
- validates manifest, checkpoint/evidence attribution, restored state, and accounting through the existing runner path;
- emits structured PAPER `READY` metadata;
- does not call `run_cycle` or `evaluated_trades`;
- does not create or advance a checkpoint;
- does not rewrite E11 evidence;
- fails nonzero on uncertain recovery;
- accepts only normal runtime invocation or exactly `--preflight`; unsupported arguments fail closed before configuration loading.

## Task 3 — per-service deploy and rollback health gating

### RED

- RED commit: `6f146ae125bfc98da13fb5e8a6147c369f3424c3`
- RED CI: `32907123830`
- Rust/workspace: GREEN
- Repository safety: GREEN
- Python: **2310 passed, 5 failed**; all five failures were the new per-service health contract.

The RED failures proved the prior G2 target-only check could not detect an unhealthy child service and did not prove restored-child health after rollback.

### GREEN

- GREEN commit: `63609d0c5468d6bed9ade3fb3fd0d7c6b60a9063`
- GREEN CI: `32907269321`
- Python: **2315 passed in 10.87s**
- Rust/workspace: GREEN
- Repository safety: GREEN

Verified behavior:

- activation checks `shreks-observe.service`, `shreks-paper-evidence.service`, `shreks-paper-campaign.service`, then `shreks.target`;
- one unhealthy child fails activation even when the target object is active;
- a previous release is not claimed restored until every restored child and the target are active;
- an unhealthy restored child makes rollback fail closed;
- first-deploy child failure leaves no active release claim;
- health probes are read-only `systemctl is-active --quiet` commands.

## Task 4 — restart/reboot observability and runbook proof

### RED

- RED commit: `6be48fe9a6e72f235d711f287cbd461fdadfd413`
- RED CI: `32907399855`
- Python: GREEN
- Repository safety: GREEN
- Rust: exactly one new runbook-contract test failed; all existing runtime/systemd tests remained GREEN.

Existing sealed tests already prove observer state restoration and PAPER checkpoint/restart-idempotency behavior, so no new trading/application recovery mechanism was required.

### GREEN / frozen behavior

- GREEN/frozen behavior commit: `4571d0f3b2e9f1cffd7ddcb4bf22b923e1197ef7`
- GREEN CI: `32907544456`
- Python: **2315 passed in 9.90s**
- Rust/workspace: GREEN
- Repository safety: GREEN

The runbook now requires inspection of:

- `systemctl is-enabled shreks.target` for boot persistence;
- per-service `ActiveState`, `SubState`, `NRestarts`, `ExecMainStatus`, and `ActiveEnterTimestamp`;
- current-boot journals;
- active release provenance via `readlink -f /opt/shreks/current`;
- durable campaign manifest, SQLite database, and E11 evidence readability;
- `reset-failed` only after the root cause is resolved;
- no manual campaign launch and no bypass of the systemd recovery preflight/start-limit boundary.

## Recovery and duplicate-work proof

G3 does not introduce a second reconciliation or idempotency system. It relies on and re-proves the sealed runtime behavior already present:

- observer registry/state restoration reopens durable operational state after restart;
- PAPER bootstrap loads persisted campaign state before entering the autonomous loop;
- the campaign runner rejects invalid accounting and conflicting evidence attribution;
- checkpoint reload and restart equivalence are validated after each persisted cycle;
- an exact completed-cycle replay is idempotent rather than creating duplicate campaign work;
- any bootstrap/recovery uncertainty fails before a new autonomous PAPER cycle starts.

Systemd now ensures the persistent paths are available before those application-level checks execute and bounds repeated crash loops.

## Operational limitation

This phase proves repository behavior, systemd contracts, deterministic application restart behavior, and deployment/rollback health gating in CI.

A real physical VPS was **not** rebooted, process-killed, or recovered through this conversation because no execution-host control plane is connected here. Therefore a real-host reboot/process-failure exercise remains an operational production gate. That exercise must confirm the installed units, persistent storage, release symlink, service restart counters/journals, PAPER preflight, and durable state on the actual VPS before G3 is considered host-proven for F7 live-capital readiness.

No claim of profitability or live-capital readiness is made by G3.

## Seal condition

The intended seal is valid only if all of the following hold after this record is committed:

1. frozen behavior remains exactly `4571d0f3b2e9f1cffd7ddcb4bf22b923e1197ef7`;
2. behavior -> seal is exactly one commit;
3. this verification record is the only changed file after behavior freeze;
4. exact-seal CI reports Python **2315 passed**, Rust/workspace GREEN, and repository safety GREEN;
5. PR #44 remains draft and unmerged;
6. live trading remains disabled.
