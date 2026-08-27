# G4 Production Telemetry Acceptance

Date: 2026-08-27

**LIVE TRADING: DISABLED.**

## Scope

This record closes the real-host acceptance boundary for Phase G4 four-layer telemetry on the production VPS. It records physical deployment and runtime evidence only. It does not change telemetry behavior, trading behavior, risk policy, promotion authority, wallet authority, signing/submission authority, or live-enable state.

## Production source and host bootstrap

The production PAPER runtime was already running sealed release:

- source/release SHA: `cb72f76b901bd170b565a53a7269a20247c27908`;
- release workflow: `33119367333` — success;
- deploy workflow: `33119585249` — success.

G4 telemetry remained outside the sealed G2 core release-bundle allowlist by design, preserving backward-compatible rollback semantics. The two telemetry units were therefore installed as exact-source host bootstrap artifacts from the deployed sealed SHA.

Both downloaded unit files passed SHA-256 verification before installation:

- `shreks-telemetry.service`: verified `OK`;
- `shreks-telemetry.timer`: verified `OK`.

The private telemetry directory was created at `/var/lib/shreks/telemetry` for the unprivileged `shreks` user/group.

Reporting-only host configuration was populated for:

- proof assessment path;
- promotion assessment path;
- telemetry output path `/var/lib/shreks/telemetry/current.json`;
- evaluation reporting policy version;
- calibration bucket count.

These values are reporting configuration only and do not alter trading policy, risk sizing, execution, promotion, signing, submission, wallet authority, or live state.

## Telemetry runtime and unit contract

The production Python release successfully imported `shreks_brain.telemetry`.

The installed service contract is the sealed G4 read-only oneshot design:

- `User=shreks` / `Group=shreks`;
- `Type=oneshot`;
- read-only preflight before snapshot generation;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- `PrivateTmp=true`;
- `NoNewPrivileges=true`;
- only `/var/lib/shreks/telemetry` is writable through `ReadWritePaths=`;
- `UMask=0077`.

The timer contract is:

- `OnBootSec=60s`;
- `OnUnitActiveSec=60s`;
- `AccuracySec=5s`;
- `Persistent=true`;
- `WantedBy=timers.target`.

Telemetry remains deliberately independent of `shreks.target`.

## First physical snapshot proof

The telemetry service completed successfully and produced `/var/lib/shreks/telemetry/current.json`.

The file was physically verified as:

- mode: `0600`;
- owner: `shreks`;
- group: `shreks`;
- size: `2249` bytes;
- mtime: `2026-08-27 22:00:37.054069625 +0000`.

An initial operator-side inspection attempt as the normal `ubuntu` account received `Permission denied`. That is expected and confirms the private `0600` boundary. The corrected acceptance read the file as the `shreks` identity.

The corrected read produced:

- `TELEMETRY_JSON_VALID=yes`;
- schema version `g4-telemetry-snapshot-v1`;
- top-level keys exactly representing generated timestamp, mode, System, Trading, Money, Proof/Risk, overall status, and schema version;
- generated timestamp `1787868037038`.

## Repeated snapshot generation proof

Two controlled snapshots were generated with the timer paused to avoid timing ambiguity.

First snapshot:

- SHA-256: `8c6120781b4359d1ce1c3e9da64e32ed328ba966c54cc6c81b2731088c1015e1`;
- mtime: `2026-08-27 22:00:37.054069625 +0000`.

Second snapshot:

- SHA-256: `f5cc729f4c6988156d7f707166fbe45daa499453c7543c7a7e4f3e5311db93da`;
- mtime: `2026-08-27 22:00:39.789814678 +0000`.

The different hashes and later mtime prove real repeated snapshot generation rather than a stale-file existence check.

The service result after the controlled run was:

- `Result=success`;
- `ExecMainStatus=0`.

`ExecMainCode=1` is systemd's normal `CLD_EXITED` code class; paired with status `0` and `Result=success`, it is a clean successful oneshot exit, not an application failure.

## Physical failure-isolation drill

The telemetry output directory was deliberately made unwritable and `shreks-telemetry.service` was started.

The service failed nonzero as expected:

- `EXPECTED_TELEMETRY_FAILURE=yes`;
- systemd recorded `status=1/FAILURE` and `Failed with result 'exit-code'` for that intentional run.

During the intentional telemetry failure, all core PAPER runtime units remained active:

- `shreks-observe.service=active`;
- `shreks-paper-evidence.service=active`;
- `shreks-paper-campaign.service=active`;
- `shreks.target=active`.

This physically proves the G4 isolation contract: telemetry failure does not stop, restart, or control the authoritative PAPER runtime.

After restoring directory permissions, telemetry recovered successfully.

## Timer persistence and current state

The telemetry timer was enabled and started successfully:

- `telemetry.timer=active`;
- `telemetry.timer.enabled=enabled`.

`systemctl list-timers` showed the next run scheduled approximately one minute later, matching the sealed one-minute cadence.

At acceptance completion, the authoritative core PAPER runtime remained active and telemetry continued independently under `timers.target`.

## Acceptance conclusion

G4 physical production acceptance is PASSED.

The host has now proven:

1. exact sealed-source telemetry units installed;
2. private unprivileged telemetry storage;
3. valid `g4-telemetry-snapshot-v1` output;
4. repeated real snapshot generation;
5. `0600` private output permissions;
6. successful oneshot execution and recovery;
7. deliberate telemetry failure remains isolated from all four core PAPER units;
8. persistent one-minute timer is active and enabled.

Repository tests already prove source reads are read-only (`mode=ro`, `PRAGMA query_only=ON`) and that source bytes/mtimes are not mutated by telemetry code. The physical systemd sandbox independently restricts production writes to `/var/lib/shreks/telemetry`.

**G4 PRODUCTION TELEMETRY ACCEPTANCE PASSED.**

Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.

**LIVE TRADING: DISABLED.**
