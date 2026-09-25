# G1C V2 Preflight-Bound Candidate Authority + Deploy Asset Verification Hotfix — Corrective Release Seal

**Date:** 2026-09-23  
**Hardened candidate-authority implementation main SHA:** `c62c2ede15f44ecae07ef557bf4accd2922d032b`  
**Deploy release-assets verification hotfix main SHA:** `6bf97399cc2503846cb8e9328b7a4ca977b31db8`  
**Status:** CORRECTIVE SEAL FOR IMMUTABLE RELEASE + PROTECTED PAPER DEPLOY/VERIFY; TOOL PRESENCE ONLY; AUTOMATIC CANDIDATE PREFLIGHT/DECISION/AUTHORITY/AUTHORING/ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Create a new sealed source SHA that contains both:

1. the schema-v2 preflight-bound G1C V2 decision-backed candidate-authority implementation; and
2. the corrected immutable-release asset verification used by the automatic PAPER deploy workflow.

The prior seal `6c441abdbabb30d0585175e298effd5a688f7db0` successfully produced a valid immutable GitHub release but could not deploy because the deploy workflow read the asset-name set from the tag release object's embedded `assets` field.

For that release, the tag lookup returned an empty embedded asset array even though the dedicated release-assets endpoint contained the expected uploaded immutable assets.

This corrective seal does not weaken release verification. It moves exact asset-set validation to GitHub's dedicated release-assets endpoint while preserving every existing release identity and local bundle-verification gate.

## Active production state before this corrective seal

Protected production remains on:

`shreks-192b5165066197ca59126e9e5c7851055b56d24a`

Its deploy/verify run:

`35803125660`

completed successfully.

That production release proved:

```text
current_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
expected_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

That release contains the candidate-value compatibility preflight but predates the schema-v2 preflight-bound candidate-authority implementation.

## Prior sealed release that did not reach production

Seal main SHA:

`6c441abdbabb30d0585175e298effd5a688f7db0`

Sealed-main CI:

`35834565803`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

Immutable release build:

`35834804257`

Result: SUCCESS.

Published immutable release:

`shreks-6c441abdbabb30d0585175e298effd5a688f7db0`

Published assets are valid and immutable:

```text
RELEASE_MANIFEST.json
sha256:8e9735168a04b4fbd605093cf66104e22a9015e181a1aac01c04104ffc77a4ec

shreks-release-6c441abdbabb30d0585175e298effd5a688f7db0.tar.gz
sha256:fc5e3f39b417220a3fb24e877257828947fb9346d0b81518f06013ceb028247f

shreks-release-6c441abdbabb30d0585175e298effd5a688f7db0.tar.gz.sha256
sha256:55be41f1c2a5d2b8332e631230e6e0f34f0ca93a6bc4cba70b69b33544805435
```

Automatic deploy run:

`35835299708`

failed twice before host contact.

Attempt 1:

- resolve: SUCCESS;
- deploy: FAILED;
- verify: SKIPPED.

Attempt 2, using the same immutable release:

- resolve: SUCCESS;
- deploy: FAILED;
- verify: SKIPPED.

Both attempts terminated at:

`release asset set mismatch`

before:

- release asset download;
- SSH;
- SCP;
- host release-manager invocation;
- production activation;
- production verification.

Therefore `6c441abdbabb30d0585175e298effd5a688f7db0` is an immutable published release but is not the active production release.

## Root cause

The deploy workflow used:

`GET /repos/<repo>/releases/tags/<tag>`

for release metadata and then validated exact asset names from the response object's embedded `assets` field.

For the affected release, that tag lookup exposed an empty embedded asset list.

The dedicated endpoint:

`GET /repos/<repo>/releases/<release-id>/assets`

returned all three expected uploaded assets correctly.

The failure was therefore in deploy-control asset enumeration, not in:

- release construction;
- release immutability;
- archive/checksum/manifest contents;
- production host state;
- SSH transport;
- release manager;
- protected PAPER runtime.

## Deploy verification hotfix

Hotfix PR #439 merged to `main` as:

`6bf97399cc2503846cb8e9328b7a4ca977b31db8`

The corrected deploy workflow still obtains release metadata from the exact tag lookup and still requires:

- exact release tag;
- exact target commit SHA;
- `draft=false`;
- `prerelease=false`;
- `immutable=true`;
- positive numeric release id.

It then queries:

`GET /repos/<repo>/releases/<release-id>/assets?per_page=100`

and requires exactly these uploaded assets:

- `RELEASE_MANIFEST.json`;
- `shreks-release-<source-sha>.tar.gz`;
- `shreks-release-<source-sha>.tar.gz.sha256`.

Only after that exact asset-set check passes may the existing workflow:

1. download the exact three release assets;
2. verify archive/checksum/manifest locally with `release_bundle.py verify`;
3. create the protected discovery-control exchange;
4. contact the host;
5. invoke the narrow root-owned release manager;
6. call the reusable production verifier.

No host-contact ordering was weakened.

## Hotfix TDD proof

Intentional RED head:

`b539a9cb8aa454ab51f43f81556250a04e7b0eb7`

RED PR CI:

`35835715633`

Result:

- Python: exactly 1 failed, 3659 passed, 2 known warnings;
- only failure: dedicated release-assets endpoint contract absent;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN hotfix head:

`7a86e36e17b3d1656e4c67b957259f9aa9ba9f6a`

GREEN PR CI:

`35835987881`

Result:

- Python: 3660 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Merged hotfix main:

`6bf97399cc2503846cb8e9328b7a4ca977b31db8`

Merged-main CI:

`35836283623`

Result:

- Python: 3660 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

The normal hotfix merge correctly did not create a release:

- release workflow `35836519584`: SKIPPED;
- deploy workflow `35836539965`: SKIPPED.

## Hardened candidate-authority content carried by this corrective seal

This seal also carries the already-proven schema-v2 implementation merged at:

`c62c2ede15f44ecae07ef557bf4accd2922d032b`

CLI:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

Module:

`shreks_brain.g1c_v2_decision_backed_candidate_authority`

The hardened binder requires an authenticated successful candidate-value preflight and approved candidate-value decision.

It derives future candidate run id/time only from the preflight and requires exact equality across source, proposal, quote evidence, candidate economics, candidate manifest SHA/fingerprint, cohort authority, and request authority.

The current hardened authority path accepts only:

`ACCEPT_PROPOSAL`

because a replacement raw amount has not been separately preflighted.

A successful authority artifact remains bounded to:

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

The automatic deployment chain does not execute this binder.

## Automatic authority granted by this corrective seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable release for the exact new seal SHA;
2. verify release metadata and exact asset set using the corrected fail-closed workflow;
3. deploy that exact release through the existing protected PAPER release manager;
4. activate the ordinary protected PAPER runtime;
5. verify exact release identity, service/process health, release-local trusted-admin tool presence/provenance, manifest-manager status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute candidate-value compatibility preflight;
- make a candidate-value decision;
- execute decision-backed candidate authority;
- author or stage a runtime-manifest candidate;
- create a transition binding;
- execute readiness;
- rotate the protected campaign manifest;
- execute V2 scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Post-deploy expected production proof

The production verifier must establish the exact new corrective release as both current and expected and must continue proving release-local presence for:

```text
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

Protected discovery remains observational. Its actual terminal status must be reported as produced by production; this seal does not force `FOUND_COMPATIBLE` and does not bypass `HOLD_NO_COMPATIBLE`.

## Helper/readiness boundary

The corrective deployment changes the active release SHA.

Any installation proof bound to an earlier release remains stale for later rotation-readiness.

A fresh exact-release helper proof remains mandatory before any future readiness/rotation ceremony.

No readiness or rotation is authorized by this seal.

## Promotion boundary

`G1C_V2_PREFLIGHT_BOUND_CANDIDATE_AUTHORITY=SEALED_AUTHORITY_EVIDENCE_ONLY`

`DEPLOY_RELEASE_ASSET_VERIFICATION=DEDICATED_ENDPOINT_EXACT_SET`

`AUTOMATIC_DECISION_BACKED_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_FILE_AUTHORING=NOT_AUTHORIZED`

`TRANSITION_BINDING=NOT_AUTHORIZED`

`ROTATION_AUTHORITY=NOT_GRANTED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
