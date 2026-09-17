# FL9 V2 First-Champion — Runtime Manifest Discovery Seal

**Date:** 2026-09-17  
**Status:** SEAL PR PENDING; DISCOVERY IMPLEMENTATION MAIN GREEN; NEW RELEASE/DEPLOY PENDING; DISCOVERY NOT YET RUN; V2 SCORING NOT YET AUTHORIZED

## Purpose

Seal the verified read-only FL9 V2 runtime-manifest discovery implementation that follows the previously sealed hydration quote-policy HOLD.

The discovery tool exists to answer one narrow production question without weakening host permissions or manufacturing policy authority:

> Does the authenticated active PAPER runtime manifest, or any authenticated manifest preserved inside a verified G8 backup bundle, provide runtime quote/probe authority compatible with the frozen FL9 V2 WSOL cohort?

This seal does not authorize scoring, PAPER promotion, wallet use, transaction signing/submission, or LIVE operation.

## Prior authority state

The previous hydration quote-policy seal established all of the following:

- the frozen accepted FL9 V2 cohort is WSOL-quoted;
- the previously supplied hydration policy was derived from a USDC-quoted runtime manifest;
- a cohort cannot be used to invent or rewrite runtime quote mint, quote decimals, safety-probe identity, raw probe amount, regime policy, safety policy, provider identity, or global-risk state;
- the correct production state is HOLD until an authenticated WSOL-compatible historical runtime manifest is identified;
- protected deployment and production verification must succeed before read-only runtime-policy discovery is allowed.

The previous sealed production release `ef94d4976cbcb066c8b13bb1b4eeb39ed46b09cb` was deployed and production-verified successfully. The verifier's deployment identity did not have read access to protected historical evidence, which is consistent with the existing host permission boundary and is not authority to loosen that boundary.

## Discovery implementation

Implementation PR #305, `feat: discover authenticated FL9 V2 runtime manifests`, added:

- `python/src/shreks_brain/fl9_v2_runtime_manifest_discovery.py`;
- console entry point `shreks-fl9-v2-runtime-manifest-discovery`;
- focused TDD coverage in `python/tests/test_fl9_v2_runtime_manifest_discovery.py`.

The tool is deliberately read-only. It:

1. authenticates the frozen FL9 V2 cohort through the existing cohort artifact reader;
2. requires the accepted cohort to resolve to one single quote mint;
3. stable-reads and canonical-decodes the active `ObserverPaperCampaignRuntimeManifest`;
4. enumerates only real, non-hidden backup directories below the supplied G8 backup root;
5. requires each historical G8 bundle to pass the existing full `verify_backup_bundle` contract before its campaign manifest is consumed;
6. stable-reads the verified campaign-manifest artifact;
7. verifies the G8 bundle again after the read and rejects any change during discovery;
8. requires the G8 manifest's recorded campaign fingerprint to match the canonical runtime-manifest fingerprint;
9. derives each candidate hydration policy only through the existing `build_fast_forecast_context_hydration_policy_from_runtime_manifest` bridge;
10. applies the existing V2 frozen-cohort quote-policy guard without rewriting any policy field;
11. emits deterministic JSON evidence describing authentication, compatibility, exact source provenance, runtime-manifest fingerprint, derived hydration-policy fingerprint, and quote authority.

A malformed/tampered active manifest or invalid/tampered G8 bundle fails closed. An authenticated but quote-incompatible manifest is reported as `REJECTED_QUOTE_POLICY`; it is not repaired.

## Exact provenance correction

Follow-up PR #306, `fix: report exact FL9 V2 manifest provenance`, corrected one operational ambiguity discovered during review.

For a historical G8 candidate:

- `source_path` now names the exact authenticated `artifacts/paper-campaign.json` file whose bytes were decoded;
- `backup_bundle_path` separately names the verified G8 bundle that authenticated those bytes.

For the active manifest:

- `source_path` names the exact active manifest file;
- `backup_bundle_path` is `null`.

This correction changes reporting provenance only. It does not change authentication, policy derivation, compatibility logic, scoring authority, risk authority, filesystem permissions, or runtime behavior.

## TDD and verification evidence — implementation PR #305

Initial RED commit:

`2bac27092decc1afb30df33d386b7278b5483720`

RED CI push run:

`35204472675`

The Python lane failed exactly because `shreks_brain.fl9_v2_runtime_manifest_discovery` did not yet exist. Repository safety remained green and unrelated lanes were unaffected.

Final PR head:

`27a8ef99fe3b6faa341d54ca87cb4fc8fa4705e3`

Exact-head branch CI:

`35206133626`

Exact-head PR CI:

`35206136385`

Both completed with all four canonical gates green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Squash-merged implementation main:

`0a603a6b57871072daa3038b2df3be4e14aa83bb`

Exact merged-main CI:

`35206440887`

completed successfully with all four canonical gates green.

## TDD and verification evidence — provenance PR #306

Intentional RED commit:

`747c897c24200317ca36d304aac8c5fa957a0026`

RED CI push run:

`35206705376`

The Python lane failed exactly on the missing/ambiguous provenance contract:

- active candidates had no `backup_bundle_path` field;
- historical G8 candidates reported the bundle directory rather than the exact authenticated `paper-campaign.json` source path.

That RED run finished with `3402 passed, 2 failed`; Repository safety, Rust tests, and ARM64 release build were green.

Final provenance head:

`31f70b8ec897dbe9457e4f339565558d7f0c54f0`

Exact-head branch CI:

`35206992445`

Exact-head PR CI:

`35207230881`

Both completed with all four canonical gates green.

Squash-merged corrected main:

`659e8f2dc1a3f411b13edeb867897eb7729d2b08`

Exact corrected-main CI:

`35207482258`

completed successfully with all four canonical gates green.

## Authority boundary

The discovery report is evidence, not permission to score.

The authenticated runtime manifest remains authoritative for the manifest-backed hydration fields, including:

- regime quote asset identity;
- safety probe output identity and raw probe amount;
- quote-asset decimals;
- regime policy;
- safety policy;
- quote provider identity;
- global-risk state.

The discovery caller must separately supply the existing FL9-only hydration assumptions required by the canonical bridge:

- hydration-policy version;
- strategy family/families;
- maximum EXIT quote age;
- execution-cost policy version;
- expected round-trip cost basis-point value, or `unknown` only when the already-approved target policy explicitly uses unknown.

The repository intentionally provides no production defaults for these values in this discovery seal. Unit-test/example values are not production authority. They must match the exact already-approved V2 target hydration/economics assumptions. If those inputs cannot be established from existing sealed V2 evidence, the correct state is HOLD and the discovery command must not be run with guessed values.

## Immutable release authorization

After this documentation-only seal PR lands on `main` with a commit subject beginning exactly `seal:`, exact sealed-main CI must pass all four canonical gates.

Only then may the existing release workflow create the immutable ARM64 release for that exact sealed SHA.

The current deployed `ef94d4976cbcb066c8b13bb1b4eeb39ed46b09cb` release does not contain this discovery CLI and must not be patched in place.

The new sealed release must be deployed through the existing protected release workflow and production-verified before the discovery CLI is used against protected production history.

## Production discovery runbook

### Preconditions

Before running discovery, require all of the following:

1. the new immutable release for the exact seal SHA exists and its release bundle verifies;
2. that exact release is deployed through the protected deployment workflow;
3. the production verifier confirms `/opt/shreks/current`, `RELEASE_MANIFEST.json`, and running service working directories bind to that same exact seal SHA;
4. all required PAPER services are healthy with no disqualifying restart/database signatures;
5. the frozen V2 cohort path remains the accepted artifact and has not been regenerated or edited;
6. the exact approved FL9-only hydration/economics inputs listed above have been recovered from existing sealed evidence rather than inferred from unit tests or this document.

Do not loosen ownership or mode bits on `/etc/shreks`, `/var/lib/shreks`, the cohort artifact, or G8 backups to make discovery convenient. Run the read-only command through an already-authorized administrator/trusted host identity that can read those protected paths.

### Protected production inputs

Frozen cohort:

`/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`

Frozen cohort artifact fingerprint:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

Frozen accepted-identity fingerprint:

`75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`

Accepted decisions:

`274334`

Coverage sessions:

`115..122`

Active PAPER runtime manifest:

`/etc/shreks/paper-campaign.json`

G8 backup root:

`/var/lib/shreks/backups`

### Command shape

Set the five non-manifest policy inputs to their exact approved V2 values before invocation. The placeholders below are intentionally not defaults:

```sh
cd /opt/shreks/current

COHORT=/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2
ACTIVE_MANIFEST=/etc/shreks/paper-campaign.json
BACKUP_ROOT=/var/lib/shreks/backups

HYDRATION_POLICY_VERSION='<exact-approved-v2-value>'
STRATEGY_FAMILY='<exact-approved-v2-value>'
MAX_EXIT_QUOTE_AGE_MS='<exact-approved-v2-value>'
EXECUTION_COST_POLICY_VERSION='<exact-approved-v2-value>'
EXPECTED_ROUND_TRIP_COST_BPS='<exact-approved-v2-value-or-explicit-unknown>'

.venv/bin/shreks-fl9-v2-runtime-manifest-discovery \
  --cohort "$COHORT" \
  --active-runtime-manifest "$ACTIVE_MANIFEST" \
  --backup-root "$BACKUP_ROOT" \
  --hydration-policy-version "$HYDRATION_POLICY_VERSION" \
  --strategy-family "$STRATEGY_FAMILY" \
  --max-exit-quote-age-ms "$MAX_EXIT_QUOTE_AGE_MS" \
  --execution-cost-policy-version "$EXECUTION_COST_POLICY_VERSION" \
  --expected-round-trip-cost-bps "$EXPECTED_ROUND_TRIP_COST_BPS"
```

If the approved target uses more than one strategy family, repeat `--strategy-family` once for each exact approved family. Do not silently add or drop families.

### Result interpretation

`status=FAILED`

- hard trust/verification failure;
- stop immediately;
- do not score;
- investigate the failed cohort, active manifest, or G8 verification boundary.

`status=HOLD_NO_COMPATIBLE`

- all consumed authority authenticated, but none produced a hydration policy compatible with the frozen cohort;
- preserve the report as evidence;
- remain HOLD;
- do not edit USDC manifests into WSOL manifests;
- do not score.

`status=FOUND_COMPATIBLE`

- at least one authenticated runtime manifest produced a canonical hydration policy accepted by the V2 quote-policy guard;
- preserve the exact candidate `source_path`, `backup_bundle_path`, `runtime_manifest_fingerprint_sha256`, and `hydration_policy_fingerprint_sha256`;
- this still does not authorize scoring.

If more than one compatible candidate is returned, discovery itself does not choose a preferred authority. A future proof/request must bind one exact authenticated manifest and its fingerprints explicitly; do not make an ad hoc freshness or profitability selection.

## Post-discovery continuation gate

Only after `FOUND_COMPATIBLE` and explicit binding of one exact authenticated WSOL-compatible runtime manifest may the project prepare a fresh release-bound V2 proof/request through canonical repository tooling.

Before any scoring attempt, the project must still:

1. bind the exact sealed release SHA;
2. bind the exact frozen cohort artifact/fingerprint;
3. bind the exact authenticated runtime-manifest source/fingerprint;
4. bind the exact derived hydration-policy fingerprint;
5. strictly read back/authenticate the resulting request;
6. re-establish quiescence;
7. re-establish holder/evidence completeness gates;
8. re-establish database sentinel/consistency gates;
9. require destination absence/non-overwrite gates;
10. re-establish economics/cost-policy gates;
11. require all existing bounded-host proof gates before scoring.

No stale request reuse, direct release-directory patch, cohort-derived runtime-policy synthesis, or hand-edited manifest substitutes for these gates.

## Promotion boundary

This seal authorizes only:

- immutable release creation for the exact seal SHA after green CI;
- protected deployment and production verification of that exact release;
- read-only runtime-manifest discovery/authentication using exact approved V2 non-manifest inputs.

It does not authorize a V2 scoring retry by itself.

`DISCOVERY_IMPLEMENTATION=MAIN_GREEN`

`SEALED_RELEASE=PENDING`

`PRODUCTION_DEPLOY=REQUIRED_FOR_NEW_SEAL`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_ONLY_AFTER_NEW_SEALED_DEPLOY_AND_VERIFY`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`MISSING_VALID_WSOL_RUNTIME_MANIFEST=HOLD`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
