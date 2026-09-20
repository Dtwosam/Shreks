# FL9 Trusted Discovery Result Exchange — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `ad89dd3668d825cf0400faaa647b1b1c59f07398`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified FL9 control-plane transport fix that delivers sanitized terminal discovery results from the unprivileged `shreks` telemetry runtime identity to the unprivileged `shreks-deploy` verifier without depending on journald visibility.

Production had already proven that immutable release creation, automatic PAPER deployment, core runtime health, telemetry scheduling, and request-marker creation were working. The remaining repeated failure was result delivery: the verifier timed out after 180 seconds while the telemetry timer and oneshot ran successfully.

## Production evidence that justified this fix

Sealed release `90c119dcf164e8ee7219c4711a9812ce3712a0c2` automatically released and deployed successfully in deploy run `35509886537`.

Its verifier proved:

- exact active release and release-manifest SHA matched;
- all three core PAPER services were active/running with `NRestarts=0`;
- recent runtime journals had no restart or SQLite contention signatures;
- protected direct historical-state access by `shreks-deploy` remained denied as designed;
- FL9 bridge import succeeded;
- `shreks-telemetry.timer` was active and fired during the verifier window;
- `shreks-telemetry.service` exited successfully with `ExecMainStatus=0`;
- `/dev/shm` was a real root-owned `01777` directory;
- the canonical verifier request marker existed with the expected deploy-account owner and mode;
- no trusted terminal result reached the verifier before the bounded timeout.

The request marker intentionally remains until verifier cleanup, so marker presence alone is not evidence that telemetry failed to process the request. The transport dependency on journal visibility was therefore removed.

## Implemented result exchange

Merged PR #322, `feat: publish FL9 discovery results through trusted exchange`, adds a bounded per-request result exchange:

1. the verifier creates `/dev/shm/shreks-fl9-v2-discovery.<request-id>.result.d`;
2. that exchange directory is owned by the existing `shreks-deploy` identity and must have exact mode `0733`;
3. telemetry derives the exchange only from the authenticated result request ID;
4. a missing exchange is allowed for backward compatibility;
5. a present exchange must be a real directory, not a symlink;
6. the exchange owner must be `shreks-deploy`;
7. telemetry writes only `result.json`;
8. publication uses no-follow/exclusive creation;
9. the result file remains `0600` while being written;
10. the canonical JSON payload is bounded to 1 MiB;
11. telemetry fsyncs the complete payload before changing the mode;
12. only after completion does telemetry set the file to `0644`;
13. the published file is re-read with stable device/inode/size/mtime checks;
14. a conflicting pre-existing result is never overwritten;
15. an identical trusted existing result is idempotently accepted;
16. the verifier requires the result file to be a regular non-symlink file;
17. the verifier requires exact owner UID equal to the `shreks` runtime identity;
18. the verifier requires exact mode `0644`;
19. the verifier uses `O_NOFOLLOW` and stable fstat/lstat identity checks;
20. the verifier requires canonical JSON before the existing semantic validation;
21. the existing semantic validator still requires exact schema, request ID, expected release SHA, observed release SHA, and an allowlisted terminal HOLD/FOUND status;
22. journald remains audit output and backward-compatible fallback;
23. cleanup removes only the current request's marker, result file, and exchange directory.

The deploy identity can cause a denial by interfering with its own exchange directory, but it cannot forge a trusted successful result because a verifier-accepted result must be owned by the `shreks` runtime UID and pass canonical, stable-read, request/release, and status validation.

## TDD and verification evidence

Intentional RED head:

`0cae90feb22452575a07d5c139d82d8558553917`

RED CI run:

`35510347299`

Result:

- exactly 10 new Python failures;
- 3446 Python tests passed;
- ARM64 release build passed;
- repository safety passed;
- failures were confined to the absent result publisher, telemetry publication hook, and verifier exchange transport.

GREEN feature head:

`594552459f5f11f66dc66bccfb5471c2d84c1ba5`

GREEN feature CI run:

`35510603132`

All four canonical gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Independent PR #322 CI run:

`35510791170`

All four canonical gates passed.

Squash-merged implementation main:

`ad89dd3668d825cf0400faaa647b1b1c59f07398`

Exact merged-main CI run:

`35510951326`

All four canonical gates passed.

## Authority boundary

This implementation and seal do not modify:

- sudoers;
- release-manager code;
- systemd units or timers;
- ownership, modes, or ACLs under `/etc/shreks` or `/var/lib/shreks`;
- wallet/signing/submission paths;
- PAPER promotion authority;
- LIVE authority.

The existing `production-paper` environment, exact immutable-release verification, transport-only deploy account, and protected runtime-state boundary remain authoritative.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment of that immutable release;
3. automatic production verification of that exact release;
4. telemetry-mediated read-only FL9 protected discovery;
5. trusted delivery of the sanitized terminal discovery result through the bounded exchange above.

## Expected production proof

The automatic chain must demonstrate:

`seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery -> terminal trusted result`

Acceptable terminal discovery statuses remain:

- `HOLD_NO_REQUEST_AUTHORITY`;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- `HOLD_NO_COMPATIBLE`;
- `FOUND_COMPATIBLE`.

Any `FAILED`, timeout, malformed result, owner/mode mismatch, symlink, release mismatch, or untrusted status remains fail-closed.

Even `FOUND_COMPATIBLE` is evidence only. It does not authorize a V2 scoring retry.

## Promotion boundary

`FL9_RESULT_EXCHANGE_IMPLEMENTATION=MAIN_GREEN`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=PENDING_PRODUCTION_TERMINAL_RESULT`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
