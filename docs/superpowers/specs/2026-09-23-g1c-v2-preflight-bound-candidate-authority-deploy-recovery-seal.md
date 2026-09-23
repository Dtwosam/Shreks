# G1C V2 Preflight-Bound Candidate Authority Deploy Recovery — Release Seal

**Date:** 2026-09-23  
**Preflight-bound authority implementation main SHA:** `c62c2ede15f44ecae07ef557bf4accd2922d032b`  
**Deploy verifier hotfix main SHA:** `6bf97399cc2503846cb8e9328b7a4ca977b31db8`  
**Status:** RECOVERY SEAL FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; AUTHORITY TOOL PRESENCE ONLY; AUTOMATIC AUTHORITY EXECUTION AND ALL DOWNSTREAM RUNTIME/TRADING AUTHORITY BLOCKED

## Purpose

Produce one fresh immutable release that contains both:

1. the schema-v2 preflight-bound G1C V2 decision-backed candidate-authority implementation; and
2. the fail-closed deploy verifier fix that reads release assets from GitHub's dedicated release-assets endpoint.

The previous sealed release was valid and immutable but its automatic deployment stopped before host contact because the tag-release API response exposed an empty embedded `assets` array.

This recovery seal does not weaken release validation. It keeps exact tag/SHA/draft/prerelease/immutability checks and verifies the exact three uploaded immutable assets through:

`/repos/<repo>/releases/<release-id>/assets?per_page=100`

before any release download or host contact.

## Previous seal and failed deploy

Previous seal commit:

`6c441abdbabb30d0585175e298effd5a688f7db0`

Sealed-main CI:

`35834565803`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

Immutable release build:

`35834804257`

Result: SUCCESS.

Published immutable release:

`shreks-6c441abdbabb30d0585175e298effd5a688f7db0`

The release is immutable and contains exactly:

- `RELEASE_MANIFEST.json`;
- `shreks-release-6c441abdbabb30d0585175e298effd5a688f7db0.tar.gz`;
- `shreks-release-6c441abdbabb30d0585175e298effd5a688f7db0.tar.gz.sha256`.

Automatic deploy run:

`35835299708`

Result:

- resolve: SUCCESS;
- deploy: FAILED;
- verify: SKIPPED.

The deploy failure occurred at the local immutable-release asset-set verification before SSH/SCP or host release-manager contact.

Therefore the protected PAPER host was not changed by that failed deploy attempt.

## Deploy verifier hotfix

PR #439 fixed the release asset verification path without changing runtime or trading authority.

Intentional RED head:

`b539a9cb8aa454ab51f43f81556250a04e7b0eb7`

RED PR CI:

`35835715633`

Result:

- Python: exactly 1 failed, 3659 passed, 2 known warnings;
- the only failure was the dedicated release-assets endpoint contract;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN head:

`7a86e36e17b3d1656e4c67b957259f9aa9ba9f6a`

GREEN PR CI:

`35835987881`

Result:

- Python: 3660 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged hotfix main:

`6bf97399cc2503846cb8e9328b7a4ca977b31db8`

Merged-main CI:

`35836283623`

Result: SUCCESS across all four canonical gates.

Because the hotfix merge was not a `seal:` commit:

- release workflow `35836519584`: SKIPPED;
- deploy workflow `35836539965`: SKIPPED.

A fresh seal is therefore required.

## Exact deploy validation retained

The corrected deploy workflow continues to require:

- source SHA is exactly 40 lowercase hex characters;
- release tag is exactly `shreks-<source-sha>`;
- tag and source SHA match exactly;
- GitHub release `tag_name` equals the expected tag;
- `target_commitish` equals the exact source SHA;
- release is not draft;
- release is not prerelease;
- release is immutable;
- release id is a positive integer;
- dedicated release-assets response is a JSON array;
- asset names equal exactly the three required release assets;
- every asset has `state=uploaded`;
- downloaded files are exactly the three expected files;
- release bundle verifies locally before host contact.

The hotfix changes only where the asset list is obtained.

## Hardened authority implementation included

The release also contains the schema-v2 preflight-bound authority implementation merged as:

`c62c2ede15f44ecae07ef557bf4accd2922d032b`

CLI:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

The hardened binder:

- requires a successful candidate-value preflight;
- requires exact source/proposal/quote-evidence equality with the approved candidate-value decision;
- derives candidate run id/time only from the preflight;
- accepts only the preflighted proposal amount;
- requires the canonical derived candidate to reproduce the exact preflighted candidate SHA/fingerprint/run/time/economics/cohort/request identity;
- writes only candidate-authoring authority evidence.

A successful authority artifact remains bounded:

```text
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

## Current production boundary before recovery

The last successfully verified protected PAPER release remains:

`shreks-192b5165066197ca59126e9e5c7851055b56d24a`

Its successful production verification proved:

```text
current_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
expected_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

The older authority tool is present there, but the schema-v2 preflight-bound implementation is not yet active because the `6c441abd...` deploy failed before host contact.

## Automatic authority granted by this recovery seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one fresh immutable ARM64 release for the exact recovery-seal SHA;
2. publish the exact release assets;
3. validate those assets through the dedicated GitHub release-assets endpoint;
4. locally verify the exact bundle before host contact;
5. deploy that exact release through the protected PAPER release manager;
6. activate the ordinary protected PAPER runtime;
7. verify exact release identity, process/service health, exact-release tool presence/provenance, manifest-manager state, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute the candidate-value preflight;
- execute the candidate-value decision;
- execute the decision-backed candidate-authority binder;
- author or stage a runtime-manifest candidate;
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

## Expected production proof

After successful deploy/verify, require:

```text
current_release=/opt/shreks/releases/<recovery-seal-sha>
expected_release=/opt/shreks/releases/<recovery-seal-sha>
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

Protected FL9 discovery may remain:

`HOLD_NO_COMPATIBLE`

because this seal transports authority tooling only and does not execute the compatibility preflight or rotate the runtime manifest.

## Helper/readiness boundary

This recovery deployment changes the active release SHA.

Any helper installation proof bound to an earlier release SHA is stale for later rotation-readiness.

A fresh exact-release helper proof remains mandatory before any future readiness/rotation ceremony.

## Authority boundary

This recovery seal does not authorize:

- automatic preflight execution;
- automatic candidate-value approval;
- automatic candidate-authority execution;
- candidate file authoring/staging;
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

`DEPLOY_RELEASE_ASSET_VALIDATION=DEDICATED_ENDPOINT_FAIL_CLOSED`

`AUTOMATIC_DECISION_BACKED_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_FILE_AUTHORING=NOT_AUTHORIZED`

`TRANSITION_BINDING=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
