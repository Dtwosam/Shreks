# FL9 Dependency-Free First Champion Builder — Design

**Date:** 2026-09-04

## Status

Implementation slice after deterministic campaign JSONL request v2 merged and sealed as
`41adf1c75142d178df5ab951a117c0a8a060ff9b` (#202).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Compose the already-sealed FL8.2, FL8.3, FL8.4, and FL8.5 layers into one narrow first-champion
builder that can operate in the production Python environment without scikit-learn, NumPy, PyArrow,
network access, or database access.

This builder does not introduce new forecast mathematics. It orchestrates existing sealed
algorithms and preserves their evidence fingerprints.

## Package boundary

Add an isolated composition package:

`shreks_brain.fast_first_champion`

Do not widen or modify the sealed FL8.5 `shreks_brain.fast_champion.__all__` surface.

The composition package imports FL8.5 as a consumer.

## Required FL9 forecast members

The first champion contains exactly the forecast members consumed by the existing FL9 continuous
action decision protocol at one explicit horizon:

1. `endpoint_cost_adjusted_return_bps` — `MEAN_REGRESSOR`;
2. `endpoint_return_bps` — `MEAN_REGRESSOR`;
3. `mae_bps` — `MEAN_REGRESSOR`;
4. `reversal_occurred` — `PRIOR_CLASSIFIER`;
5. `route_unavailability_observed` — `PRIOR_CLASSIFIER`.

These two naive families are already sealed FL8.2 implementations and require only the standard
library.

The builder does not claim they are optimal. Their purpose is to establish the first honest,
reproducible, non-fixture model baseline. Later challengers may use richer model families if real
evidence justifies the added dependency/complexity.

## Inputs

`build_fast_first_champion(...)` requires exact caller-supplied:

- `FastTrainingBundle`;
- complete `FastForecastEvaluationContext` corpus for the FL8.3 prediction identities;
- `FastChronologicalValidationPolicy`;
- TEST `FastForecastEvaluationPolicy`;
- champion version;
- explicit selection decision reference;
- explicit selection timestamp;
- explicit selection reason;
- one forecast horizon;
- model-version prefix;
- training-policy version;
- minimum TEST scored-observation count.

There are no hidden wall-clock reads, random choices, economic thresholds, or model-family choices.

## Validation and TEST evidence

For each required target the builder creates one exact
`FastForecastTrainingRequest` using the fixed naive family and supplied model/policy versions.

It then runs the existing:

1. FL8.3 chronological validation engine;
2. FL8.4 TEST evaluation engine.

The evaluation policy must select TEST. Validation evidence cannot be substituted.

The exact point-in-time context corpus is caller supplied and remains subject to the existing FL8.4
exact-coverage and fingerprint rules.

## Explicit evidence floor

The builder requires a positive caller-supplied
`minimum_test_scored_observations`.

Every one of the five TEST reports must meet that floor.

This is a data-sufficiency guard only. It does not rank models, inspect error thresholds, or infer a
selection decision from metrics.

If one target lacks enough scorable TEST evidence, the whole first-champion build fails closed.

## Selection chronology

The explicit selection timestamp must be late enough for the complete chronological TEST interval
and its forecast horizon to have matured.

For the supplied validation policy:

`latest_test_end + horizon_ms <= decided_at_unix_ms`.

This deliberately conservative rule prevents the selection record from predating the labels needed
for its TEST evidence.

## Runtime refit

After the supplied selection decision/evidence boundary is validated, the runtime artifact for each
required target is refit through the existing FL8.2 trainer using only decision identities whose
requested target horizon was mature by the selection timestamp:

- decision timestamp is strictly before selection;
- `decision_observed_at + horizon_ms <= decided_at`.

The builder independently verifies the returned artifact's maximum training decision timestamp plus
horizon does not exceed selection time.

The final runtime refit may include pre-selection validation/test decisions whose labels were mature
by the explicit selection timestamp. This is consistent with FL8.5: the chronological fold models
remain the TEST evidence, while the runtime artifact is a final refit aligned to the same sealed
request/source bundle.

## Explicit FL8.5 packaging

The builder passes exactly one tuple per required target into the sealed
`build_fast_forecast_champion` API:

- final runtime artifact;
- exact FL8.3 validation run;
- exact FL8.4 TEST report.

Selection reference/time/reason are supplied unchanged to FL8.5.

No metric-based automatic selection is performed.

## Result evidence

`FastFirstChampionBuildResult` contains:

- composition version;
- exact FL8.5 champion;
- five runtime artifacts;
- five validation runs;
- five TEST reports.

The result validates canonical required target/horizon order and cross-links every champion member
back to the exact runtime artifact, validation-run fingerprint, and TEST-report fingerprint carried
in the result.

It therefore cannot represent a champion/evidence tuple that only happens to share target names.

## What this slice does not solve

This slice is deliberately pure and in-memory.

It does not decide where real FL8.4 context rows come from. The existing FL8.4 design intentionally
requires explicit point-in-time market regime, strategy-family, liquidity, and cost context rather
than guessing them from future outcomes.

A following host-request slice must authenticate that context corpus and combine it with the #201
runtime JSONL+SQLite bundle builder.

## Authority boundary

The composition source contains no:

- scikit-learn, NumPy, or PyArrow import;
- SQLite access;
- provider/network access;
- PAPER execution;
- risk intent construction;
- registry mutation;
- signing;
- transaction submission;
- LIVE authority.

It only constructs offline forecast evidence and an immutable FL8.5 forecast configuration.

## TDD provenance

Intentional RED:

`016efcfffe99c1f77f83ad89d554edf4f6d9fd5a`.

The RED failed only because the new first-champion API did not yet exist.

During implementation audit, the first draft attempted to export the composition API through the
sealed FL8.5 package. The existing exact-public-API contract was found before sealing, and the new
code was moved to the isolated `fast_first_champion` package. The final diff leaves the FL8.5
package untouched.

A production implementation head passed Python with 3120 tests before the final result
cross-link hardening.

## Following work

Build a canonical file-backed first-champion request/context artifact that:

1. authenticates the Rust feature JSONL;
2. assembles the logical FL8.1 bundle from JSONL + read-only SQLite through #201;
3. authenticates explicit FL8.4 context rows;
4. invokes this dependency-free builder;
5. writes the immutable champion and its validation/evaluation evidence without overwrite;
6. emits `INSUFFICIENT_EVIDENCE` rather than inventing missing context or mature target data.

After a genuine champion exists, use #202 to run the deterministic baseline population and #199 to
run the learned comparison over the same post-selection population.

LIVE remains disabled.
