# Fast PAPER Champion Bootstrap Authority — Release Seal

**Date:** 2026-09-29  
**Base main SHA:** `2e71bbadd1f88812bc3ad0ba121b5ab14c08dc03`  
**Status:** SEAL PENDING; ONE EXPLICIT FORECAST-CHAMPION BOOTSTRAP AUTHORIZED ONLY AFTER EXACT SEALED RELEASE DEPLOY/VERIFY; PAPER CUTOVER, AUTOMATIC PROMOTION, SIGNING/SUBMISSION, AND LIVE REMAIN DISABLED

## Purpose

Close one production commissioning gap discovered while preparing the learned Fast PAPER shadow runtime.

The repository already contains the score-free Fast Lane runtime integration, shadow supervisor,
restart-safe PAPER execution, promotion evidence, protected cutover tooling, and the original
canonical forecast-champion evidence producer:

`shreks-fast-first-champion-run`.

However, physical inspection of the protected production host proved that no canonical artifact with
schema:

`shreks.fast_lane_forecast_champion`

exists under the protected Shreks evidence roots or the active immutable release. The dormant Fast
PAPER shadow unit is installed, but the protected Fast authority bundle cannot be truthfully authored
without an exact immutable forecast champion.

This seal authorizes exactly one bounded bootstrap of that missing forecast champion through the
already-sealed first-champion evidence chain.

It does not authorize the obsolete FL9 V2 scoring/control path.

## Architecture boundary

The approved decision architecture remains:

`event/state -> future-path forecasts -> execution economics -> expected net value -> BUY/SKIP/HOLD/REDUCE/SELL -> independent risk -> PAPER execution`.

The bootstrap produces only the immutable forecast artifact consumed by that score-free path.

It must not create or restore:

- token-quality scoring authority;
- total-score thresholds;
- score-backed candidate approval;
- score-backed PAPER promotion;
- score-backed LIVE promotion;
- legacy `score_candidate(...)` or `decide_entry(...)` runtime authority.

`SCORING_CONTROL_PATH=FORBIDDEN` remains unchanged.

## Historical V2 failure is evidence only

The preserved 2026-09-16 FL9 V2 attempt failed closed during context hydration with:

`decision quote mint does not match hydration quote policy`.

That request and hydration policy are bound to historical release
`0ff91c93a2534f77fb3dffb555a26b1401a0acc8` and must not be relabeled, edited, or reused as
current bootstrap authority.

The V2 scorer remains historical evidence only. This seal does not authorize a V2 scoring retry.

## Existing canonical producer

The only champion-producing execution path authorized by this seal is the existing release-local
command:

`shreks-fast-first-champion-run --request <canonical-current-release-request.json>`.

That command already composes the sealed proof-workspace, deterministic evidence-plan,
runtime-backed hydration policy/context, chronological TEST evaluation, immutable champion codec,
and atomic first-champion publication.

No new model family, target set, fold search, scoring layer, or promotion rule is introduced.

## Exact-release prerequisite

After this docs-only seal lands on `main`, exact sealed-main CI and immutable release creation must
succeed before the bootstrap may run.

The trusted-admin ceremony must pin one exact production-verified release:

```text
EXPECTED_RELEASE_SHA=<exact deployed sealed SHA>
CURRENT_RELEASE=$(readlink -f /opt/shreks/current)
CURRENT_SHA=$(basename "$CURRENT_RELEASE")
CURRENT_SHA == EXPECTED_RELEASE_SHA
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

The release must remain unchanged through proof preparation, request creation, champion execution,
and final strict readback.

No path may select a release by freshness.

## Fresh bootstrap inputs

The bootstrap must use fresh, current-release-bound canonical inputs.

Required inputs are:

1. one new `shreks.fast_proof_workspace` created from the authoritative observer database through
   the exact release-local `shreks-fast-proof-workspace`;
2. one new canonical runtime-backed hydration policy created through
   `shreks-fast-context-policy-from-runtime` from the exact active legacy PAPER runtime manifest;
3. one authenticated training-economics overlay accepted by the existing first-champion request
   writer;
4. one authenticated training execution-cost policy accepted by the same writer;
5. one new canonical host request written through `shreks-fast-first-champion-request`;
6. one new absent host-run destination.

Every non-derivable evaluation/evidence parameter required by the existing writer remains explicit.
This seal supplies no hidden numeric defaults.

Historical proof workspaces or host requests whose release-source SHA differs from the exact active
sealed release may not be reused as current authority.

## One-attempt authority

A trusted administrator may execute exactly one current-release champion bootstrap attempt after all
fresh inputs authenticate.

Authority is consumed when `shreks-fast-first-champion-run` is invoked.

A successful result must contain a strictly readable immutable host-run artifact whose nested
`champion.json` authenticates as:

`schema_name=shreks.fast_lane_forecast_champion`.

The result must preserve at least:

- exact release source SHA;
- host-request fingerprint;
- proof-workspace fingerprint;
- hydration-policy fingerprint;
- training-bundle fingerprint;
- chronological plan fingerprint;
- champion version;
- champion fingerprint;
- canonical champion-file SHA-256;
- immutable host-run artifact fingerprint.

If execution fails, this seal does not silently authorize a retry. Preserve the exact fail-closed
evidence and review a separate retry decision.

## Post-success boundary

A successful champion bootstrap authorizes only champion inspection and later construction of the
already-required Fast PAPER shadow authority bundle.

It does not itself authorize:

- installing Fast PAPER authority files under `/etc/shreks`;
- daemon reload;
- starting the detached Fast shadow service;
- replacing legacy PAPER authority;
- automatic champion promotion;
- authoritative Fast PAPER mutation;
- signing or submission;
- LIVE.

The separately sealed shadow host-preparation, physical commissioning, FL11 evidence, promotion,
baseline, and physical cutover gates remain mandatory.

## Automatic delivery boundary

This docs-only seal may use the existing sealed release pipeline:

`seal merge -> exact-main CI -> immutable release -> protected PAPER deploy/verify`.

Automatic deployment must not execute champion fitting or champion publication.

The bootstrap remains an explicit trusted-admin evidence action after the exact new release has been
deployed and production-verified.

## Failure handling

The bootstrap must fail closed for any of the following:

- active release drift;
- release-manifest mismatch;
- stale proof workspace;
- stale or incompatible hydration policy;
- training-economics authentication failure;
- training execution-cost policy authentication failure;
- observer database instability rejected by the sealed readers;
- evidence-plan insufficiency;
- chronological TEST evidence failure;
- existing request/host-run destination;
- staging residue;
- champion strict-read/fingerprint failure.

Failure creates no PAPER or LIVE authority.

## Explicit authority state

Before a successful one-attempt bootstrap:

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_AUTHORITY=SEALED_ONE_EXPLICIT_ATTEMPT_AFTER_DEPLOY
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

After a successful strict-read bootstrap, only the first field may advance to:

`FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=AUTHENTICATED_IMMUTABLE_ARTIFACT`.

All other authority boundaries remain unchanged until their separately sealed ceremonies complete.

## Next slice after successful bootstrap

After one authentic forecast champion physically exists, construct the initial Fast PAPER shadow
authority candidate bundle using that exact champion plus the exact release-local decision and
feature-feed binaries.

That later slice must still pass:

- runtime-manifest canonical binding;
- service/execution/buy-writer policy cross-binding;
- protected authority preflight/install;
- protected env install;
- service-identity state provisioning;
- host preflight;
- detached physical shadow commissioning.

Do not skip directly from champion publication to production PAPER cutover.
