# G1C V2 Preflight-Bound Candidate Authority API-Download Recovery — Release Seal

**Date:** 2026-09-23  
**Preflight-bound authority implementation main SHA:** `c62c2ede15f44ecae07ef557bf4accd2922d032b`  
**Final deploy transport hotfix main SHA:** `c2cc5becdff71456e5d232a945d05d22dd24d4fb`  
**Status:** FINAL RECOVERY SEAL FOR IMMUTABLE RELEASE + PROTECTED PAPER DEPLOY/VERIFY; AUTHORITY TOOL PRESENCE ONLY; AUTOMATIC AUTHORITY/RUNTIME/TRADING ACTIONS BLOCKED

## Purpose

Create one fresh immutable release containing:

1. the schema-v2 preflight-bound decision-backed candidate-authority implementation; and
2. the corrected fail-closed GitHub release transport that both enumerates and downloads exact release assets through verified API asset identities.

The prior recovery release `shreks-91a4792cfb4b739884ac5a49ffebe288ed80c7f8` built successfully, and its dedicated release-assets enumeration passed, but `gh release download` independently returned `no assets to download`.

That deploy stopped before local bundle verification and before SSH, SCP, or host release-manager contact.

This seal replaces that unreliable download surface with exact downloads by the already-verified positive unique asset IDs.

## Prior failed recovery

Previous recovery seal:

`91a4792cfb4b739884ac5a49ffebe288ed80c7f8`

Sealed-main CI:

`35837392894` — SUCCESS.

Immutable release build:

`35837745295` — SUCCESS.

Automatic deploy:

`35838293289`

Result:

- resolve: SUCCESS;
- immutable release identity + dedicated asset enumeration: SUCCESS;
- exact release asset download: FAILED with `no assets to download`;
- local bundle verification: SKIPPED;
- host transfer/release manager: SKIPPED;
- production verify: SKIPPED.

Therefore the protected PAPER host was not changed by that attempt.

## Final release-asset transport hotfix

PR #442 replaced `gh release download` with downloads by exact verified asset ID.

The workflow now:

1. authenticates exact release tag/SHA/draft/prerelease/immutability;
2. enumerates the release through the dedicated release-assets endpoint;
3. requires exactly the manifest, archive, and checksum names;
4. requires every asset to be `uploaded`;
5. requires every asset ID to be a positive integer;
6. requires all asset IDs to be unique;
7. constructs a local exact name-to-ID mapping only from that authenticated set;
8. downloads each exact asset with:
   `GET /repos/<repo>/releases/assets/<asset-id>`
   using `Accept: application/octet-stream`;
9. requires exactly the three expected local files;
10. runs `release_bundle.py verify` before any SSH/SCP or host contact.

There is no wildcard or independent release re-enumeration in the download step.

## TDD proof for final transport hotfix

Intentional RED head:

`2f29fb037ae2c2ab587d9f45b4dbd8984a977463`

RED CI:

`35838508756`

Result:

- Python: exactly 1 failed, 3660 passed, 2 known warnings;
- the only failure proved `gh release download` was still present;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Intermediate implementation run:

`35838947689`

Result:

- Python: exactly 1 failed, 3660 passed, 2 known warnings;
- the only failure was one stale legacy test that still required `gh release download`;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Final GREEN head:

`a3cd04ad9430028f464dfd49cf2df485612a5ed3`

GREEN PR CI:

`35839321580`

Result:

- Python: 3661 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Merged hotfix main:

`c2cc5becdff71456e5d232a945d05d22dd24d4fb`

Merged-main CI:

`35839933195`

Result:

- Python: 3661 passed, 2 known warnings;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Normal-fix delivery workflows correctly skipped:

- release `35840479125`: SKIPPED;
- deploy `35840484783`: SKIPPED.

## Preflight-bound candidate-authority implementation included

The release continues to contain the schema-v2 hardened binder:

`shreks-g1c-v2-decision-backed-candidate-authority-bind`

The binder requires:

- canonical source runtime manifest;
- frozen FL9 V2 cohort;
- authenticated V2 host-request authority;
- exact successful candidate-value compatibility preflight;
- approved candidate-value decision;
- new authority destination.

It no longer accepts operator-provided paper run id/time.

It requires the approved decision and preflight to match exactly on source/proposal/quote-evidence/economics provenance.

It accepts only the preflighted proposal amount and requires canonical derivation to reproduce the exact candidate already proven `COMPATIBLE`.

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

## Current production boundary before this seal

The last successfully verified active protected PAPER release remains:

`shreks-192b5165066197ca59126e9e5c7851055b56d24a`

Its verification proved:

```text
current_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
expected_release=/opt/shreks/releases/192b5165066197ca59126e9e5c7851055b56d24a
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=HOLD_NO_COMPATIBLE
```

The schema-v2 preflight-bound authority implementation is not yet active on the protected host because both newer sealed deploy attempts stopped before host contact.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. publish exactly the required release assets;
3. authenticate exact release identity;
4. enumerate and authenticate exact asset names/states/IDs;
5. download only those verified assets by exact API ID;
6. verify the release bundle locally;
7. deploy that exact release through the protected PAPER release manager;
8. activate the ordinary protected PAPER runtime;
9. verify exact release identity, service/process health, exact-release tool presence/provenance, manifest-manager state, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute candidate-value preflight;
- execute candidate-value decision;
- execute decision-backed candidate-authority binding;
- author or stage a candidate runtime manifest;
- create transition binding;
- execute readiness;
- rotate the protected manifest;
- execute V2 scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign/submit transactions;
- enable LIVE.

## Expected production evidence

After successful deploy/verify, require:

```text
current_release=/opt/shreks/releases/<this-seal-sha>
expected_release=/opt/shreks/releases/<this-seal-sha>
g1c_v2_candidate_value_preflight=present
g1c_v2_decision_backed_candidate_authority=present
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

Protected FL9 discovery may remain:

`HOLD_NO_COMPATIBLE`

because this release transports the hardened authority path but does not execute preflight/decision/authority or rotate the active PAPER manifest.

## Helper/readiness boundary

This deployment changes the active release SHA.

Any helper installation proof bound to an earlier release SHA becomes stale for later rotation-readiness.

A fresh exact-release helper proof remains mandatory before future readiness/rotation.

## Authority boundary

This seal does not authorize:

- automatic preflight execution;
- automatic candidate-value approval;
- automatic candidate-authority execution;
- candidate authoring/staging;
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

`RELEASE_ASSET_ENUMERATION=DEDICATED_ENDPOINT_FAIL_CLOSED`

`RELEASE_ASSET_DOWNLOAD=VERIFIED_ASSET_ID_API_ONLY`

`AUTOMATIC_DECISION_BACKED_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_FILE_AUTHORING=NOT_AUTHORIZED`

`TRANSITION_BINDING=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
