# FL8.1 Fast Lane Training Dataset / Versioning — Design

## Status

Design for build-order phase **FL8.1 Training dataset/versioning**.

Base: FL7.6 is SEALED at merged-main commit `c646b257c4c3f2221bcab7bde01eafcebe2a7b38` with fresh push-triggered four-gate GREEN CI `33767370313`.

LIVE remains disabled.

## Build-order requirement

The canonical build order says:

> **FL8.1 Training dataset/versioning** — Use point-in-time-safe features plus multi-horizon and counterfactual labels.

FL8.1 must make the sealed Fast Lane evidence usable for learning without changing how execution, labels, or point-in-time state are computed.

## Existing authorities to preserve

FL8.1 already has three independently sealed evidence authorities:

1. **Fast Lane point-in-time state** — Rust `FastMarketState` / `FastMarketSnapshot` in `shreks-core` owns rolling event-window math.
2. **FL4 future-path labels** — Rust `fast_future_path_labels` owns multi-horizon path outcomes, coverage, completeness, capacity, route and cost-adjusted returns.
3. **FL5 counterfactual labels** — Python `CounterfactualActionOutcome` / counterfactual Parquet owns `BUY_NOW/SKIP/DELAY_ENTRY/HOLD/REDUCE_NOW/SELL_NOW` action outcomes and exact execution-evidence provenance.

The older D6 Python research dataset remains valid and point-in-time-safe, but it predates Fast Lane and cannot silently become the entire FL8 feature surface. Its B2/D5/regime/score fields may later be joined as auxiliary features, but FL8.1 must expose the actual event-resolution state used by FL6/FL7.

## Critical architecture decision: never reimplement FastMarketState in Python

`FastMarketSnapshot` is derived from canonical `fast_events`; it is deliberately not duplicated into a durable snapshot table. Recomputing its windows in Python would create a second implementation of:

- rolling event retention;
- count/quote-flow imbalance;
- arrival rates;
- velocity/acceleration;
- local high/low identity;
- post-high trough identity;
- drawdown/recovery;
- reserve-context replay;
- lifecycle detection timing.

That would create feature drift between training and production.

FL8.1 therefore adds a **read-only Rust training-feature exporter**. It replays the canonical SQLite evidence through the already-sealed Rust state engine and emits a versioned interchange record. Python only parses and validates those records; it never recomputes a Fast Lane feature.

## Read-only historical exporter

Add an explicit non-mutating database open path for research export. It must:

- require an existing database file;
- open SQLite `READ_ONLY | NO_MUTEX`;
- never create directories/files;
- never run migrations;
- require the current schema required by the exporter;
- preserve existing conflict-quarantine behavior by using the same storage replay selectors as FL4;
- never acquire provider, signer, transaction, PAPER or LIVE authority.

The exporter operates over unique canonical FL4 decision identities. A decision is identified by:

```text
(signature, ordinal, sequence, mint, quote_mint, venue, observed_at_unix_ms)
```

Only decisions backed by the requested FL4 label version are eligible.

For each market, the exporter:

1. loads canonical events through `fast_events_for_market_with_reserve_context`, which already fails closed on quarantined source conflicts and reconstructs reserves from immutable raw evidence;
2. loads canonical lifecycle events for the mint;
3. replays events in sequence through `FastMarketState::with_default_windows`;
4. applies only lifecycle evidence whose `detected_at_unix_ms <= decision observed_at_unix_ms`;
5. emits the snapshot immediately after the decision event has been applied;
6. never applies a future event or future-detected lifecycle event before emitting that decision row.

This produces the same point-in-time state logic used by the deterministic Fast Lane baselines.

## Fast training feature interchange

Version 1 constant:

```text
FAST_TRAINING_FEATURE_SCHEMA_NAME = "shreks.fast_lane_training_features"
FAST_TRAINING_FEATURE_SCHEMA_VERSION = 1
```

The Rust exporter writes canonical JSON Lines. Each line is one decision row with no future labels.

Top-level identity/provenance fields:

- schema name/version;
- decision signature;
- decision ordinal;
- decision sequence;
- mint;
- quote mint;
- venue;
- decision observed timestamp;
- decision event provider;
- decision source-observed timestamp;
- decision occurred timestamp;
- slot;
- event kind;
- actor if present;
- decision executable entry price from FL4 identity;
- optional decision entry total quote;
- snapshot last sequence;
- snapshot last price.

Point-in-time context:

- reserve context encoded as a stable tagged object with exact raw integer values/decimals;
- last lifecycle event encoded as a stable tagged object with detection timestamp and canonical migration identity, or null;
- exactly the sealed default windows, in ascending order.

Each window carries the complete sealed `FastWindowSummary` values. Optional path identities remain optional; zero-flow values remain real zeros. Floats must be finite before export.

The exporter must emit deterministic row ordering by canonical decision sequence and deterministic object/array shape. Re-running against an unchanged database must produce byte-identical JSONL.

## Why JSONL instead of another SQLite feature table

The snapshot is derived state, not a new operational authority. Persisting it into SQLite would create another mutable derived-state table and migration burden. JSONL is an immutable interchange artifact:

- Rust remains the only feature calculator;
- Python can validate it before training;
- the artifact can be fingerprinted and archived alongside Parquet targets;
- no operational database semantics change.

## Training bundle shape

FL8.1 writes a **versioned immutable training bundle**, not one giant denormalized table.

Bundle schema:

```text
shreks.fast_lane_training_bundle / version 1
```

Contents:

1. `features.parquet`
   - one row per canonical decision;
   - point-in-time Fast Lane feature values only;
   - no future fields.

2. `future_path_labels.parquet`
   - one row per decision × FL4 horizon;
   - preserves FL4 label version, coverage, completeness and all path metrics;
   - incomplete labels retain null target values exactly as stored rather than being treated as zero/no-move.

3. `counterfactual_action_labels.parquet`
   - the already-sealed FL5 physical schema/version;
   - long-form action outcomes;
   - `UNKNOWN` and `NOT_EXECUTABLE` remain distinct from executable zero-return outcomes;
   - no missing fill is invented.

4. `manifest.json`
   - bundle schema name/version;
   - feature schema name/version;
   - required FL4 label version;
   - required FL5 label/dataset schema versions;
   - decision count;
   - future-label row count;
   - counterfactual row count;
   - min/max decision timestamps;
   - logical SHA-256 of each table;
   - SHA-256 of the Rust JSONL source artifact;
   - deterministic whole-bundle logical fingerprint.

The counterfactual Parquet is validated using the existing sealed reader/writer contract rather than redefined.

## Exact joins

A feature row joins FL4 by exact canonical decision identity:

```text
signature + ordinal + sequence + mint + quote_mint + venue + observed_at_unix_ms
```

FL4 label rows must match their canonical decision FastEvent and requested label version.

FL5 entry counterfactual `decision_id` remains the sealed form:

```text
{signature}:{ordinal}:h{horizon_ms}:v{future_path_label_version}
```

FL8.1 validates that every counterfactual row maps to an existing FL4 decision/horizon in the same bundle and that mint, quote mint, horizon and label version agree. It does not rewrite the FL5 ID format.

Open-position counterfactual records that do not map to a canonical FL4 entry decision may be placed in a later position-state training bundle; FL8.1 version 1 fails closed rather than guessing a feature identity for them.

## Future-path target semantics

The FL4 table preserves every stored field:

- horizon/version/completeness;
- coverage complete-through and contiguity;
- event count / no-trade flag;
- endpoint identity/time/price/return;
- MFE / MAE;
- time to peak / trough;
- reversal occurrence/timing;
- minimum and endpoint exit capacity;
- route unavailability;
- best and endpoint cost-adjusted achievable return.

`complete` and `incomplete` are first-class values. An incomplete row must not contain invented target completion.

## Point-in-time leakage gates

FL8.1 rejects a bundle when any of these are violated:

- feature decision identity differs from canonical FL4 decision identity;
- feature snapshot last sequence exceeds the decision sequence;
- feature snapshot time exceeds the decision time;
- a window path timestamp exceeds decision time;
- lifecycle `detected_at` exceeds decision time;
- FL4 endpoint/future evidence appears in the feature table;
- FL5 evidence observed after its allowed action/horizon contract contradicts the sealed FL5 row;
- duplicate decision feature identities;
- duplicate FL4 decision/horizon identities;
- duplicate FL5 logical action identities;
- mixed incompatible schema/label versions.

FL8.1 does not remove valid future labels from the label tables; it keeps them physically separate from the feature table so downstream model code must opt into targets explicitly.

## Determinism and fingerprints

Logical fingerprints are based on stable column order, stable row order, explicit nulls, exact integer values and canonical float representation. Physical Parquet bytes are not treated as the logical identity.

Rows sort by:

- features: `(decision_sequence, signature, ordinal)`;
- FL4: `(decision_sequence, horizon_ms, signature, ordinal)`;
- FL5: existing sealed counterfactual canonical ordering.

A whole-bundle fingerprint hashes the schema/version metadata plus component logical fingerprints and row counts.

## Public Python API

Add focused training-data modules under `shreks_brain.research`, exposing at least:

- training bundle schema/version constants;
- `FastTrainingFeatureRecord` / parsed feature-window/context models;
- `FuturePathTrainingLabel`;
- `FastTrainingBundleManifest`;
- `read_fast_training_feature_jsonl`;
- `load_future_path_training_labels_from_sqlite`;
- `write_fast_training_bundle`;
- `read_fast_training_bundle`;
- logical fingerprint helpers.

No model estimator, scaler, split policy, champion or inference API belongs in FL8.1.

## Rust API / binary

Add a storage-side training export module and a small binary that can be invoked as:

```text
export_fast_training_features <database.sqlite3> <output.jsonl>
```

The binary must refuse overwrite unless the destination does not exist, so a generated training source artifact is immutable by default.

No provider clients or environment secrets are read.

## Non-goals

FL8.1 does **not**:

- train a model;
- select a model family;
- split train/validation/test data (FL8.3);
- calibrate forecasts (FL8.4);
- create/promote a champion (FL8.5);
- run Rust inference (FL8.6);
- change deterministic strategies;
- change PAPER fills/accounting/risk;
- change any LIVE authority.

## Exit criterion for FL8.1

FL8.1 is complete when Shreks can deterministically export and reload a versioned training bundle in which:

- Fast Lane features are generated only by sealed Rust point-in-time state logic;
- FL4 multi-horizon labels are exact and completeness-aware;
- FL5 counterfactual action labels preserve executability/provenance semantics;
- all identities and versions join exactly;
- leakage contradictions fail closed;
- repeated export from identical inputs yields identical logical fingerprints;
- no training, promotion or LIVE authority is introduced.
