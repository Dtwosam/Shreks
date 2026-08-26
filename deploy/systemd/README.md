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
- Durable G6 alert queue/state: `/var/lib/shreks/alerts/state.json`
- Service identity: dedicated unprivileged `shreks` user/group.

Create the runtime identity and persistent directories once:

```sh
sudo useradd --system --home /var/lib/shreks --shell /usr/sbin/nologin shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks/telemetry
sudo install -d -o shreks -g shreks -m 0700 /var/lib/shreks/alerts
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

Do not use an editable Python install for the production release. `shreks-paper-campaign.service`, `shreks-telemetry.service`, and `shreks-alerts.service` start `/opt/shreks/current/.venv/bin/python`, and the units disable Python bytecode writes so the release tree stays read-only at runtime.

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

### G5 private read-only dashboard configuration

G5 adds a separate authenticated operator view over the sealed G4 telemetry and persisted PAPER evidence. It has no trade, risk, promotion, signing, submission, wallet, or filesystem-mutation authority. Configure only the dashboard transport/read-side values:

```text
SHREKS_DASHBOARD_BIND_HOST=127.0.0.1
SHREKS_DASHBOARD_PORT=<explicit-port-1024-through-65535>
SHREKS_DASHBOARD_USERNAME=<operator-username>
SHREKS_DASHBOARD_PASSWORD_FILE=/etc/shreks/dashboard-password
SHREKS_DASHBOARD_TELEMETRY_PATH=/var/lib/shreks/telemetry/current.json
SHREKS_DASHBOARD_MAX_TRADES=<explicit-integer-1-through-500>
```

Create the password outside GitHub and outside the release tree, then install it separately as a protected host secret. Ownership/mode should be `root:shreks 0640`:

```sh
sudo install -o root -g shreks -m 0640 dashboard-password /etc/shreks/dashboard-password
```

The dashboard listener is **loopback only**. Do not bind it to a public interface and do not expose its **plain HTTP port** directly to the public Internet. For phone or remote access, terminate HTTPS with a **same-host TLS reverse proxy** that forwards only to loopback, or use an **authenticated private overlay/tunnel**. Keep the dashboard's own Basic authentication enabled behind either transport.

### G6 outbound alert configuration

G6 adds **outbound notifications only**. It reads sealed telemetry, persisted provider/PAPER evidence, and read-only systemd health; it writes only its own durable alert queue. There are **no commands or trading controls through Telegram**, no incoming bot updates/webhooks, and no auto-remediation.

Configure the non-secret operational values explicitly:

```text
SHREKS_ALERTS_TELEGRAM_CHAT_ID=<explicit-private-chat-id>
SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE=/etc/shreks/telegram-bot-token
SHREKS_ALERTS_STATE_PATH=/var/lib/shreks/alerts/state.json
SHREKS_ALERTS_MARKET_STALE_MS=<explicit-positive-milliseconds>
SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE=<explicit-positive-integer>
SHREKS_ALERTS_TELEMETRY_PATH=/var/lib/shreks/telemetry/current.json
```

The Telegram bot token is a host-only secret. It is **never stored in the environment file or GitHub**. Create it outside the release tree and install it with ownership/mode `root:shreks 0640`:

```sh
sudo install -o root -g shreks -m 0640 telegram-bot-token /etc/shreks/telegram-bot-token
```

G6 reuses the existing `SHREKS_PAPER_CAMPAIGN_*` paths to restore/read PAPER ledger evidence; it does not create a second trading-policy namespace. The alert state file is created atomically under `/var/lib/shreks/alerts/state.json` with private permissions. Before each send, the full detected queue is persisted. After a successful send, only that event is acknowledged. If delivery fails, the **failed event and all later events remain queued** for the next timer run.

## Install and start

```sh
sudo install -o root -g root -m 0644 deploy/systemd/shreks-observe.service /etc/systemd/system/shreks-observe.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-evidence.service /etc/systemd/system/shreks-paper-evidence.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-campaign.service /etc/systemd/system/shreks-paper-campaign.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-telemetry.service /etc/systemd/system/shreks-telemetry.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-telemetry.timer /etc/systemd/system/shreks-telemetry.timer
sudo install -o root -g root -m 0644 deploy/systemd/shreks-dashboard.service /etc/systemd/system/shreks-dashboard.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-alerts.service /etc/systemd/system/shreks-alerts.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-alerts.timer /etc/systemd/system/shreks-alerts.timer
sudo install -o root -g root -m 0644 deploy/systemd/shreks.target /etc/systemd/system/shreks.target
sudo systemctl daemon-reload
sudo systemctl enable --now shreks.target
sudo systemctl enable --now shreks-telemetry.timer
sudo systemctl enable --now shreks-dashboard.service
sudo systemctl enable --now shreks-alerts.timer
systemctl is-enabled shreks.target
```

`shreks.target` is wanted by `multi-user.target`, so enabling it is the reboot-persistence mechanism for the core PAPER runtime. A healthy host should report `enabled` above and should bring the target and its three required child services back after boot.

The G4 telemetry timer is intentionally independent of `shreks.target`. It schedules a read-only oneshot snapshot once per minute and is enabled under `timers.target`. **telemetry failure does not stop shreks.target** and is not part of deployment success/rollback health gating.

The two telemetry unit files are a G4 host-bootstrap artifact. Install or update them only from the exact sealed G4 source being deployed. The sealed G2 v1 release-bundle schema and root-owned core release manager remain unchanged so pre-G4 verified releases stay valid rollback points. Do not treat telemetry-unit installation as a bypass around G2's verified core release path.

The G5 dashboard service is also intentionally independent of `shreks.target`; enable it separately with `systemctl enable --now shreks-dashboard.service`. Its listener is constrained to localhost by both the validated dashboard configuration and systemd network policy. **dashboard failure cannot stop the PAPER runtime**. G5 is read-only: there are **no operator controls until G7**, and a dashboard outage must not mutate or restart authoritative trading state.

The G6 alert timer is intentionally independent of `shreks.target` and runs `shreks-alerts.service` once per minute. The oneshot service has outbound network access for Telegram but only `/var/lib/shreks/alerts` is writable. **alert failure cannot stop the PAPER runtime**. A failed delivery returns nonzero and leaves the durable queue intact for the next timer cycle; it never starts, stops, restarts, halts, promotes, signs, submits, or otherwise controls trading services.

Verify the three core processes and the independent telemetry/dashboard/alert services:

```sh
systemctl status shreks-observe
systemctl status shreks-paper-evidence
systemctl status shreks-paper-campaign
systemctl status shreks-telemetry.timer
systemctl status shreks-dashboard.service
systemctl status shreks-alerts.timer
journalctl -u shreks-observe
journalctl -u shreks-paper-evidence
journalctl -u shreks-paper-campaign
journalctl -u shreks-telemetry.service
journalctl -u shreks-dashboard.service
journalctl -u shreks-alerts.service
```

A crash or reboot restarts failed core services automatically. Each core service uses `Restart=on-failure` with a five-second delay and a bounded five-restarts-per-five-minutes start limit. Persistent release/config/state paths are required before service startup, and each core service verifies `/var/lib/shreks` exists and is writable before entering its runtime.

The paper campaign has an additional fail-closed recovery gate: systemd runs the runtime with `--preflight` before `ExecStart`. The preflight loads and validates the same manifest, checkpoint, evidence attribution, and accounting/restart state used by the autonomous PAPER runtime without executing a cycle. If recovery is uncertain, preflight exits nonzero and the campaign does not start.

The telemetry service also runs a read-only `--preflight` before writing `/var/lib/shreks/telemetry/current.json`. Failure leaves the previous snapshot intact and is visible through the telemetry service journal; it does not weaken PAPER safety or stop the core target.

The dashboard service has no writable runtime path. It reads the protected password, G4 telemetry, and configured PAPER evidence through the release's read-only dashboard source and serves only authenticated GET routes. Its restart policy is bounded independently from the core PAPER target.

The alert service is a short-lived oneshot. It persists its own queue before any network send, acknowledges successful messages one at a time, and relies on `shreks-alerts.timer` for bounded retry cadence. It has no inbound network listener and no authority to mutate the sources it observes.

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

A target-level `active` result alone is not enough. All three core child services must be active; G2/G3 release activation and rollback also gate success on each child plus `shreks.target` independently. Telemetry is monitored separately because reporting failure must not become execution authority. The G5 dashboard and G6 alerts are monitored separately for the same reason.

## Persistent-state and release provenance checks

Before treating a restarted host as safe for unattended PAPER operation, confirm the exact active release and that the protected durable inputs are still readable:

```sh
readlink -f /opt/shreks/current
test -r /etc/shreks/paper-campaign.json
test -r /etc/shreks/dashboard-password
test -r /etc/shreks/telegram-bot-token
test -r /var/lib/shreks/shreks.db
test -r /var/lib/shreks/paper-evaluation-e11.json
test -r /var/lib/shreks/telemetry/current.json
test -r /var/lib/shreks/alerts/state.json
```

The resolved `/opt/shreks/current` target must be the expected verified release SHA. Do not create a fresh SQLite database, E11 ledger, checkpoint namespace, or campaign manifest just to make a restart pass. If the expected durable state is missing, corrupt, contradictory, or cannot be reconciled, keep autonomous entries halted and repair/recover the evidence rather than resetting history.

Before treating a restarted runtime as healthy, also confirm the observer is advancing, the paper-evidence daemon is completing bounded cycles, `shreks-paper-campaign` is emitting PAPER status records, the shared database and E11 evidence are durable, and provider-failure counts are not silently rising. The telemetry timer should continue producing private snapshots, but a telemetry failure alone does not change trading state. Dashboard health is observational only and cannot repair, halt, promote, or execute anything. Alert health is notification-only; a delivery failure must not mutate authoritative state or become a reason to bypass PAPER safety gates.

## Start-limit failures

Repeated core-service failure is intentionally bounded rather than restarted forever. If systemd reports `start-limit-hit`, inspect `ExecMainStatus`, the service journal, the PAPER preflight failure record, persistent-state readability, and release provenance first.

Use `reset-failed` only after the root cause is resolved and the durable recovery checks above are clean:

```sh
sudo systemctl reset-failed shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service
sudo systemctl start shreks.target
```

Do not use `reset-failed` as a retry loop. If the campaign preflight still fails, leave it failed closed.

Critically, **do not bypass the campaign preflight** and **do not launch the campaign runtime manually** with the Python module or a direct process command. Manual launch would bypass systemd's `ExecStartPre`, mount/readiness checks, restart limits, target membership, and the auditable restart counters that G3 relies on.

For the independently supervised dashboard, inspect `systemctl status shreks-dashboard.service` and `journalctl -u shreks-dashboard.service` before resetting a start-limit failure. Do not work around failed authentication, unreadable evidence, or non-loopback configuration by weakening the unit hardening.

For G6 alerts, inspect `systemctl status shreks-alerts.timer`, `systemctl status shreks-alerts.service`, and `journalctl -u shreks-alerts.service`. Do not delete `/var/lib/shreks/alerts/state.json` to suppress or skip a failed notification; preserve the queue and fix the host secret, connectivity, or source-read problem.

## Upgrade and rollback

Build/test the intended sealed commit first. G2's root-owned release manager continues to own the verified core code rollout: it stops `shreks.target`, installs the four core systemd units from the verified v1 release, atomically repoints `/opt/shreks/current`, reloads systemd, starts the target, and requires observer, paper evidence, paper campaign, and target to all be active. A failed core child triggers rollback; rollback is not considered successful until every restored core child and the target are active again.

G4 telemetry supervision is deliberately outside that core health/rollback contract. On first G4 host enablement, install the telemetry service/timer from the exact sealed G4 source after the verified G4 code release is active, then enable the timer. If rolling back to a pre-G4 code release, disable the telemetry timer because that older Python release does not contain the telemetry runtime. This monitoring transition never substitutes for or weakens the G2 core rollback path.

G5 dashboard supervision is also outside the core health/rollback contract. Install or update `shreks-dashboard.service` only from the exact verified G5 source after its code release is active. If rolling back to a pre-G5 release, disable the dashboard service because that release does not contain the dashboard runtime. Dashboard failure must never be treated as permission to bypass a PAPER proof, risk, recovery, or deployment gate.

G6 alert supervision is likewise outside the core health/rollback contract. Install or update `shreks-alerts.service` and `shreks-alerts.timer` only from the exact verified G6 source after its code release is active. If rolling back to a pre-G6 release, disable `shreks-alerts.timer` because that older Python release does not contain the alert runtime. Alert failure must never be treated as permission to bypass a PAPER proof, risk, recovery, or deployment gate.

Do not replace or delete the persistent database, E11 evidence, campaign manifest, telemetry history/output directory, protected dashboard password, protected Telegram token, durable alert queue, or protected environment file during a code rollback. Preserve evidence history. If recovery or reconciliation fails, keep paper/live execution disabled and investigate before resuming autonomous operation.

G4 adds read-only four-layer telemetry and independent monitoring supervision. G5 adds a private authenticated read-only dashboard over that evidence. G6 adds durable outbound critical alerts and phone notifications. None of these phases adds auto-remediation, promotion authority, transaction construction, signing, submission, wallet handling, Telegram control commands, or live execution.

Real phone delivery is not considered proven until the deployed host has an operator-supplied Telegram chat ID and protected bot token and an actual notification is observed on the intended phone. Repository/CI proof establishes the outbound-only contract and durable retry semantics, not external Telegram delivery availability.

**LIVE TRADING: DISABLED**
