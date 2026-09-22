# FL9 V2 Discovery-Backed Request Preparation Production Presence — Release Seal

**Date:** 2026-09-22  
**Discovery-backed request-preparation implementation main SHA:** `ba635d8ad43e67cc03c6296f42bb19c3d5268c18`  
**Production-presence implementation main SHA:** `b66828722a7ac02590ad1686c7c87b064202cdbe`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF REQUEST-PREPARATION TOOL PRESENCE ONLY; AUTOMATIC REQUEST PREPARATION DISABLED; SCORING/MODEL FITTING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the FL9 V2 discovery-backed request-preparation bridge together with its exact-release production-presence proof.

The preparation bridge converts one authenticated compatible discovery authority into one canonical future FL9 V2 host request plus one immutable provenance receipt.

It does not execute that request.

This seal exists only to transport and verify the request-preparation CLI/module in the protected PAPER production release.

It does not authorize automatic request preparation, V2 scoring, model fitting, champion publication, PAPER promotion, wallet access, signing/submission, or LIVE.

## Current production state before this seal

The latest immutable GitHub release is:

`shreks-ca5f0cc977974e3eae1a1c81e2e662de54bcf558`

Automatic release/deploy for that seal succeeded:

- sealed-main CI: `35770433412`;
- immutable release build: `35770712504`;
- protected PAPER deploy/verify: `35771315130`.

Production verification proved the exact active release, service/process health, trusted-admin tooling provenance, and:

```text
g1c_v2_decision_backed_rotation_plan=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

The later discovery-backed request-preparation implementation merge:

`ba635d8ad43e67cc03c6296f42bb19c3d5268c18`

passed merged-main CI `35775663175`.

Its release workflow `35775919568` and deploy workflow `35775924402` skipped by design because the main commit subject was not `seal:`.

The production-presence implementation merge:

`b66828722a7ac02590ad1686c7c87b064202cdbe`

passed merged-main CI `35789949566`.

Its release workflow `35790192303` and deploy workflow `35790198585` also skipped by design because the main commit subject was not `seal:`.

Therefore production has not yet received the discovery-backed request-preparation CLI/module.

No discovery-backed request has been automatically prepared.

No V2 scoring or model fitting has been automatically executed.

## Request-preparation implementation

Implementation main SHA:

`ba635d8ad43e67cc03c6296f42bb19c3d5268c18`

Final implementation head:

`4e4c4e2a6a49e550773f4f4e33a9e1e701a9e0a1`

CLI:

`shreks-fl9-v2-discovery-backed-request-prepare`

Module:

`shreks_brain.fl9_v2_discovery_backed_request_preparation`

The tool accepts only reviewed source artifacts and explicit future-request policy inputs.

It authenticates:

- the discovery-authority binding;
- the binding-selected runtime manifest;
- the exact release identity;
- the frozen V2 cohort;
- the hydration policy;
- the proof workspace;
- the canonical request written by the sealed V2 request writer.

It requires new, non-existing destinations for the future request, future evidence, and preparation receipt.

A successful preparation receipt remains evidence only:

```text
request_preparation_authority=DISCOVERY_BOUND_REQUEST_ONLY
scoring_authority=NOT_GRANTED
champion_publication_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The preparation tool does not execute scoring or model fitting.

## TDD and implementation proof

### Discovery-backed request preparation

Final implementation head:

`4e4c4e2a6a49e550773f4f4e33a9e1e701a9e0a1`

PR #431 CI:

`35775334803`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64 release build.

Merged implementation main:

`ba635d8ad43e67cc03c6296f42bb19c3d5268c18`

Merged-main CI:

`35775663175`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED head:

`7d14008ee6ecb68407ee636f2d43c1188d57c9fe`

RED CI:

`35789544286`

Result:

- Python: exactly 1 failed, 3650 passed, 2 known warnings;
- the only failure was the intentionally absent FL9 V2 request-preparation production-presence surface;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN production-presence head:

`77ec7d40a685d3d6bd6dfbac82e4ce8ec5a5dfbf`

PR #432 CI:

`35789602102`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64 release build.

Merged production-presence main:

`b66828722a7ac02590ad1686c7c87b064202cdbe`

Merged-main CI:

`35789949566`

Result: SUCCESS across all four canonical gates.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the preparation command:

- `shreks-fl9-v2-discovery-backed-request-prepare` exists in release-local Python;
- the script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.fl9_v2_discovery_backed_request_preparation` imports through exact release-local Python;
- the module path resolves inside that same expected release.

Expected evidence includes:

```text
fl9_v2_discovery_backed_request_prepare=present
fl9_v2_discovery_backed_request_prepare_path=<exact-release-local-path>
fl9_v2_discovery_backed_request_prepare_module=<exact-release-local-module-path>
```

The verifier must not invoke the preparation command.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the discovery-backed request-preparation CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, exact-release request-preparation tool presence/provenance, existing trusted-admin tooling, read-only helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute the discovery-backed request-preparation command;
- create a future V2 request;
- create a preparation receipt;
- execute V2 scoring;
- execute model fitting;
- publish champion evidence;
- promote PAPER;
- change risk intent;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin preparation boundary

Only after production verification proves the preparation CLI/module exact-release-local, and only after an exact reviewed compatible discovery-authority binding plus all required source artifacts exist, may a trusted administrator run the documented root-private preparation ceremony.

That ceremony may write only:

- one canonical future V2 host request;
- one immutable discovery-bound preparation receipt.

The future evidence destination remains an unexecuted destination.

Request existence does not grant scoring authority.

Preparation-receipt existence does not grant scoring authority.

Any V2 scoring or model-fitting execution requires a separate later decision and proof slice.

## Authority boundary

This seal does not authorize:

- automatic preparation execution;
- automatic or manual scoring merely because a request exists;
- V2 model fitting;
- champion evidence publication;
- PAPER promotion;
- risk intent;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`FL9_V2_DISCOVERY_BACKED_REQUEST_PREPARATION=SEALED_TOOL_PRESENCE_ONLY`

`DISCOVERY_BACKED_REQUEST_PREPARATION_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_REQUEST_PREPARATION=DISABLED`

`REQUEST_PREPARATION_AUTHORITY=DISCOVERY_BOUND_REQUEST_ONLY_WHEN_EXPLICITLY_INVOKED`

`SCORING_AUTHORITY=NOT_GRANTED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`CHAMPION_PUBLICATION_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
