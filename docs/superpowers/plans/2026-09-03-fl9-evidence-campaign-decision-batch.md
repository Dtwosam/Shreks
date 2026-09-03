# FL9 Evidence Campaign Decision Batch — Implementation Plan

**Date:** 2026-09-03

Base: SEALED FL9 superiority proof merge `e0a462cbc6dea0517fbd04acec6712f7d5446c30`.

Design: `docs/superpowers/specs/2026-09-03-fl9-evidence-campaign-decision-batch-design.md`.

## Goal

Create an offline deterministic bridge:

```text
FL8.1 FastTrainingFeatureRecord
        ↓ sealed Python feature extraction
169 raw features
        ↓ canonical request JSON
Rust batch adapter
        ↓
sealed FL8.6 champion inference
        ↓
sealed FL9 continuous action policy
        ↓ canonical result JSON
FL7 FastPaperActionAssessment translation
```

No provider/storage/PAPER execution/promotion/LIVE authority.

## Task 1 — RED Rust champion→action composition contract

Create:

`crates/shreks-core/tests/fast_campaign_decision.rs`

Lock crate-root API:

- `FastCampaignDecisionError`
- `assess_continuous_action_from_champion`

RED assertions:

1. exact 169 raw features accepted;
2. for every policy horizon the helper requires exactly:
   - endpoint cost-adjusted return;
   - endpoint return;
   - MAE;
   - reversal probability;
   - route-unavailability probability;
3. helper result equals manually constructed `FastActionForecastSet` + sealed `assess_continuous_action`;
4. exact champion version/fingerprint carried into assessment;
5. missing member fails closed;
6. feature length mismatch fails closed;
7. non-finite feature fails closed;
8. no fallback target/horizon;
9. no I/O/runtime/trading API.

Expected RED: unresolved crate-root imports.

## Task 2 — Implement pure Rust composition

Create:

`crates/shreks-core/src/fast_lane/campaign.rs`

Update exports only:

- `crates/shreks-core/src/fast_lane/mod.rs`
- `crates/shreks-core/src/lib.rs`

Implementation:

- target order is explicit and stable;
- call sealed `predict_fast_forecast` once per required target/horizon;
- construct `FastActionForecastSet`;
- call sealed `assess_continuous_action`;
- error enum wraps exact inference/action errors;
- no allocation or transformation of live market state beyond the supplied raw vector.

## Task 3 — RED Rust batch wire + CLI contract

Create:

`crates/shreks-core/tests/fast_campaign_decision_cli.rs`

Create protocol fixtures:

- `crates/shreks-core/tests/fixtures/fl9_campaign_champion.json`
- `crates/shreks-core/tests/fixtures/fl9_campaign_decision_request.json`
- `crates/shreks-core/tests/fixtures/fl9_campaign_decision_results.json`

Lock additional pure campaign APIs for request/result wire decode/evaluate/encode, then RED assertions:

1. binary `shreks-fast-campaign-decision` exists;
2. requires exactly two positional paths: champion JSON and request JSON;
3. unknown request fields rejected;
4. wrong schema rejected;
5. duplicate source event IDs rejected;
6. zero source sequence/negative timestamp rejected;
7. within one market key, request order cannot regress sequence or timestamp;
8. feature length/non-finite input rejected;
9. canonical response fields/order/fingerprint deterministic;
10. repeated identical invocation outputs byte-identical stdout;
11. missing champion member returns non-zero;
12. stderr carries reason, stdout stays empty on failure.

Expected RED: binary target absent.

## Task 4 — Implement Rust CLI

Create:

`crates/shreks-core/src/bin/shreks-fast-campaign-decision.rs`

Use only existing dependencies:

- std;
- serde;
- serde_json;
- sha2;
- `shreks_core`.

No clap/new dependency.

Request/result wire structs and strict serde decoding live in the pure campaign module and use `#[serde(deny_unknown_fields)]`.

CLI only reads files, loads the champion through `load_fast_forecast_champion_json`, delegates to pure campaign decode/evaluate/encode APIs, and prints the canonical result.

No wall clock.

## Task 5 — RED Python request/response contracts

Create:

```text
python/tests/test_fast_campaign_decision_models.py
python/tests/test_fast_campaign_decision_codec.py
python/tests/test_fast_campaign_decision_feature_adapter.py
python/tests/test_fast_campaign_decision_authority.py
```

Lock public package:

`shreks_brain.fast_campaign`

Names:

- `FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME`
- `FAST_CAMPAIGN_DECISION_RESULT_SCHEMA_NAME`
- `FAST_CAMPAIGN_DECISION_SCHEMA_VERSION`
- `FastCampaignDecisionPosition`
- `FastCampaignReduceExecutionCost`
- `FastCampaignActionConstraints`
- `FastCampaignDecisionRequest`
- `FastCampaignContinuousActionPolicy`
- `FastCampaignDecisionBatch`
- `FastCampaignDecisionResult`
- `FastCampaignDecisionResults`
- `build_fast_campaign_decision_request`
- `build_fast_campaign_decision_batch`
- `encode_fast_campaign_decision_batch`
- `decode_fast_campaign_decision_results`
- `fast_campaign_result_to_paper_assessment`

Assertions:

1. feature row adapter calls sealed `extract_fast_forecast_features`;
2. feature count equals sealed 169 names;
3. event ID is exact signature:ordinal;
4. market key is exact venue:mint:quote;
5. source sequence/time exact;
6. constraints/position validate strictly;
7. duplicate event IDs rejected in batch;
8. per-market order regressions rejected;
9. canonical compact sorted request JSON;
10. result decoder rejects unknown/missing/noncanonical fields;
11. result fingerprint recomputed;
12. FL7 assessment preserves event identity/action and deterministic reason evidence;
13. adapter package has no subprocess/network/SQLite/provider/execution/promotion/LIVE authority;
14. no future-path or counterfactual labels imported.

The Python package deliberately does **not** invoke the Rust process. Process orchestration belongs to the later campaign executor slice so this API remains pure and testable.

## Task 6 — Implement Python pure adapter

Create:

```text
python/src/shreks_brain/fast_campaign/__init__.py
python/src/shreks_brain/fast_campaign/models.py
python/src/shreks_brain/fast_campaign/codec.py
python/src/shreks_brain/fast_campaign/features.py
```

No filesystem writes, subprocess, DB, network, or execution.

Result decoder must exactly mirror Rust response wire.

## Task 7 — Cross-language wire lock

Rust and Python consume the same canonical request fixture. The deterministic test champion is fixture-only and explicitly carries no promotion authority. Rust CLI stdout must byte-match the committed expected-result fixture, and Python independently decodes that result and recomputes its fingerprint. Fixture values are protocol tests only and are not economic evidence.

## Task 8 — Authority firewall

Add source tests prohibiting in new campaign modules:

Rust core/campaign:
- `std::net`
- provider/storage crates;
- signing/submission;
- runtime mode;
- registry promotion.

Python `fast_campaign`:
- `subprocess`
- `sqlite3`
- `requests`
- `httpx`
- `urllib`
- provider modules;
- PAPER execution functions;
- promotion/registry mutation;
- future/counterfactual labels.

The Rust CLI may use `std::fs` and stdout/stderr only.

## Task 9 — Full candidate verification

Require:

- targeted Rust composition tests GREEN;
- Rust CLI tests GREEN;
- targeted Python campaign tests GREEN;
- full Rust workspace GREEN;
- full Python suite GREEN;
- repository safety GREEN;
- native ARM64 release GREEN.

Scope audit must show only:

- design/plan;
- Rust campaign module/exports/binary/tests/three protocol fixtures;
- Python fast_campaign package/tests.

No storage/provider/observer/runtime deployment files.

## Task 10 — Clean history and seal

After final candidate 4/4 GREEN:

1. freeze final tree;
2. reconstruct design → plan → consolidated RED → implementation;
3. require exact tree identity;
4. force-move only `build/fl9-evidence-campaign-runner`;
5. clean-head 4/4;
6. update PR evidence;
7. guarded merge by expected head SHA;
8. merged-main 4/4;
9. mark **FL9 evidence campaign decision seam — SEALED**.

FL9 economic exit remains **EVIDENCE PENDING**.

## Next slice after seal

Build the campaign executor that:

- invokes this decision batch seam;
- obtains **explicit contemporaneous execution evidence** from a trusted source;
- drives sealed FL7 PAPER accounting for learned and deterministic candidates on the same event population;
- normalizes through sealed E11/E5;
- evaluates through the sealed FL9 superiority proof.

No observed trade print may be silently treated as an executable quote.

LIVE remains disabled.
