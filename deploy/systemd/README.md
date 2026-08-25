# Shreks systemd deployment

This is the initial single-host Linux supervision layout for the paper runtime. GitHub remains the source/review/CI/release control plane; these services run continuously on the execution host.

**LIVE TRADING: DISABLED**

## Host layout

- Release checkout or symlink: `/opt/shreks/current`
- Runtime environment file: `/etc/shreks/shreks.env`
- Persistent operational state: keep the configured SQLite database under a durable host path such as `/var/lib/shreks/`, never inside an ephemeral release directory.
- Service identity: dedicated unprivileged `shreks` user/group.

Create the runtime identity and persistent directories once:

```sh
sudo useradd --system --home /var/lib/shreks --shell /usr/sbin/nologin shreks
sudo install -d -o shreks -g shreks -m 0750 /var/lib/shreks
sudo install -d -o root -g shreks -m 0750 /etc/shreks
```

Build the sealed branch/release and make it available at `/opt/shreks/current`:

```sh
cd /opt/shreks/current
cargo build --release --workspace
```

Create `/etc/shreks/shreks.env` from the repository `.env.example`, then fill every required runtime value on the host. Provider credentials and evidence-campaign parameters belong only in this host file or an equivalent protected runtime secret mechanism. Do not commit populated values.

```sh
sudo chmod 600 /etc/shreks/shreks.env
sudo chown root:root /etc/shreks/shreks.env
```

The configured database path must resolve to persistent storage writable by the `shreks` service user. Both processes must point at the same authoritative SQLite WAL database.

## Install and start

```sh
sudo install -o root -g root -m 0644 deploy/systemd/shreks-observe.service /etc/systemd/system/shreks-observe.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks-paper-evidence.service /etc/systemd/system/shreks-paper-evidence.service
sudo install -o root -g root -m 0644 deploy/systemd/shreks.target /etc/systemd/system/shreks.target
sudo systemctl daemon-reload
sudo systemctl enable --now shreks.target
```

Verify both processes are supervised:

```sh
systemctl status shreks-observe
systemctl status shreks-paper-evidence
journalctl -u shreks-observe
journalctl -u shreks-paper-evidence
```

A crash or reboot should restart the services automatically. Before treating a restarted runtime as healthy, confirm the observer is advancing, the paper-evidence daemon is completing bounded cycles, the shared database is durable, and provider-failure counts are not silently rising.

## Upgrade and rollback

Build/test the intended sealed commit first. Stop `shreks.target`, atomically repoint `/opt/shreks/current` to the tested release, then start the target again. Do not replace or delete the persistent database during a code rollback. Preserve the environment file and evidence history. If recovery or reconciliation fails, keep paper/live execution disabled and investigate before resuming autonomous operation.
