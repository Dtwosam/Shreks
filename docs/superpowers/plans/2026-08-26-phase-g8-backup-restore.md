# Phase G8 Backup and Restore Proof Implementation Plan

**Base:** sealed G7 `8d31368eaefd50560855b4ef69050760c1134bee`  
**Branch:** `feat/phase-g8-backup-restore`  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g8-backup-restore-design.md`

**LIVE TRADING: DISABLED.**

## Goal

Implement and seal a fail-closed local backup/restore layer for authoritative PAPER and operational safety state. The implementation must preserve sealed G7 behavior, add no live/trading/service-control authority, require no paid infrastructure, and prove staged restore through the existing PAPER preflight.

## Task 1 — Strict bundle manifest and verifier

### RED

Add `python/tests/test_g8_backup_manifest.py` proving the new contract is absent and defining:

- exact schema/version and canonical JSON round-trip;
- exact logical artifact-role vocabulary;
- unique roles and paths;
- SHA-256 and non-negative byte-size validation;
- normalized safe relative paths only;
- rejection of absolute paths, `..`, duplicate/ambiguous paths, unknown roles, extra keys, NaN/non-canonical JSON;
- required role set and optional alert-state semantics;
- no secret/telemetry artifact role;
- verifier rejects missing, extra, symlinked, size-mismatched, and hash-mismatched artifacts;
- SQLite artifact must pass integrity/quick-check.

Commit RED and confirm Python fails only because the G8 backup package is absent; Rust and repository safety remain green.

### GREEN

Implement:

- `python/src/shreks_brain/backup/__init__.py`
- `models.py`
- `manifest.py`
- `verify.py`

Keep the API pure/read-only except verification reads. Run full CI to GREEN.

## Task 2 — Online snapshot creator and coherence retry

### RED

Add `python/tests/test_g8_backup_snapshot.py` covering:

- SQLite WAL-mode source with committed data captured through `sqlite3.Connection.backup()`;
- no raw `-wal` or `-shm` bundle artifacts;
- source database/files unchanged by snapshot;
- exact bytes of E11, campaign manifest, G7 risk state, and configured alert state;
- telemetry, password/token/API-key/private-key paths never copied;
- private directory/file permissions;
- temporary bundle is not treated as completed;
- final publication only after all verification succeeds;
- bounded retry when staged PAPER preflight detects cross-file incoherence;
- no retry forever and no fabricated success;
- failed attempts clean only invocation-owned temporary paths.

RED must fail only because snapshot runtime does not exist.

### GREEN

Implement `snapshot.py` using:

- private temp directory inside backup root;
- online SQLite backup;
- exact fixed-role file copies;
- strict artifact hashing/manifest creation;
- existing PAPER preflight against staged DB/E11/manifest/risk state;
- bounded capture attempts;
- atomic publish after successful verification.

Run full CI to GREEN.

## Task 3 — Staging-only restore and restart-equivalence proof

### RED

Add `python/tests/test_g8_backup_restore.py` covering:

- restore only to empty target;
- no overwrite of existing target files;
- corrupt/partial/tampered bundle rejection before restore;
- path traversal/symlink rejection;
- restored SQLite quick-check;
- restored campaign manifest fingerprint/run ID match bundle metadata;
- restored PAPER checkpoint/ledger/position/processed-intent state is identical;
- E11 evidence survives exactly and PAPER preflight passes;
- G7 halt/kill revision/state survives exactly;
- G6 pending alert queue/state survives exactly;
- source bundle remains unchanged;
- restore code never references systemctl/live/wallet/signing/submission.

### GREEN

Implement `restore.py` with fixed destination filenames and private permissions. Invoke existing PAPER preflight against staged restored paths. Return a typed immutable verification result; do not install into live host paths.

Run full CI to GREEN.

## Task 4 — Config, runtime CLI, and bounded retention

### RED

Add `python/tests/test_g8_backup_runtime.py` covering:

- `SHREKS_BACKUP_ROOT` path validation;
- bounded positive `SHREKS_BACKUP_RETENTION_COUNT`;
- bounded positive `SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS`;
- reuse of existing authoritative DB/E11/manifest/risk/alert path configuration;
- no backup namespace strategy/risk/live keys;
- backup command produces one verified bundle or exits nonzero;
- verify command is read-only;
- restore command requires explicit bundle + empty staging target;
- retention runs only after successful publish;
- retention removes oldest verified completed bundles only;
- malformed/unrelated directories are never deleted;
- newest completed bundle is never deleted;
- runtime status output contains no secret values.

### GREEN

Implement:

- `config.py`
- `runtime.py`

Use deterministic structured status output and bounded retention. Run full CI to GREEN.

## Task 5 — systemd isolation and operator runbook

### RED

Add `crates/shreks-observer/tests/g8_backup_systemd.rs` requiring:

- `deploy/systemd/shreks-backup.service` and `.timer`;
- oneshot under `shreks` user/group;
- release Python runtime;
- read-only `/var/lib/shreks` and `/etc/shreks` plus only `ReadWritePaths=/var/lib/shreks/backups`;
- no network/IP access;
- hardening flags consistent with existing independent services;
- no `PartOf=shreks.target`, no lifecycle dependency on PAPER/dashboard/alerts;
- hourly persistent timer with bounded randomized delay;
- no `systemctl`, live, wallet, signing, submission, reboot, shutdown authority;
- `.env.example` contains only the G8 operational keys;
- runbook documents backup initialization, capacity, verification, staging restore, separate secret recovery, manual service stop/install/preflight/start, G7 state preservation, optional off-host copy, rollback, and future onchain reconciliation;
- LIVE TRADING remains disabled.

### GREEN

Add:

- `.env.example` G8 keys;
- `deploy/systemd/shreks-backup.service`;
- `deploy/systemd/shreks-backup.timer`;
- `deploy/systemd/G8_BACKUP_RESTORE.md`;
- only minimal existing README integration if needed.

Run full CI to GREEN.

## Task 6 — Audit, freeze, and seal

1. Select the final all-green behavior SHA as frozen G8 behavior.
2. Record frozen CI and exact Python test cardinality.
3. Compare sealed G7 -> frozen G8 and audit every changed file.
4. Prove no provider adapter, DB schema/migration, strategy/scoring/risk threshold, sizing/slippage, profitability/proof formula, promotion, wallet/signing/submission, or live-enable drift.
5. Replace this plan file with the G8 verification record in one docs-only commit.
6. Prove frozen -> seal is exactly one commit / one file.
7. Run exact-seal CI and require exact frozen Python cardinality plus Rust/workspace and repository safety GREEN.
8. Update the G8 draft PR with frozen/seal evidence.
9. Re-fetch PR metadata and prove open / draft / unmerged.
10. Do not merge G7 or G8. Do not enable live trading.

## Real-host evidence retained after repository seal

Repository CI cannot prove physical disk/reboot/operator recovery. Before any future live-money enablement, host proof must include:

- actual WAL-mode production-shaped online backup;
- permissions and available-disk/retention monitoring;
- destructive restore into an isolated host/sandbox from a selected bundle;
- PAPER preflight and restart-equivalence after installed restore;
- G7 halt/kill state preservation;
- pending G6 alert preservation;
- host reboot and timer persistence;
- optional off-host/offline copy retrieval if that operational practice is adopted;
- separate host-secret recovery procedure;
- for future LIVE, onchain balance/position reconciliation before enabling any live authority.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
