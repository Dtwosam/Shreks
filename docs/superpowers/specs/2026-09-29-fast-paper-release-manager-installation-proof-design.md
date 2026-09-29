# Fast Lane Root Release-Manager Installation Proof — Design

**Date:** 2026-09-29  
**Base main SHA:** `ff4c61143f51b3dcf5cd8db17985bf912dcb1a2d`

## Purpose

Close the final root-control-plane prerequisite before the first physical Fast
PAPER cutover.

The Fast-aware release manager is already sealed inside the immutable Shreks
wheel, but automatic deployment intentionally does not replace the separately
installed root helper:

```text
/usr/local/sbin/shreks-release-manager
```

A trusted administrator therefore needs one release-bound proof that refreshes
that helper to the exact sealed Fast-aware bytes while proving the historical
deployment sudoers rule and current PAPER service lifecycle remain unchanged.

This slice does not perform the physical cutover.

## Trusted inputs

The command requires:

- one explicit expected current release SHA;
- execution from that release's own virtualenv;
- the exact current release symlink;
- the canonical release manifest;
- exactly one manifest-hashed Shreks wheel;
- the sealed deploy-control members inside that wheel.

Required sealed members:

```text
shreks_brain/_sealed_deploy_control/release_manager.py
shreks_brain/_sealed_deploy_control/release_bundle.py
```

The adjacent installed `release_bundle.py` must already equal the exact sealed
member because the standalone root release manager imports it directly.

## Root helper replacement

The only mutable control-plane path is:

```text
/usr/local/sbin/shreks-release-manager
```

It must already be a regular non-symlink `root:root 0755` executable with the
expected Python script shape.

If its bytes already equal the sealed current release, the operation is
proof-only and does not replace the inode.

Otherwise the command:

1. captures the exact existing bytes;
2. writes the sealed current-release bytes to a temporary root-owned 0755 file;
3. re-reads the installed helper and requires it still equals the captured
   bytes;
4. atomically replaces the helper;
5. fsyncs the parent directory;
6. proves the installed bytes/metadata equal the sealed release;
7. rolls the prior helper back if any post-replacement proof fails.

No absent helper is created by this command. This is a refresh of one existing
root control-plane helper, not a bootstrap installer.

## Sudoers invariant

The proof independently reads:

```text
/etc/sudoers.d/shreks-release-manager
```

It must remain `root:root 0440` and have exactly one effective non-comment
line:

```text
shreks-deploy ALL=(root) NOPASSWD: /usr/local/sbin/shreks-release-manager install /var/tmp/shreks-release-*.tar.gz /var/tmp/shreks-release-*.tar.gz.sha256 /var/tmp/shreks-release-*.RELEASE_MANIFEST.json
```

Any widened command, second effective rule, metadata drift, symlink, or
replacement fails closed.

The proof records the exact sudoers SHA-256 before and after and requires exact
equality.

## Service-lifecycle invariant

The command may perform read-only `systemctl show` for exactly:

- `shreks-observe.service`;
- `shreks-paper-evidence.service`;
- `shreks-paper-campaign.service`.

For each unit it binds:

- ActiveState;
- SubState;
- NRestarts;
- MainPID;
- ExecMainStatus;
- ActiveEnterTimestampMonotonic.

The complete observation must be byte-equivalent semantically before and after
helper refresh.

The command has no start/stop/restart/daemon-reload/enable/disable authority.

## Durable proof

A successful command writes one caller-specified absolute root-private receipt
with no-replace semantics and mode `0600`.

It records:

- current release identity;
- manifest-hashed wheel identity;
- sealed release-manager member and SHA-256;
- prior installed release-manager SHA-256;
- whether replacement actually occurred;
- sealed and installed release-bundle companion identity;
- exact sudoers SHA-256;
- unchanged service-lifecycle proof;
- a canonical proof fingerprint.

Authority fields remain:

```text
physical_cutover_authority=NOT_EXERCISED
paper_execution_authority=UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## CLI

```text
shreks-fast-paper-release-manager-install-proof \
  <expected-release-sha> \
  --receipt-path /root/shreks-fast-paper-cutover/release-manager-installation-proof-<release-sha>.json
```

The command requires root and the exact current-release virtualenv.

## Acceptance proof

Tests must prove:

1. stale root release-manager bytes are replaced by the exact sealed member;
2. exact current bytes produce proof without inode replacement;
3. a stale/mismatched `release_bundle.py` blocks replacement;
4. widened sudoers blocks replacement;
5. service restart/PID drift after replacement rolls back the prior helper;
6. the root-private receipt is canonical, fingerprinted and mode 0600;
7. only read-only `systemctl show` is callable;
8. no physical cutover, PAPER execution, scoring, signing/submission or LIVE
   authority is introduced;
9. Python, Rust, ARM64 and repository-safety CI remain green.

## Following slice

After this implementation is sealed and deployed while legacy PAPER remains
authoritative, a trusted administrator may run the exact release-bound refresh
on the protected host.

The physical-cutover preflight must then consume the durable proof directly,
re-authenticate its release/helper/bundle/sudoers bindings before service
control, and bind its proof fingerprint into the cutover preflight receipt.
Activation must re-authenticate the same proof after legacy PAPER is stopped
and require the fingerprint to remain unchanged before final Fast handoff.

Only a resulting `READY_FOR_PROTECTED_PAPER_CUTOVER` may proceed to the
separately authorized physical Fast PAPER cutover ceremony.

LIVE remains disabled.
