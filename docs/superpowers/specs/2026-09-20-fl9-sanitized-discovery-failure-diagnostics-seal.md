# FL9 Sanitized Discovery Failure Diagnostics — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `d9859d12cc70876e1d6f5b18dd1429bba7bb29b0`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verifier change that keeps terminal FL9 `FAILED` results fail-closed while surfacing only trusted, bounded diagnostics needed to identify the next implementation defect.

Production had already proven that the automatic release/deploy chain, telemetry control transport, request/release/schema binding, and trusted result exchange were working. The remaining blocker was that the verifier stopped at terminal `FAILED` before exposing the sanitized failure code.

## Production evidence that justified the fix

Automatic production delivery run `35512058141` for immutable release:

`734e2bcb913d69490bcbc4b987be1b578baabc42`

proved:

- immutable release resolution succeeded;
- protected PAPER deploy succeeded;
- exact active release and manifest SHA matched;
- all core PAPER services were healthy with zero restarts;
- the FL9 control result arrived in about one minute rather than timing out;
- request ID, result schema, expected release SHA, and observed release SHA checks passed;
- the terminal FL9 status was `FAILED`;
- the verifier failed before exposing a bounded failure code/message.

That established that the transport path itself was no longer the blocker.

## Implemented behavior

Merged PR #324, `fix: surface sanitized FL9 discovery failure`, changes verifier handling only.

For a trusted terminal `FAILED` result, the verifier now reports only:

- trusted result source: `exchange` or `journal`;
- bounded uppercase failure code;
- whitespace-normalized bounded failure message.

It does not print the raw result on the failure path.

Both supported failure shapes remain accepted:

1. top-level `error_code` plus string `error`;
2. the fixed nested `CONTROL_RESULT_PUBLISH_FAILED` shape.

The verifier still exits nonzero for `FAILED`.

## TDD evidence

Intentional RED head:

`5938a449169cc2f7e007c9dde796a43a7fc7bb6a`

RED CI:

`35512303622`

Exactly one new Python delivery-contract failure was observed while 3456 Python tests passed; Rust, ARM64, and repository safety were green.

GREEN feature head:

`a170f35eb08f0f096e5c2a3b8878d132a306b2b1`

GREEN feature CI:

`35512467609`

All four canonical gates passed.

Independent PR #324 CI:

`35512642709`

All four canonical gates passed.

Merged implementation main:

`d9859d12cc70876e1d6f5b18dd1429bba7bb29b0`

Exact merged-main CI:

`35512787891`

All four canonical gates passed.

The non-seal release and deploy runs for the implementation skipped as intended, proving this fix cannot reach production without an explicit seal.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

- immutable release creation for the exact seal SHA;
- automatic protected PAPER deployment of that immutable release;
- automatic production verification;
- read-only FL9 protected discovery;
- fail-closed exposure of the trusted bounded failure code/message if discovery ends in `FAILED`.

The existing `production-paper` environment, immutable-release verification, narrow deploy account, and protected runtime-state boundaries remain authoritative.

## Expected proof after deploy

The automatic chain must demonstrate one of the existing trusted terminal outcomes.

If the result is `FAILED`, the verifier must expose only:

- `fl9_v2_discovery_result_source=<exchange|journal>`;
- bounded failure code;
- bounded normalized failure message;

and must still fail the delivery chain.

That evidence may be used to choose the next repository fix. It does not authorize scoring.

## Authority explicitly not granted

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`

No model fitting, scoring request, champion publication, risk-intent creation, signing, submission, wallet handling, or live-capital action is authorized by this seal.
