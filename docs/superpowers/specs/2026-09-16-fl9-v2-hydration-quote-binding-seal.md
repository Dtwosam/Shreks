# FL9 V2 First-Champion — Hydration Quote-Policy Binding Seal

**Date:** 2026-09-16  
**Status:** SEAL PR PENDING; IMPLEMENTATION MAIN GREEN; PRODUCTION SCORING NOT YET AUTHORIZED

## Purpose

Bind the verified FL9 V2 hydration quote-policy fail-closed correction to a release-authorized seal commit without manufacturing a hydration policy from frozen cohort identity and without changing the generic hydrator, PAPER runtime-policy bridge, frozen cohort, evaluation policy, economics policy, PAPER promotion state, or LIVE state.

This seal also records the production input boundary exposed by the correction: a future V2 historical-context run requires an authenticated runtime manifest whose quote/probe identity is already compatible with the frozen cohort. For the current frozen cohort that means WSOL authority. If no such authenticated manifest exists, the correct production state is HOLD.

## Production semantic HOLD

The frozen accepted FL9 V2 cohort is WSOL-quoted. The previously supplied hydration policy was derived from a USDC-quoted runtime manifest.

That policy was internally authenticated, but it was semantically incompatible with the frozen cohort: historical regime lookup and EXIT quote hydration would have used quote/probe identity from the USDC runtime authority while the accepted cohort identities were WSOL-quoted.

Rewriting the policy's mint, decimals, or raw probe amount from cohort identity would not be authentication. It would manufacture a new policy that no sealed runtime manifest authorized.

The production HOLD therefore remains valid evidence. It authorizes neither a hand-edited policy nor a scoring retry.

## Corrective implementation

Implementation PR #303, `fix: bind FL9 V2 hydration quote policy to frozen cohort`, adds a V2-only compatibility gate while leaving the generic hydrator and runtime-policy bridge unchanged.

The correction:

- requires the accepted V2 cohort to resolve to one single non-empty quote mint;
- requires `hydration_policy.regime_read_policy.quote_asset_mint` to equal that frozen cohort quote mint;
- requires `hydration_policy.safety_probe_identity.output_mint` to equal that same frozen cohort quote mint;
- performs the compatibility check during canonical V2 host-request preparation before publication;
- repeats the same compatibility check in the bounded production host runner before bundle construction;
- never rewrites quote mint, quote decimals, safety probe identity, or raw probe amount;
- preserves the existing hydration-policy fingerprint authentication and all existing release/cohort/quiescence/database/economics/evidence gates.

The generic manifest bridge remains the canonical conversion boundary. It authenticates the complete `ObserverPaperCampaignRuntimeManifest` and copies the runtime authority's regime-read policy, regime policy, safety policy, safety probe identity, global-risk state, quote provider, and quote-asset decimals into the hydration policy. It does not infer those fields from a cohort.

## TDD and verification evidence

The branch began with an intentional RED commit:

`15687861288ffb5fb1152cee93d9fb1b0edd45ce`

CI run:

`35151822913`

failed in the Python lane because the new V2 hydration-policy authority module did not yet exist. Repository safety, Rust tests, and ARM64 release build remained green.

Final implementation PR head:

`3863ecca4d2be1099289d97a8959f1ebca301056`

Exact-head PR CI:

`35153625912`

completed successfully with all four canonical gates green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Squash-merged implementation main:

`eaac32fe930799ebca9dbbf6289542448535e70a`

Exact merged-main push CI:

`35155279588`

completed successfully with all four canonical main gates green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The automatic release workflow observed that main CI but correctly skipped release creation because the implementation main subject begins with `fix:` rather than `seal:`.

## Hydration-policy authority boundary

A frozen cohort is evidence of decision identity. It is not authority to invent the runtime policy under which historical context is hydrated.

For V2 historical hydration, the authenticated runtime manifest is authoritative for the fields that determine historical context lookup and execution-safety interpretation, including:

- regime quote asset identity;
- safety probe output identity;
- quote-asset decimals;
- safety probe identity and its raw amount;
- regime and safety policy;
- quote provider identity;
- global-risk state.

The V2 cohort compatibility guard is therefore a validator only. It can reject an authenticated policy whose quote identity conflicts with the frozen cohort, but it cannot repair or synthesize that policy.

For the current frozen WSOL cohort, the next acceptable production input is an authenticated historical WSOL `ObserverPaperCampaignRuntimeManifest` whose canonical runtime-policy bridge yields a hydration policy accepted by the V2 compatibility guard.

If no authenticated WSOL runtime manifest exists, production remains HOLD. Creating one by copying a USDC manifest and editing mint/decimals/raw probe fields is explicitly outside authority.

## Immutable release authorization

After this documentation-only seal PR lands on `main` with a subject beginning exactly `seal:`, the repository release workflow may build a new immutable ARM64 release for that exact sealed SHA, but only after exact sealed-main CI passes successfully.

This seal introduces no runtime implementation change beyond the already verified `eaac32fe930799ebca9dbbf6289542448535e70a` implementation tree plus this documentary binding.

The currently deployed release remains immutable and must not be patched in place.

## Production continuation boundary

After the sealed release is built, verified, and deployed, the next VPS action is **read-only authority discovery**, not another V2 scoring attempt.

The production sequence is strictly:

1. merge this seal PR with a `seal:` subject;
2. require exact sealed-main CI to pass all four canonical gates;
3. require the automatic immutable ARM64 release for that exact sealed SHA to complete and its release assets to verify;
4. deploy that exact release through the protected deployment path;
5. verify `/opt/shreks/current`, release manifest, and runtime process identity all bind to the sealed SHA;
6. perform read-only discovery of candidate historical PAPER runtime manifests on the production host;
7. for each candidate, authenticate it through the canonical runtime-manifest decoder/encoder contract before deriving any hydration policy;
8. accept only a candidate whose authenticated quote/probe authority is WSOL-compatible and whose canonical bridge output passes the V2 cohort compatibility guard;
9. if no such candidate exists, record HOLD and stop;
10. only after a valid authenticated WSOL runtime authority is identified, prepare a fresh release-bound V2 proof/request through canonical repository-controlled tooling;
11. strictly read back and authenticate the request, then re-establish all quiescence, holder, database-sentinel, destination-absence, economics, and evidence gates before any scoring attempt.

No hand-edited mint, decimals, raw probe amount, stale request reuse, direct release-directory patch, or cohort-derived policy synthesis substitutes for these gates.

## Promotion boundary

This seal authorizes only release creation and the subsequent read-only discovery/authentication step after protected deployment.

It does not by itself authorize a V2 scoring retry.

A future scoring retry requires both the sealed/deployed code authority and a separately authenticated WSOL historical runtime-policy authority.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_AFTER_SEALED_DEPLOYMENT`

`MISSING_VALID_WSOL_RUNTIME_MANIFEST=HOLD`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
