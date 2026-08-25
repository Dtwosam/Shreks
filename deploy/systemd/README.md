# Shreks systemd deployment

This is the initial single-host Linux supervision layout for the paper runtime. GitHub remains the source/review/CI/release control plane; these services run continuously on the execution host.

**LIVE TRADING: DISABLED**

## Host layout

- Release checkout or symlink: `/opt/shreks/current`
- Per-release Python environment: `/opt/shreks/current/.venv`
- Runtime environment file: `/etc/shreks/shreks.env`
- Immutable paper-campaign manifest: `/etc/shreks/paper-campaign.json`
- Persistent operational state: keep the configured SQLite database and E11 evidence under a durable host path such as `/var/lib/shreks/`, never inside an ephemeral release directory.
- Service identity: dedicated unprivileged `shreks` user/group.

Create the runtime identity and persistent directories once:

```sh
sudo useradd --system --home /var/lib/shreks --shell /usr/sbin/nologin shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks
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

Do not use an editable Python install for the production release. `shreks-paper-campaign.service` starts `/opt/shreks/current/.venv/bin/python`, and the unit disables Python bytecode writes so the release tree stays read-only at runtime.

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

## Install and start

```sh
sudo install -o root -g root -m 0644 deploy/systemd/shreks-observe.service /etc/systemd/system/shreks-observe.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-evidence.service /etc/systemd/system/shreks-paper-evidence.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-campaign.service /etc/systemd/system/shreks-paper-campaign.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks.target /etc/systemd/system/shreks.target
sudo systemctl daemon-reload
sudo systemctl enable --now shreks.target
```

Verify all three processes are supervised:

```sh
systemctl status shreks-observe
systemctl status shreks-paper-evidence
systemctl status shreks-paper-campaign
journalctl -u shreks-observe
journalctl -u shreks-paper-evidence
journalctl -u shreks-paper-campaign
```

A crash or reboot restarts failed services automatically. The paper campaign does not execute a new cycle until its manifest has validated and the sealed G1B runner has loaded/reconciled durable C6/E11 state. If manifest validation, checkpoint restoration, E11 attribution, accounting, or restart equivalence fails, the process exits nonzero and systemd retries; it does not silently create a fresh trading state.

Before treating a restarted runtime as healthy, confirm the observer is advancing, the paper-evidence daemon is completing bounded cycles, `shreks-paper-campaign` is emitting PAPER status records, the shared database and E11 evidence are durable, and provider-failure counts are not silently rising.

## Upgrade and rollback

Build/test the intended sealed commit first. Stop `shreks.target`, atomically repoint `/opt/shreks/current` to the tested release, then start the target again. Because each release contains its own `.venv`, rollback restores the matching Python implementation as well as the Rust binaries.

Do not replace or delete the persistent database, E11 evidence, or campaign manifest during a code rollback. Preserve the protected environment file and evidence history. If recovery or reconciliation fails, keep paper/live execution disabled and investigate before resuming autonomous operation.

GitHub-to-VPS release automation remains deferred to G2. This G1C unit only proves the supervised PAPER runtime boundary and restart behavior; it does not add deployment credentials, promotion authority, transaction construction, signing, submission, or live execution.

**LIVE TRADING: DISABLED**
