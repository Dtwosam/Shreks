# FL9 Evidence Campaign Runner — Decision Batch Seam

**Date:** 2026-09-03

## Status

Design for the first executable slice of the real FL9 evidence campaign after the superiority proof infrastructure was SEALED.

Base: merged-main `e0a462cbc6dea0517fbd04acec6712f7d5446c30`, merged-main CI `33814345340` four-gate GREEN.

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

The FL9 exit criterion requires the approved forecast champion plus the learned continuous-action policy to produce stable, auditable decisions and eventually beat deterministic baselines in PAPER/shadow evidence.

The repository now has:

- SEALED FL8.5 champion artifact format;
- SEALED FL8.6 Rust inference parity;
- SEALED FL9 continuous-action policy;
- SEALED FL9 PAPER/shadow superiority proof infrastructure;
- SEALED FL8.1 Python feature extraction from authoritative Rust-derived training feature rows.

What is still missing is an offline, deterministic seam that can evaluate **many point-in-time feature rows through the exact Rust champion + Rust FL9 policy** without prematurely implementing FL10 live runtime integration.

## Non-goals

This slice does **not**:

- build FastMarketState from Python;
- map live FastMarketState directly to the 169-feature vector;
- access providers or RPCs;
- read operational SQLite;
- execute PAPER fills;
- derive executable quotes from trade prints;
- run deterministic FL6 baselines yet;
- promote a model;
- enable LIVE;
- claim profitability or economic superiority.

The next campaign slice will use this decision seam plus explicit execution evidence to drive sealed FL7 PAPER accounting and deterministic baseline comparison.

## Architecture decision

### Rust remains the decision authority

Add a pure `shreks-core` composition function:

```rust
assess_continuous_action_from_champion(
    champion: &FastForecastChampion,
    raw_features: &[Option<f64>],
    policy: &FastContinuousActionPolicy,
    position: &FastActionPositionState,
    constraints: &FastActionConstraints,
) -> Result<FastContinuousActionAssessment, FastCampaignDecisionError>
```

The function:

1. validates the 169-element raw feature vector through sealed FL8.6 prediction calls;
2. for every configured policy horizon, obtains exactly these targets:
   - `endpoint_cost_adjusted_return_bps`
   - `endpoint_return_bps`
   - `mae_bps`
   - `reversal_occurred`
   - `route_unavailability_observed`
3. constructs one `FastActionForecastSet` using the exact champion identity;
4. delegates action choice to sealed `assess_continuous_action`;
5. performs no I/O and has no runtime or execution authority.

No target fallback, horizon fallback, zero-fill, or missing-member substitution is allowed.

### FL10 boundary is preserved

FL8.6 deliberately left `FastMarketState -> 169 raw features` for FL10.

This slice keeps that boundary intact. It consumes only an already-produced raw vector.

For offline evidence, Python may obtain that raw vector by applying the existing sealed `extract_fast_forecast_features(FastTrainingFeatureRecord)` to an immutable FL8.1 feature row. That is research/evidence plumbing, not live runtime integration.

## Pure Rust batch wire/evaluator

The same `fast_lane::campaign` module owns strict serde wire structs plus pure request decode, batch evaluation, result fingerprinting, and canonical response encoding. This keeps schema validation testable without file I/O and makes the binary only an adapter shell.

## Offline Rust batch CLI

Add a narrow binary in the existing `shreks-core` package:

`crates/shreks-core/src/bin/shreks-fast-campaign-decision.rs`

Invocation:

```text
shreks-fast-campaign-decision <champion.json> <request.json>
```

The CLI:

- reads one exact FL8.5 champion JSON file;
- loads it through sealed `load_fast_forecast_champion_json`;
- reads one request JSON file;
- delegates strict decode/order validation, evaluation, fingerprinting, and canonical encoding to the pure campaign module;
- writes the returned canonical JSON response to stdout;
- reads no database;
- uses no network;
- reads no wall clock;
- writes no files;
- performs no trade or promotion action.

The binary exists only as an offline cross-language adapter.

## Request wire contract

Schema:

- `schema_name = "shreks.fast_campaign_decision_batch"`
- `schema_version = 1`

Batch fields:

- schema name/version;
- `policy`;
- ordered `decisions`.

Policy is one nested strict `FastCampaignContinuousActionPolicyWire` object whose fields map exactly to `FastContinuousActionPolicy`:

- `version`
- `horizons_ms`
- `entry_exposure_candidates`
- `reduce_target_exposure_candidates`
- `adverse_excursion_weight`
- `reversal_penalty_bps`
- `route_unavailability_penalty_bps`
- `horizon_disagreement_weight`
- `minimum_buy_value_bps`
- `minimum_hold_value_bps`
- `missing_forecast_open_action`

Decision fields:

- `source_event_id`
- `market_key`
- `source_sequence`
- `as_of_unix_ms`
- `features` — exact 169-length JSON array, each value finite number or null;
- `position`
- `constraints`

Position wire:

```json
{"kind":"FLAT"}
```

or

```json
{"kind":"OPEN","current_exposure_fraction":0.5}
```

Constraints wire fields map exactly to `FastActionConstraints`:

- `max_exposure_fraction`
- `buy_economically_allowed`
- `expected_future_exit_cost_bps`
- `reduce_execution_costs`
- `sell_executable`
- `sell_now_cost_bps`
- `force_sell`

Each reduction cost contains exact target exposure and execution cost bps.

Unknown fields are rejected.

## Response wire contract

Schema:

- `schema_name = "shreks.fast_campaign_decision_results"`
- `schema_version = 1`

Top-level:

- schema;
- champion version/fingerprint;
- ordered `decisions`;
- canonical SHA-256 `batch_fingerprint_sha256`.

Each result preserves:

- source event ID;
- market key;
- source sequence;
- as-of timestamp;
- action;
- reason;
- selected horizon;
- current exposure;
- target exposure;
- selected reward/risk/execution-cost/value bps;
- full horizon evidence;
- full candidate assessments.

The response fingerprint covers all material except the fingerprint field itself.

Repeated identical champion + request must produce byte-identical canonical response JSON.

## Python offline request/response adapter

Add:

`python/src/shreks_brain/fast_campaign/`

It is offline evidence plumbing only.

Public surface:

- schema constants;
- immutable request position/constraint models;
- `build_fast_campaign_decision_request(...)`;
- `build_fast_campaign_decision_batch(...)`;
- canonical encode/decode;
- immutable result models;
- `fast_campaign_result_to_paper_assessment(...)`.

### Feature-row input

`build_fast_campaign_decision_request` consumes exact:

- `FastTrainingFeatureRecord`;
- caller-supplied position;
- caller-supplied constraints.

It calls sealed:

`extract_fast_forecast_features(record)`

and preserves the FL8.1 decision identity:

- source event ID = `"{decision_signature}:{decision_ordinal}"`;
- source sequence = `decision_sequence`;
- as-of = `decision_observed_at_unix_ms`;
- market key = `"{venue}:{mint}:{quote_mint}"`.

No feature is recomputed from raw market events in Python.

### FL7 assessment translation

A decoded Rust result can be converted to exact `FastPaperActionAssessment` using caller-supplied:

- `assessment_version`;
- `strategy_family`;
- `strategy_version`.

The assessment:

- preserves source event/market/sequence/time exactly;
- maps Rust action string to exact FL7 `FastPaperAction`;
- records deterministic reasons including the Rust selected reason and selected horizon/value evidence.

This translation does not approve or execute a trade.

## Evidence integrity

The Python batch builder records only point-in-time features and caller-supplied contemporaneous constraints.

The Rust response cannot contain:

- future labels;
- realized future returns;
- counterfactual outcomes;
- PAPER fills;
- promotion status;
- runtime mode.

No wall-clock timestamp appears in request or response.

## Fail-closed behavior

Reject:

- wrong schema;
- unknown fields;
- duplicate source event IDs;
- non-monotonic request order within the same market key;
- negative timestamps;
- zero sequence;
- feature count != 169;
- non-finite features;
- non-finite policy/constraint values;
- invalid position/constraint combinations;
- missing champion member for any required target/horizon;
- champion fingerprint mismatch;
- non-finite prediction or action output;
- noncanonical response on Python decode;
- response/request identity mismatch.

## Testing

### Rust

- pure composition parity against manually constructed `FastActionForecastSet`;
- exact target/horizon request coverage;
- missing member fails closed;
- malformed feature vectors fail closed;
- batch CLI deterministic canonical output;
- duplicate/out-of-order identity rejection;
- unknown-field rejection;
- response fingerprint recomputation.

### Python

- build raw 169 vector only through sealed feature extractor;
- canonical request encoding;
- exact identity preservation;
- response canonical/fingerprint validation;
- FL7 assessment translation;
- no subprocess/network/SQLite/provider/trading authority in the adapter package;
- no future label imports.

Three protocol-only fixtures lock the cross-language seam: one valid five-target champion, one canonical 169-feature request, and one canonical expected result. Rust CLI stdout must byte-match the expected result; Python independently decodes that same result and validates its fingerprint.

## Economic claim boundary

Passing this slice proves only:

- exact Rust champion + Rust FL9 policy can be exercised offline in batch;
- Python can prepare point-in-time raw vectors without duplicating FastMarketState;
- decision results are auditable and deterministic.

It does **not** prove economic edge.

FL9 exit remains **EVIDENCE PENDING** until a later campaign consumes real explicit execution evidence, produces sealed PAPER/shadow economic evidence for the learned policy and required deterministic baselines on the same population, and the sealed proof report returns `SUPERIOR`.

LIVE remains disabled.
