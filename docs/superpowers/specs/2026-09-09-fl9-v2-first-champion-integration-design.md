# FL9 V2 First Champion Integration — Design

**Date:** 2026-09-09  
**Base main SHA:** `ad2cc70374a5ff7b085a5a159cc9e1a6808d050c`  
**Status:** DESIGN  
**Scope:** separately versioned V2 first-champion integration only  
**PAPER promotion:** BLOCKED  
**LIVE:** DISABLED

## 1. Purpose

Consume the physically sealed FL9 V2 cohort artifact exactly, read target/model evidence only after that cohort identity is fixed, and produce the first runtime-compatible V2 champion evidence without changing V1 request bytes or V1 evidence semantics.

The authoritative cohort artifact is:

- policy: `fl9-v2-cohort-acceptance-v1`
- artifact fingerprint: `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`
- accepted identity fingerprint: `75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`
- horizon: `30000 ms`
- selection timestamp: `1788902319835`
- training cut: `1788892302791`
- validation cut: `1788898931418`
- TEST end exclusive: `1788902289835`

This slice must not re-run tradable-universe selection or change cohort membership.

## 2. Governing invariants

The V2 integration must:

1. require the exact physical cohort artifact fingerprint;
2. require the exact accepted identity population before target access;
3. require training-bundle feature identities to equal the accepted cohort identities exactly;
4. use the frozen 30-second horizon and frozen chronological split;
5. use FL8.3 V2 signature-only quarantine and novelty semantics;
6. train one required model member per existing FL9 target/family;
7. evaluate the natural TEST population;
8. evaluate the exact unseen-mint TEST subset using the same predictions;
9. enforce per-target natural TEST scored observations >= 40,000;
10. enforce per-target unseen-mint TEST scored observations >= 35,000;
11. fail closed rather than changing the cohort, horizon, split, thresholds, or model family;
12. preserve the existing runtime champion file contract for downstream consumers;
13. keep V1 first-champion schemas, bytes, code paths, and behavior unchanged.

## 3. Frozen required model members

Use the existing five required FL9 members at exactly 30,000 ms:

1. `endpoint_cost_adjusted_return_bps` — `MEAN_REGRESSOR`
2. `endpoint_return_bps` — `MEAN_REGRESSOR`
3. `mae_bps` — `MEAN_REGRESSOR`
4. `reversal_occurred` — `PRIOR_CLASSIFIER`
5. `route_unavailability_observed` — `PRIOR_CLASSIFIER`

No family selection is performed in this slice.

## 4. Selected package boundary

Add a sibling package:

`shreks_brain.fast_first_champion_v2`

Do not modify the public authority semantics of:

- `shreks_brain.fast_first_champion`
- `shreks_brain.fast_validation`
- `shreks_brain.fast_champion`
- existing V1 host/file request schemas

The V2 package may consume those layers but must not reinterpret V1 artifacts as V2 evidence.

## 5. Cohort-bound training bundle

The V2 path must read the accepted cohort artifact first.

Only after validating its exact fingerprint may it access FL4 labels/training-economics evidence.

The cohort-bound bundle builder must:

- read the authenticated feature source;
- select exactly the accepted cohort decision identities;
- fail if any accepted identity lacks a feature row;
- fail if the selected feature identity set differs from the accepted cohort set;
- read the requested FL4 label version for the frozen 30-second horizon;
- retain only labels whose exact seven-field decision identity is accepted;
- fail if accepted decision identity coverage is incomplete or contradictory;
- bind the exact feature-source SHA and selected logical feature fingerprint;
- project the existing training-economics overlay only onto accepted 30-second identities;
- build counterfactual evidence only for the accepted identities;
- assemble an ordinary sealed `FastTrainingBundle`;
- require the final bundle feature identity set to equal the cohort accepted identity set exactly.

The source feature/label databases may contain newer rows. Newer or otherwise unaccepted rows must not enter the V2 training bundle.

## 6. Exact V2 chronological policy

Use one `FastChronologicalGeneralizationPolicy` with one exact fold:

- training: `[1788878323281, 1788892302791)`
- validation: `[1788892302791, 1788898931418)`
- TEST: `[1788898931418, 1788902289835)`

Required policy identity:

- version: `fl8.3-chronological-generalization-v2`
- feature firewall: `fl8.3-feature-identity-firewall-v1`
- firewall fingerprint: `e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

Required V2 novelty floors:

- unseen-mint validation rows >= 40,000
- unseen-mint validation unique mints >= 20
- unseen-mint TEST rows >= 40,000
- unseen-mint TEST unique mints >= 25

For the sealed cohort, the V2 run must reconcile to:

- training rows: 164,645
- validation rows: 54,858
- TEST rows: 54,831
- shared signatures: 0
- validation unseen-mint: 49,754 rows / 24 mints
- TEST unseen-mint: 54,828 rows / 31 mints

The integration must compare V2 run identity populations against the cohort artifact, not only counts.

## 7. V2 evaluation

The existing FL8.4 evaluator is exact-type-bound to the V1 validation run and therefore must not be fed synthetic V1 evidence.

Add an isolated V2 evaluator in the sibling V2 package.

It must preserve FL8.4 metric semantics and produce fingerprinted evaluation evidence for a `FastChronologicalGeneralizationRun`.

Two TEST reports are required per target:

### 7.1 Natural TEST

Uses every V2 TEST prediction from the frozen fold.

Required scored floor per target:

`>= 40000`

### 7.2 Unseen-mint TEST

Uses the exact identity set from:

`fold_result.test_novelty.unseen_mint_identities`

It must reuse the exact natural TEST predictions for those identities. No retraining and no second inference pass may alter prediction values.

Required scored floor per target:

`>= 35000`

The unseen-mint report must bind:

- the same V2 validation-run fingerprint;
- the same training-bundle fingerprint;
- the exact unseen-mint TEST identity fingerprint;
- the exact prediction values already present in the natural TEST run.

A target failing either scored-observation floor fails the complete first-champion attempt.

## 8. Runtime refit

Only after the V2 TEST evidence for a target passes both floors may the final runtime artifact be fit.

Runtime refit may use only accepted cohort decision identities whose 30-second target is mature by the frozen selection timestamp.

No row outside the accepted cohort may enter the refit.

The final artifact must preserve:

- exact target;
- exact family;
- exact 30-second horizon;
- exact training-policy version;
- exact training-bundle fingerprint;
- chronology ending no later than the frozen selection timestamp.

## 9. Runtime-compatible champion

Existing downstream runtime code reads `FastForecastChampionArtifact`.

Do not fork the runtime consumer solely to carry V2 evidence.

Instead, the V2 package must build an ordinary runtime-compatible `FastForecastChampionArtifact` using the existing champion model types and fingerprint rules, but through a new V2 packager rather than the V1 `build_fast_forecast_champion(...)` function, which correctly remains type-bound to V1 evidence.

For each member, store:

- final runtime forecast artifact;
- V2 policy version;
- V2 generalization-run fingerprint;
- natural TEST evaluation policy version;
- natural TEST evaluation-report fingerprint;
- natural TEST scored/target-unavailable counts.

The ordinary champion file therefore remains consumable by existing offline/runtime readers.

## 10. Separate V2 evidence wrapper

Because the runtime champion schema has only one TEST-report reference per member, add a V2 evidence wrapper that binds the runtime champion to the complete V2 proof.

Conceptual schema:

`shreks.fast_first_champion_v2_evidence` v1

Per required member record:

- target/family/horizon;
- runtime artifact fingerprint;
- V2 generalization-run fingerprint;
- natural TEST report fingerprint;
- natural TEST scored count;
- unseen-mint TEST report fingerprint;
- unseen-mint TEST scored count;
- unseen-mint TEST identity fingerprint.

Top-level evidence binds:

- exact cohort artifact fingerprint;
- exact accepted identity fingerprint;
- training-bundle fingerprint;
- V2 policy/firewall identity;
- frozen selection timestamp;
- runtime champion fingerprint;
- all five member records;
- final V2 evidence fingerprint.

## 11. File artifact layout

Use an immutable output directory.

Conceptual layout:

- `manifest.json`
- `champion.json`
- `natural-test/<member-key>.json`
- `unseen-mint-test/<member-key>.json`
- `v2-evidence.json`

Every file hash is recorded in the manifest.

The writer refuses overwrite.

The reader must verify:

- exact file set;
- canonical JSON;
- all file SHA-256 values;
- champion fingerprint;
- V2 evidence fingerprint;
- exact cohort fingerprint;
- natural/unseen member alignment.

## 12. V2 host/request path

Add a separately versioned V2 host request. Do not mutate V1 request schemas.

The request must include:

- exact deployed release source SHA;
- exact cohort artifact path;
- expected cohort artifact fingerprint;
- authenticated feature source/proof workspace;
- observer SQLite path;
- context-hydration policy and fingerprint;
- training-economics overlay and fingerprint;
- execution-cost policy and fingerprint;
- destination path;
- FL4 label version;
- counterfactual base quantity;
- TEST evaluation policy;
- champion/model/training-policy versions;
- explicit reason.

The request must not contain:

- host-selected horizon;
- host-selected split;
- mutable selection clock;
- minimum-row tuning knobs for the frozen cohort.

The frozen cohort manifest supplies horizon, split, and selection timestamp.

## 13. Production execution order

The first production V2 champion attempt must execute in this order:

1. verify deployed release identity;
2. read and verify the exact cohort artifact;
3. bind accepted identities;
4. assemble the cohort-bound training bundle;
5. verify exact bundle/cohort identity reconciliation;
6. hydrate evaluation contexts for the exact V2 validation/TEST populations;
7. run the five V2 generalization models;
8. produce natural TEST reports;
9. produce unseen-mint TEST reports from the same predictions;
10. enforce 40,000 / 35,000 scored floors for every target;
11. only after all five members pass, refit runtime artifacts;
12. build the runtime-compatible champion;
13. write/read the immutable V2 evidence artifact;
14. only then inspect model/economic results for the next decision gate.

No PAPER promotion occurs automatically.

## 14. Fail-closed conditions

Fail the attempt on any of:

- cohort artifact fingerprint mismatch;
- accepted identity fingerprint mismatch;
- missing/extra selected feature identity;
- label identity contradiction;
- training-economics identity contradiction;
- bundle/cohort identity mismatch;
- wrong horizon/split/selection timestamp;
- wrong V2 policy/firewall fingerprint;
- signature/novelty population mismatch;
- natural TEST scored floor failure;
- unseen-mint TEST scored floor failure;
- natural/unseen prediction mismatch;
- runtime refit using an unaccepted identity;
- output overwrite;
- file/fingerprint readback mismatch.

No automatic threshold relaxation, alternate split, alternate horizon, or cohort regeneration is allowed.

## 15. TDD requirements

At minimum prove:

1. exact physical cohort fingerprint required;
2. wrong cohort fingerprint fails before target access;
3. source supersets cannot add unaccepted identities;
4. missing accepted feature identity fails;
5. selected feature identities equal accepted identities exactly;
6. exact 30-second labels only;
7. label identity drift fails;
8. exact frozen fold required;
9. V2 run populations reconcile to cohort partitions;
10. V2 novelty identities reconcile to cohort novelty identities;
11. natural TEST uses every V2 TEST prediction exactly once;
12. unseen TEST uses the exact unseen identity set;
13. unseen TEST reuses natural prediction values;
14. natural scored floor is per target;
15. unseen scored floor is per target;
16. either floor failure fails the entire attempt;
17. runtime refit identities are cohort-bound and target-mature;
18. existing runtime champion reader accepts the V2-produced champion;
19. V1 first-champion bytes and tests remain unchanged;
20. immutable artifact write/read fingerprints round-trip;
21. authority scan proves no PAPER/risk/signing/LIVE path is added.

## 16. Authority boundary

This slice may:

- read target values for the already sealed cohort;
- train offline baseline forecast models;
- evaluate validation/TEST evidence;
- write immutable offline champion evidence.

This slice may not:

- change cohort membership;
- change FL9 admission;
- change runtime action thresholds;
- mutate model registry/promotion state;
- send PAPER orders;
- create risk intents;
- construct/sign/submit transactions;
- enable LIVE.

**Cohort floor:** ACCEPTED  
**V2 first-champion integration:** AUTHORIZED  
**PAPER promotion:** BLOCKED  
**LIVE:** DISABLED
