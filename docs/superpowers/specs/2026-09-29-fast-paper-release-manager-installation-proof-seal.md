# Fast Lane Root Release-Manager Installation Proof — Release Seal

**Date:** 2026-09-29  
**Implementation main SHA:** `c1cb14c36760e7eaf3d6a34f97228efb166fe0a0`  
**Implementation PR:** #666  
**Implementation PR head:** `54748513977db2602886d5ada3b1d194b354e5f7`  
**Implementation CI:** `36556562028`  
**Status:** SEALED FOR IMMUTABLE RELEASE + DEPLOY OF ROOT-HELPER REFRESH/PROOF CAPABILITY ONLY; PHYSICAL FAST PAPER CUTOVER NOT AUTHORIZED; PAPER AUTHORITY UNCHANGED; SIGNING/SUBMISSION NOT AUTHORIZED; LIVE DISABLED

## Purpose

Seal the release-bound root-control-plane proof required before the first
physical Fast PAPER cutover.

The implementation proves and, when necessary, atomically refreshes exactly:

```text
/usr/local/sbin/shreks-release-manager
```

to the exact Fast-aware helper transported by the active immutable release.

This seal does not execute that root helper refresh on the protected host and
does not switch PAPER authority.

## Implementation proof

PR #666 merged at:

`c1cb14c36760e7eaf3d6a34f97228efb166fe0a0`

Exact reviewed PR head:

`54748513977db2602886d5ada3b1d194b354e5f7`

Exact-head CI:

`36556562028`

Result:

- Python: SUCCESS — `4321 passed, 4 warnings`;
- Rust workspace: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

The implementation provides:

- exact current-release/manifest/wheel authentication;
- exact sealed `release_manager.py` extraction;
- exact sealed `release_bundle.py` companion verification;
- atomic replacement of only the existing root release manager when stale;
- proof-only behavior when the helper is already exact;
- rollback to the prior manager bytes if post-replacement proof fails;
- exact historical sudoers-rule verification;
- unchanged observe/evidence/PAPER service-lifecycle proof;
- root-private canonical 0600 proof receipt;
- read-only systemd-show command allowlisting.

## Companion compatibility proof

The currently deployed-era `release_bundle.py` bytes from release
`8cea1cb5907e9b8b1208b383bbc2dceb627be8d8` are byte-identical to the
sealed companion in the Fast-aware release-manager seal
`ff4c61143f51b3dcf5cd8db17985bf912dcb1a2d`.

The root release-manager bytes differ, as expected.

Therefore the protected host can refresh only
`/usr/local/sbin/shreks-release-manager` while requiring the installed
`/usr/local/sbin/release_bundle.py` companion to remain exact.

## Automatic delivery authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI
is green, authorize the existing immutable release/deploy chain only to:

1. build and verify one immutable release for the exact seal SHA;
2. include
   `shreks-fast-paper-release-manager-install-proof`;
3. publish that exact immutable GitHub release;
4. deploy that release through the existing protected G2 path;
5. keep the current PAPER authority unchanged;
6. keep the installed root release manager unchanged during automatic deploy.

Automatic delivery must not:

- modify `/usr/local/sbin/shreks-release-manager`;
- modify `/usr/local/sbin/release_bundle.py`;
- modify `/etc/sudoers.d/shreks-release-manager`;
- execute the installation-proof command as root;
- create or rotate Fast PAPER cutover authorization;
- stop/start/restart/reload PAPER services;
- perform physical Fast PAPER cutover;
- execute PAPER actions;
- access wallet material;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin host step after deployment

Only after the exact sealed release is active and ordinary production
verification succeeds may a trusted administrator run:

```sh
CURRENT_RELEASE="$(readlink -f /opt/shreks/current)"
CURRENT_SHA="$(basename "$CURRENT_RELEASE")"

sudo install -d -o root -g root -m 0700 /root/shreks-fast-paper-cutover

sudo "$CURRENT_RELEASE/.venv/bin/shreks-fast-paper-release-manager-install-proof" \
  "$CURRENT_SHA" \
  --receipt-path \
  "/root/shreks-fast-paper-cutover/release-manager-installation-proof-$CURRENT_SHA.json"
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

The administrator must review that proof before any physical-cutover command.

## Sudoers boundary

The effective deployment sudoers content must remain exactly:

```text
shreks-deploy ALL=(root) NOPASSWD: /usr/local/sbin/shreks-release-manager install /var/tmp/shreks-release-*.tar.gz /var/tmp/shreks-release-*.tar.gz.sha256 /var/tmp/shreks-release-*.RELEASE_MANIFEST.json
```

No additional deploy-account root command is authorized.

## Following protected step

After the exact helper refresh/proof succeeds on the protected host:

1. authenticate the durable installation-proof receipt;
2. re-run `shreks-fast-paper-physical-cutover preflight`;
3. require `READY_FOR_PROTECTED_PAPER_CUTOVER`;
4. verify legacy PAPER remains authoritative before activation;
5. only then may a trusted administrator separately invoke the already-reviewed
   physical Fast PAPER cutover ceremony.

The physical cutover remains a manual protected-host authority boundary.

## Authority state after this seal

```text
production_paper_runtime=UNCHANGED
fast_aware_root_release_manager_refresh=SEALED_AND_DEPLOYABLE
root_helper_refresh_authority=TRUSTED_ADMIN_ONLY
physical_cutover_authority=NOT_GRANTED_BY_THIS_SEAL
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```
