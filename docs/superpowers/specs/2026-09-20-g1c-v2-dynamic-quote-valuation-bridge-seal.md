# G1C Runtime Manifest V2 Same-Row Dynamic Quote Valuation — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `69c4f85170797dff7f7e3c92ecdcb024e84befd1`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 CODE CAPABILITY ONLY; NO V2 MANIFEST ACTIVATION; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the fail-closed G1C PAPER execution bridge for authenticated runtime-manifest v2 quote valuation.

This implementation allows an authenticated `g1c-paper-campaign-runtime-manifest-v2` using the already-sealed `exact_market_ratio` quote-USD valuation policy to execute PAPER cycles without trusting a static volatile-asset USD value.

The dynamic quote-asset USD rate is derived only from the exact current persisted market row already selected for that PAPER cycle.

This seal authorizes deployment of the code capability only.

It does not authorize authoring, installing, activating, or rotating production to a v2/WSOL campaign manifest.

The currently active production v1/USDC campaign remains the production runtime authority unless a later separately sealed transition explicitly changes it.

## Background

Production FL9 V2 discovery has already established:

- frozen V2 cohort quote mint = WSOL;
- authenticated active PAPER campaign quote mint = USDC;
- recent durable PAPER quote evidence = USDC;
- no compatible authenticated historical runtime manifest;
- trusted terminal status = `HOLD_NO_COMPATIBLE`.

The repository therefore correctly remains HOLD.

A hand-edited WSOL v1 manifest is not acceptable because legacy v1 PAPER quote economics use the manifest-fixed `quote_asset.usd_per_token`.

That static model is appropriate for the preserved USDC campaign but is not adequate authority for a volatile WSOL quote asset.

Two prior merged slices established the prerequisites:

1. point-in-time quote-asset USD evidence from exact persisted market rows;
2. an authenticatable G1C runtime-manifest v2 carrying explicit `exact_market_ratio` quote-USD valuation authority.

The present implementation connects those two sealed contracts while preserving v1 behavior.

## Canonical valuation authority

For runtime-manifest v2 with:

`quote_usd_valuation_policy.mode = exact_market_ratio`

the PAPER runtime derives the quote-token USD rate from one exact persisted market row:

`quote_asset_usd_per_token = price_usd / price_native`

The derivation is allowed only when:

- the persisted native price exists;
- the persisted native price is positive and finite;
- the persisted USD price exists;
- the persisted USD price is positive and finite;
- source matches the cycle's current market source;
- venue matches the cycle's current market venue;
- candidate identity matches;
- base mint matches the cycle candidate mint;
- quote mint matches the authenticated manifest quote asset;
- freshness remains inside the sealed current-market age bound;
- the exact persisted market row id equals the current market row id already selected by the cycle.

No fallback to another row is allowed.

No lookup of a more convenient older exact pair is allowed when the cycle's current market row has different quote identity.

No current external price is substituted for historical point-in-time evidence.

## Exact-row binding

The implementation extends:

`ObserverMarketStore.quote_asset_usd_evidence(...)`

with optional:

`expected_market_row_id`

When supplied, the derived evidence must resolve to that exact row.

The PAPER valuation resolver supplies:

`expected_market_row_id = window.current.row_id`

This binds valuation economics and cycle market features to the same persisted observation.

A mismatch fails closed.

## Quote construction

The existing PAPER quote builders preserve their legacy default:

- when no explicit dynamic USD rate is provided, use `quote_asset.usd_per_token`.

They now additionally accept an explicit:

`quote_asset_usd_per_token`

The explicit value must be:

- numeric;
- not boolean;
- finite;
- strictly positive.

For v2 `exact_market_ratio`, the assembler supplies the value derived from the exact-row evidence.

For v1, no explicit dynamic value is supplied and the legacy static path remains unchanged.

## Route-unavailable semantics

The implementation does not invent economics for unavailable routes.

Dynamic valuation evidence is required only when executable quote economics are actually needed.

A route-unavailable PAPER quote remains route-unavailable without manufacturing a dynamic execution value.

Missing reference-price evidence continues to defer the quote according to existing fail-closed behavior.

## Assembly propagation

`assemble_observer_paper_cycle(...)` now accepts an optional authenticated valuation mode.

Only the canonical `exact_market_ratio` dynamic mode is accepted.

The aggregate campaign coordinator propagates that same mode to every candidate component.

`ObserverPaperCampaignCoordinatorRunner` stores the validated mode and passes it unchanged on every cycle.

The operator-control wrapper preserves the same mode while applying existing halt/kill semantics.

Operator controls cannot silently downgrade a v2 campaign to v1 static valuation.

## Runtime authority

The runtime no longer rejects every authenticated v2 manifest categorically.

Instead, bootstrap derives the valuation mode solely from:

`manifest.quote_usd_valuation_policy`

There is no environment-variable override, host-config override, dashboard control, or command-line flag that can invent or replace that manifest authority.

For v1:

- manifest valuation policy is absent;
- runtime passes no dynamic mode;
- the legacy static quote-value path remains active.

For v2:

- the authenticated manifest policy supplies `exact_market_ratio`;
- the runtime passes that exact mode through the coordinator;
- dynamic quote valuation uses same-row evidence.

## Audit provenance

`ObserverPaperCycleAudit` now records:

- `quote_usd_valuation_mode`;
- `quote_usd_valuation_market_row_id`;
- `quote_usd_valuation_evidence_fingerprint`.

For v1:

- mode = `manifest_fixed`;
- dynamic market row id = null;
- dynamic evidence fingerprint = null.

For v2 dynamic execution:

- mode = `exact_market_ratio`;
- market row id identifies the exact persisted observation;
- evidence fingerprint commits to the derived quote-USD evidence.

The row id and fingerprint must co-exist.

Manifest-fixed valuation cannot carry dynamic evidence fields.

## Component fingerprinting

The legacy v1 component PAPER cycle fingerprint remains:

`fingerprint(cycle)`

This preserves the existing v1 fingerprint path.

For v2 dynamic execution, the component fingerprint additionally commits to:

- the assembled PAPER cycle;
- the canonical valuation mode;
- the exact quote-USD valuation evidence.

The aggregate campaign audit already commits to component fingerprints, so v2 valuation provenance flows into the aggregate campaign evidence without changing the aggregate data model.

## Fail-closed conditions

V2 dynamic PAPER assembly fails closed when any required valuation condition is invalid, including:

- unsupported valuation mode;
- missing exact persisted market columns;
- missing native price;
- malformed native price;
- non-positive native price;
- missing USD price;
- non-positive USD price;
- stale exact market evidence;
- source mismatch;
- venue mismatch;
- candidate mismatch;
- base-mint mismatch;
- quote-mint mismatch;
- current market row mismatch;
- non-finite derived USD rate;
- non-positive derived USD rate;
- altered valuation provenance.

The implementation does not fall back to manifest-fixed economics for a v2 dynamic campaign when dynamic valuation fails.

## V1 compatibility

The active production campaign remains a v1 USDC manifest.

This implementation intentionally preserves:

- v1 canonical runtime-manifest bytes;
- v1 manifest fingerprint semantics;
- v1 static `quote_asset.usd_per_token` behavior;
- v1 cycle fingerprint path;
- v1 runtime configuration;
- v1 production campaign identity;
- existing PAPER checkpoint attribution;
- existing E11 evidence format;
- existing G7 operator controls;
- existing FL9 discovery authority.

Deploying this code must therefore leave current production PAPER behavior unchanged while adding a dormant, authenticated v2 execution capability.

## TDD evidence

Canonical clean RED head:

`5c7cb6f0a208117cd2a33cc744dda812a098754a`

Canonical RED CI:

`35534431429`

Result:

- Python: exactly 10 failures, 3491 passed, 1 warning;
- failures were confined to the intentionally absent bridge surfaces:
  - explicit dynamic quote-USD rate support;
  - exact expected-market-row binding;
  - v2 assembly valuation mode;
  - v2 audit provenance;
  - authenticated v2 runtime execution;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Final implementation head before merge:

`74d5b9ce152833200286390781b9ae22d679e547`

GREEN push CI:

`35534311590`

Independent GREEN PR CI:

`35534312533`

Result:

- Python: 3501 passed, 1 warning;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`69c4f85170797dff7f7e3c92ecdcb024e84befd1`

Exact merged-main CI:

`35534811453`

Result:

- Python: 3501 passed, 1 warning;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Changed implementation surfaces

The implementation is bounded to:

- observer-market exact quote-USD evidence row binding;
- PAPER quote construction with optional explicit dynamic quote USD rate;
- G1C quote-valuation resolver;
- observer PAPER cycle assembly and audit provenance;
- aggregate campaign propagation;
- operator-control propagation;
- authenticated runtime-manifest v2 execution-mode propagation;
- tests and exact-market fixtures.

It does not add provider credentials, signing code, submission code, registry promotion, or LIVE execution authority.

## Authority boundary

This implementation and seal do not modify or authorize:

- production campaign-manifest bytes;
- creation of a production WSOL manifest;
- installation or activation of a v2 manifest;
- campaign rotation;
- frozen cohort bytes;
- preserved V2 request bytes;
- preserved hydration-policy bytes;
- protected evidence ownership, modes, or ACLs;
- sudoers;
- systemd privilege boundaries;
- deploy account privileges;
- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing;
- transaction submission;
- LIVE trading.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment of this code capability;
3. automatic production verification;
4. confirmation that the existing v1 USDC campaign remains healthy and unchanged;
5. confirmation that FL9 discovery remains bound to authenticated runtime-manifest authority.

This seal does not authorize a v2/WSOL manifest transition.

## Expected production proof

The automatic release/deploy chain must demonstrate:

`seal merge -> exact sealed-main CI -> immutable release -> protected PAPER deploy -> current v1 campaign activation -> protected FL9 discovery -> reusable production verification`

Production verification must show:

- exact active release SHA equals the sealed SHA;
- exact release-manifest source SHA equals the sealed SHA;
- `shreks-observe.service` active/running with zero restarts;
- `shreks-paper-evidence.service` active/running with zero restarts;
- `shreks-paper-campaign.service` active/running with zero restarts;
- no unexpected PAPER restart/failure signature;
- trusted FL9 discovery result source;
- existing active campaign remains the authenticated v1 USDC authority;
- production does not begin executing any v2 manifest merely because support code is present;
- no scoring request is created by this deployment.

Given the current production authority, the expected FL9 semantic result remains:

`HOLD_NO_COMPATIBLE`

unless a separately authenticated compatible manifest already exists by the time verification runs.

If production unexpectedly reports `FOUND_COMPATIBLE`, that result must be treated as a discovery fact requiring authority inspection; it does not authorize scoring.

## Next separate authority slice

After successful deployment of this code capability, any move toward a WSOL PAPER runtime requires a separate slice for a genuine new-run v2 manifest.

That future slice must not hand-edit the active v1 USDC manifest.

It must establish an authenticated candidate/new-run manifest, assess it read-only against the frozen V2 cohort and preserved request authority, and separately authorize any installation/rotation.

## Promotion boundary

`G1C_V2_QUOTE_VALUATION_BRIDGE=SEALED_CODE_CAPABILITY`

`PRODUCTION_V2_MANIFEST=NOT_AUTHORIZED`

`PRODUCTION_V1_USDC_CAMPAIGN=UNCHANGED`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
