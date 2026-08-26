# G8 Backup and Restore Runbook

## Scope and safety invariants

G8 protects durable Shreks PAPER truth and operator safety state. It does not add trading authority, wallet access, transaction signing, transaction submission, or service-management authority to the backup process.

**LIVE TRADING: DISABLED.**

The application backup command creates and verifies local recovery bundles. The application restore command restores only into an explicit empty staging directory. Promotion of staged files into active host paths remains a separate, manual operator maintenance procedure.

The G8 bundle contains:

- the authoritative operational SQLite database captured with SQLite online backup;
- E11 evidence;
- the immutable fingerprinted PAPER campaign manifest;
- the durable G7 operator risk-control state;
- the durable G6 alert state when configured and present.

Secrets are not backed up. Dashboard credentials, Telegram bot tokens, provider keys, wallet material, private keys, and seed material must be recovered separately from the operator's protected secret-management process. Derived telemetry is intentionally excluded because it can be regenerated.

## Host directories and permissions

Create the local backup root before enabling the timer:

```sh
install -d -o shreks -g shreks -m 0700 /var/lib/shreks/backups
```

G8 creates completed bundle directories with mode `0700` and bundle files with mode `0600`. Do not loosen these permissions.

Before enabling or testing backups, verify available local capacity:

```sh
df -h /var/lib/shreks/backups
du -sh /var/lib/shreks/backups
```

The backup service is sandboxed to read Shreks state and write only `/var/lib/shreks/backups`. It runs with a private network namespace and does not perform off-host transfer itself.

## Runtime configuration

Set the following operational keys in `/etc/shreks/shreks.env`:

```text
SHREKS_BACKUP_ROOT=/var/lib/shreks/backups
SHREKS_BACKUP_RETENTION_COUNT=168
SHREKS_BACKUP_MAX_CAPTURE_ATTEMPTS=3
```

The backup runtime reuses the already-sealed operational paths for the PAPER SQLite database, E11 evidence, campaign manifest, G7 operator risk-control state, and optional G6 alert state. Do not add strategy, scoring, risk-limit, wallet, signing, submission, or live-mode values to the G8 namespace.

## Install and enable the timer

Install `shreks-backup.service` and `shreks-backup.timer` with the other release units, then reload systemd and enable only the timer:

```sh
systemctl daemon-reload
systemctl enable --now shreks-backup.timer
systemctl status shreks-backup.timer
systemctl list-timers shreks-backup.timer
```

The timer runs hourly with bounded randomized delay. It is deliberately not part of `shreks.target` and does not require, stop, restart, or start PAPER, dashboard, or alert services.

For a one-time operator test, invoke the oneshot directly:

```sh
systemctl start shreks-backup.service
systemctl status shreks-backup.service
journalctl -u shreks-backup.service --since today
```

A successful run must leave a completed verified bundle under `/var/lib/shreks/backups`.

## Verify a completed bundle

Always verify a bundle before using it for recovery or copying it elsewhere:

```sh
cd /opt/shreks/current
.venv/bin/python -m shreks_brain.backup.runtime verify /var/lib/shreks/backups/<bundle>
```

Equivalent module form used by the sealed G8 contract is `python -m shreks_brain.backup.runtime verify <bundle>`.

Verification checks the canonical G8 manifest, exact role set, file sizes and SHA-256 hashes, path safety, symlink rejection, and SQLite integrity. A bundle that fails verification is not a recovery source and must not be deleted automatically by retention.

## Stage a restore

Restore never overwrites active state. Choose a private, empty staging directory that is not a symlink. The safest pattern is to create a dedicated parent and let G8 create the final empty staging directory itself:

```sh
install -d -o shreks -g shreks -m 0700 /var/lib/shreks/restore
cd /opt/shreks/current
.venv/bin/python -m shreks_brain.backup.runtime verify /var/lib/shreks/backups/<bundle>
.venv/bin/python -m shreks_brain.backup.runtime restore /var/lib/shreks/backups/<bundle> /var/lib/shreks/restore/<ticket-or-timestamp>
```

The contract is `python -m shreks_brain.backup.runtime restore <bundle> <empty staging directory>`.

The staged result must preserve the original PAPER checkpoint attribution, E11 evidence, campaign fingerprint, G7 operator risk-control state, and optional G6 alert-state bytes. The restore command also runs the existing read-only PAPER preflight against the staged state. It does not activate that state.

## Manual host activation after a verified restore

Activation is a separate maintenance operation. Do not perform it while PAPER is still writing active state.

1. Record the active release, active campaign fingerprint, latest PAPER checkpoint sequence, and the current G7 operator risk-control state. If entry halt or the emergency kill switch is active, preserve that state exactly.
2. Verify the source bundle again and inspect the staged manifest and staged G7 operator risk-control state.
3. Stop only the PAPER writer before replacing any active PAPER files:

```sh
systemctl stop shreks-paper-campaign.service
```

4. Run the sealed PAPER preflight against the staged database, E11 path, campaign manifest, and G7 control file. The staged state must pass preflight before any active-path replacement.
5. Back up the current active files separately as rollback evidence. Do not use the G8 retention process to delete this maintenance evidence.
6. Install the staged operational SQLite database, E11 evidence, campaign manifest, and G7 operator risk-control state into their configured active paths using the same owner/group and restrictive permissions used by the running system. If G6 alert state was included and is part of the recovery objective, restore it separately with the same discipline.
7. Re-run PAPER preflight against the active paths. Confirm campaign fingerprint, checkpoint sequence, E11 attribution, and the G7 operator risk-control state. A restored halt or kill latch must remain latched until explicitly cleared through the existing G7 control workflow.
8. Only after active-path preflight succeeds, restart PAPER:

```sh
systemctl start shreks-paper-campaign.service
```

9. Confirm service status and fresh telemetry before treating the host as recovered.

The G8 application code never performs the stop, replacement, or start steps above. Those commands are documented here only for the human-controlled maintenance procedure.

## Secret recovery

Secrets are not backed up by G8. Recover `/etc/shreks` secret files independently from the operator's protected secret source and restore their original owner/group/mode. Do not place secret values into a G8 bundle, the repository, command-line arguments, or recovery notes.

## Off-host copy

Local backup is not sufficient protection against total VPS loss. After a bundle passes `verify`, copy the completed bundle to operator-controlled off-host storage using a separate host process. The G8 service itself intentionally has no network access and performs no off-host upload.

Keep at least one recent verified off-host copy outside the VPS failure domain. Re-verify the bundle after any transfer before considering it recoverable.

## Rollback

For rollback to a pre-G8 release, disable the G8 timer and service integration, but preserve `/var/lib/shreks/backups` and any staged recovery evidence until the rollback is proven healthy. A software rollback must not destroy the evidence needed to recover PAPER truth or G7 safety state.

If rolling back to software that predates G7, preserve the G7 operator risk-control state separately even if the older binary cannot consume it. Never interpret inability to read a newer safety file as permission to clear a halt or kill latch.

## Future live-money recovery gate

G8 proves repository-level PAPER backup and restore behavior only. Any future live-money recovery requires a separately sealed recovery contract and onchain reconciliation of wallet balances, open positions, pending transactions, fills, and external state before execution may resume. A local SQLite restore can never be treated as proof of live onchain truth.

**LIVE TRADING: DISABLED.**
