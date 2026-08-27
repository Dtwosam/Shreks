# G3 systemd member-restart isolation production seal

Date: 2026-08-27

## Scope

This seal qualifies the G3 systemd supervision correction that prevents an individual core PAPER runtime service restart from cascading into a target-wide sibling shutdown.

LIVE TRADING remains disabled. This change does not add signing, submission, wallet, promotion, live-mode, trading-policy, or risk authority.

## Production evidence that exposed the defect

The previously sealed graceful-shutdown release `7b96f87748eb4311ae1b286895e0bbbb176380ff` was deployed to the production VPS and the observer was restarted directly through systemd.

The observer graceful-shutdown fix itself passed physical acceptance:

- active release resolved to `/opt/shreks/releases/7b96f87748eb4311ae1b286895e0bbbb176380ff`;
- all four core runtime units were active before the restart;
- loaded observer contract remained `KillSignal=SIGINT`, `TimeoutStopSec=30s`, `Restart=on-failure`;
- `systemctl restart shreks-observe.service` returned `RESTART_RC=0`;
- measured restart duration was `RESTART_SECONDS=0`;
- observer returned `Result=success`, `ExecMainStatus=0`, `ActiveState=active`, `SubState=running`;
- journal recorded `Shreks observe stopped: legacy_cycles=1 v2_sampler_cycles=0`, followed by successful deactivation and immediate clean start;
- no `stop-sigterm` timeout, `SIGKILL`, `status=9/KILL`, or timeout-result signature appeared.

That host acceptance therefore closes the physical proof boundary for the observer in-flight provider shutdown defect.

The same direct member restart exposed a separate supervision defect in the existing systemd topology. After the clean observer restart, `shreks.target` became inactive and `shreks-paper-campaign.service` was re-entering activation. The observer itself had succeeded; the final runtime-state failure was a target/member dependency cascade.

## Root cause

The sealed target declared all three core runtime members with:

```ini
Requires=shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service
```

Each member also declares:

```ini
PartOf=shreks.target
Restart=on-failure
```

Stopping a required member as part of an explicit member restart can deactivate the requiring target. Because the members are also `PartOf=shreks.target`, target deactivation propagates into sibling stops. This defeats the intended G3 bounded per-process recovery behavior by turning one member restart into a wider runtime teardown.

## Sealed behavior

`shreks.target` now starts the three core members with:

```ini
Wants=shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service
```

The member units retain `PartOf=shreks.target` and `Restart=on-failure`.

This preserves the intended lifecycle split:

- starting or boot-enabling `shreks.target` pulls all three core PAPER services in;
- intentionally stopping/restarting the target still propagates to members through `PartOf=shreks.target`;
- an individual member's bounded restart no longer makes the target depend on that transient stop and therefore should not cascade-stop siblings;
- release activation and rollback continue to verify every core unit plus `shreks.target` independently before success;
- fail-closed application recovery/preflight and durable SQLite state semantics remain unchanged.

## TDD proof

RED commit:

- `18d623263db0c012214755ae21b3e09bbdad78d0` — `test: reproduce systemd target restart cascade`
- CI run `33118353640`
- Python and repository-safety jobs passed.
- Rust failed at the new regression test because `shreks.target` did not yet contain the required core-service `Wants=` contract.

GREEN implementation commit:

- `fc5e0b37c0bcb77bf71cbb44677a79dd7bd20d72` — `fix: isolate runtime member restarts from target teardown`
- PR #67 changed only the target dependency directive plus the regression test.
- GREEN PR CI run `33118474371`: Rust, Python, repository safety, and native ARM64 release build all passed.

Merged main:

- merge commit `a47a5af21693a63e2d892d4961ff77aed01cf76d`
- merged-main CI run `33118613459`: Rust, Python, repository safety, and native ARM64 release build all passed.

## Scope audit

Code delta is intentionally narrow:

1. `deploy/systemd/shreks.target`: `Requires=` changed to `Wants=` for the three existing core runtime members.
2. `crates/shreks-observer/tests/systemd_units.rs`: regression contract updated to require `Wants=` and reject the old core-member `Requires=` line.

No observer provider code, PAPER strategy logic, accounting, safety policy, risk policy, execution authority, database schema, release verifier, or deployment verifier was changed.

## Remaining physical-host acceptance boundary

This seal is eligible for release/deployment only after its own seal CI is green.

After deployment to the production VPS, physical acceptance must directly restart `shreks-observe.service` and prove all of the following in the same observation window:

1. `/opt/shreks/current` resolves to this exact sealed release.
2. `shreks.target`, evidence, campaign, and observer are active before the drill.
3. observer restart completes below the unchanged 30-second timeout with no SIGKILL/timeout signature.
4. `shreks.target` remains active throughout/after the member restart.
5. evidence and campaign remain active and do not undergo a restart caused by the observer drill; capture their main PIDs before and after to prove sibling continuity.
6. observer main PID changes as expected for the direct restart.
7. all four core runtime units are active after the drill.
8. persistent PAPER state remains readable/continuous; no state reset or fresh database is used to make acceptance pass.

Until that physical restart-isolation drill passes, the supervision topology is not considered host-sealed.

**LIVE TRADING: DISABLED.**
