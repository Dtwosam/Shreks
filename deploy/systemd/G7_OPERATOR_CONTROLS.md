# G7 operator control runbook

**LIVE TRADING: DISABLED**

G7 adds only two authenticated browser safety actions: `HALT NEW ENTRIES` and `EMERGENCY KILL SWITCH`. Clearing either safety state is deliberately host-only. The dashboard cannot buy, sell, promote, enable live mode, sign, submit, restart services, reset the kill switch, or clear the entry halt.

## Durable state

Both the PAPER runtime and the private dashboard use exactly one durable state file:

```text
SHREKS_RISK_CONTROL_STATE_PATH=/var/lib/shreks/risk/operator-control.json
```

Create the directory before enabling G7. It must be owned by the unprivileged `shreks` service identity and mode `0700`:

```sh
sudo install -d -o shreks -g shreks -m 0700 /var/lib/shreks/risk
```

Initialize the state exactly once through the host-only authority:

```sh
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.risk_control.cli initialize --state-path /var/lib/shreks/risk/operator-control.json
```

The durable state is written canonically and atomically with mode `0600`; its lock and temporary file stay in the same protected directory. Never hand-edit the JSON. The PAPER runtime reads this file on every cycle. If configured state is missing or invalid, new entries fail closed while emergency liquidation is **not** fabricated.

Before starting the G7 dashboard or PAPER runtime, verify:

```sh
test -r /var/lib/shreks/risk/operator-control.json
test -w /var/lib/shreks/risk
```

## Browser authority

The authenticated dashboard exposes only:

- `HALT NEW ENTRIES` — blocks new entries through the existing risk engine.
- `EMERGENCY KILL SWITCH` — blocks new entries and activates the existing global-halt exit path.

The emergency action requires the exact confirmation phrase `EMERGENCY KILL SWITCH`, CSRF protection, and the current revision. Stale revisions are rejected. Browser controls are disabled when the authoritative state is unavailable or already at an equal/safer state.

There is no browser reset/resume route. A dashboard outage cannot start, stop, restart, promote, sign, submit, or enable live trading.

## Host-only reset procedure

Read the current state first and record the **expected revision** you are acting on:

```sh
sudo -u shreks cat /var/lib/shreks/risk/operator-control.json
```

Do not reset safety state until the incident that caused the halt has been investigated and the operator has verified the PAPER runtime is safe to continue.

Resetting an emergency kill switch is a separate step and intentionally leaves `halt_new_entries=true`:

```sh
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.risk_control.cli reset-kill-switch --state-path /var/lib/shreks/risk/operator-control.json --expected-revision <N> --confirmation 'RESET KILL SWITCH' --reason 'host operator verified incident clear'
```

Re-read the file, take the new expected revision, then clear the entry halt only after the kill switch is inactive:

```sh
sudo -u shreks /opt/shreks/current/.venv/bin/python -m shreks_brain.risk_control.cli clear-entry-halt --state-path /var/lib/shreks/risk/operator-control.json --expected-revision <N> --confirmation 'CLEAR ENTRY HALT' --reason 'host operator verified normal operation'
```

Both host commands require the exact confirmation phrase, the current expected revision, and a bounded audit reason. Revision conflicts fail without mutation. Never delete/recreate the state to bypass a conflict.

## Service authority boundary

`shreks-dashboard.service` remains independent of `shreks.target`. Its systemd sandbox keeps `/var/lib/shreks` and `/etc/shreks` read-only except for the single `ReadWritePaths=/var/lib/shreks/risk` exception required to persist the two G7 safety-increasing actions. It remains loopback-only and cannot manage services.

`shreks-paper-campaign.service` reads the same state file and refuses startup when that configured file is unreadable. It has no dependency on the dashboard. The dashboard is not added to `shreks.target`, so dashboard failure cannot stop the PAPER runtime.

## Rollback

When performing a **rollback to a pre-G7 release**, preserve the G7 risk-control state at `/var/lib/shreks/risk/operator-control.json`. Do not delete, truncate, replace, or silently reinitialize it merely because the older release does not consume it.

After a rollback to a pre-G7 release, browser controls are disabled because the older dashboard/runtime does not understand G7 authority. Preserve the G7 risk-control state so a later G7-or-newer deployment resumes from the last auditable safety state instead of manufacturing a permissive default.

If the preserved state indicates a halt or kill condition, treat that state as operational evidence during rollback/recovery. Do not infer that an older release is safe to resume merely because it cannot read the G7 file.

**LIVE TRADING: DISABLED**
