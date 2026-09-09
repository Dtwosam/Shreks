# FL9 V2 First Champion — Lifecycle Canonicalization Code Seal

**Date:** 2026-09-09  
**Implementation main SHA:** `fa675bd6b9cbb23ac9bd526576f758767905c050`  
**Status:** SEALED FOR NEW IMMUTABLE RELEASE; PHYSICAL V2 CHAMPION EVIDENCE NOT YET CREATED

## Supersedes the prior physical-attempt release

The deployed immutable release:

`shreks-561da94de1e2b17e337bbab37e29cd4fe01ffa3b`

is operationally superseded for the next physical FL9 V2 first-champion attempt.

That release correctly fixed the production-database copy problem, but its sealed FL8.1 feature exporter exposed a second fail-closed production blocker while the paper runtime was deliberately quiesced.

No V2 proof workspace or champion evidence artifact was published by the failed attempt.

## Production blocker evidence

The sealed exporter failed with:

`training lifecycle replay failed: fast-lane lifecycle stream has conflicting events at detection time 1788271966968`

Production read-only diagnostics proved exactly two verified `pump_graduation` lifecycle rows at that detection time for mint:

`9nR2fjDsbSpQPcWmK8zz1HhKA1hQ7Zj7Gvb5YoEppump`

The rows agreed exactly on:

- lifecycle kind: `pump_graduation`;
- provider: `solana_public`;
- mint and WSOL quote mint;
- Pump.fun bonding-curve -> PumpSwap transition;
- pool: `BDPbm7JE9jHKMVc8Wr8vhttpHcngtEj4VBRRKa7aRwqi`;
- slot: `443443146`;
- detection time: `1788271966968`;
- occurrence time: `1788271965000`.

They differed only in durable transaction signature.

The mint could not be discarded as irrelevant history: the already-sealed physical V2 cohort contains 2,768 accepted decisions for it:

- training: 2,761;
- validation: 6;
- test: 1.

The physical cohort fingerprint remained:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

PAPER was restored after the failed proof attempt and all three runtime services returned active on the deployed sealed release with zero service restarts.

## Contract gap

FL8.1's sealed design requires the training exporter to load canonical lifecycle events before replay through `FastMarketState`.

Storage intentionally preserves verified lifecycle truth per signature and `lifecycle_events_for_mint` returns those verified rows deterministically. Before PR #268, the training exporter had no cross-signature semantic canonicalization step.

Therefore two verified signatures describing the exact same point-in-time lifecycle transition reached `FastMarketState::apply_lifecycle`, whose global runtime contract correctly rejects two distinct events at the same detection time.

The correction belongs in the training/export boundary, not in production state or durable storage truth.

## Export-only correction

PR #268 changes only FL8.1 training lifecycle preparation.

Before training replay, lifecycle rows are deterministically ordered by:

1. detection time;
2. lifecycle kind;
3. provider;
4. mint;
5. quote mint;
6. source venue;
7. destination venue;
8. pool address;
9. slot;
10. occurrence time;
11. signature.

Rows are collapsed only when every lifecycle semantic field above except signature is equal.

The retained representative is deterministic because signature is the final lexical tie-break.

Any same-time disagreement in kind, provider, mint, quote mint, venues, pool, slot, detection time, or occurrence time remains distinct and therefore still reaches the existing `FastMarketState` fail-closed conflict.

This correction does not modify:

- `FastMarketState`;
- lifecycle storage schema or verified rows;
- provider/runtime ingestion;
- PAPER decisions or accounting;
- the physical V2 cohort;
- frozen V2 chronology, horizon, split, or evidence floors;
- promotion authority;
- LIVE authority.

## RED / GREEN evidence

RED test-only head:

`77bd73838e11468c81306fef0e5bd1892783776c`

RED CI:

`34369823876`

The RED run passed:

- Repository safety;
- Python tests;
- ARM64 release build.

Rust failed only the new production-shaped semantic-duplicate regression:

`exporter_canonicalizes_same_time_semantic_lifecycle_duplicates_by_signature`

with the expected same-time lifecycle conflict. The guard proving substantive same-time lifecycle disagreement still fails closed passed.

GREEN implementation head:

`47f1bf3167bdd8ad2078800bd2df5fe2e19271de`

GREEN PR CI:

`34370227544`

All four gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Merged main:

`fa675bd6b9cbb23ac9bd526576f758767905c050`

Merged-main CI:

`34370580833`

All four merged-main gates passed.

## Frozen upstream V2 authority remains unchanged

Physical cohort artifact fingerprint:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

Accepted identity fingerprint:

`75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`

TEST unseen-mint identity fingerprint:

`f896c03590a66f4385a01a347039c9dd8a3ab60a4a181e631fa2e838e12ef285`

Feature identity firewall fingerprint:

`e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

V2 first-champion policy:

`fl9-v2-first-champion-v1`

The required five members, natural TEST floor of 40,000 scored rows per target, and unseen-mint TEST floor of 35,000 scored rows per target are unchanged.

## Authority boundary

This seal authorizes:

- one new immutable ARM64 release containing the lifecycle-export correction;
- protected deployment to `production-paper`;
- generation of a fresh release-bound proof workspace;
- generation of the matching training-economics overlay;
- one new quiesced read-only V2 first-champion evidence attempt.

This seal does **not** authorize:

- learned-vs-deterministic superiority claims;
- PAPER promotion;
- action-policy promotion;
- risk-intent creation;
- registry promotion;
- transaction construction;
- signing/submission;
- LIVE trading.

PAPER promotion remains **BLOCKED**.

LIVE remains **DISABLED**.

## Required next physical sequence

1. seal-main CI must pass all four gates;
2. automatic release workflow must build the exact seal SHA;
3. verify immutable release `shreks-<seal-sha>` and its exact three release assets;
4. deploy that exact release through the protected production-paper workflow;
5. verify active release, manifest, service process identity, and restart counts;
6. keep sufficient filesystem headroom without modifying `/var/lib/shreks` evidence;
7. stop `shreks.target` and verify the target plus observer, paper-evidence, and paper-campaign units are all `inactive`;
8. use a **new** run root and generate a fresh proof workspace from the exact deployed release and sealed proof tools;
9. generate a matching training-economics overlay from that new proof feature JSONL;
10. authenticate the unchanged physical V2 cohort;
11. choose a new immutable V2 evidence destination before request creation;
12. create the canonical V2 host request from authenticated deployed sources;
13. execute `sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-first-champion <request-path>`;
14. read back and freeze the final evidence identity/counts before interpreting model or economic metrics;
15. restart `shreks.target` after the command exits and reverify runtime identity.

The failed run root from the superseded release must not be reused as the proof workspace for the new release.

If the next evidence command fails, preserve request/input artifacts, do not overwrite a final evidence destination, restore PAPER, and investigate before retry.

## Physical completion boundary

A later physical evidence seal may claim completion only if evidence proves:

```text
deployed_release_identity=PASS
database_quiescence=PASS
database_data_version_stable=PASS
physical_cohort_fingerprint_verified=YES
release_bound_proof=PASS
overlay_proof_identity=PASS
bundle_identity_reconciliation=PASS
v2_generalization_members=5
natural_test_floor_per_target=PASS
unseen_mint_test_floor_per_target=PASS
runtime_compatible_champion=CREATED_AND_VERIFIED
v2_evidence_artifact=CREATED_AND_VERIFIED
paper_runtime_restored=PASS
paper_promotion=BLOCKED
live_trading=DISABLED
```

No physical champion/model result is accepted by this code seal.
