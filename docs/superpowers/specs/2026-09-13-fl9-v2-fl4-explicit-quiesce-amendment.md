# FL9 V2 FL4 Physical Runbook — Explicit Quiesce Amendment

## Status

**AUTHORIZED RUNBOOK AMENDMENT.**

This document supersedes only the quiesce stop operation in `docs/superpowers/specs/2026-09-12-fl9-v2-fl4-physical-execution-runbook.md`.

The original runbook says to stop `shreks.target` and then require the three PAPER runtime services to be inactive. During the first physical execution attempt against sealed runtime `9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`, that target-only stop did not produce the required inactive service state: `shreks-observe.service` remained active, the gate failed before any database-holder check, authenticated request creation, or FL4 mutation, and the EXIT restoration path returned PAPER/telemetry to their prior active state.

A subsequent read-only host diagnostic proved:

- `/opt/shreks/current` still resolved to `9ca080ca9b5ad01e39bbaef6c7e024acd4a78f73`;
- all three core services were healthy again with `NRestarts=0`;
- the installed `/etc/systemd/system` unit files were byte-identical to the release-local units;
- each core service exposed `PartOf=shreks.target`;
- there was no unit-file drift to repair.

The existing sealed release manager already defines the canonical explicit PAPER stop order as:

1. `shreks-paper-campaign.service`;
2. `shreks-paper-evidence.service`;
3. `shreks-observe.service`;
4. `shreks.target`.

The FL4 physical procedure must therefore use that same explicit stop order rather than relying on target-only stop propagation.

## Superseding quiesce operation

For all future executions of the physical FL4 runbook, replace only this original operation:

```bash
systemctl stop shreks.target
```

with:

```bash
systemctl stop \
  shreks-paper-campaign.service \
  shreks-paper-evidence.service \
  shreks-observe.service
systemctl stop shreks.target
```

Telemetry handling is unchanged: stop `shreks-telemetry.timer` and any running `shreks-telemetry.service` before stopping the PAPER runtime.

After the explicit stop sequence, the procedure must still require all of the following before any request creation or database mutation:

- `shreks.target` is inactive;
- `shreks-observe.service` is inactive;
- `shreks-paper-evidence.service` is inactive;
- `shreks-paper-campaign.service` is inactive;
- `shreks-telemetry.timer` is inactive;
- the SQLite database, WAL, and SHM have no unexpected holders;
- frozen-cohort authority and prestate are reauthenticated under quiescence;
- the out-of-cohort fingerprint exactly matches the pre-quiesce baseline.

Any failure remains a HOLD.

## Unchanged authority

This amendment changes no FL4 population code, cohort identity, expected count, SQLite mutation identity, request format, first-pass report, idempotence report, scope proof, restoration behavior, runtime systemd unit, release artifact, strategy, risk, PAPER promotion rule, transaction authority, or LIVE state.

The SQLite-writing observer must still run only as `shreks`. Root remains limited to cohort authentication, request construction, service control, and read-only verification. PAPER must still be restored on every success or failure path.

LIVE remains disabled.
