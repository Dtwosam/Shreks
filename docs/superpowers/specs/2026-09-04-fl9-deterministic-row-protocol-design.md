# FL9 Stateful Deterministic Row Evaluation Protocol — Design

**Date:** 2026-09-04

## Status

Design after deterministic PAPER prefix-replay session merged as `b24e35d98214d295fd8740e5513ccae17fcbc5fd` (PR #175).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create the offline Rust seam that evaluates exactly one next FL8.1 row for one deterministic lifecycle candidate using the candidate's **actual PAPER-derived posture** and explicit chronological evidence.

This closes the stateful boundary:

`actual PAPER prefix -> FLAT/OPEN posture -> exact Rust FL6 row evaluation -> lifecycle decision -> PAPER prefix replay`.

## Ownership

Add the protocol to `shreks-storage`.

That crate already owns:

- `FastTrainingFeatureRecord`;
- FL8.1 snapshot hydration;
- FL6 baseline campaign composition;
- deterministic lifecycle composition;
- deterministic candidate manifests.

Putting the bridge in `shreks-core` would create an invalid storage dependency cycle.

## Architecture

### Pure protocol/evaluator module

Add:

`crates/shreks-storage/src/fast_deterministic_row.rs`

It owns strict serde request/response wire types, candidate-manifest materialization, FL8.1 record decoding, evidence hydration, one-row lifecycle evaluation, canonical response encoding, and response SHA-256.

No file/network/database/runtime authority exists in the module.

### Narrow offline CLI

Add:

`crates/shreks-storage/src/bin/shreks-fast-deterministic-row.rs`

Invocation:

`shreks-fast-deterministic-row <request.json>`

The binary:

- reads exactly one request file;
- delegates decode/evaluation/encoding to the pure module;
- writes canonical response JSON to stdout;
- reads no database;
- uses no network;
- reads no wall clock;
- writes no files;
- has no PAPER execution, promotion, signing, submission, or LIVE authority.

## Request schema

`schema_name = "shreks.fast_deterministic_row_request"`

`schema_version = 1`

Top-level fields:

- schema name/version;
- exact deterministic candidate manifest object;
- exact FL8.1 training feature record object;
- session-derived posture;
- baseline-specific explicit evidence.

Unknown fields fail closed.

### Candidate manifest is the policy authority

The evaluator materializes typed Rust policies directly from the canonical manifest:

- lifecycle policy;
- selected FL6.1–FL6.4 entry policy;
- selected FL6.5–FL6.6 manager policy.

The request does **not** accept a second copy of strategy thresholds.

This prevents a caller from presenting candidate fingerprint A while evaluating policy B.

### FL8.1 record

The request embeds one exact row in the same JSON shape emitted by `export_fast_training_features`.

Add a strict storage-side decoder that:

- accepts exact schema name/version;
- rejects unknown fields;
- reconstructs the existing `FastTrainingFeatureRecord`;
- reuses existing FL8.1 validation;
- does not recompute market state.

The record is the authority for:

- source event ID;
- market key;
- sequence;
- decision clock;
- current snapshot;
- current mint/quote/venue.

## Posture wire

FLAT:

`{"kind":"FLAT"}`

OPEN:

- `kind = "OPEN"`;
- `current_exposure_fraction`;
- `opened_at_unix_ms`.

The Python PAPER session supplies these values.

The request does not carry position ID because FL6 does not need it.

Validation:

- FLAT has no exposure/open time;
- OPEN exposure finite within `(0,1]`;
- OPEN opening time non-negative and not after row decision time.

## Evidence wire

The evidence variant must equal the manifest-selected component for the current posture.

### FL6.1 / FL6.2 / FL6.3 entry variants

Variants:

- `IMPULSE_SCALP`;
- `MICRO_PULLBACK`;
- `PRE_GRADUATION`.

Each contains optional execution economics:

- cost model version;
- entry leg costs;
- exit leg costs;
- intended base quantity;
- executable entry price quote;
- forecast exit price quote;
- exit capacity base;
- required edge bps;
- risk margin bps.

Market and timestamp are **not** supplied. They are derived from the FL8.1 row.

Missing execution evidence remains explicit `null` and therefore preserves sealed fail-closed SKIP behavior.

### FL6.4 Graduation Flow

Contains:

- explicit pre-migration `FastMarketSnapshot` wire;
- optional boost boolean;
- optional entry execution economics.

Post/current snapshot is always hydrated from the current FL8.1 row.

The companion pre snapshot is never invented from the current record.

The pre snapshot wire includes exact market/time/reserve/lifecycle/window state needed by sealed FL6.4 validation.

### FL6.5 Wallet Cohort

Contains optional point-in-time wallet evidence:

- evidence version;
- wallet feature/profile/relationship policy versions;
- support/exits side summaries;
- hold-horizon weight;
- optional weighted median hold.

The evaluator derives:

- candidate mint from current row;
- evidence decision timestamp from current row;
- position market/time from current row;
- `opened_at_unix_ms` from OPEN session posture.

The request cannot override those identities.

### FL6.6 Longer Runner

Contains:

- protective booleans;
- optional continuation evidence:
  - evidence version;
  - forecast source version/horizon;
  - base quantity;
  - current executable exit price;
  - expected future exit price;
  - downside exit price;
  - current/future capacity;
  - expected holding cost;
  - current/future exit leg costs.

The evaluator derives market/time from the current row.

Missing continuation remains explicit and preserves sealed fail-closed REDUCE behavior.

## One-row evaluation

Algorithm:

1. decode and authenticate candidate manifest;
2. materialize exact typed lifecycle + selected component policies;
3. decode and validate exact FL8.1 row;
4. hydrate canonical current snapshot;
5. validate session-derived posture;
6. require evidence variant to match selected manifest component for that posture;
7. construct exactly one `FastDeterministicLifecycleRequest`;
8. call sealed `evaluate_fast_deterministic_lifecycle_batch` with a one-element slice;
9. require exactly one returned decision;
10. encode canonical response.

No FL6 formula is copied into the protocol module.

## Response schema

`schema_name = "shreks.fast_deterministic_row_result"`

`schema_version = 1`

Fields:

- schema name/version;
- candidate version;
- candidate fingerprint;
- lifecycle policy;
- one canonical deterministic lifecycle decision;
- `result_fingerprint_sha256`.

Decision fields match the existing deterministic lifecycle wire exactly:

- source event ID;
- market key;
- source sequence;
- as-of time;
- posture;
- component kind/version;
- action;
- current exposure;
- target exposure.

The response does not contain fills or economic outcomes.

## Python adapter boundary

A following Python adapter will build this request from:

- decoded candidate manifest;
- FL8.1 record;
- `FastDeterministicPaperPosture`;
- explicit chronological baseline evidence.

It will invoke the offline CLI and decode the result into exact `FastDeterministicLifecycleDecision`, then append that decision to the PAPER prefix session.

Do not add subprocess authority to the existing pure lifecycle/PAPER packages; the CLI invocation belongs in a dedicated offline evidence adapter.

## TDD

RED first:

1. golden Impulse Scalp + Longer Runner manifest + FLAT row evaluates through exact sealed lifecycle path;
2. manifest policy materialization reproduces all selected policy fields;
3. request cannot override market/time in entry execution evidence;
4. OPEN Longer Runner derives market/time and preserves session exposure;
5. Wallet Cohort position opening time comes only from OPEN posture;
6. missing Longer Runner continuation preserves sealed REDUCE;
7. wrong evidence kind for manifest/posture fails;
8. malformed/unknown FL8.1 row fields fail;
9. Graduation Flow uses current row only as post snapshot and explicit pre snapshot;
10. canonical response is deterministic and authenticated;
11. CLI stdout byte-matches pure encoder;
12. source firewall forbids DB/provider/network/PAPER execution/promotion/LIVE.

## Economic boundary

This bridge proves only that sequential real-PAPER posture can drive the exact Rust deterministic baseline logic offline.

It does not supply empirical evidence, claim profitability, compare expectancy, promote, or enable LIVE.
