# Automatic PAPER Delivery Chain — Release Seal

**Date:** 2026-09-19  
**Implementation main SHA:** `c55811ac94ae455e0f7508cb478781d7c70a6f52`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified GitHub control-plane change that removes the recurring manual dispatch gap between an approved immutable Shreks release and protected PAPER deployment/verification.

The normal authorized delivery path is now:

```text
seal merge -> CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery
```

This seal changes delivery orchestration only. It does not grant new trading, scoring, promotion, signing, submission, wallet, provider, or LIVE authority.

## Implemented delivery chain

Merged PR #314, `feat: automate sealed PAPER delivery chain`, adds:

1. automatic `Deploy verified Shreks release` triggering after `Build sealed Shreks release` completes;
2. automatic deploy eligibility only when the upstream release run completed successfully and itself came from the canonical automatic `workflow_run` release path;
3. a non-secret resolve job that derives one exact `source_sha` and `shreks-<source_sha>` release tag;
4. exact lowercase 40-hex release identity validation for automatic and manual paths;
5. independent GitHub Release verification before any VPS contact;
6. exact release tag equality;
7. exact `target_commitish == source_sha`;
8. mandatory `draft == false`;
9. mandatory `prerelease == false`;
10. mandatory `immutable == true`;
11. an exact three-asset release set:
    - `RELEASE_MANIFEST.json`;
    - `shreks-release-<sha>.tar.gz`;
    - `shreks-release-<sha>.tar.gz.sha256`;
12. preservation of local bundle verification before transfer;
13. preservation of the existing `production-paper` environment;
14. preservation of the existing transport-only SSH secret set;
15. preservation of the existing narrow root-owned release-manager invocation;
16. reusable `Verify production PAPER runtime` support through `workflow_call`;
17. automatic invocation of that verifier only after deploy succeeds;
18. exact deployed source SHA passed into production verification;
19. existing manual deploy and manual verification paths retained as fallbacks.

## Fail-closed behavior

The automatic chain stops without deployment when:

- the upstream release workflow fails;
- the upstream release run did not originate from the canonical automatic release path;
- the source SHA or release tag is malformed;
- the named GitHub Release does not exist;
- release `target_commitish` differs from the resolved source SHA;
- the release is draft or prerelease;
- the release is not immutable;
- the release asset set differs from the exact three expected assets;
- local release-bundle verification fails.

Production verification does not run after a failed deploy.

A failed verifier/discovery run fails the delivery chain and grants no later authority.

## Verification evidence

Intentional RED head:

`3ab98a13df0525cdae8511d24a1ec2fe18c58835`

RED CI run:

`35365969169`

The new delivery contract failed exactly on the missing deploy-chain seam while 3439 Python tests passed and repository safety/ARM64 remained green.

The delivery contract was then tightened before production workflow edits to cover automatic release provenance, immutable-release validation, reusable verification, and chained ordering.

Final feature head:

`65447593549a9231789553ef2aca5b8f946b28bf`

Final feature-head CI run:

`35367499596`

All four canonical gates were green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Independent PR #314 CI run:

`35367803095`

All four canonical gates completed successfully and no review threads remained.

Squash-merged implementation main:

`c55811ac94ae455e0f7508cb478781d7c70a6f52`

Exact merged-main CI run:

`35368098405`

All four canonical gates completed successfully.

Because the implementation commit subject begins `feat:`, the automatic release run `35368357325` correctly skipped. The downstream automatic deploy run `35368379200` also skipped. This proves that merging the implementation alone does not accidentally release or deploy without an explicit seal.

## Production authority granted by this seal

After this docs-only `seal:` commit lands on `main` and its exact main CI is green, this seal authorizes:

1. automatic immutable ARM64 release creation for the exact sealed SHA;
2. automatic protected deployment of that exact immutable release to `production-paper`;
3. automatic production verification of that exact deployed SHA;
4. the existing telemetry-mediated read-only FL9 V2 protected discovery performed by the verifier.

The `production-paper` GitHub Environment remains authoritative. Any configured environment approval, branch restriction, or secret policy is not bypassed by this automation.

Manual deploy and manual verify remain operator fallbacks.

## Authority explicitly not granted

This seal does not authorize:

- a V2 scoring retry;
- a fresh scoring request;
- model fitting;
- champion publication;
- PAPER promotion;
- risk-intent creation;
- transaction construction;
- signing;
- transaction submission;
- wallet/private-key handling;
- LIVE trading.

No discovery result automatically advances into scoring.

## Expected first end-to-end proof

After this seal merges:

1. exact sealed-main CI must pass Repository safety, Python tests, Rust tests, and ARM64 release build;
2. `Build sealed Shreks release` must automatically build the exact sealed SHA;
3. the resulting GitHub Release `shreks-<seal-sha>` must be immutable and contain exactly the three expected assets;
4. `Deploy verified Shreks release` must start automatically from that successful canonical release run;
5. the deploy workflow must independently re-verify the release object before VPS contact;
6. the protected VPS must activate exactly `/opt/shreks/releases/<seal-sha>`;
7. the reusable production verifier must run automatically after deploy success;
8. runtime manifest/process/service identity must bind to the exact sealed SHA;
9. the verifier may exercise protected FL9 discovery;
10. any HOLD result remains HOLD and grants no scoring authority.

## Promotion boundary

`AUTO_PAPER_DELIVERY_IMPLEMENTATION=MAIN_GREEN`

`AUTO_PAPER_DELIVERY_SEAL=PENDING_MERGE`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_ONLY_AFTER_NEW_SEALED_DEPLOY_AND_VERIFY`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
