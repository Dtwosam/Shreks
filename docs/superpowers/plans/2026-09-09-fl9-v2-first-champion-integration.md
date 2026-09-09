# FL9 V2 First Champion Integration — Implementation Plan

**Date:** 2026-09-09  
**Base design branch:** `design-fl9-v2-first-champion-integration`  
**Required base main SHA:** `ad2cc70374a5ff7b085a5a159cc9e1a6808d050c`

## Goal

Implement the separately versioned V2 first-champion path that consumes the exact physically sealed cohort artifact and produces runtime-compatible champion evidence only after both precommitted TEST scoring floors pass.

The work is intentionally split into two implementation PRs after this design/plan PR:

1. **V2 core evidence integration** — cohort-bound bundle, V2 evaluation, builder, runtime-compatible champion packaging, immutable evidence artifact.
2. **V2 production host/request path** — exact release/cohort binding, authenticated host inputs, CLI, production artifact generation.

Do not combine either implementation with PAPER promotion, learned-vs-baseline comparison, or LIVE work.

---

## Frozen constants

The implementation must freeze and test:

```text
cohort_policy=fl9-v2-cohort-acceptance-v1
cohort_artifact_fingerprint=bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a
accepted_identity_fingerprint=75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b
horizon_ms=30000
selection_at_unix_ms=1788902319835
training_start=1788878323281
training_cut=1788892302791
validation_cut=1788898931418
test_end=1788902289835
natural_test_scored_floor=40000
unseen_mint_test_scored_floor=35000
feature_firewall_fingerprint=e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0
```

No caller may override these values for V1 of the V2 integration policy.

---

# PR A — V2 core evidence integration

## Task A1 — Add RED V2 contract tests

**Add:**

- `python/tests/test_fast_first_champion_v2_models.py`
- `python/tests/test_fast_first_champion_v2_authority.py`

Prove RED for:

- exact V2 schema/policy version;
- exact physical cohort and accepted-identity fingerprints;
- exact horizon/split/selection timestamp;
- exact 40k/35k scoring floors;
- exact five target/family members;
- immutable values require a new policy version;
- public API is intentionally small;
- source scan forbids V1 host mutation, PAPER, risk, signing, submission, and LIVE imports.

Expected RED: V2 package absent.

## Task A2 — Define V2 models and policy

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/__init__.py`
- `python/src/shreks_brain/fast_first_champion_v2/models.py`

Define exact immutable contracts for:

- `FastFirstChampionV2Policy`;
- `FastFirstChampionV2MemberEvidence`;
- `FastFirstChampionV2BuildResult`;
- `FastFirstChampionV2EvidenceManifest`;
- `FastFirstChampionV2EvidenceArtifact`.

The member evidence must bind:

- target/family/horizon;
- runtime artifact fingerprint;
- V2 run fingerprint;
- natural TEST report fingerprint/count;
- unseen-mint TEST report fingerprint/count;
- unseen-mint TEST identity fingerprint.

Run focused tests GREEN.

## Task A3 — Add cohort-bound bundle construction

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/bundle.py`
- `python/tests/test_fast_first_champion_v2_bundle.py`

Inputs:

- verified `Fl9V2CohortAcceptanceArtifact`;
- authenticated feature JSONL;
- read-only observer SQLite;
- FL4 label version;
- training-economics overlay;
- execution-cost policy;
- counterfactual base quantity.

Required order:

1. validate exact cohort artifact fingerprint;
2. extract accepted decision identities;
3. read feature source;
4. select exact accepted identities;
5. fail on missing accepted features;
6. read target/economics evidence only after cohort validation;
7. select exact accepted 30-second label/economics rows;
8. build counterfactual evidence only for selected identities;
9. construct `FastTrainingBundle`;
10. assert final feature identity set equals accepted cohort identity set.

Tests must cover:

- source superset ignored safely;
- missing accepted identity fails;
- extra identity cannot enter bundle;
- duplicate/contradictory identity fails;
- wrong horizon fails;
- label identity mismatch fails;
- overlay identity mismatch fails;
- resulting bundle fingerprints are deterministic.

Do not change existing `build_fast_training_bundle_from_runtime_sources(...)` behavior.

## Task A4 — Add V2 evaluation engine

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/evaluation.py`
- `python/tests/test_fast_first_champion_v2_evaluation.py`

The evaluator consumes:

- `FastTrainingBundle`;
- `FastChronologicalGeneralizationRun`;
- exact contexts;
- TEST evaluation policy;
- explicit slice: natural TEST or exact unseen-mint TEST.

It must not synthesize a V1 validation run.

Natural TEST:

- every V2 TEST prediction exactly once.

Unseen-mint TEST:

- exact identities from V2 novelty evidence;
- exact prediction values reused from the natural V2 TEST predictions;
- no retraining;
- no second model inference required.

Use existing FL8.4 report/model dataclasses where compatible, but keep V2 evaluation orchestration isolated.

Add parity fixtures proving V2 metric calculations agree with FL8.4 for equivalent synthetic prediction/actual/context populations.

## Task A5 — Add V2 core builder

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/builder.py`
- `python/tests/test_fast_first_champion_v2_builder.py`

For each exact required member:

1. create the exact training request;
2. run `run_fast_chronological_generalization(...)`;
3. verify fold/population identities against the cohort artifact;
4. evaluate natural TEST;
5. evaluate exact unseen-mint TEST from the same predictions;
6. enforce natural scored count >= 40,000;
7. enforce unseen scored count >= 35,000;
8. only then fit the final runtime artifact on target-mature accepted identities.

Fail the entire build if any member fails either floor.

Tests must prove per-target failure is fail-closed and no later target is used to relax an earlier failure.

## Task A6 — Build runtime-compatible champion through a V2 packager

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/champion.py`
- `python/tests/test_fast_first_champion_v2_champion.py`

Do not call the V1 `build_fast_forecast_champion(...)` with synthetic evidence.

Construct the existing `FastForecastChampionArtifact` model through the new V2 packager using:

- existing `FastForecastChampionSelection`;
- existing `FastForecastChampionMember`;
- existing champion fingerprint function.

For each member:

- validation policy version = V2 policy version;
- validation run fingerprint = exact V2 generalization-run fingerprint;
- TEST report fingerprint/count = natural TEST evidence.

Tests must prove:

- existing `write/read_fast_forecast_champion` round-trip succeeds;
- existing offline champion consumer can read the V2-produced champion;
- all five member cross-links reconcile;
- no V1 builder behavior changes.

## Task A7 — Add immutable V2 evidence artifact

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/artifact.py`
- `python/tests/test_fast_first_champion_v2_artifact.py`

Artifact layout:

```text
manifest.json
champion.json
v2-evidence.json
natural-test/<member-key>.json
unseen-mint-test/<member-key>.json
```

Requirements:

- canonical deterministic JSON;
- exact file allowlist;
- no generated-at wall clock in canonical bytes;
- file SHA-256 recorded;
- exact cohort fingerprint recorded;
- exact accepted identity fingerprint recorded;
- exact bundle fingerprint recorded;
- exact champion fingerprint recorded;
- natural/unseen reports cross-linked by target/horizon/run;
- overwrite refused;
- readback verifies every file/fingerprint.

## Task A8 — Run V1/V2 regression and authority gates

Run focused suites:

```bash
python -m pytest   python/tests/test_fast_first_champion_v2_models.py   python/tests/test_fast_first_champion_v2_bundle.py   python/tests/test_fast_first_champion_v2_evaluation.py   python/tests/test_fast_first_champion_v2_builder.py   python/tests/test_fast_first_champion_v2_champion.py   python/tests/test_fast_first_champion_v2_artifact.py   python/tests/test_fast_first_champion_v2_authority.py   python/tests/test_fast_chronological_v2_models.py   python/tests/test_fast_chronological_v2_firewall.py   python/tests/test_fast_chronological_v2_population.py   python/tests/test_fast_chronological_v2_engine.py   python/tests/test_fast_first_champion_builder.py   python/tests/test_fast_first_champion_file_request.py   python/tests/test_fast_first_champion_plan.py   python/tests/test_fast_first_champion_host_run.py -q
```

Then:

```bash
python -m pytest python/tests -q
cargo test --workspace
```

Require repository safety and ARM64 release build in CI.

Scope audit must reject changes in:

- V1 first-champion source except tests if absolutely necessary;
- V1 validation engine;
- existing champion model/reader/writer behavior;
- collector;
- risk;
- PAPER executor;
- signing/submission;
- LIVE paths.

Merge only exact reviewed head after all four CI gates.

---

# PR B — V2 production host/request path

Begin only after PR A is merged and merged-main CI is green.

## Task B1 — Add RED V2 host request contracts

**Add:**

- `python/tests/test_fast_first_champion_v2_host_run.py`
- `python/tests/test_fast_first_champion_v2_host_request_writer.py`

The V2 request must require:

- expected release source SHA;
- cohort artifact path;
- exact expected cohort fingerprint;
- proof workspace / authenticated feature source;
- observer DB;
- hydration policy and fingerprint;
- training-economics overlay and fingerprint;
- execution-cost policy and fingerprint;
- destination;
- FL4 label version;
- counterfactual base quantity;
- TEST evaluation policy;
- champion/model/training-policy versions;
- reason.

It must not expose horizon/split/selection/minimum-floor tuning fields.

## Task B2 — Implement exact host request encode/decode/write

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/host_request.py`

Canonical request fingerprinting must reject:

- unknown fields;
- duplicate JSON keys;
- raw non-finite floats;
- wrong cohort fingerprint;
- wrong release SHA shape;
- unsafe destination.

Writer refuses overwrite.

## Task B3 — Implement V2 host run

**Add:**

- `python/src/shreks_brain/fast_first_champion_v2/host_run.py`

Required execution order:

1. verify release identity from request;
2. read cohort artifact;
3. verify exact physical cohort fingerprint;
4. derive frozen horizon/split/selection from cohort;
5. build cohort-bound training bundle;
6. hydrate exact evaluation contexts;
7. run V2 core builder;
8. write immutable V2 evidence artifact;
9. read artifact back;
10. print machine-readable success status.

No host wall clock may choose the V2 selection timestamp.

## Task B4 — Add CLI

Register a new entry point only after tests are RED:

`shreks-fl9-v2-first-champion`

CLI must require only the canonical V2 request path.

It must not accept ad-hoc horizon/split/floor overrides.

## Task B5 — Authority and regression gates

Prove V2 host code contains no:

- PAPER execution;
- risk intent creation;
- registry promotion;
- signing;
- transaction submission;
- LIVE enablement.

Run full Python/Rust/CI gates and merge exact reviewed head.

---

# Production evidence sequence

After PR B is sealed in a release and deployed:

1. verify exact deployed release/process identity;
2. verify exact physical cohort artifact remains present and unchanged;
3. create a new immutable V2 first-champion destination;
4. execute the V2 host request;
5. read back the V2 evidence artifact;
6. record:
   - exact cohort fingerprint;
   - training-bundle fingerprint;
   - five V2 run fingerprints;
   - five natural TEST scored counts/report fingerprints;
   - five unseen-mint TEST scored counts/report fingerprints;
   - runtime champion fingerprint;
   - final V2 evidence artifact fingerprint;
7. only then inspect model metrics/economics;
8. decide whether evidence warrants later PAPER/shadow comparison.

Do not promote automatically.

---

## Completion boundary

This integration is complete only when:

```text
physical_cohort_fingerprint_verified=YES
bundle_identity_reconciliation=PASS
v2_generalization_members=5
natural_test_floor_per_target=PASS
unseen_mint_test_floor_per_target=PASS
runtime_compatible_champion=CREATED_AND_VERIFIED
v2_evidence_artifact=CREATED_AND_VERIFIED
paper_promotion=BLOCKED
live_trading=DISABLED
```

The following slice is then model/economic evidence review and the learned-vs-deterministic PAPER/shadow comparison required by FL9. It is not part of this implementation plan.
