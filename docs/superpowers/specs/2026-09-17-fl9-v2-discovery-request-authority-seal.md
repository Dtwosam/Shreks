# FL9 V2 Runtime-Manifest Discovery — Prior-Request Authority Seal

**Date:** 2026-09-17  
**Implementation main SHA:** `8e521a07d54235b0da985d08d70e6c5c52278d37`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; READ-ONLY DISCOVERY ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified FL9 V2 runtime-manifest discovery improvement that removes manual re-entry of the five hydration assumptions intentionally absent from the PAPER runtime manifest.

A preserved canonical V2 first-champion host request may be used only as historical evidence authority for the exact hydration-policy fingerprint that request previously bound. The request is not reused for scoring and does not authorize publication of any new champion evidence.

All runtime quote/regime/safety/provider/global-risk authority continues to come only from authenticated candidate PAPER runtime manifests through the existing canonical runtime-manifest bridge.

## Implemented authority chain

Merged PR #308, `fix: source FL9 V2 discovery assumptions from authenticated request`, adds a second fail-closed discovery authority mode.

The request-authority path:

1. stable-reads an existing real V2 host-request file;
2. strict-decodes it with `decode_fast_first_champion_v2_host_request`;
3. authenticates the current frozen V2 cohort and requires its artifact fingerprint to equal the request's expected cohort fingerprint;
4. resolves the hydration-policy path already bound by that canonical request;
5. stable-reads the referenced existing real hydration-policy file;
6. strict-decodes it with `decode_fast_forecast_context_hydration_policy`;
7. recomputes the policy fingerprint and requires exact equality with `request.expected_hydration_policy_fingerprint_sha256`;
8. extracts only these five non-manifest assumptions:
   - hydration-policy version;
   - strategy family/families;
   - maximum accepted EXIT quote age;
   - execution-cost-policy version;
   - expected round-trip cost bps, preserving unknown as `null`;
9. delegates candidate evaluation to the already-sealed runtime-manifest discovery path;
10. records canonical request/policy provenance in `non_manifest_input_authority`.

The prior hydration policy's runtime-derived fields are deliberately discarded. Its quote mint, quote decimals, regime policy, safety policy, safety probe identity, quote provider, and global-risk state are not reused for candidate construction.

## CLI authority modes

The discovery CLI now supports two mutually exclusive modes:

- `--v2-host-request-authority <path>` with none of the five explicit non-manifest flags;
- the existing explicit-input mode with all five values supplied.

Mixing modes, supplying partial explicit authority, a non-canonical/tampered request, a mismatched frozen-cohort fingerprint, a missing/symlinked/changing policy file, a non-canonical/tampered policy, or a policy fingerprint mismatch fails closed before candidate runtime-manifest discovery is trusted.

The stale request remains historical evidence only. It must never be executed, republished, rewritten, or treated as a request bound to a newer release.

## TDD and verification evidence

Intentional RED head:

`27528907978b8e7ef75c945bc96096535e8c9559`

RED CI run:

`35216886173`

Python failed on the absent request-authority resolver while Repository safety, Rust tests, and ARM64 release build remained green.

Final PR head:

`d94acd1b5b2d04f8a4ba91b41f6cfd5a13c72d8e`

Final PR CI run:

`35217499238`

Result:

- Python: SUCCESS (`3409 passed`);
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

A first GREEN attempt exposed only a synthetic test-fixture mismatch against the intentionally frozen physical cohort fingerprint. The production equality check was preserved; the fixture was corrected to bind the synthetic cohort to the canonical request identity.

Squash-merged main:

`8e521a07d54235b0da985d08d70e6c5c52278d37`

Exact merged-main CI run:

`35217793876`

All four canonical gates completed successfully:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The automatic release workflow correctly skipped the implementation commit because its subject is `fix:`, not `seal:`.

## Existing frozen production authority

The discovery remains bound to the previously accepted physical FL9 V2 cohort:

`/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`

Frozen cohort artifact fingerprint:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

Frozen accepted-identity fingerprint:

`75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`

The currently deployed sealed release `47332667144c40ff37dc4e05fb71ce32374d7d51` was production-deployed and verified successfully before this implementation merged. It does not contain the request-authority improvement and must not be patched in place.

## Immutable release and deployment gate

After this documentation-only seal lands on `main` with a commit subject beginning `seal:`, exact sealed-main CI must pass Repository safety, Python, Rust, and ARM64 release build.

Only after that green CI may the automatic release workflow create immutable release `shreks-<seal-sha>`.

That exact release must then be deployed through the existing protected `Deploy verified Shreks release` workflow and checked through `Verify production PAPER runtime` before the request-authority discovery mode is used against protected production history.

Do not broaden the `shreks-deploy` account's permissions. Protected `/etc/shreks` and `/var/lib/shreks` history remains readable only through an already-authorized administrator/trusted `shreks` host identity.

## Production discovery continuation

After sealed deploy and production verification, locate one preserved canonical V2 host-request file from the existing protected FL9 evidence chain. Do not invent a path and do not synthesize a request.

The request must strict-decode and its frozen cohort binding must equal the accepted physical cohort fingerprint above. The hydration-policy path embedded in that request must still exist as a real file, strict-decode canonically, and recompute to the exact fingerprint carried by the request.

Then run the release-local discovery command in request-authority mode against:

- the exact frozen cohort artifact;
- `/etc/shreks/paper-campaign.json`;
- `/var/lib/shreks/backups`;
- the exact preserved canonical V2 host-request authority path.

Command shape:

```sh
cd /opt/shreks/current

.venv/bin/shreks-fl9-v2-runtime-manifest-discovery \
  --cohort /var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2 \
  --active-runtime-manifest /etc/shreks/paper-campaign.json \
  --backup-root /var/lib/shreks/backups \
  --v2-host-request-authority '<exact-preserved-canonical-v2-request-path>'
```

The placeholder is not a default. If no preserved canonical request satisfying the authority chain can be established, remain HOLD.

## Result boundary

`status=FAILED` means a trust/authentication failure. Stop and investigate; do not score.

`status=HOLD_NO_COMPATIBLE` means consumed authority authenticated but no candidate runtime manifest produced a hydration policy compatible with the frozen cohort. Preserve the report and remain HOLD.

`status=FOUND_COMPATIBLE` means at least one authenticated runtime manifest produced a canonical hydration policy accepted by the V2 quote-policy guard. Preserve exact candidate source path, backup bundle provenance, runtime-manifest fingerprint, derived hydration-policy fingerprint, and `non_manifest_input_authority` provenance.

Even `FOUND_COMPATIBLE` does not authorize scoring.

## Post-discovery gate before any V2 scoring retry

Only after one exact authenticated WSOL-compatible runtime manifest is explicitly bound may a fresh release-bound proof/request be prepared through canonical repository tooling.

Before scoring, all existing gates must be re-established, including:

- exact sealed release identity;
- exact frozen cohort artifact/fingerprint;
- exact authenticated runtime-manifest source/fingerprint;
- exact derived hydration-policy fingerprint;
- fresh canonical request publication and strict readback;
- quiescence;
- holder/evidence completeness;
- database sentinel/consistency;
- destination absence/non-overwrite;
- training-economics and execution-cost-policy authentication;
- bounded-host evidence integrity checks.

No stale-request reuse, direct release patch, cohort-derived runtime-policy synthesis, or hand-edited runtime manifest substitutes for those gates.

## Promotion boundary

This seal authorizes only:

- immutable release creation for the exact seal SHA after green CI;
- protected deployment and production verification of that exact release;
- read-only request-authority recovery and runtime-manifest discovery.

It does not authorize model fitting, a V2 scoring retry, champion evidence publication, PAPER promotion, risk-intent creation, signing/submission, or LIVE trading.

`REQUEST_AUTHORITY_IMPLEMENTATION=MAIN_GREEN`

`SEALED_RELEASE=PENDING`

`PRODUCTION_DEPLOY=REQUIRED_FOR_NEW_SEAL`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_ONLY_AFTER_NEW_SEALED_DEPLOY_AND_VERIFY`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
