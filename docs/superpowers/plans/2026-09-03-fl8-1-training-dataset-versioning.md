# FL8.1 Fast Lane Training Dataset / Versioning — Implementation Plan

> Execute this plan on `build/fl8-1-training-dataset-versioning`, based only on SEALED FL7.6 merged-main `c646b257c4c3f2221bcab7bde01eafcebe2a7b38`.

**Goal:** Produce a deterministic, versioned, leakage-safe historical Fast Lane training bundle using Rust-generated point-in-time features plus canonical FL4 and FL5 labels.

**Architecture:** Rust storage replay remains the only Fast Lane feature calculator. A read-only exporter emits canonical JSONL feature records. Python validates those records, loads exact FL4 labels read-only from SQLite, validates the sealed FL5 counterfactual Parquet, and writes a fingerprinted immutable bundle. No model training or LIVE authority is introduced.

---

## Task 1 — RED: Rust read-only point-in-time feature export contract

**Create tests:**
- `crates/shreks-storage/tests/fl8_training_feature_export.rs`
- `crates/shreks-storage/tests/fl8_training_feature_export_binary.rs`

Specify:

1. Stable constants:
   - `FAST_TRAINING_FEATURE_SCHEMA_NAME = "shreks.fast_lane_training_features"`
   - `FAST_TRAINING_FEATURE_SCHEMA_VERSION = 1`
2. `ShreksDb::open_existing_read_only`:
   - missing path fails;
   - existing current-schema DB opens;
   - no migration/write occurs;
   - connection cannot mutate.
3. Export selection uses unique FL4 decisions for requested `FUTURE_PATH_LABEL_VERSION`.
4. Replay uses canonical event order and exact decision identity.
5. Decision snapshot includes the decision event itself but excludes all later events.
6. Future lifecycle evidence is excluded; lifecycle evidence detected at/before decision may appear.
7. Reserve context is reconstructed through existing immutable source replay.
8. Every sealed default window is present exactly once, ascending.
9. Window metrics equal direct `FastMarketState` replay for the same prefix.
10. Conflict-quarantined source evidence fails closed via existing replay path.
11. JSONL export is deterministic and byte-identical for unchanged source DB.
12. Binary refuses missing input, refuses existing output, writes no database state, and contains no provider/signer/LIVE authority.

Commit intentional RED before adding production symbols.

Run canonical CI and require Rust failure only on absent FL8.1 Rust API/binary while safety/Python/ARM64 remain green.

---

## Task 2 — GREEN: Rust exporter and read-only open path

**Modify:**
- `crates/shreks-storage/Cargo.toml`
- `crates/shreks-storage/src/lib.rs`

**Create:**
- `crates/shreks-storage/src/training_features.rs`
- `crates/shreks-storage/src/bin/export_fast_training_features.rs`

Implementation requirements:

1. Add only serialization dependencies required for deterministic JSONL (`serde`, `serde_json`).
2. Add `ShreksDb::open_existing_read_only` using SQLite read-only flags and schema validation without migrations.
3. Add canonical unique-FL4-decision selector.
4. Group decisions by `FastMarketKey`, load trusted event replay with reserve context, load lifecycle events, and replay once per market.
5. Snapshot immediately after each decision event.
6. Flatten only already-computed `FastMarketSnapshot` / `FastWindowSummary` values into a versioned serializable record.
7. Validate finite floats, decision identity, default windows and no future timestamp leakage before serialization.
8. Write JSONL to a newly-created file only; sort by decision sequence.
9. Keep database read-only and do not expose providers, intents, transactions, runtime mode or signing.

Run targeted Rust tests and canonical four-gate CI.

---

## Task 3 — RED: Python feature-interchange parser and FL4 loader

**Create tests:**
- `python/tests/test_fast_training_feature_interchange.py`
- `python/tests/test_fast_training_future_path_labels.py`

Specify:

1. Exact feature schema/version acceptance.
2. Canonical JSONL order and duplicate decision rejection.
3. Every default window must be present once and ascending.
4. Non-finite values fail closed.
5. Snapshot sequence/time/path/lifecycle leakage checks.
6. Stable parsed feature identity and logical fingerprint.
7. FL4 SQLite loader is read-only and requires an existing DB.
8. Loader validates canonical decision and endpoint FastEvent identity.
9. Loader rejects conflict-quarantined decisions/endpoints.
10. Loader preserves every FL4 target field, coverage, completeness, no-trade semantics and nulls exactly.
11. Mixed/wrong FL4 label versions fail closed.
12. Stable chronological ordering and duplicate decision/horizon rejection.

Commit intentional Python RED before creating production parser/loader modules.

Run CI and require Python failure only on absent FL8.1 Python public API while other gates are green.

---

## Task 4 — GREEN: Python feature parser and FL4 loader

**Create:**
- `python/src/shreks_brain/research/training_models.py`
- `python/src/shreks_brain/research/training_sources.py`

Implementation requirements:

- frozen validated models;
- exact schema/version constants;
- canonical decision key type/helper;
- JSONL parser with strict key sets and type checks;
- no recomputation of Rust window metrics;
- logical fingerprint with float-hex canonicalization;
- read-only SQLite FL4 loader modeled on the sealed counterfactual source validation boundary;
- exact canonical source and conflict-quarantine checks;
- explicit complete/incomplete state.

Run targeted Python tests and full suite.

---

## Task 5 — RED: training bundle / Parquet contract

**Create tests:**
- `python/tests/test_fast_training_bundle.py`
- `python/tests/test_fast_training_bundle_leakage.py`
- `python/tests/test_fast_training_public_api.py`

Specify bundle version 1:

```text
schema name = shreks.fast_lane_training_bundle
schema version = 1
```

Specify:

1. `features.parquet` one row per decision.
2. `future_path_labels.parquet` one row per decision/horizon.
3. Existing sealed FL5 `counterfactual_action_labels.parquet` schema is used unchanged.
4. All component versions recorded in manifest.
5. Exact feature↔FL4 identity joins.
6. Exact FL5 `decision_id`↔FL4 decision/horizon joins.
7. Counterfactual mint/quote/horizon/version mismatches fail.
8. Unmapped open-position counterfactual IDs fail closed in v1.
9. `UNKNOWN`, `NOT_EXECUTABLE`, and executable zero returns stay distinct.
10. Incomplete FL4 labels are retained as incomplete, never zero-filled.
11. Future columns never appear in feature schema.
12. Stable physical column order and strict Arrow types.
13. Component logical fingerprints and deterministic whole-bundle fingerprint.
14. Repeated write/read yields identical logical manifest.
15. Existing output directory/file collisions fail rather than silently mutate an immutable bundle.
16. Public API exposes no estimator, trainer, champion, provider, signer, transaction or LIVE authority.

Commit RED before bundle implementation.

---

## Task 6 — GREEN: immutable training bundle writer/reader

**Create:**
- `python/src/shreks_brain/research/training_parquet.py`
- `python/src/shreks_brain/research/training_bundle.py`

**Modify:**
- `python/src/shreks_brain/research/__init__.py`

Implementation requirements:

1. Explicit Arrow schemas for feature and FL4 tables.
2. Zstd compression, no physical-byte identity assumption.
3. Existing `read_counterfactual_parquet` validation for FL5 component.
4. Exact joins before writing.
5. Manifest JSON canonicalized and fingerprinted.
6. Destination created atomically enough to avoid reporting a complete bundle after partial validation failure; validate all logical inputs before writing.
7. Reader revalidates schemas, metadata, row counts, fingerprints and joins.
8. No model/split/calibration/champion code.

Run targeted tests and full Python suite.

---

## Task 7 — Integration proof across Rust export -> Python bundle

**Create test:**
- `python/tests/test_fast_training_bundle_integration.py` or a Rust/Python fixture pair as appropriate.

Use a small deterministic canonical SQLite fixture containing:

- at least two decisions for one market;
- a future event after the first decision;
- at least one complete and one incomplete FL4 horizon;
- lifecycle evidence before one decision and future lifecycle evidence after another;
- FL5 entry counterfactual outcomes including an explicit `UNKNOWN` or `NOT_EXECUTABLE` path.

Prove:

1. Rust export for first decision excludes later event/lifecycle data.
2. Python feature parser fingerprints it deterministically.
3. FL4 labels join only by exact identity.
4. FL5 rows join only to their exact horizon/version.
5. bundle write/read is equivalent.
6. changing only a future label changes label/bundle fingerprints but not the feature fingerprint.

---

## Task 8 — Candidate verification, history cleanup and seal

1. Require candidate four-gate GREEN.
2. Audit changed files for provider/DB operational semantics/strategy/PAPER/LIVE changes.
3. Collapse authoring noise so history is exactly:

```text
design -> plan -> RED(s) -> implementation
```

If multiple independent RED commits are retained, keep them explicit and documented; otherwise collapse all pre-implementation tests into one RED commit after proving each TDD boundary in CI.

4. Compare clean feature branch to SEALED FL7.6 and document exact file scope.
5. Require fresh exact-clean-head four-gate GREEN.
6. Open/finish PR with full TDD proof.
7. Mark ready.
8. Expected-head guarded merge exact clean head.
9. Require fresh push-triggered merged-main four-gate GREEN.
10. Mark FL8.1 SEALED only after merged-main proof.

LIVE remains disabled throughout. FL8.1 does not claim forecasting quality or profitability.
