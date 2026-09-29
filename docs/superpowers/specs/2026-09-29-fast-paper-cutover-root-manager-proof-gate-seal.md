# Fast Lane Physical Cutover Root-Manager Proof Gate — Release Seal

**Date:** 2026-09-29  
**Implementation main SHA:** `e66f9f53f7a6fd90bdc96e7df639b3f7d7f856b5`  
**Implementation PR:** #669  
**Implementation PR head:** `7724768a4a7c3a3171610256296e121dcd18543c`  
**Implementation CI:** `36558894571`  
**Status:** SEALED FOR IMMUTABLE RELEASE + DEPLOY OF ROOT-PROOF-GATED PHYSICAL CUTOVER CAPABILITY ONLY; PHYSICAL CUTOVER REMAINS A SEPARATE TRUSTED-ADMIN CEREMONY; PAPER AUTHORITY UNCHANGED; SIGNING/SUBMISSION NOT AUTHORIZED; LIVE DISABLED

## Purpose

Seal the hard root-manager-proof gate for the protected physical Fast PAPER
cutover.

The implementation requires the cutover path itself to authenticate the durable
root-private release-manager installation proof before any service-control work
and again after legacy PAPER is stopped. The exact proof fingerprint is bound
into both physical-preflight and successful physical-cutover receipts.

This seal does not execute physical cutover and does not switch PAPER authority.

## Implementation proof

PR #669 merged at:

`e66f9f53f7a6fd90bdc96e7df639b3f7d7f856b5`

Exact reviewed PR head:

`7724768a4a7c3a3171610256296e121dcd18543c`

Exact-head CI:

`36558894571`

Result:

- Python: SUCCESS — `4327 passed, 4 warnings`;
- Rust workspace: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

The implementation provides:

- mandatory `--release-manager-installation-proof-path` input for physical
  preflight and activation;
- canonical closed-schema proof parsing with duplicate-key, non-finite-value,
  ownership, mode, symlink, fingerprint, and authority checks;
- re-authentication of the exact current release, manifest-hashed wheel,
  sealed release-manager and release-bundle bytes, installed root helper and
  companion bytes, and exact historical deployment sudoers rule;
- failure before any systemd call when the durable proof is absent, stale,
  tampered, mismatched, or drifted;
- binding of the exact proof fingerprint into the physical-preflight receipt;
- second proof authentication after legacy PAPER is stopped and before final
  Fast handoff;
- pre-start rollback to legacy PAPER authority if proof identity changes across
  the stop boundary;
- binding of the exact proof fingerprint into a successful cutover receipt.

## Automatic delivery authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI
is green, authorize the existing immutable release/deploy chain only to:

1. build and verify one immutable release for the exact seal SHA;
2. include the root-proof-gated physical Fast PAPER cutover implementation;
3. publish that exact immutable GitHub release;
4. deploy that release through the existing protected G2 path;
5. run the existing ordinary production verification;
6. keep current PAPER authority unchanged throughout automatic delivery.

Automatic delivery must not:

- execute the root-manager installation-proof command as root;
- create or rotate Fast PAPER cutover authorization;
- stop/start/restart/reload PAPER services outside the existing deploy
  verification contract;
- invoke physical Fast PAPER cutover;
- execute Fast PAPER economic actions;
- access wallet material;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin host step after deployment

The durable proof is release-bound. After the exact sealed release becomes the
active `/opt/shreks/current` release and ordinary production verification
succeeds, a trusted administrator must create a fresh proof for that exact
release:

```sh
CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"
RELEASE_MANAGER_INSTALL_PROOF="/root/shreks-fast-paper-cutover/release-manager-installation-proof-$CURRENT_SHA.json"

sudo install -d -o root -g root -m 0700 /root/shreks-fast-paper-cutover

sudo "$CURRENT_RELEASE/.venv/bin/shreks-fast-paper-release-manager-install-proof" \
  "$CURRENT_SHA" \
  --receipt-path "$RELEASE_MANAGER_INSTALL_PROOF"
```

A successful proof must state:

```text
status=VERIFIED
deploy_sudoers_exact_rule=true
service_lifecycle_unchanged=true
physical_cutover_authority=NOT_EXERCISED
paper_execution_authority=UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The prior proof from any older release is not sufficient for the new sealed
release.

## Following protected step

Only after the fresh exact-release proof succeeds may a trusted administrator
run the read-only physical cutover preflight with:

```text
--release-manager-installation-proof-path "$RELEASE_MANAGER_INSTALL_PROOF"
```

The preflight must return:

```text
READY_FOR_PROTECTED_PAPER_CUTOVER
```

and legacy PAPER must still be authoritative at that point.

Actual activation remains a separate explicit protected-host ceremony using the
same exact proof path and the same final Fast run ID that passed preflight.

## Failure boundary

If proof authentication fails before service control, no PAPER service change
is permitted.

If the proof changes after legacy PAPER is stopped but before Fast handoff, the
existing pre-start rollback path restores legacy PAPER authority.

If a failure occurs after Fast has started and the system enters a fail-closed
manual-recovery state, do not blindly restore legacy PAPER. Use the sealed
read-only Fast PAPER manual-recovery assessment path before any recovery plan.

## Authority state after this seal

```text
production_paper_runtime=UNCHANGED_UNTIL_EXPLICIT_PHYSICAL_CUTOVER
root_manager_installation_proof_gate=SEALED_AND_DEPLOYABLE
root_helper_refresh_authority=TRUSTED_ADMIN_ONLY
physical_cutover_authority=NOT_GRANTED_BY_THIS_SEAL
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```
