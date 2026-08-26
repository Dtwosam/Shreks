# Shreks systemd deployment

This is the single-host Linux supervision layout for the PAPER runtime. GitHub remains the source/review/CI/release/deployment control plane; these services run continuously on the execution host.

**LIVE TRADING: DISABLED**

## Host layout

- Release checkout or symlink: `/opt/shreks/current`
- Per-release Python environment: `/opt/shreks/current/.venv`
- Runtime environment file: `/etc/shreks/shreks.env`
- Immutable paper-campaign manifest: `/etc/shreks/paper-campaign.json`
- Persistent operational state: keep the configured SQLite database and E11 evidence under a durable host path such as `/var/lib/shreks/`, never inside an ephemeral release directory.
- Private derived telemetry: `/var/lib/shreks/telemetry/current.json`
- Service identity: dedicated unprivileged `shreks` user/group.

Create the runtime identity and persistent directories once:

```sh
sudo useradd --system --home /var/lib/shreks --shell /usr/sbin/nologin shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks/telemetry
sudo install -d -o root -g shreks -m 0750 /etc/shreks
```

Build the sealed branch/release and make it available at `/opt/shreks/current`. The Python virtual environment belongs to the immutable release so rollback changes both Rust and Python code together:

```sh
cd /opt/shreks/current
cargo build --release --workspace
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install ./python
```

Do not use an editable Python install for the production release. `shreks-paper-campaign.service` and `shreks-telemetry.service` start `/opt/shreks/current/.venv/bin/python`, and the units disable Python bytecode writes so the release tree stays read-only at runtime.

## Runtime configuration

Create `/etc/shreks/shreks.env` from the repository `.env.example`, then fill every required runtime value on the host. Provider credentials and paper-evidence collection parameters belong only in this host file or an equivalent protected runtime secret mechanism. Do not commit populated values.

```sh
sudo chmod 600 /etc/shreks/shreks.env
sudo chown root:root /etc/shreks/shreks.env
```

For the G1C paper campaign, use durable absolute paths and keep trading policy out of environment configuration. A production-shaped host configuration includes:

```text
SHREKS_PAPER_CAMPAIGN_OBSERVER_DB_PATH=/var/lib/shreks/shreks.db
SHREKS_PAPER_CAMPAIGN_E11_PATH=/var/lib/shreks/paper-evaluation-e11.json
SHREKS_PAPER_CAMPAIGN_MANIFEST_PATH=/etc/shreks/paper-campaign.json
SHREKS_PAPER_CAMPAIGN_INTERVAL_SECONDS=<explicit-positive-seconds>
SHREKS_PAPER_CAMPAIGN_MAX_CYCLES=
```

Leave `SHREKS_PAPER_CAMPAIGN_MAX_CYCLES` blank for continuous supervised PAPER operation. A positive integer is only for finite verification campaigns. The G1C runtime rejects unsupported `SHREKS_PAPER_CAMPAIGN_*` keys, so strategy thresholds, selection bounds, starting capital, fill assumptions, score weights, slippage limits, and risk limits cannot become a second environment-driven policy channel.

The configured observer database path must resolve to persistent storage writable by the `shreks` service user. Observation, paper evidence, and the paper campaign must use the same authoritative SQLite WAL database. E11 evidence must also remain under durable writable storage such as `/var/lib/shreks`.

Install the already-generated, fingerprinted campaign manifest as a protected read-only runtime artifact. Do not hand-edit a persisted manifest: decoding verifies canonical content, candidate attribution, the embedded initial C6 state, and the manifest fingerprint.

```sh
sudo install -o root -g shreks -m 0640 paper-campaign.json /etc/shreks/paper-campaign.json
```

The campaign manifest contains policy/economic configuration but no wallet signing secret. Wallet/private signing credentials remain out of GitHub and are not required by this PAPER runtime.

### G4 read-only telemetry configuration

G4 produces a local reporting artifact only. It reads the operational database, PAPER state/evidence, and optional proof/promotion assessment files; it does not mutate those sources and has no trade, promotion, signing, submission, wallet, or live authority. Configure the reporting paths and evaluator reporting parameters explicitly:

```text
SHREKS_TELEMETRY_PROOF_PATH=/var/lib/shreks/candidate-proof-assessments.json
SHREKS_TELEMETRY_PROMOTION_PATH=/var/lib/shreks/promotion-assessments.json
SHREKS_TELEMETRY_OUTPUT_PATH=/var/lib/shreks/telemetry/current.json
SHREKS_TELEMETRY_EVALUATION_POLICY_VERSION=<explicit-reporting-policy-version>
SHREKS_TELEMETRY_CALIBRATION_BUCKET_COUNT=<explicit-integer-2-through-100>
```

The telemetry evaluation policy does not set trading thresholds or starting capital. Starting equity is taken from the restored PAPER ledger, while profitability/proof observations are copied from the sealed evaluation/proof path. Missing proof/promotion evidence is reported as unavailable rather than fabricated.

## Install and start

```sh
sudo install -o root -g root -m 0644 deploy/systemd/shreks-observe.service /etc/systemd/system/shreks-observe.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-evidence.service /etc/systemd/system/shreks-paper-evidence.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-campaign.service /etc/systemd/system/shreks-paper-campaign.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-telemetry.service /etc/systemd/system/shreks-telemetry.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-telemetry.timer /etc/systemd/system/shreks-telemetry.timer
sudo install -o root -g root -m 0644 deploy/systemd/shreks.target /etc/systemd/system/shreks.target
sudo systemctl daemon-reload
sudo systemctl enable --now shreks.target
sudo systemctl enable --now shreks-telemetry.timer
systemctl is-enabled shreks.target
```

`shreks.target` is wanted by `multi-user.target`, so enabling it is the reboot-persistence mechanism for the core PAPER runtime. A healthy host should report `enabled` above and should bring the target and its three required child services back after boot.

The G4 telemetry timer is intentionally independent of `shreks.target`. It schedules a read-only oneshot snapshot once per minute and is enabled under `timers.target`. **telemetry failure does not stop shreks.target** and is not part of deployment success/rollback health gating.

Verify the three core processes and the independent telemetry timer:

```sh
systemctl status shreks-observe
systemctl status shreks-paper-evidence
systemctl status shreks-paper-campaign
systemctl status shreks-telemetry.timer
journalctl -u shreks-observe
journalctl -u shreks-paper-evidence
journalctl -u shreks-paper-campaign
journalctl -u shreks-telemetry.service
```

A crash or reboot restarts failed core services automatically. Each core service uses `Restart=on-failure` with a five-second delay and a bounded five-restarts-per-five-minutes start limit. Persistent release/config/state paths are required before service startup, and each core service verifies `/var/lib/shreks` exists and is writable before entering its runtime.

The paper campaign has an additional fail-closed recovery gate: systemd runs the runtime with `--preflight` before `ExecStart`. The preflight loads and validates the same manifest, checkpoint, evidence attribution, and accounting/restart state used by the autonomous PAPER runtime without executing a cycle. If recovery is uncertain, preflight exits nonzero and the campaign does not start.

The telemetry service also runs a read-only `--preflight` before writing `/var/lib/shreks/telemetry/current.json`. Failure leaves the previous snapshot intact and is visible through the telemetry service journal; it does not weaken PAPER safety or stop the core target.

## Crash/reboot health evidence

After any process crash, host reboot, deployment, or unexpected restart, capture systemd's own supervision evidence for every core child service:

```sh
systemctl show shreks-observe.service -p ActiveState -p SubState -p NRestarts -p ExecMainStatus -p ActiveEnterTimestamp
systemctl show shreks-paper-evidence.service -p ActiveState -p SubState -p NRestarts -p ExecMainStatus -p ActiveEnterTimestamp
systemctl show shreks-paper-campaign.service -p ActiveState -p SubState -p NRestarts -p ExecMainStatus -p ActiveEnterTimestamp
```

The fields mean:

- `ActiveState` and `SubState`: whether systemd currently considers the process running.
- `NRestarts`: how many automatic service restarts systemd has performed for the current manager lifetime.
- `ExecMainStatus`: the most recent main-process exit status.
- `ActiveEnterTimestamp`: when the service most recently entered the active state.

Inspect the current boot's journals around the restart as well:

```sh
journalctl -b -u shreks-observe.service
journalctl -b -u shreks-paper-evidence.service
journalctl -b -u shreks-paper-campaign.service
```

A target-level `active` result alone is not enough. All three core child services must be active; G2/G3 release activation and rollback also gate success on each child plus `shreks.target` independently. Telemetry is monitored separately because reporting failure must not become execution authority.

## Persistent-state and release provenance checks

Before treating a restarted host as safe for unattended PAPER operation, confirm the exact active release and that the protected durable inputs are still readable:

```sh
readlink -f /opt/shreks/current
test -r /etc/shreks/paper-campaign.json
test -r /var/lib/shreks/shreks.db
test -r /var/lib/shreks/paper-evaluation-e11.json
test -r /var/lib/shreks/telemetry/current.json
```

The resolved `/opt/shreks/current` target must be the expected verified release SHA. Do not create a fresh SQLite database, E11 ledger, checkpoint namespace, or campaign manifest just to make a restart pass. If the expected durable state is missing, corrupt, contradictory, or cannot be reconciled, keep autonomous entries halted and repair/recover the evidence rather than resetting history.

Before treating a restarted runtime as healthy, also confirm the observer is advancing, the paper-evidence daemon is completing bounded cycles, `shreks-paper-campaign` is emitting PAPER status records, the shared database and E11 evidence are durable, and provider-failure counts are not silently rising. The telemetry timer should continue producing private snapshots, but a telemetry failure alone does not change trading state.

## Start-limit failures

Repeated core-service failure is intentionally bounded rather than restarted forever. If systemd reports `start-limit-hit`, inspect `ExecMainStatus`, the service journal, the PAPER preflight failure record, persistent-state readability, and release provenance first.

Use `reset-failed` only after the root cause is resolved and the durable recovery checks above are clean:

```sh
sudo systemctl reset-failed shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service
sudo systemctl start shreks.target
```

Do not use `reset-failed` as a retry loop. If the campaign preflight still fails, leave it failed closed.

Critically, **do not bypass the campaign preflight** and **do not launch the campaign runtime manually** with the Python module or a direct process command. Manual launch would bypass systemd's `ExecStartPre`, mount/readiness checks, restart limits, target membership, and the auditable restart counters that G3 relies on.

## Upgrade and rollback

Build/test the intended sealed commit first. G2's root-owned release manager stops `shreks.target`, installs the core and telemetry unit files from the verified release, atomically repoints `/opt/shreks/current`, reloads systemd, starts the target, and requires observer, paper evidence, paper campaign, and target to all be active. A failed core child triggers rollback; rollback is not considered successful until every restored core child and the target are active again. Telemetry units are versioned and restored with the release, but telemetry activity is not a release health gate.

Do not replace or delete the persistent database, E11 evidence, campaign manifest, telemetry history/output directory, or protected environment file during a code rollback. Preserve evidence history. If recovery or reconciliation fails, keep paper/live execution disabled and investigate before resuming autonomous operation.

G4 adds read-only four-layer telemetry and independent monitoring supervision only. It does not add a dashboard, alerts, auto-remediation, promotion authority, transaction construction, signing, submission, wallet handling, or live execution.

**LIVE TRADING: DISABLED**
