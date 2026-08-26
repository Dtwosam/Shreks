# Phase G Host Acceptance Evidence Verification Record

## Scope

This is the final repository verification record for the **non-numbered Phase G host-acceptance evidence slice**. It is stacked exactly on sealed G8 and exists only to make the remaining physical-host Phase-G exit gates deterministic, secret-safe, and auditable.

This is **not G9**. The supplied build order ends Phase G at G8.

Repository CI proves the host-acceptance harness mechanics only. It does **not** prove that a physical VPS has been deployed, rebooted, process-killed, restored, or accepted.

**LIVE TRADING: DISABLED.**

## Immutable anchors

- Sealed G8 base: `99c5de232eb36e6fdd7777d089453f16c03ef38a`
- Frozen host-acceptance behavior: `d2b8a5d83d0b4444765036d02a2dc535a8a590be`
- Frozen behavior CI: `32980518873`
  - Python: **2608 passed in 13.83s**
  - Rust/workspace: GREEN
  - Repository safety: GREEN

## TDD evidence

### Task 1 — canonical evidence models and codec

- RED commit: `0fe4c3a9f4838d081eea2116ee49505862d199dd`
- RED CI: `32976902489`
- RED failure: Python collection failed only because `shreks_brain.host_acceptance` did not exist; repository safety was GREEN and Rust was unaffected.
- GREEN commit: `b90c5a92c474bd04d6f059c2ff8fa0da10f331bc`
- GREEN CI: `32977273124`
- Python: **2592 passed**; Rust/workspace and repository safety GREEN.

Delivered:
- immutable exact-schema host evidence models;
- stable stage/status vocabularies;
- canonical newline-terminated JSON;
- strict exact-key decode;
- SHA-256 evidence fingerprints;
- fail-closed overall status semantics;
- no host/process/network/trading authority.

### Task 2 — read-only host collector

- RED commit: `8667246ddca848a71faba54c9e0bd5dc7d820bce`
- RED CI: `32977641851`
- RED failure: Python collection failed only because `host_acceptance.collector` did not exist; repository safety GREEN.
- GREEN commit: `1ac87ab35482ad0f9f987bbd6c30c686bb90c906`
- GREEN CI: `32978030415`
- Python: **2595 passed**; Rust/workspace and repository safety GREEN.

Delivered:
- exact active-release provenance observation;
- read-only `systemctl show` / `systemctl is-enabled` service and timer observation;
- read-only `ss -ltnH` dashboard listener observation;
- sealed PAPER preflight reuse without advancing a cycle;
- sealed G7 state loading;
- sealed G8 bundle verification;
- secret paths are metadata/stat-only and secret contents are never opened, hashed, printed, or persisted;
- missing or failed required evidence never becomes PASS.

### Task 3 — restart/reboot/restore continuity comparator

- RED commit: `535f48fb47d983494b30a33676dd44ae1e76b77b`
- RED CI: `32979273947`
- RED failure: Python collection failed only because the comparator module did not exist.
- GREEN implementation/export head: `a5cf68c2ddc881ba46d1131d101c33fd2ffa433d`
- GREEN CI: `32979484270`
- Python: **2603 passed**; Rust/workspace and repository safety GREEN.

Delivered deterministic failure evidence for:
- invalid source evidence fingerprints;
- non-PASS before/after records;
- invalid stage transitions;
- host/release/PAPER-run/candidate/campaign identity changes;
- PAPER cycle or ledger time regression;
- ledger entry-count regression;
- lost processed intent keys;
- G7 risk-control continuity changes;
- process restart with changed boot ID;
- reboot with unchanged boot ID.

`AFTER_RESTORE_DRILL` intentionally imposes no boot-ID relation while preserving all PAPER/release/G7 truth checks.

The comparator has no filesystem, subprocess, network, profitability, trade, wallet, signing, submission, or live authority.

### Task 4 — secret-safe operator CLI and physical-host runbook

- RED test commits: `b3d3432e...` and `19532715...`
- RED CI: `32979793208`
- Python failed only because `host_acceptance.runtime` did not exist.
- Rust failed on the intentionally absent host runbook plus an over-broad test-only authority marker; repository safety stayed GREEN.
- Runtime implementation: `3ad1f2a63fcdfc24a1deff47091e0ee79537708c`
- Physical runbook: `3d1c1484...`
- Test-only authority-marker corrections: `6cb98d5aec1a98e727ccc9e3f7dda67d50b10872`, `d2b8a5d83d0b4444765036d02a2dc535a8a590be`
- Frozen GREEN CI: `32980518873`
- Python: **2608 passed in 13.83s**; Rust/workspace and repository safety GREEN.

Delivered CLI authority is exactly:
- `capture`: one read-only host evidence capture into canonical private `0600` output;
- `compare`: one canonical before/after continuity assessment into private `0600` output.

The parser exposes no restart, reboot, start, stop, enable, disable, kill, wallet, signing, submission, trade, or live command.

Physical lifecycle actions remain explicit operator actions outside the routine harness.

The physical-host runbook documents:
- exact verified release provenance;
- BASELINE capture;
- actual process-kill/restart drill;
- actual server reboot drill;
- G8 isolated restore drill;
- G6 real phone-delivery/retry evidence;
- G7 halt/kill propagation and persistence evidence;
- loopback-only dashboard evidence;
- rollback and forward-recovery provenance;
- explicit distinction between repository CI and physical-host acceptance.

## Frozen scope audit

Exact sealed G8 -> frozen host-acceptance comparison:

- ahead by: **15 commits**
- behind by: **0**
- changed files: **14**
- all changed files are additions.

Changed files are exactly:

1. `crates/shreks-observer/tests/phase_g_host_acceptance_runbook.rs`
2. `deploy/systemd/PHASE_G_HOST_ACCEPTANCE.md`
3. `docs/superpowers/plans/2026-08-26-phase-g-host-acceptance-evidence.md`
4. `docs/superpowers/specs/2026-08-26-phase-g-host-acceptance-evidence-design.md`
5. `python/src/shreks_brain/host_acceptance/__init__.py`
6. `python/src/shreks_brain/host_acceptance/codec.py`
7. `python/src/shreks_brain/host_acceptance/collector.py`
8. `python/src/shreks_brain/host_acceptance/compare.py`
9. `python/src/shreks_brain/host_acceptance/models.py`
10. `python/src/shreks_brain/host_acceptance/runtime.py`
11. `python/tests/test_phase_g_host_acceptance_collector.py`
12. `python/tests/test_phase_g_host_acceptance_compare.py`
13. `python/tests/test_phase_g_host_acceptance_models.py`
14. `python/tests/test_phase_g_host_acceptance_runtime.py`

No existing provider adapter, database schema/migration, strategy/setup/scoring implementation, trading-risk threshold, sizing/slippage formula, execution/fill/exit logic, accounting/ledger/checkpoint behavior, profitability/proof formula, registry/promotion authority, dashboard behavior, alert behavior, backup behavior, wallet/signing/submission path, transaction construction, or live-enable implementation changed.

No existing G1-G8 production file was modified.

## Repository-sealed behavior

The repository now has one deterministic evidence harness for proving that the sealed G1-G8 stack survives real host operations without losing PAPER truth or G7 safety state.

The harness:
- cannot perform lifecycle actions;
- cannot read secret values;
- cannot alter PAPER/accounting state;
- cannot alter G7 state;
- cannot activate a restored G8 bundle;
- cannot trade, sign, submit, promote, or enable live mode;
- refuses to turn failed/unavailable evidence into PASS.

## Physical-host evidence still required

This repository seal **must not** be interpreted as physical Phase-G acceptance.

The following still must be executed on the actual dedicated Linux host:

1. deploy an exact verified release through the sealed G2 path;
2. capture a passing real BASELINE;
3. perform an actual process-kill/restart drill and obtain a passing continuity comparison;
4. perform an actual host reboot and obtain a passing continuity comparison;
5. prove dashboard loopback-only exposure and intended private remote access;
6. prove one real G6 notification reaches the intended phone and durable retry survives delivery failure;
7. prove G7 halt and emergency-kill propagation, stale-revision rejection, restart persistence, and browser authority limits;
8. produce a production-shaped G8 backup and complete an isolated verified restore drill;
9. prove verified rollback and forward recovery;
10. continue the real PAPER campaign until the separate after-cost profitability/proof gates have sufficient independent evidence.

A physical-host PASS must be derived from the real-host evidence records, not from CI.

## Free-host platform note

The currently sealed G2 release builder is pinned to `x86_64-unknown-linux-gnu`. A free ARM64 VPS therefore requires a separately verified **host-platform compatibility slice** before deploying Shreks there; the deployment integrity path must not be bypassed by copying an ad-hoc ARM binary onto the server.

That compatibility work is operational packaging only and must preserve all sealed trading behavior.

## Seal requirements

After this verification-record commit:

1. frozen behavior -> seal must be exactly **1 commit / 1 changed file / 0 behind**;
2. the sole changed file must be this verification record;
3. exact-seal CI must reproduce the frozen **2608 Python tests** with Rust/workspace and repository safety GREEN;
4. PR #50 must remain **open, draft, and unmerged** at the exact seal SHA.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
