# Fast PAPER Shadow Physical Commissioning — Design

**Date:** 2026-09-27  
**Base main SHA:** `a894a830ed365fa1d6a246a54725a028f83258d7`

## Purpose

Turn the already-prepared, detached Fast PAPER shadow service into a physically
observable VPS workload without granting production PAPER cutover or LIVE
authority.

This slice is the first place that may mutate systemd state for the shadow
unit. Its mutation boundary is deliberately tiny:

1. authenticate the exact active immutable release and completed protected host
   preparation;
2. perform exactly one `systemctl daemon-reload`;
3. perform exactly one `systemctl start shreks-fast-paper-shadow.service`;
4. prove the service remains detached and not enabled;
5. observe the running process for a bounded window;
6. record exact release/process/runtime/resource evidence;
7. optionally perform one separately explicit restart-reconstruction proof.

It must not stop or replace the legacy PAPER runtime, modify
`shreks.target`, enable the shadow unit, change authority/config/state files,
sign/submit transactions, or enable LIVE.

## CLI

Add one release-local trusted-administrator CLI:

```text
shreks-fast-paper-shadow-physical-commission preflight <expected-release-sha>
shreks-fast-paper-shadow-physical-commission activate <expected-release-sha> --observe-seconds <N>
shreks-fast-paper-shadow-physical-commission observe <expected-release-sha> --observe-seconds <N>
shreks-fast-paper-shadow-physical-commission restart-proof <expected-release-sha> --observe-seconds <N>
```

All commands require effective uid 0 and execution from the exact active
release virtualenv.

Observation windows are explicit bounded integers from 5 through 900 seconds.

## Preconditions

Every command reuses the merged protected host readiness proof and therefore
requires:

- `/opt/shreks/current` equals the explicit source SHA;
- the release-local executable is exact;
- the installed detached unit is exact;
- the protected authority bundle is exact;
- the protected env is exact;
- isolated shadow state ownership/modes are exact;
- supervisor bootstrap succeeds;
- the unit is absent from `shreks.target`.

The systemd unit must still report a non-enabled state. `enabled` and
`enabled-runtime` are forbidden.

## Systemd command allowlist

The production command runner accepts only these exact command families for
`shreks-fast-paper-shadow.service`:

- `systemctl daemon-reload`;
- `systemctl start shreks-fast-paper-shadow.service`;
- `systemctl restart shreks-fast-paper-shadow.service` only from the
  `restart-proof` path;
- `systemctl show ... --no-pager`;
- `systemctl is-enabled ...`;
- `journalctl -u ... --since=@<bounded timestamp> --output=cat --no-pager`.

There is no `enable`, `disable`, `stop`, target mutation, unit-file write,
or release-manager call.

## Activation

`activate` requires the unit to be inactive before mutation and no prior
successful activation receipt.

It then:

1. captures the exact pre-state;
2. runs one daemon reload;
3. re-runs protected host readiness;
4. verifies the unit is still detached/non-enabled;
5. runs one start;
6. waits for `ActiveState=active`, `SubState=running`, positive `MainPID`,
   zero `ExecMainStatus`, and stable exact process provenance;
7. observes for the requested bounded window;
8. requires at least two canonical
   `shreks.fast_paper_shadow_supervisor_status` RUNNING records whose
   `completed_cycles` strictly advance;
9. requires the process PID and restart counter not to change during the
   healthy observation window;
10. records canonical resource/evidence observations;
11. writes a no-replace root-private activation receipt.

If health/observation fails after start, no success receipt is written. The tool
does not gain stop authority as a rollback shortcut. Legacy PAPER remains
authoritative and the failed shadow service must be investigated explicitly.

## Process/release provenance

For the running `MainPID`, prove:

- `/proc/<pid>/cwd` resolves to the exact immutable release directory;
- `/proc/<pid>/cmdline` begins with the active release virtualenv Python path;
- command line contains
  `-m shreks_brain.fast_paper_runtime.shadow_supervisor`;
- systemd `FragmentPath` is the exact installed shadow unit;
- systemd `WorkingDirectory` is `/opt/shreks/current`;
- systemd `User` and `Group` are both `shreks`;
- systemd `PrivateNetwork=yes`.

No process-name heuristic is sufficient by itself.

## Bounded observation evidence

The observation receipt records:

- exact release source SHA;
- unit active/substate/unit-file state;
- MainPID;
- NRestarts;
- ExecMainStatus;
- supervisor manifest/champion/action-policy identity;
- completed-cycle start/end;
- decisions-produced delta;
- executions-committed delta;
- decision/execution cursor start/end;
- PAPER checkpoint start/end;
- pending-BUY/open-position counts;
- process CPU tick delta and normalized CPU percent;
- RSS start/end/peak;
- shadow-state byte size start/end/delta;
- private-network interface names and receive/transmit deltas;
- observation duration;
- receipt fingerprint.

Healthy commissioning does not require a BUY or fill during a short observation
window. It requires the supervised loop itself to advance while its durable
state remains valid.

The private network namespace must expose no non-loopback interface. Any
unexpected non-loopback interface fails the commissioning proof.

## Restart reconstruction proof

`restart-proof` is a distinct explicit root action and is allowed only after a
successful activation receipt exists for the same exact release.

Before restart it authenticates the running service and captures:

- manifest fingerprint;
- run id;
- binding fingerprint;
- checkpoint sequence/fingerprint;
- runtime-state fingerprint;
- last processed source identity;
- pending BUY identity;
- exact ordered market-position identities;
- restart counter.

It then runs exactly one `systemctl restart`, waits for the new MainPID to be
healthy, and observes another bounded window.

The restored state must prove:

- same release/manifest/run/binding identities;
- checkpoint sequence never regresses;
- last processed source sequence never regresses;
- runtime state decodes with its existing uniqueness/fingerprint invariants;
- market position identities remain unique;
- any exact pre-restart pending BUY is either still the same pending identity or
  has advanced through a valid later durable state;
- the manual restart changes MainPID and systemd InvocationID;
- the automatic-restart counter does not increase during the controlled restart proof;
- the post-restart process passes the same provenance checks;
- supervisor cycles resume and advance.

The proof does not require byte-identical state because fresh chronological
events may legitimately arrive during the restart window. It proves durable
monotonic reconstruction without resetting or duplicating identities.

## Evidence storage

Commissioning evidence lives under:

```text
/root/shreks-fast-paper-shadow-commissioning/
```

The directory is root:root `0700` and must remain outside `/var/lib/shreks/fast-paper-shadow`, because that runtime tree is writable by the `shreks` service identity and therefore cannot protect administrator receipts from rename/removal.

Successful receipts are root:root `0600`, canonical JSON, no-replace:

```text
activation-<release-sha>.json
restart-<release-sha>.json
```

The service runs as `shreks`, so it cannot modify these receipts.

## Authority state

Successful activation explicitly records:

```text
shadow_runtime=ACTIVE_DETACHED
shadow_enable_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
authoritative_paper_runtime=LEGACY_UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

Successful restart proof does not widen those fields.

## RED acceptance

Tests must prove:

1. root/exact-release/protected-host readiness is mandatory;
2. systemd mutation command allowlist contains daemon-reload, one start, and
   separately explicit restart only;
3. enable/disable/stop/target mutation is rejected;
4. activation refuses an already-active or enabled shadow unit;
5. daemon reload occurs before start and protected preflight is re-run after
   reload;
6. process provenance binds cwd/cmdline/systemd properties to the exact release;
7. canonical supervisor journal records must advance completed cycles;
8. stable observation rejects PID/restart-counter churn;
9. CPU/RSS/storage/private-network evidence is bounded and canonical;
10. activation receipt is write-once/root-private and prevents a second
    activation ceremony for that release;
11. restart proof requires the activation receipt and one exact restart;
12. restart proof requires new MainPID/InvocationID while rejecting automatic-restart-counter churn;
13. restart proof accepts monotonic durable advancement and rejects regression;
14. no legacy PAPER service mutation, no enable, no target membership, no
    signing/submission, and no LIVE authority;
15. the CLI is packaged in the release;
16. full Python/Rust/repository-safety/ARM64 release CI stays green.

## Physical acceptance boundary

Repository CI can prove command boundaries, parsing, receipts, and restart
logic, but cannot claim physical acceptance.

The phase advances only after a trusted administrator runs the release-local
commands on the real production-paper VPS and preserves both successful
receipts from the exact deployed release.

Only after that physical evidence exists may learned shadow economics and
operational evidence be accumulated toward FL11. Production PAPER cutover
remains a later explicit gate.
