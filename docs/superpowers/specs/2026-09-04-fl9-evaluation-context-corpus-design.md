# FL9 Authenticated Forecast Evaluation Context Corpus — Design

**Date:** 2026-09-04

## Status

Implementation slice after the dependency-free first champion builder merged and sealed as
`e290efc9701f366730265b7760e63d4aefc18119` (#203).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

The first-champion builder can consume real FL8.1 evidence without heavy dependencies, but FL8.4
intentionally requires caller-supplied point-in-time segmentation context that is not fully present
in the FL8.1 feature row:

- market regime;
- applicable strategy families;
- executable exit capacity in quote units;
- expected round-trip cost in basis points.

Those values must not be reconstructed from future outcomes or silently filled with defaults.

Before a file-backed host champion request can be trusted, the exact context rows need a durable,
canonical, tamper-evident representation.

## Decision

Add a small authenticated context corpus to the existing
`shreks_brain.fast_first_champion` composition package.

The corpus contains only exact existing `FastForecastEvaluationContext` values. It does not
introduce a new context model or a source-generation policy.

Schema:

`shreks.fast_forecast_evaluation_context_corpus` v1.

## Corpus model

`FastForecastEvaluationContextCorpus` contains:

- schema name;
- schema version;
- canonical tuple of exact `FastForecastEvaluationContext` values;
- FL8.4 logical `context_fingerprint_sha256`.

The corpus recomputes the existing sealed
`fast_forecast_context_fingerprint_sha256(...)` function and requires exact equality.

There is no second context fingerprint algorithm.

## Canonical ordering

Caller order is non-semantic.

The builder canonicalizes rows by:

1. `as_of_unix_ms`;
2. decision sequence;
3. decision signature;
4. decision ordinal.

Decision identities must be unique.

The canonical corpus order therefore matches FL8.3/FL8.4 decision ordering and is stable across
equivalent caller orderings.

## Context row representation

Every encoded row has exactly:

- `decision_identity`;
- `as_of_unix_ms`;
- `market_regime`;
- `strategy_families`;
- `executable_exit_capacity_quote`;
- `expected_round_trip_cost_bps`.

The decoder reconstructs the existing FL8.4 dataclass, so all existing validation still applies:

- exact seven-field FL8.1 decision identity;
- context timestamp equals identity timestamp;
- non-empty market regime;
- sorted unique non-empty strategy families;
- optional non-negative finite liquidity/cost values.

No future target, realized PnL, realized execution result, or post-decision label exists in this
artifact.

## Float encoding

Optional liquidity/cost values preserve the exact numeric scalar type already admitted by FL8.4:

- JSON `null`;
- JSON integer when the supplied context contains an integer scalar; or
- an exact tagged object `{"$float":"<float.hex()>"}` for a Python float.

Raw JSON floats are rejected. Integer preservation matters because the sealed FL8.4 fingerprint canonicalizer distinguishes integer and float scalar types.

Non-finite values are rejected both at JSON parsing and tagged-float decode.

This preserves the same finite-float audit discipline used throughout sealed Fast Lane artifacts.

## Canonical JSON

Encoding uses:

- sorted keys;
- compact separators;
- UTF-8;
- no NaN/infinity;
- exactly one trailing newline.

Decoding constructs the exact corpus and then requires byte-equivalence with canonical re-encoding.
Non-canonical formatting, unknown fields, missing fields, malformed tagged values, or fingerprint
tampering fail closed.

## File persistence

`write_fast_forecast_evaluation_context_corpus(...)` refuses to overwrite an existing path.

`read_fast_forecast_evaluation_context_corpus(...)` requires an existing regular file and executes
the same strict decoder.

This artifact is suitable for later inclusion as a hashed source of a file-backed first-champion
request.

## Evidence-source boundary

This slice does not claim where the context values came from.

That is deliberate.

A later host/runtime evidence collector must provide real point-in-time context, or report that the
required context is unavailable. This corpus merely makes supplied evidence immutable and
authenticated.

It must never:

- infer market regime from future returns;
- infer strategy-family applicability from which strategy later won;
- fabricate liquidity capacity;
- manufacture expected costs;
- use a future label to complete a missing field.

## Authority boundary

The corpus module contains no:

- SQLite/database access;
- provider/network access;
- model training;
- champion selection;
- PAPER execution;
- trade intent creation;
- registry/promotion mutation;
- signing;
- transaction submission;
- LIVE authority.

## TDD provenance

Intentional RED:

`e0004586610f61e3e083c79105b0cab118e827c9`.

RED failed only because the new corpus API was absent. Repository safety remained GREEN.

## Following work

Build the file-backed first-champion request over sealed #201/#203/#204 components:

1. authenticate the canonical Rust FL8.1 feature JSONL;
2. read the protected observer SQLite only through the already-sealed read-only runtime bundle path;
3. authenticate this explicit context corpus;
4. bind exact validation/evaluation/selection policies;
5. call the dependency-free first-champion builder;
6. write the immutable champion plus TEST evaluation evidence into an atomic no-overwrite artifact;
7. fail as `INSUFFICIENT_EVIDENCE` when required context, mature labels, or TEST count is unavailable.

Only after a genuine champion artifact exists should the same post-selection population flow into
#202 deterministic baselines and #199 learned comparison.

LIVE remains disabled.
