# Phase G3 24/7 Supervision and Restart Proof Design

**Base:** sealed G2 `f71f448f79f2257e081f80e4a3caf2d0dfc6c9e7`

**Canonical requirement:** Phase G3 requires Shreks services to restart after process failure or host reboot, reopen persistent state before autonomous work resumes, pause new entries when recovery/reconciliation is uncertain, avoid duplicate intents/trades across restart, and expose service/runtime health.

**LIVE TRADING: DISABLED.**

## 1. Decision

Use the existing `systemd` architecture. Do not introduce Docker, Kubernetes, Redis, an external supervisor, or a second runtime control plane.

G1C already established the three production PAPER services and `shreks.target`; G2 established immutable release activation. G3 hardens those existing boundaries rather than replacing them.

## 2. Existing sealed behavior relied on

The PAPER campaign runtime already bootstraps persisted state before its cycle loop. `ObserverPaperCampaignRunner` loads evidence/checkpoints, validates accounting, rejects corrupt checkpoint/evidence state, makes exact completed-cycle replay idempotent, and validates checkpoint restart equivalence after writes.

Therefore uncertain campaign recovery already fails before another autonomous cycle can execute. G3 will make that recovery check explicit as a systemd `ExecStartPre` preflight and bound repeated crash loops so a persistent fault becomes an observable failed service rather than an endless restart storm.

## 3. Systemd supervision contract

All three services will retain non-root `User=shreks` / `Group=shreks`, the sealed `/opt/shreks/current` release path, and `Restart=on-failure`.

Each service will add:

- `RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current`
- `StartLimitIntervalSec=300`
- `StartLimitBurst=5`
- `RestartSec=5s`
- pre-start checks that `/var/lib/shreks` exists and is writable by the service user.

The PAPER campaign service will additionally run a recovery-only Python preflight before `ExecStart`. The preflight loads the same runtime config/manifest and invokes the same sealed bootstrap path, but it performs no cycle, no entry/exit decision, no checkpoint write, and no evidence mutation.

`shreks-paper-campaign.service` will also gain `PartOf=shreks.target` so target stop/restart propagation covers all three services consistently.

`shreks.target` will require, rather than merely want, the three runtime services during target start. Runtime health after start will still be checked per service because a target can remain active after a child later fails.

## 4. Recovery preflight

Add an internal `--preflight` mode to `python -m shreks_brain.observer_campaign.runtime`.

Preflight semantics:

1. load the same environment-backed runtime config;
2. decode and validate the same sealed campaign manifest;
3. construct the same coordinator runner;
4. load persisted evidence/checkpoint state;
5. run existing accounting/attribution validation through bootstrap;
6. emit one structured PAPER `READY` status line and exit `0`;
7. on any uncertainty/error, emit existing failure metadata and exit nonzero;
8. never call `run_cycle` or `evaluated_trades` and never create a checkpoint/evidence mutation.

This is a supervision/readiness mode only. It does not add public strategy, risk, execution, promotion, signing, or live authority.

## 5. Deployment health gating

G2 initially health-checked only `shreks.target`. G3 will strengthen `release_manager.py` so activation and rollback require all of:

- `shreks-observe.service`
- `shreks-paper-evidence.service`
- `shreks-paper-campaign.service`
- `shreks.target`

to be active.

If any service fails its activation health check, the release manager uses the existing rollback path. The previous release is not considered restored until all three services and the target are active.

This change improves deployment correctness only; it does not alter runtime trading behavior.

## 6. Restart and duplicate-action proof

G3 will add/retain tests proving:

- the systemd target is enabled under `multi-user.target` for reboot startup;
- services restart on failure but stop retrying after a bounded burst;
- persistent paths are ordered before startup;
- campaign recovery preflight runs before the autonomous loop;
- a successful preflight creates no cycle/checkpoint/evidence mutation;
- corrupt/invalid recovery state makes preflight fail closed;
- restart bootstrap restores the prior checkpoint before more work;
- exact completed-cycle replay remains idempotent and does not create duplicate paper actions;
- deploy/rollback health checks inspect every service.

No new trade-idempotency implementation is justified because the sealed campaign runner already owns that behavior.

## 7. Health observability

G3 uses native systemd observability rather than building G4 telemetry early. The operator runbook will include commands exposing:

- `ActiveState`
- `SubState`
- `NRestarts`
- `ExecMainStatus`
- service start timestamps
- recent journal entries

for each service, plus current release provenance and target status.

Persistent faults that exhaust the start limit become visible as failed/inactive service state. G4 will later aggregate these signals into telemetry/dashboard surfaces.

## 8. Authority exclusions

G3 must not add:

- wallet/private signing key handling;
- transaction construction/signing/submission;
- live-mode enablement;
- strategy/scoring/risk threshold changes;
- registry/promotion mutation;
- new trade execution paths;
- database schema/migration changes;
- external orchestration infrastructure.

The only production behavior changes are supervision/readiness and deployment health gating around already sealed PAPER runtime behavior.
