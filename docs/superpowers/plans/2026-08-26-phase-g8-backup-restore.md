# Phase G8 Backup and Restore Proof Verification Record

**Base sealed G7:** `8d31368eaefd50560855b4ef69050760c1134bee`  
**Base exact-seal CI:** `32969491598` — 2531 Python tests, Rust/workspace GREEN, repository safety GREEN  
**Frozen G8 behavior:** `45ecdab878dd286ebf7f9970c6512730831fdea0`  
**Frozen G8 CI:** `32974180534` — 2585 Python tests, Rust/workspace GREEN, repository safety GREEN  
**Branch:** `feat/phase-g8-backup-restore`  
**PR:** #49, stacked on sealed G7  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g8-backup-restore-design.md`

**LIVE TRADING: DISABLED.**

## Seal conclusion

G8 repository behavior is frozen at `45ecdab878dd286ebf7f9970c6512730831fdea0`. The frozen implementation adds a fail-closed local backup/restore proof for authoritative PAPER truth and operational safety state without adding trading authority, wallet authority, signing/submission authority, live-enable authority, or automated service-control authority.

The frozen CI run `32974180534` completed successfully with exactly **2585 Python tests passing**, Rust/workspace GREEN, and repository safety GREEN.

Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.

## G7 -> frozen G8 geometry and file audit

GitHub compare from sealed G7 `8d31368eaefd50560855b4ef69050760c1134bee` to frozen G8 `45ecdab878dd286ebf7f9970c6512730831fdea0` proves:

- status: `ahead`;
- ahead: **27 commits**;
- behind: **0 commits**;
- total commits: **27**;
- changed files: **19**;
- PR additions at freeze: **3314**;
- PR deletions at freeze: **0**.

Every changed path was audited:

1. `.env.example` — bounded G8 operational backup settings only.
2. `crates/shreks-observer/tests/g8_backup_systemd.rs` — host sandbox/authority/runbook contract tests.
3. `deploy/systemd/G8_BACKUP_RESTORE.md` — operator backup/recovery runbook.
4. `deploy/systemd/shreks-backup.service` — isolated no-network oneshot backup service.
5. `deploy/systemd/shreks-backup.timer` — independent hourly persistent timer.
6. `docs/superpowers/plans/2026-08-26-phase-g8-backup-restore.md` — implementation plan, replaced by this verification record at seal.
7. `docs/superpowers/specs/2026-08-26-phase-g8-backup-restore-design.md` — G8 design record.
8. `python/src/shreks_brain/backup/__init__.py` — explicit G8 public API.
9. `python/src/shreks_brain/backup/config.py` — bounded operational configuration.
10. `python/src/shreks_brain/backup/manifest.py` — strict canonical bundle manifest codec.
11. `python/src/shreks_brain/backup/models.py` — immutable G8 bundle models and role vocabulary.
12. `python/src/shreks_brain/backup/restore.py` — verified staging-only restore.
13. `python/src/shreks_brain/backup/runtime.py` — backup/verify/restore CLI and bounded retention.
14. `python/src/shreks_brain/backup/snapshot.py` — online coherent snapshot creation.
15. `python/src/shreks_brain/backup/verify.py` — read-only bundle verification and SQLite integrity proof.
16. `python/tests/test_g8_backup_manifest.py` — strict manifest/verifier contract.
17. `python/tests/test_g8_backup_restore.py` — staging restore and authority contract.
18. `python/tests/test_g8_backup_runtime.py` — config/CLI/retention contract.
19. `python/tests/test_g8_backup_snapshot.py` — online snapshot/coherence contract.

No provider adapter changed. No operational database schema or migration changed. No strategy/setup/scoring formula changed. No risk threshold, sizing, slippage, fill, exit, accounting, profitability, proof, promotion, or registry formula changed. No wallet, signer, transaction-builder, transaction-submission, or live-execution file changed. No existing G7 safety-state model or command vocabulary changed.

## Frozen behavior proof

### 1. Strict bundle manifest and verifier

The sealed G8 bundle schema is `g8-backup-bundle-v1` with explicit artifact roles for:

- authoritative operational SQLite;
- E11 evidence;
- immutable PAPER campaign manifest;
- G7 operator risk-control state;
- optional G6 alert state.

The verifier enforces canonical schema decoding, exact allowed role vocabulary, unique roles and paths, SHA-256 hashes, byte sizes, normalized safe relative paths, required core roles, exact file-set matching, symlink rejection, traversal rejection, and SQLite `quick_check` integrity.

Secrets and derived telemetry are not representable as G8 artifact roles.

Task 1 TDD evidence:

- RED commit: `4a5e1740af36f71cdb9c8afdbd0457810eaa7e09`;
- RED CI: `32970451524`, Python failed only because `shreks_brain.backup` did not exist;
- GREEN behavior head: `3f08b080b3f4f9cd552a8da67c4012a271bebc1b`;
- GREEN CI: `32970644473`, **2557 Python tests**, Rust/workspace GREEN, repository safety GREEN.

### 2. Online coherent snapshot creation

Snapshot creation:

- rejects unsafe/symlinked sources;
- captures SQLite through `sqlite3.Connection.backup()` rather than raw DB/WAL copying;
- preserves committed WAL-backed truth while the source remains live;
- normalizes only the staged SQLite copy to single-file `DELETE` journaling;
- copies exact E11, campaign-manifest, G7 control, and configured G6 alert bytes;
- validates staged campaign and G7 state;
- runs the existing read-only PAPER preflight against staged DB/E11/manifest/G7 state;
- retries only bounded defined coherence/preflight failures;
- publishes atomically only after verification;
- uses private bundle directory/file permissions;
- never stops, starts, restarts, or otherwise controls Shreks services.

A real GREEN-candidate failure exposed a WAL edge case: the online backup retained WAL journal mode and staged preflight could create untracked sidecars. The fix normalized only the staged copy after the online backup. The authoritative source database remains untouched and WAL-backed.

Task 2 TDD evidence:

- RED commit: `d99ff293df78c5c2080a22f8571cd1482cda40f2`;
- RED CI: `32970854199`, Python failed only because the snapshot API was absent;
- intermediate candidate CI: `32971057075`, one live-WAL test failed while 2563 tests passed;
- WAL normalization fix: `097360d4bed83411bc5ef7f2ce6519eb7efe8fe7`;
- GREEN CI: `32971379622`, **2564 Python tests**, Rust/workspace GREEN, repository safety GREEN.

### 3. Staging-only restore

Restore behavior:

- verifies the complete source bundle before touching staging;
- accepts only a real empty, non-symlink staging target;
- copies to fixed private staging filenames;
- preserves SQLite checkpoint truth, E11 bytes, campaign attribution/fingerprint, G7 control state, and optional G6 alert bytes;
- validates the staged campaign and G7 state;
- runs the existing read-only PAPER preflight;
- reads the restored PAPER checkpoint for typed verification output;
- leaves the source bundle bit-for-bit unchanged;
- refuses tampered bundles before staging artifacts are created;
- cleans only known G8-created staging artifacts after defined restore failure;
- contains no service-control, live, wallet, private-key, seed, signing, submission, or subprocess authority.

During implementation, tests initially referenced nonexistent `OperatorRiskControlSource.HOST`. The test was corrected to sealed G7 `HOST_CLI`; production G7 behavior was not widened. A second mismatch used nonexistent `PaperLoopState.as_of_unix_ms`; G8 was aligned to the sealed field `last_cycle_at_unix_ms` rather than modifying PAPER state.

Task 3 TDD evidence:

- RED commit: `e3a5fe218a27f2a3e5d8fd5e8706a3f78c489b6a`;
- RED CI: `32971597321`, failed because `shreks_brain.backup.restore` did not exist;
- implementation head: `7ed9204c99e82b81217799689f766415f9ad493d`;
- fixture-alignment head: `94527458c9c3a36146c420c51cfa946f7366f6c1`;
- final field-alignment head: `c506a734b49941dfd068ec96b2179963de760645`;
- GREEN CI: `32972755114`, **2572 Python tests**, Rust/workspace GREEN, repository safety GREEN.

### 4. Bounded runtime config, CLI, and retention

The G8-specific environment namespace accepts only:

- `SHREKS_BACKUP_ROOT`;
- `SHREKS_BACKUP_RETENTION_COUNT`, bounded 1 through 10000;
- `SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS`, bounded 1 through 100.

G8 reuses the existing sealed operational DB/E11/campaign/G7-control/optional-G6-alert paths. Unknown `SHREKS_BACKUP_*` keys are rejected, including strategy, risk, live, or private-key settings.

The CLI exposes only `backup`, `verify`, and explicit staging `restore`. Retention runs only after successful publication, considers only successfully verified completed bundle directories, removes oldest eligible bundles to the configured bound, never deletes the newest completed bundle, and leaves malformed or unrelated directories untouched.

An intermediate GREEN candidate exposed an incorrect exact-type check against `Path`; Linux correctly produced `PosixPath`. G8 was fixed to the intended `isinstance(value, Path)` invariant without changing runtime semantics.

Task 4 TDD evidence:

- RED commit: `69d2e12d17a89b75a17ffb895793add93b47593a`;
- RED CI: `32973043527`, Python failed only because `backup.config` did not exist;
- initial candidate CI: `32973230467`, 2583 tests passed and two failed only on the pathlib concrete-type check;
- portability fix: `c5a3b1b6bd682a47e307c3923a2e7c0a50d8ea52`;
- GREEN CI: `32973371724`, **2585 Python tests**, Rust/workspace GREEN, repository safety GREEN.

### 5. Isolated systemd backup and recovery runbook

The G8 backup service is an independent `Type=oneshot` unit under the `shreks` user/group. It uses the release Python runtime, mounts Shreks state read-only, and grants write authority only to `/var/lib/shreks/backups`.

The service has:

- `PrivateNetwork=true`;
- `RestrictAddressFamilies=AF_UNIX`;
- `NoNewPrivileges=true`;
- private tmp/devices;
- strict system/home/kernel/control-group hardening;
- no dependency or coupling to PAPER, dashboard, alerts, or `shreks.target`.

The timer is independent, hourly, persistent, and randomized within a bounded delay.

The runbook separates application staging restore from host activation. The application never calls `systemctl`. Manual recovery requires an operator to stop the PAPER writer, inspect and preflight staged state, install active files deliberately, re-run active-path preflight, preserve any G7 halt/kill latch exactly, and only then restart PAPER.

The runbook also documents private modes, disk-capacity checks, separate secret recovery, optional verified off-host copy, rollback evidence preservation, and mandatory future onchain reconciliation before any live-money recovery.

Task 5 TDD evidence:

- RED commit: `07814dced2050aa93e1932e76e80f6cbfa8cede6`;
- RED CI: `32973551104`, Python and repository safety remained GREEN while Rust failed only because the G8 runbook file was absent;
- first complete host candidate: `f9bda5f80d0a77d5b6f15506a6be437813b530bb`;
- candidate CI: `32973990493`, Python/safety GREEN and 4/5 G8 host tests passed; the sole failure was case-sensitive runbook evidence wording;
- wording-only fix: `45ecdab878dd286ebf7f9970c6512730831fdea0`;
- final frozen CI: `32974180534`, **2585 Python tests**, Rust/workspace GREEN, repository safety GREEN.

## Authority firewall conclusion

The G8 diff does not create a new trading or lifecycle authority path.

- Backup code reads authoritative PAPER/safety state and writes only G8 backup/staging storage chosen for the operation.
- Restore code cannot install into active host state automatically.
- G8 application code cannot stop/start/restart services.
- The systemd backup service has no IP network access and one writable backup directory.
- The service is not coupled to the PAPER target or PAPER lifecycle.
- Secrets are deliberately excluded from bundle roles and the G8 service.
- G8 does not modify strategy selection, scoring, trading risk, fills, exits, accounting, proof, promotion, wallet, signer, submission, or live-execution behavior.

No audit defect required reopening frozen G8 behavior.

## Repository seal operation

This verification record is the only file permitted to change after frozen behavior `45ecdab878dd286ebf7f9970c6512730831fdea0`.

Post-commit seal requirements:

1. frozen G8 -> seal must be exactly **1 commit / 1 file**;
2. the sole file must be this verification record;
3. exact-seal CI must complete successfully;
4. exact-seal Python cardinality must remain exactly **2585 passed**;
5. Rust/workspace must remain GREEN;
6. repository safety must remain GREEN;
7. PR #49 must remain open, draft, and unmerged on sealed G7.

## Real-host evidence retained after repository seal

Repository seal proves implementation behavior and authority boundaries, not physical-host recovery. Before any future live-money enablement, host evidence must still prove:

- the units and timer installed on the actual Linux VPS;
- writable backup storage, available-disk checks, and retention behavior on the real filesystem;
- a production-shaped online backup while the PAPER database is WAL-backed;
- at least one selected bundle verified after creation;
- a destructive recovery drill into an isolated host/sandbox, followed by PAPER preflight and restart-equivalence proof;
- preservation of G7 halt/kill state;
- preservation of pending G6 alert state when included;
- timer persistence across host reboot;
- retrieval and re-verification of an off-host copy if off-host storage is adopted;
- separate protected recovery of host secrets;
- for any future LIVE system, onchain reconciliation before any execution authority may resume.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
