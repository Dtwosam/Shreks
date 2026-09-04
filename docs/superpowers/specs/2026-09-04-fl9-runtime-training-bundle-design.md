# FL9 Runtime Training Bundle — Design

**Date:** 2026-09-04

## Status

Implementation slice after sealed proof-tool transport merge
`b2304cf423429af93354cbb6429aab1191507768` (#200).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The verified production wheel intentionally has no third-party dependencies. The VPS can now
materialize the authenticated Rust FL8.1 exporter, but the existing FL8.1 bundle persistence path
requires PyArrow because it writes and rereads Parquet.

That physical storage dependency prevents the already-sealed training, validation, evaluation, and
champion code from consuming real host evidence even though those downstream layers operate on the
logical `FastTrainingBundle` object and do not require Parquet themselves.

## Decision

Separate logical evidence assembly from physical Parquet persistence.

Parquet remains the sealed archival representation. It is not removed or reinterpreted.

Add pure standard-library builders that create the exact same logical rows, manifests, joins, and
fingerprints in memory. Existing Parquet writers delegate to the same logical counterfactual builder
so physical and storage-free paths cannot drift silently.

## FL5 logical dataset builder

`build_counterfactual_dataset(...)` accepts only exact
`CounterfactualOutcomeSet` values.

It reuses the existing canonical row builder, ordering, validation, logical action identity,
dataset SHA-256, and `CounterfactualDatasetManifest`.

For equivalent outcome sets:

`in-memory rows/manifest == Parquet rows/manifest`.

No PyArrow import occurs until the caller explicitly requests Parquet persistence.

## FL8.1 component builder

`build_fast_training_bundle_from_components(...)` accepts exact:

- `FastTrainingFeatureDataset`;
- `FuturePathTrainingLabelDataset`;
- tuple of exact `CounterfactualOutcomeSet` values.

Before creating the bundle it:

1. recomputes the feature logical fingerprint;
2. authenticates the feature JSONL source fingerprint shape;
3. recomputes the FL4 logical fingerprint;
4. builds canonical FL5 logical rows/manifest;
5. reuses the existing exact feature/FL4/FL5 join validator;
6. reuses the existing FL8.1 manifest builder and bundle fingerprint.

The resulting `FastTrainingBundle` is therefore logically identical to the persisted bundle that
would be written from the same evidence.

## Production-shaped runtime source builder

`build_fast_training_bundle_from_runtime_sources(...)` consumes:

- Rust-exported canonical feature JSONL path;
- read-only observer SQLite path;
- explicit FL4 label version;
- explicit positive finite counterfactual base quantity.

It:

1. parses/authenticates the Rust feature JSONL;
2. loads FL4 labels through the existing read-only canonical SQLite loader;
3. for every exact FL4 decision/horizon/version, reloads FL5 source provenance through the existing
   read-only counterfactual source loader;
4. requires that provenance match the FL4 row;
5. runs the existing pure entry-counterfactual labeler;
6. builds the normal logical FL8.1 bundle through the component builder.

The explicit base quantity is research-label input only. It is not a position size, order request,
risk allocation, or trading instruction.

## Missing execution evidence

The source loader already refuses to manufacture requested-quantity executable trade evidence.

Therefore when exact execution evidence is unavailable:

- `BUY_NOW` remains `UNKNOWN`;
- `SKIP` remains executable with zero PnL by definition;
- no future price, capacity, stored aggregate cost, or protocol constant is promoted into a
  fabricated historical fill.

This behavior is preserved unchanged by the runtime builder.

## Why this is safe for FL8.2–FL8.5

The sealed training, chronological validation, evaluation, and champion layers consume
`FastTrainingBundle` logical objects and fingerprints.

They do not require the bundle to have been reread from Parquet.

Therefore this slice changes only how equivalent already-authenticated evidence reaches the
existing logical object. Feature extraction, target selection, chronology, leakage quarantine,
training, prediction, evaluation, and champion packaging remain untouched.

## First real champion dependency

The first genuine FL9 evidence run does not need scikit-learn.

The sealed FL8.2 model surface already provides:

- `MEAN_REGRESSOR` for continuous FL9 forecast targets;
- `PRIOR_CLASSIFIER` for binary FL9 forecast targets.

These standard-library models can produce all forecast members required by the continuous action
policy. They are intentionally simple and may fail the economic superiority test. That failure is
valid evidence, not a reason to fabricate a stronger result.

Ridge/logistic challengers remain later optimization work if real evidence shows they are needed.

## Authority boundary

This slice may read local research files and SQLite through existing read-only loaders.

It does not:

- call providers or networks;
- mutate SQLite;
- alter PAPER state;
- create risk/trade intents;
- choose or promote a champion;
- run an FL9 campaign;
- sign or submit transactions;
- enable LIVE.

## TDD provenance

Intentional RED:

`93378caa0f0495500f95fc71fe0891e7d50f2482`.

RED failure was isolated to Python collection for the missing new logical builder APIs. Repository
safety and ARM64 release build remained green.

## Verification

Seal only after the exact final head proves:

- in-memory FL5 rows/manifest equal Parquet logical evidence;
- in-memory FL8.1 bundle equals the persisted Parquet bundle for equivalent real-shaped fixture data;
- runtime JSONL+SQLite assembly imports no PyArrow;
- missing execution evidence remains UNKNOWN rather than fabricated;
- feature/FL4 fingerprint tampering fails closed;
- authority firewall remains intact;
- full Python, Rust, repository-safety, and ARM64 release CI are green.

## Following work

Build the standard-library first-real-champion/evidence orchestration over this runtime bundle:

1. derive explicit chronological folds from the real evidence population;
2. train/evaluate the required mean/prior forecast members;
3. explicitly package the first non-fixture FL8.5 champion;
4. materialize the sealed #200 native tools;
5. feed the same post-selection evidence population into deterministic and learned PAPER campaigns;
6. write the #198 proof artifact and accept `SUPERIOR`, `FAILED`, or
   `INSUFFICIENT_EVIDENCE` exactly as measured.

LIVE remains disabled.
