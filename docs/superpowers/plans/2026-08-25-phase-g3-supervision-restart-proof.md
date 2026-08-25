# Phase G3 24/7 Supervision and Restart Proof Implementation Plan

**Goal:** Harden the existing systemd PAPER runtime so process failure/reboot restart, persistent-state recovery, bounded crash loops, per-service health gating, and restart observability are explicitly proven without changing trading authority.

**Base:** sealed G2 `f71f448f79f2257e081f80e4a3caf2d0dfc6c9e7`

**Design:** `docs/superpowers/specs/2026-08-25-phase-g3-supervision-restart-proof-design.md`

**LIVE TRADING: DISABLED.**

## Task 1 — systemd persistent-state and bounded restart contract

**Files:**
- modify `deploy/systemd/shreks-observe.service`
- modify `deploy/systemd/shreks-paper-evidence.service`
- modify `deploy/systemd/shreks-paper-campaign.service`
- modify `deploy/systemd/shreks.target`
- modify `crates/shreks-observer/tests/systemd_units.rs`

### RED

Add tests requiring:

- `RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current`
- `StartLimitIntervalSec=300`
- `StartLimitBurst=5`
- `Restart=on-failure`
- `RestartSec=5s`
- `/usr/bin/test -d /var/lib/shreks`
- `/usr/bin/test -w /var/lib/shreks`
- campaign `PartOf=shreks.target`
- campaign preflight command before `ExecStart`
- target `Requires=` all three services
- target remains `WantedBy=multi-user.target`

Run full CI and confirm Rust fails only on the new supervision assertions.

### GREEN

Update units only. Do not alter executable/runtime authority.

## Task 2 — read-only PAPER recovery preflight

**Files:**
- modify `python/src/shreks_brain/observer_campaign/runtime.py`
- modify `python/tests/test_observer_campaign_runtime.py`

### RED

Tests must prove a preflight function/CLI:

- loads the same runtime config and bootstrap path;
- returns success for valid durable state;
- emits structured `READY` PAPER metadata;
- does not call `run_cycle` or `evaluated_trades`;
- creates no checkpoint when none existed;
- leaves evidence bytes unchanged when evidence exists;
- restores/validates an existing checkpoint without advancing its sequence;
- fails closed on invalid manifest/checkpoint/evidence state;
- rejects unknown CLI arguments.

### GREEN

Add internal `--preflight` mode only. Do not export new authority from `observer_campaign.__init__`.

## Task 3 — per-service deployment health and rollback gating

**Files:**
- modify `deploy/release/release_manager.py`
- modify `python/tests/test_g2_release_manager.py`

### RED

Require activation health checks for each service plus `shreks.target`. Prove:

- one failed child service triggers rollback even if target itself is active;
- rollback is successful only after all restored services and target are active;
- first-deploy child failure leaves no active release claim;
- health probing remains read-only and contains no runtime secret/state mutation.

### GREEN

Centralize the exact four-unit health check in the release manager and reuse it for activation and rollback.

## Task 4 — operator restart/reboot observability and proof

**Files:**
- modify `deploy/systemd/README.md`
- extend `crates/shreks-observer/tests/systemd_units.rs`
- add a G3 restart-idempotency proof test only if existing sealed runtime tests do not already cover the exact restart condition.

Lock runbook instructions for:

- enable-on-boot `shreks.target`;
- `systemctl show` fields `ActiveState`, `SubState`, `NRestarts`, `ExecMainStatus`, `ActiveEnterTimestamp`;
- per-service status/journal inspection;
- `systemctl reset-failed` only after the root cause is resolved;
- never bypass preflight/start limits by launching campaign runtime manually;
- persistent-state/provenance checks before resuming unattended operation.

## Task 5 — freeze, audit, verification record, seal

After final behavior CI is GREEN:

1. freeze exact behavior SHA and CI/pass count;
2. compare sealed G2 -> G3 behavior;
3. audit every changed file;
4. verify no strategy/risk/provider/storage/execution/promotion/signing/live authority change;
5. replace this plan with a final verification record;
6. seal with one docs-only commit whose subject contains `seal`;
7. prove behavior->seal is exactly one commit/one verification file;
8. require exact-seal Python/Rust/repository-safety GREEN;
9. update stacked draft PR metadata;
10. remain draft/unmerged and keep live disabled.
