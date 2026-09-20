# FL9 Discovery Unreadable-Authority Skip — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `8e616250fff5e432a3a1970bf3b3e3d9ab574484`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified production correction for bounded FL9 V2 historical request-authority discovery.

The correction preserves the protected evidence boundary while preventing one intentionally unreadable descendant `fl9-v2-*` subtree from converting the entire bounded historical authority search into an infrastructure `FAILED` result.

The historical search root itself remains fail-closed.

## Production evidence

Sealed release:

`a057181f59d126db7bcd18c57a9dcfb10f49a12c`

was successfully built and deployed through the normal immutable protected PAPER chain.

Production verification then proved:

- exact active release and release-manifest binding;
- all three core PAPER services active/running with zero restarts;
- no recent runtime restart or SQLite contention signature;
- FL9 discovery bridge available;
- trusted terminal result delivered through the shared-memory result exchange.

The trusted failure diagnostic was:

- result source: `exchange`;
- failure code: `DISCOVERY_FAILED`;
- failure message: `[Errno 13] Permission denied: '/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2/v2-first-champion-request.json'`.

The frozen cohort directory is intentionally sealed `0700` with `0600` files. Existing repository authority explicitly prohibits weakening that artifact with `chmod`, `chown`, copying, or equivalent permission widening merely to make it telemetry-readable.

## Corrective implementation

Merged PR #326, `fix: skip unreadable FL9 discovery authority subtrees`, changes only the bounded historical request-authority enumeration plus regression tests.

The implementation:

1. keeps the configured historical request search root fail-closed;
2. keeps the fixed filename `v2-first-champion-request.json`;
3. keeps the existing bounded search depth, directory count, and candidate count;
4. uses `lstat()` for descendant directory classification so symlink directories are not traversed;
5. treats a descendant candidate inspection error as unavailable authority and continues;
6. treats a descendant directory listing error as unavailable authority and continues;
7. continues to authenticate every readable candidate through the existing sealed request/hydration authority path;
8. returns the existing `HOLD_NO_REQUEST_AUTHORITY` state when no readable/authentic authority remains;
9. does not change the result schema or successful authority selection rules;
10. does not change protected cohort ownership or modes.

No unreadable protected subtree is promoted into request authority.

## TDD and verification evidence

Intentional RED head:

`fadb6e44d9624f8fd7e3742c3a87cf5666ca7a8e`

RED CI run:

`35514673847`

Result:

- exactly the two new unreadable-subtree regression tests failed;
- 3457 existing Python tests passed;
- repository safety passed;
- ARM64 release build passed;
- unrelated existing behavior remained intact.

GREEN implementation head before newline-only hygiene:

`4303d4e94c7786eb3ea11c8e072c4a1aa658da76`

GREEN CI run:

`35514810822`

All four canonical gates passed, including 3459 Python tests.

Final PR head:

`047d50dc1d0e690e7c1428e38214d1fa29fc44d6`

Final PR CI run:

`35514947423`

Conclusion: `success`.

Squash-merged implementation main:

`8e616250fff5e432a3a1970bf3b3e3d9ab574484`

Exact merged-main CI run:

`35517017727`

All four canonical gates passed:

- Repository safety;
- Python tests: 3459 passed;
- Rust tests;
- ARM64 release build.

## Authority boundary

This implementation and seal do not modify or authorize:

- frozen cohort ownership or permissions;
- protected evidence ownership or permissions;
- systemd units/timers;
- sudoers;
- release-manager code;
- scoring-request creation;
- V2 model scoring or retry;
- champion publication or promotion;
- PAPER promotion;
- wallet/signing/submission paths;
- LIVE trading.

The existing `production-paper` environment, immutable-release verification, transport-only deploy account, protected runtime-state boundary, and fail-closed discovery authority remain unchanged.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment of that immutable release;
3. automatic production verification of that exact release;
4. telemetry-mediated read-only FL9 protected discovery under the existing bounded authority rules;
5. observation of the trusted terminal discovery status/result required to choose the next implementation slice.

A trusted HOLD or FOUND result remains evidence only. It does not authorize scoring.

## Expected production proof

The automatic chain must demonstrate:

`seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery -> trusted terminal result`

Expected trusted discovery outcomes remain:

- `HOLD_NO_REQUEST_AUTHORITY`;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- `HOLD_NO_COMPATIBLE`;
- `FOUND_COMPATIBLE`.

A terminal `FAILED` remains fail-closed and must surface only the previously sealed bounded diagnostic output.

Even `FOUND_COMPATIBLE` does not authorize a V2 scoring retry.

## Promotion boundary

`FL9_UNREADABLE_AUTHORITY_SKIP_IMPLEMENTATION=MAIN_GREEN`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=PENDING_PRODUCTION_TERMINAL_RESULT`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
