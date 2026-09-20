# G1C V2 Protected PAPER Runtime-Manifest Rotation — Design

**Date:** 2026-09-20  
**Status:** implementation slice; explicit administrator PAPER rotation authority only

## Purpose

The repository can now:

1. execute authenticated runtime-manifest v2 semantics;
2. author one canonical new-run v2 candidate from authenticated v1 authority;
3. assess that candidate read-only against the frozen FL9 V2 cohort and preserved request authority;
4. bind the exact v1 source, v2 candidate, and compatible assessment into one immutable transition artifact.

The remaining gap is protected host activation.

This slice adds one explicit administrator-only operation that may replace the active PAPER campaign manifest after all transition evidence is already bound. It does not grant the normal GitHub deployment account runtime-state mutation authority.

## Authority model

The transition binding remains evidence, not permission. Its installation, activation, rotation, and scoring fields remain NOT_GRANTED.

Actual rotation authority is the trusted administrator's explicit root invocation of the separately installed root-owned manager:

```text
/usr/local/sbin/shreks-paper-manifest-manager rotate <candidate> <binding> <binding-fingerprint> <release-sha>
```

The existing `shreks-deploy` sudoers rule is unchanged and still permits only the historical verified release-manager install command.

The new manager is transported inside the manifest-hashed Shreks wheel as sealed deployment-control content so an administrator can install exact release-bound bytes without expanding the historical top-level G2 release allowlist.

## Protected paths

Production rotation is fixed to the repository's existing host contract:

- current release: `/opt/shreks/current`;
- environment: `/etc/shreks/shreks.env`;
- active campaign manifest: `/etc/shreks/paper-campaign.json`;
- operational SQLite: `/var/lib/shreks/shreks.db`;
- E11 evidence: `/var/lib/shreks/paper-evaluation-e11.json`;
- G7 operator risk control: `/var/lib/shreks/risk/operator-control.json`;
- rotation evidence: `/var/lib/shreks/manifest-rotations`.

Before any service stop, the manager requires the environment file to bind the runtime to those exact DB/E11/manifest/control paths. This prevents a maintenance command from proving one state tree while systemd would start another.

## Input authentication

Before quiescing PAPER, the manager requires:

- active manifest is regular, non-symlink, canonical v1, mode 0640;
- candidate is regular, non-symlink, canonical v2;
- transition binding is regular, non-symlink, canonical and fingerprint-valid;
- explicit operator binding fingerprint equals the binding;
- active source raw SHA-256, manifest fingerprint, run ID, and quote mint match the binding;
- candidate raw SHA-256, manifest fingerprint, run ID, start timestamp, quote mint, and decimals match the binding;
- current release symlink, release directory name, and canonical RELEASE_MANIFEST source SHA equal the explicit operator release SHA;
- current release Python is a regular non-symlink executable;
- G7 operator control state is readable and valid.

Failure before campaign quiesce performs no systemd or protected-manifest mutation.

## Quiesce and immutable evidence

The manager stops only `shreks-paper-campaign.service`. Observer and paper-evidence collection remain independent.

After stop succeeds, it creates exactly one private evidence directory named by the transition binding fingerprint. Existing evidence for the same binding is never overwritten.

The directory records exact bytes for:

- source campaign manifest;
- candidate campaign manifest;
- transition binding;
- PREPARED receipt.

All evidence files are mode 0600 and the directory is mode 0700.

The candidate preflight uses the private copied candidate, not the mutable staging input. Therefore the preflight bytes are exactly the bytes later installed even if the original staging path changes after authentication.

## Candidate preflight

With the PAPER writer stopped, the manager constructs the existing sealed runtime config using:

- real operational SQLite;
- real E11 evidence;
- private candidate manifest copy;
- real G7 operator-control state;
- inert one-cycle configuration values used only to satisfy the config type.

It calls the existing read-only PAPER preflight. No cycle is executed and no DB/E11 checkpoint/evidence mutation is authorized by preflight.

A new paper_run_id can coexist with preserved historical SQLite/E11 content because the sealed coordinator restores checkpoints and validates evidence attribution by paper run. Historical source-run truth is not erased.

## Atomic protected replacement

Only after candidate preflight succeeds does the manager replace `/etc/shreks/paper-campaign.json`.

The replacement:

- occurs through a temporary regular file in the same directory;
- fsyncs file content;
- preserves the source manifest's uid, gid, and exact 0640 mode;
- uses atomic `os.replace`;
- fsyncs the parent directory.

No SQLite, E11, G7 control, environment, release, systemd unit, wallet, or secret file is replaced.

## Active preflight and startup

After replacement but before service start, the manager runs the same PAPER preflight against the protected active manifest path.

It then starts only `shreks-paper-campaign.service`. Systemd therefore runs the ordinary release-managed startup gates, including protected FL9 discovery and the normal PAPER recovery preflight.

Success additionally requires:

- systemd reports the campaign active;
- MainPID is positive;
- process cwd is the exact expected immutable release;
- Python executable is from that release's copied venv;
- protected active manifest bytes equal the authenticated candidate bytes.

Only then is an ACTIVATED receipt written.

## Automatic rollback

Any failure after campaign quiesce triggers rollback.

If candidate bytes were installed, the exact source bytes preserved before mutation are atomically restored with the original metadata. If no replacement occurred, source bytes are re-verified.

The manager then:

1. preflights the protected source manifest;
2. starts the campaign;
3. requires active service/process identity;
4. requires protected manifest bytes equal the original source;
5. writes a ROLLED_BACK receipt when the evidence directory exists.

If rollback itself fails, the command reports rotation-and-rollback failure rather than claiming recovery.

Candidate-run checkpoint or E11 rows are never deleted during rollback. If the candidate managed to execute before a later health check failed, those rows remain preserved evidence and are ignored by the restored source run's run-scoped recovery.

## Receipt authority boundary

PREPARED, ACTIVATED, and ROLLED_BACK receipts commit to:

- release source SHA;
- transition binding fingerprint;
- source manifest fingerprint and paper run;
- candidate manifest fingerprint and paper run;
- candidate quote mint;
- terminal rotation status.

Every receipt also states:

- scoring_authority = NOT_GRANTED;
- paper_promotion_authority = BLOCKED;
- live_authority = DISABLED.

No scorer, model fitting, promotion, registry mutation, wallet, signer, transaction construction, or transaction submission code is introduced.

## Release transport

`build_release.sh` copies the exact manager source into:

```text
shreks_brain/_sealed_deploy_control/paper_manifest_manager.py
```

and verifies the completed wheel member byte-for-byte against the sealed checkout, using the same compatibility mechanism already used for `release_bundle.py` and `release_manager.py`.

The top-level release manifest remains unchanged.

## Verification plan

Focused tests prove:

1. successful source -> candidate rotation;
2. candidate preflight is against the private evidence copy;
3. candidate preflight failure restarts the untouched source manifest;
4. post-install health failure restores and restarts the source manifest;
5. active source mismatch fails before service stop;
6. runtime environment path drift fails before service stop;
7. evidence modes and write-once layout;
8. manager remains root/manual and does not widen deploy sudo authority;
9. sealed wheel transport includes the exact manager bytes.

Then run all four canonical CI lanes on the PR head and exact merged main.

**V2 SCORING RETRY: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE TRADING: DISABLED.**
