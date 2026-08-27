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

Seal commit and CI:

- seal commit `cb72f76b901bd170b565a53a7269a20247c27908` — `seal: isolate systemd member restarts`
- seal CI run `33118794390`: Rust, Python, repository safety, and native ARM64 release build all passed.

## Scope audit

Code delta is intentionally narrow:

1. `deploy/systemd/shreks.target`: `Requires=` changed to `Wants=` for the three existing core runtime members.
2. `crates/shreks-observer/tests/systemd_units.rs`: regression contract updated to require `Wants=` and reject the old core-member `Requires=` line.

No observer provider code, PAPER strategy logic, accounting, safety policy, risk policy, execution authority, database schema, release verifier, or deployment verifier was changed.

## Physical-host acceptance — PASSED

The exact sealed release was built and deployed through the verified ARM64 delivery path:

- immutable release tag: `shreks-cb72f76b901bd170b565a53a7269a20247c27908`;
- release workflow run `33119367333` completed successfully, including exact sealed-source checkout, Rust tests, Python tests, release-bundle verification, duplicate-tag rejection, and immutable GitHub release creation;
- deploy workflow run `33119585249` completed successfully, including exact release validation, local asset verification before host contact, transfer, and host release-manager invocation;
- production `/opt/shreks/current` resolved exactly to `/opt/shreks/releases/cb72f76b901bd170b565a53a7269a20247c27908`.

The loaded production target contract showed:

```ini
Wants=shreks-observe.service shreks-paper-evidence.service shreks-paper-campaign.service
```

and no old core-member `Requires=` line.

Before the direct observer restart, all four core units were active. Continuity markers were captured:

- `TARGET_ACTIVE_ENTER_BEFORE=108265317556`;
- `EVIDENCE_PID_BEFORE=23277`;
- `CAMPAIGN_PID_BEFORE=23733`.

`systemctl restart shreks-observe.service` then returned `RESTART_RC=0` with `RESTART_SECONDS=0`.

After the observer-only restart:

- `shreks-observe.service=active`;
- `shreks-paper-evidence.service=active`;
- `shreks-paper-campaign.service=active`;
- `shreks.target=active`;
- `TARGET_ACTIVE_ENTER_AFTER=108265317556`, exactly unchanged;
- `EVIDENCE_PID_AFTER=23277`, exactly unchanged;
- `CAMPAIGN_PID_AFTER=23733`, exactly unchanged.

The observer reported:

- `Result=success`;
- `NRestarts=0`;
- `ExecMainCode=0`;
- `ExecMainStatus=0`;
- `ActiveState=active`;
- `SubState=running`.

Its journal recorded a clean stop of PID `23275` and immediate start of PID `23800`, proving the observer process itself changed while its siblings did not. The same journal contained no `stop-sigterm` timeout, `SIGKILL`, `status=9/KILL`, or timeout-result signature.

The sibling/target journal for the same observation window contained no entries and specifically no target, paper-evidence, or paper-campaign stop event. The host acceptance script therefore reported:

```text
No timeout/SIGKILL signatures detected
No sibling/target teardown detected
G3 PRODUCTION SUPERVISION ACCEPTANCE PASSED
```

Persistent PAPER continuity was preserved operationally during the drill: paper-evidence and paper-campaign remained continuously active with the same main PIDs before and after the observer restart, the target active-enter timestamp did not change, and no database, E11, checkpoint, manifest, or other durable state reset/reinitialization action was performed to make acceptance pass.

This closes the production physical-host acceptance boundary for G3 member-restart isolation.

**G3 PRODUCTION SUPERVISION ACCEPTANCE: PASSED.**

**LIVE TRADING: DISABLED.**
