# FL9 Sanitized Discovery Failure Reporting — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `d9859d12cc70876e1d6f5b18dd1429bba7bb29b0`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified production-verifier fix that keeps a trusted terminal FL9 V2 discovery `FAILED` result fail-closed while exposing only the bounded diagnostics required to identify the next defect:

- trusted result source: `exchange` or `journal`;
- bounded uppercase failure code;
- whitespace-normalized bounded failure message.

The verifier does not print the raw failure result on this path.

## Production evidence that justified this fix

The previously sealed trusted result-exchange release `734e2bcb913d69490bcbc4b987be1b578baabc42` automatically deployed and reached protected production verification in run `35512058141`.

That run proved:

- immutable release creation and protected PAPER deployment succeeded;
- the exact active release and release-manifest SHA matched;
- all three core PAPER services were active/running with zero restarts;
- the trusted FL9 discovery result arrived through the bounded result exchange before the verifier timeout;
- request ID, expected release SHA, observed release SHA, schema, and canonical-result validation passed;
- the terminal discovery status was `FAILED`;
- the verifier then exited before surfacing the sanitized failure code/message needed to diagnose that fail-closed result.

The transport problem was therefore no longer the blocker. The next required evidence is the trusted bounded failure diagnostic itself.

## Implemented verifier behavior

Merged PR #324, `fix: surface sanitized FL9 discovery failure`, changes only the production verifier workflow plus its static contract tests.

The verifier now:

1. records whether the accepted trusted result came from the shared-memory exchange or journald fallback;
2. preserves the existing exact request/release/schema binding validation;
3. accepts the existing successful HOLD/FOUND status allowlist unchanged;
4. recognizes a terminal `FAILED` result only after trusted-result validation;
5. accepts the current top-level failure shape with `error_code` plus string `error`;
6. accepts the legacy nested failure shape only for the fixed `CONTROL_RESULT_PUBLISH_FAILED` code;
7. requires the failure code to match `[A-Z0-9_]{1,64}`;
8. requires a string failure message;
9. collapses whitespace and bounds the message to 240 characters;
10. prints only result source, bounded failure code, and bounded normalized failure message;
11. does not print the raw discovery result on the failure branch;
12. cleans up the current request marker/result/exchange;
13. exits nonzero exactly as before.

No success path gains new authority.

## TDD and verification evidence

Intentional RED head:

`5938a449169cc2f7e007c9dde796a43a7fc7bb6a`

RED CI run:

`35512303622`

Result:

- exactly 1 new Python failure;
- 3456 Python tests passed;
- Rust tests passed;
- ARM64 release build passed;
- repository safety passed.

GREEN feature head:

`a170f35eb08f0f096e5c2a3b8878d132a306b2b1`

GREEN feature CI run:

`35512467609`

All four canonical gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Squash-merged implementation main:

`d9859d12cc70876e1d6f5b18dd1429bba7bb29b0`

Exact merged-main CI run:

`35512787891`

Conclusion: `success`.

The non-seal downstream runs for that implementation correctly remained inert:

- release run `35512899082`: `skipped`;
- deploy run `35512901265`: `skipped`.

This confirms the implementation did not release or deploy merely by landing on `main`.

## Authority boundary

This implementation and seal do not modify or authorize:

- systemd units/timers;
- sudoers;
- release-manager code;
- protected runtime-state ownership, modes, or ACLs;
- scoring-request creation;
- V2 model scoring/retry;
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
4. telemetry-mediated read-only FL9 protected discovery;
5. trusted bounded reporting of a terminal discovery failure source/code/message so the next implementation slice can be chosen from production evidence.

## Expected production proof

The automatic chain must demonstrate:

`seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery -> terminal trusted result`

If discovery returns one of the existing successful statuses, the verifier may report it under the already-sealed authority:

- `HOLD_NO_REQUEST_AUTHORITY`;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- `HOLD_NO_COMPATIBLE`;
- `FOUND_COMPATIBLE`.

If discovery returns `FAILED`, the verifier must remain fail-closed and report only:

- `fl9_v2_discovery_result_source`;
- `fl9_v2_discovery_failure_code`;
- `fl9_v2_discovery_failure_message`.

Any timeout, malformed result, untrusted failure shape, owner/mode mismatch, symlink, release mismatch, or untrusted status remains fail-closed.

Even `FOUND_COMPATIBLE` remains evidence only and does not authorize a scoring retry.

## Promotion boundary

`FL9_SANITIZED_FAILURE_REPORTING_IMPLEMENTATION=MAIN_GREEN`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=PENDING_PRODUCTION_TERMINAL_RESULT`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
