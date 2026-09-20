# FL9 V2 Direct Pre-Staged Request Binding — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `7a98bdca2a5a16c4f43d5260138b012d71d3081c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; WORKFLOW TRANSPORT CORRECTION ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified correction that removes GitHub Actions job-output transport from the protected FL9 pre-staged discovery request binding.

The deploy workflow already derives one deterministic request ID from the workflow run:

`gha-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`

The reusable production verifier now receives that same deterministic ID directly from the caller workflow context instead of depending on a deploy job output.

No host-side authority, runtime policy, evidence permission, scoring path, or trading behavior changes.

## Production evidence

Prior sealed release:

`5fc12bfea5702e585216e3541f535b2bc349a1d6`

passed exact sealed-main CI and immutable release creation.

Protected deploy/verify run:

`35527101922`

showed:

- immutable release resolution succeeded;
- protected deploy succeeded;
- exact sealed release became active;
- all three core PAPER services were active/running with zero restarts;
- no recent runtime restart or SQLite contention signature was present;
- FL9 discovery bridge was available;
- reusable production verification then failed before discovery-result polling.

The deploy job emitted the GitHub Actions warning:

`Skip output 'discovery_request_id' since it may contain secret.`

The old workflow exported the deterministic request ID from the deploy step through `GITHUB_OUTPUT`, exposed it as a deploy-job output, then passed `needs.deploy.outputs.discovery_request_id` into the reusable verifier.

When GitHub suppressed that output, the reusable verifier received an empty pre-staged input. Its fallback derived the same run-bound request ID, but fallback mode requires a new exchange directory. The already pre-staged exchange for that exact ID existed, so verification failed immediately after `fl9_v2_discovery_bridge=available`.

This was a workflow transport failure, not a PAPER runtime failure.

## Correction

Merged PR #335, `fix: bind prestaged FL9 discovery directly into reusable verifier`, now:

1. keeps deploy-side host staging bound to:
   `DISCOVERY_REQUEST_ID="gha-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"`;
2. removes the deploy job `discovery_request_id` output;
3. removes the step `id: deploy_host` that existed only to expose that output;
4. removes the `GITHUB_OUTPUT` write for the request ID;
5. removes `needs.deploy.outputs.discovery_request_id`;
6. passes the same deterministic ID directly to the reusable verifier:
   `discovery_request_id: gha-${{ github.run_id }}-${{ github.run_attempt }}`.

The deploy and verifier therefore bind to one exact workflow-run identity without any dynamic job-output transport that GitHub may suppress.

## TDD evidence

Intentional RED head:

`9a264b4866131ed94c5fc49c0e285b598daecae9`

RED CI:

`35528734879`

Result:

- Python: exactly 2 failures, 3472 passed;
- both failures proved the direct run-bound verifier binding was absent;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Final PR head:

`55018df58d7ef596e34abb37d29415107b212550`

Final PR CI:

`35528853365`

Result:

- Python: 3474 passed;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`7a98bdca2a5a16c4f43d5260138b012d71d3081c`

Exact merged-main CI:

`35529031517`

Result:

- Python: 3474 passed;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Authority boundary

This implementation and seal do not modify or authorize:

- deploy SSH account privileges;
- sudoers;
- systemd units;
- protected evidence ownership, modes, or ACLs;
- frozen cohort bytes;
- preserved V2 request or hydration-policy bytes;
- active campaign-manifest bytes;
- runtime quote/regime/safety/provider/global-risk authority;
- persisted PAPER quote evidence;
- model fitting or V2 scoring retry;
- champion publication;
- PAPER promotion;
- wallet/signing/submission;
- LIVE trading.

The change is only workflow binding of an already-existing deterministic request identifier.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment;
3. automatic reusable production verification using the direct run-bound pre-staged request ID;
4. observation of the trusted FL9 terminal result and the already-sealed quote-evidence diagnostic.

A trusted diagnostic remains evidence only.

## Expected production proof

The automatic chain must demonstrate:

`seal merge -> exact-main CI -> immutable release -> pre-stage request gha-<run>-<attempt> -> PAPER activation -> protected discovery -> reusable verifier receives the same exact request ID directly -> trusted result exchange`

The deploy workflow should no longer emit a suppressed `discovery_request_id` job-output warning because that output no longer exists.

Production verification must preserve:

- exact active release SHA;
- exact release-manifest source SHA;
- all three core PAPER services healthy with zero restarts;
- trusted discovery result source;
- exact request/release binding;
- terminal FL9 status;
- any already-authorized `runtime_quote_evidence_diagnostic`.

## Promotion boundary

`FL9_DIRECT_PRESTAGED_REQUEST_BINDING=MAIN_GREEN`

`RUNTIME_QUOTE_EVIDENCE=DIAGNOSTIC_ONLY`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
