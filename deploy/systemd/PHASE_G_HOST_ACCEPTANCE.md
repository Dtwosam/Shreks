# Phase G Physical Host Acceptance

This document is the operator workflow for the **non-numbered Phase G exit slice** stacked on sealed G8 base `99c5de232eb36e6fdd7777d089453f16c03ef38a`.

The repository tests prove the harness mechanics. **CI does not prove physical-host acceptance.** Phase G becomes host-proven only after this workflow is executed on the dedicated Linux server from the **exact verified release** and the resulting evidence records pass.

The routine harness is read-only with respect to runtime state: **routine harness has no lifecycle authority**. It can run `systemctl show`, `systemctl is-enabled`, and `ss` through its collector, but it cannot start, stop, restart, enable, disable, kill, reboot, trade, sign, submit, or enable live mode. The destructive actions below are separate, explicit operator drills.

`LIVE TRADING: DISABLED`. F7 remains separately gated even after Phase G host acceptance passes.

## 1. Preconditions

Use the G2 release/deployment path and verify release provenance before collecting evidence. `/opt/shreks/current` must resolve to the exact release SHA being tested under `/opt/shreks/releases/<sha>`, and that release must have its verified `RELEASE_MANIFEST.json`.

All sealed PAPER services and independent Phase-G services/timers must already be installed and healthy:

- `shreks-observe.service`
- `shreks-paper-evidence.service`
- `shreks-paper-campaign.service`
- `shreks.target`
- `shreks-telemetry.timer`
- `shreks-dashboard.service`
- `shreks-alerts.timer`
- `shreks-backup.timer`

Create a private evidence directory:

```bash
sudo install -d -o shreks -g shreks -m 0700 /var/lib/shreks/host-acceptance
```

The harness records metadata for protected files, but **secret values are never copied into evidence**. Do not paste the dashboard password, Telegram bot token, signing material, API credentials, or any other secret into command output, evidence filenames, shell history, or this runbook.

Expected protected secret files remain host-only, for example:

```text
/etc/shreks/dashboard-password
/etc/shreks/telegram-bot-token
```

## 2. Common capture command

Run captures as the `shreks` service identity from `/opt/shreks/current`. Replace `<SEALED_SHA>` with the exact release SHA under test.

```bash
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.host_acceptance.runtime capture \
  --stage BASELINE \
  --host-label shreks-production-paper \
  --expected-release-sha <SEALED_SHA> \
  --observer-database /var/lib/shreks/shreks.db \
  --evidence /var/lib/shreks/e11/evaluated-trades.jsonl \
  --campaign-manifest /etc/shreks/paper-campaign.json \
  --risk-control /var/lib/shreks/risk/operator-control.json \
  --backup-root /var/lib/shreks/backups \
  --dashboard-port 8787 \
  --paper-cycle-interval-seconds 1 \
  --dashboard-password /etc/shreks/dashboard-password \
  --telegram-token /etc/shreks/telegram-bot-token \
  --output /var/lib/shreks/host-acceptance/baseline.json
```

Use the paths configured on the actual host if the sealed deployment uses different explicit PAPER evidence paths. A capture exit code of `0` means the record itself is `PASS`; nonzero must be investigated rather than overridden.

## 3. BASELINE -> process restart -> compare

1. Capture `BASELINE` as above.
2. Record current service status with read-only `systemctl status`/`show` commands.
3. Perform one explicit failure drill outside the harness. Example:

```bash
sudo systemctl kill --kill-whom=main --signal=SIGKILL shreks-paper-campaign.service
```

4. Verify systemd restarts the PAPER campaign under its sealed restart policy and that the service becomes active again.
5. Capture the after record using the same arguments, changing only:

```text
--stage AFTER_PROCESS_RESTART
--output /var/lib/shreks/host-acceptance/after-process-restart.json
```

6. Compare:

```bash
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.host_acceptance.runtime compare \
  /var/lib/shreks/host-acceptance/baseline.json \
  /var/lib/shreks/host-acceptance/after-process-restart.json \
  --output /var/lib/shreks/host-acceptance/process-restart-comparison.json
```

A PASS requires the same boot ID, unchanged release/campaign/candidate/G7 safety identity, no loss of processed PAPER intents, and non-regressing PAPER/ledger progress.

## 4. BASELINE -> host reboot -> compare

Take a fresh `BASELINE` immediately before the reboot so the comparison has one unambiguous starting point.

Perform the reboot explicitly outside the harness:

```bash
sudo systemctl reboot
```

After SSH access returns, verify the target and independent timers/services are healthy. Then capture:

```text
--stage AFTER_REBOOT
--output /var/lib/shreks/host-acceptance/after-reboot.json
```

Compare the pre-reboot baseline to the after-reboot record with:

```bash
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.host_acceptance.runtime compare \
  /var/lib/shreks/host-acceptance/baseline-before-reboot.json \
  /var/lib/shreks/host-acceptance/after-reboot.json \
  --output /var/lib/shreks/host-acceptance/reboot-comparison.json
```

`AFTER_REBOOT` must show a different boot ID while preserving the same PAPER and G7 truth.

## 5. G8 isolated restore drill -> AFTER_RESTORE_DRILL

Follow `deploy/systemd/G8_BACKUP_RESTORE.md` exactly. First verify a completed G8 backup bundle, then restore it only into an empty isolated staging directory. Application restore remains staging-only; do not activate restored files as part of this drill.

The G8 workflow includes:

```bash
python -m shreks_brain.backup.runtime verify ...
python -m shreks_brain.backup.runtime restore ...
```

Require the staged PAPER preflight to pass and verify the restored G7 halt/kill state and optional G6 alert state match the bundle.

After the isolated restore drill has completed without mutating active PAPER state, capture:

```text
--stage AFTER_RESTORE_DRILL
--output /var/lib/shreks/host-acceptance/after-restore-drill.json
```

Compare it to a fresh pre-drill `BASELINE`. `AFTER_RESTORE_DRILL` does not require a particular boot-ID relation, but all PAPER/campaign/release/G7 continuity rules still apply.

## 6. G6 and G7 physical drills

The host-acceptance harness does not duplicate those authorities.

- **G6:** follow the alert deployment/retry guidance in `deploy/systemd/README.md`. Prove one real controlled notification reaches the intended phone, journals do not contain the bot token, a simulated delivery failure leaves the durable event pending, and a later successful run acknowledges it without affecting PAPER uptime.
- **G7:** follow `deploy/systemd/G7_OPERATOR_CONTROLS.md`. Prove dashboard `HALT NEW ENTRIES` propagates on the next PAPER cycle, stale revisions fail, `EMERGENCY KILL SWITCH` reaches the existing global-halt exit path, state survives restart, and browser controls cannot reset/resume authority.

These are required physical-host evidence even when the repository tests are green.

## 7. Dashboard exposure

The dashboard process must listen only on loopback (`127.0.0.1` and/or `::1`). Remote/phone access must use the intended private overlay/tunnel or same-host TLS reverse proxy from the G5 runbook. A listener on `0.0.0.0`, `[::]`, or another non-loopback interface makes host acceptance fail.

## 8. Rollback and release provenance

Use only the sealed G2 verified release manager for rollback. Before rollback, preserve the current acceptance records and verified release provenance. After rollback, verify `/opt/shreks/current` points to the intended prior verified SHA and the core PAPER health gate passes.

Because continuity comparison intentionally requires the same release identity, do not compare a pre-rollback record from release A directly with a post-rollback record from release B. Instead:

1. retain the release-A evidence;
2. perform the verified rollback;
3. take a new `BASELINE` under release B;
4. run a process-restart continuity drill under release B;
5. roll forward through the verified G2 release path;
6. take a fresh baseline under the restored forward release.

That sequence gives explicit **release provenance** and rollback/recovery evidence without weakening the comparator.

## 9. Evidence handling

Acceptance records and comparison assessments are canonical JSON written `0600` in `/var/lib/shreks/host-acceptance`. Keep the directory `0700`, back it up separately as operational evidence if desired, and never edit a record by hand. Any decode/fingerprint failure invalidates that record.

Do not treat resource observations such as load, memory, or free disk as profitability metrics. They are operational observations only.

## 10. Phase-G host exit rule

Phase G can be called host-proven only after all of the following exist from the real dedicated host:

1. verified release provenance;
2. a passing BASELINE;
3. passing process-restart comparison;
4. passing real reboot comparison;
5. loopback-only dashboard evidence and private remote access proof;
6. real G6 delivery and durable retry proof;
7. real G7 halt/kill propagation and persistence proof;
8. a verified production-shaped G8 backup and isolated restore drill;
9. rollback and forward-recovery evidence;
10. continued real PAPER evidence for the separate profitability/proof gates.

Repository CI is necessary but insufficient. It cannot claim a real reboot, real phone delivery, real provider behavior, real host storage durability, or profitability.

**LIVE TRADING: DISABLED.**
