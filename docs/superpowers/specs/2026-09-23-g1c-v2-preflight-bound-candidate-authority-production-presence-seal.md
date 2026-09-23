# G1C V2 Preflight-Bound Decision-Backed Candidate Authority — Release Seal

**Date:** 2026-09-23  
**Preflight-bound candidate-authority implementation main SHA:** `c62c2ede15f44ecae07ef557bf4accd2922d032b`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF HARDENED AUTHORITY TOOL PRESENCE ONLY; AUTOMATIC AUTHORITY EXECUTION DISABLED; CANDIDATE FILE AUTHORING/STAGING, TRANSITION, ROTATION, SCORING, PROMOTION, AND LIVE BLOCKED

## Purpose

Seal the hardened G1C V2 decision-backed candidate-authority binder that now requires one exact successful candidate-value compatibility preflight before candidate-authoring authority may exist.

The hardened binder closes the remaining drift path between:

1. the exact hypothetical candidate previously proven `COMPATIBLE`;
2. the explicit candidate-value decision;
3. later candidate-authoring authority.

It authenticates the preflight receipt and approved candidate-value decision, requires exact source/proposal/quote-evidence equality, derives future run identity/time only from the preflight, and requires the canonical candidate authority derivation to reproduce the exact preflighted candidate SHA/fingerprint/run/time/economics/cohort/request identity.

This seal transports and verifies that hardened tool only.

It does not execute the binder.

It does not create or stage a runtime-manifest candidate.

It does not grant transition binding, manifest rotation, V2 scoring/model fitting, PAPER promotion, wallet access, signing/submission, or LIVE.

## Current production state before this seal

The active immutable production release is:

`shreks-192b5165066197ca59126e9e5c7851055b56d24a`

Protected PAPER deploy/verify run:

`35803125660`

completed successfully.

Production verification proved:

```text
current_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
expected_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

That release contains the candidate-value preflight but still contains the older decision-backed authority implementation that accepted separately supplied future `paper_run_id` and `start_at_unix_ms`.

No production candidate-authority artifact has been created through the hardened schema-v2 path because that path is not yet in the active release.

No runtime-manifest candidate has been authored or staged.

No transition binding, readiness, manifest rotation, scoring/model fitting, or PAPER promotion has been executed by this slice.

## Hardened candidate-authority implementation

Implementation was merged to `main` as:

`c62c2ede15f44ecae07ef557bf4accd2922d032b`

Final GREEN implementation head:

`68cc374fe9eba1aa669e9b4fd6ae51e90ee340e4`

CLI remains:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

Module remains:

`shreks_brain.g1c_v2_decision_backed_candidate_authority`

Authority schema is now version 2.

The hardened CLI requires only:

- canonical source runtime manifest;
- frozen FL9 V2 cohort;
- authenticated V2 host-request authority;
- successful candidate-value preflight receipt;
- approved candidate-value decision;
- one new non-existing authority destination.

It no longer accepts:

- `--paper-run-id`;
- `--start-at-unix-ms`;
- raw quote mint;
- raw quote decimals;
- raw entry-input amount.

Future candidate run identity/time come only from the authenticated preflight receipt.

Candidate economics come only from the approved candidate-value decision, which must match the same proposal/evidence committed by the preflight.

## Preflight/decision equality requirements

Before candidate-authoring authority may be derived, the preflight receipt and candidate-value decision must agree exactly on:

- source runtime-manifest SHA-256;
- source runtime-manifest fingerprint;
- source paper run id;
- source sizing-proposal SHA-256;
- sizing-proposal fingerprint;
- quote-evidence authority;
- quote-evidence fingerprint;
- quote-evidence observation timestamp;
- target quote mint;
- target quote decimals;
- proposed raw entry amount.

The approved amount must equal the amount proven by the preflight.

Therefore the hardened authority path accepts only:

`decision=ACCEPT_PROPOSAL`

A `REPLACE_PROPOSAL` decision is rejected because the replacement amount was not the amount proven compatible by the existing preflight artifact.

A future replacement-value path requires its own separately designed compatibility proof before it may grant candidate-authoring authority.

## Exact candidate equality requirements

The binder still delegates canonical candidate derivation to the existing G1C V2 candidate-authority implementation.

It then requires the derived candidate to equal the preflighted hypothetical candidate on:

- candidate manifest SHA-256;
- runtime-manifest fingerprint;
- candidate paper run id;
- candidate start timestamp;
- quote mint;
- quote decimals;
- raw entry-input amount;
- frozen cohort fingerprint;
- frozen cohort quote mint;
- request fingerprint;
- request release source SHA;
- request hydration-policy fingerprint.

Any mismatch fails closed and writes no candidate-authority artifact.

## Successful authority artifact

A successful schema-v2 decision-backed authority artifact may record:

```text
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_compatibility=COMPATIBLE
preflight_authority=EVIDENCE_ONLY
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The artifact additionally commits the exact candidate-value preflight SHA/fingerprint/status/provenance.

It remains candidate-authoring authority evidence only.

It is not a runtime-manifest candidate.

## TDD proof

Intentional RED head:

`5a56c8150f095d0e72f02b36c6c625e238dc5a15`

RED PR CI:

`35804608101`

Result:

- Python: exactly 1 failed, 3657 passed, 2 known warnings;
- the only failure was `test_decision_backed_candidate_authority_is_preflight_bound`;
- the failure proved the existing binder did not yet import/require the candidate-value preflight;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN implementation head:

`68cc374fe9eba1aa669e9b4fd6ae51e90ee340e4`

GREEN PR CI:

`35805311212`

Result:

- Python: 3659 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged implementation main:

`c62c2ede15f44ecae07ef557bf4accd2922d032b`

Merged-main CI:

`35833220526`

Result:

- Python: 3659 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

The feature merge correctly did not release or deploy:

- release workflow `35833488776`: SKIPPED;
- deploy workflow `35833496151`: SKIPPED.

Therefore production still contains the older authority implementation until this release seal succeeds.

## Existing production-presence verifier

The repository already has exact-release production-presence verification for:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

The verifier proves without invoking the binder that:

- the release-local script is a regular non-symlink executable;
- the resolved script path belongs to the exact expected immutable release;
- the authority module imports through exact release-local Python;
- the module resolves inside that same release.

Expected evidence after this seal includes:

```text
g1c_v2_decision_backed_candidate_authority=present
g1c_v2_decision_backed_candidate_authority_path=<exact-release-local-path>
g1c_v2_decision_backed_candidate_authority_module=<exact-release-local-module-path>
```

The ordinary verifier must continue to avoid executing the authority binder.

Because the release-local module is replaced atomically with the immutable release, exact-release presence proves the hardened schema-v2 implementation is the one available to trusted administrators.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the hardened decision-backed authority CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, exact-release tool presence/provenance, candidate-value preflight presence, manifest-manager status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute the candidate-value preflight;
- execute the candidate-value decision;
- execute the decision-backed authority binder;
- create or stage a runtime-manifest candidate;
- create a transition binding;
- execute rotation readiness;
- rotate the protected manifest;
- execute V2 scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- change risk intent;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin boundary after deploy

Only after production verification proves both:

- candidate-value preflight exact-release presence;
- hardened decision-backed candidate-authority exact-release presence;

may a trusted administrator use the documented evidence chain.

The required order remains:

1. produce/review authenticated `MULTI_REFERENCE_REVIEW` sizing evidence;
2. produce an evidence-only candidate compatibility preflight;
3. review exact `COMPATIBLE` preflight evidence;
4. make a separate explicit candidate-value decision;
5. bind schema-v2 decision-backed candidate authority using that exact preflight + decision;
6. review the authority artifact separately;
7. only then use the separately sealed candidate-authoring path to reproduce the exact committed candidate.

Do not run transition binding merely because candidate-authoring authority exists.

Do not run rotation-readiness merely because a candidate exists.

## Helper/readiness boundary

Deployment of this seal changes the active release SHA.

Any helper installation proof bound to an earlier release SHA becomes stale for later rotation-readiness.

A fresh exact-release helper proof remains mandatory before any future readiness/rotation ceremony.

No helper-proof refresh is required merely to produce the offline preflight, decision, authority, candidate, or transition artifacts unless the downstream readiness tool requires it.

## Authority boundary

This seal does not authorize:

- automatic candidate compatibility preflight;
- automatic candidate-value decision;
- automatic decision-backed authority execution;
- candidate runtime-manifest authoring/staging;
- transition binding;
- rotation-readiness execution;
- production manifest rotation;
- V2 scoring/model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_PREFLIGHT_BOUND_CANDIDATE_AUTHORITY=SEALED_AUTHORITY_EVIDENCE_ONLY`

`DECISION_BACKED_CANDIDATE_AUTHORITY_SCHEMA=V2_PREFLIGHT_BOUND`

`AUTOMATIC_DECISION_BACKED_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_FILE_AUTHORING=NOT_AUTHORIZED`

`TRANSITION_BINDING=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
