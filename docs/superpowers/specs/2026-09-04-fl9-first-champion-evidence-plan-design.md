# FL9 Deterministic First Champion Evidence Plan — Design

**Date:** 2026-09-04

## Status

Implementation slice after atomic first-champion preparation merged and sealed as
`c44fcd7ffc71d64ca593718761239e36db3c0bc2` (#208).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Remove hand-picked chronological fold timestamps from the first real champion workflow while
preserving a strict anti-cherry-picking boundary.

The planner answers one narrow question:

> Given an already-built FL8.1 bundle, an explicit forecast horizon, an explicit selection
> timestamp, and explicit evidence floors, what single chronological fold must be used for the first
> champion proof?

The planner does not choose the horizon and does not choose the selection clock. Both remain
explicit caller evidence.

## Non-adaptive split rule

The planner uses one immutable split policy:

`fl9-first-champion-60-20-20-v1`.

It performs these steps before running any forecast model:

1. compute `test_end = selection_at_unix_ms - horizon_ms`;
2. retain only feature decisions with `decision_observed_at_unix_ms < test_end`;
3. group retained rows by exact decision timestamp so equal timestamps can never be divided across
   partitions;
4. require enough retained rows to satisfy the explicit raw-row floor in all three partitions;
5. choose the training boundary whose cumulative raw-row count is closest to 60%;
6. choose the validation/test boundary whose cumulative raw-row count is closest to 80%;
7. require the explicit raw-row floor on training, validation, and test.

Ties are resolved deterministically toward the smaller cumulative count.

The resulting single fold is:

- training: `[first_eligible_timestamp, training_cut)`;
- validation: `[training_cut, validation_cut)`;
- test: `[validation_cut, selection_at - horizon)`.

Therefore:

`test_end + horizon_ms == selection_at_unix_ms`.

The first-champion builder's sealed selection chronology gate is satisfied exactly.

## Why the split is chosen before target checks

The planner never:

- searches alternative cut points after seeing validation loss;
- moves a boundary after seeing target values;
- optimizes for returns, PnL, hit rate, action choice, superiority, or champion outcome;
- selects the fold with the best model metrics.

The raw 60/20/20 boundary is fixed from feature timestamps and row counts only.

Only after the fold is frozen does the planner check whether the evidence is sufficient.

If the frozen split is unusable, the planner fails. It does not try another split.

## Leakage quarantine

The planner does not reimplement FL8.3 quarantine.

For every first-champion target/member, it runs sealed
`run_fast_chronological_validation(...)` using the already-frozen policy.

This delegates:

- mint overlap quarantine;
- actor overlap quarantine;
- signature overlap quarantine;
- mature-training target checks;
- post-quarantine non-empty checks;
- canonical prediction population construction

to the sealed FL8.3 implementation.

All five required targets must produce the same:

- raw partition counts;
- post-quarantine partition counts;
- quarantine fingerprint;
- TEST prediction identities.

Any difference fails closed.

## Required target population

The planner reuses the exact internal member tuple used by the sealed #203 first-champion builder:

1. endpoint cost-adjusted return — mean regressor;
2. endpoint raw return — mean regressor;
3. MAE — mean regressor;
4. reversal occurrence — prior classifier;
5. route-unavailability occurrence — prior classifier.

The planner does not maintain a second independently editable target/family list.

Each validation dry-run uses a fixed dependency-free naive training-policy version:

`fl9-first-champion-plan-naive-v1`.

Its model output is not used to choose the split.

## TEST target availability floor

For the exact post-quarantine TEST prediction identities, the planner checks the FL4 row at the
requested horizon for each required target.

For every target:

`test_target_available_count >= minimum_test_scored_observations`.

Missing target values do not become zero, false, or neutral.

In particular, missing route-unavailability evidence is insufficient rather than implicitly
interpreted as route availability.

This pre-check mirrors the evidence floor that #203 will later enforce through FL8.4 TEST
evaluation.

## Selection maturity

The planner excludes evaluation decisions at or after:

`selection_at_unix_ms - horizon_ms`.

This leaves the full target horizon available before the declared selection time.

A decision exactly on the cutoff is intentionally outside validation/TEST. The sealed #203 runtime
refit may still use it if its target is mature at selection, because final runtime training and
independent TEST evaluation have different roles.

## Plan artifact

Schema:

`shreks.fast_first_champion_evidence_plan` v1.

Semantic version:

`fl9-first-champion-evidence-plan-v1`.

The canonical plan binds:

- FL8.1 training-bundle fingerprint;
- feature logical fingerprint;
- feature-source JSONL SHA;
- future-path logical fingerprint;
- explicit horizon;
- explicit selection timestamp;
- explicit raw-partition floor;
- explicit TEST-scored floor;
- eligible pre-selection row count;
- exact chronological validation policy;
- raw and post-quarantine counts;
- FL8.3 quarantine fingerprint;
- five target-evidence entries;
- plan fingerprint.

Each target-evidence entry binds:

- exact target;
- exact model family;
- FL8.3 validation-run fingerprint;
- TEST prediction count;
- TEST target-available count.

## Canonical codec

The plan encoder uses compact sorted UTF-8 JSON with exactly one trailing newline.

There are no floating-point policy values in this schema.

The decoder rejects:

- malformed/non-canonical JSON;
- duplicate keys;
- unknown/missing fields;
- wrong schema/version;
- invalid enums;
- wrong required-member order;
- count inconsistencies;
- target evidence below the explicit floor;
- plan fingerprint mismatch.

The plan can be written/read as one authenticated JSON file.

## TDD provenance

Intentional RED:

`3142ded0eb9056e28fca810a14f54a9358cac175`.

RED matrix:

- Python: expected module-not-found for `shreks_brain.fast_first_champion_plan`;
- Repository safety: GREEN;
- Rust: GREEN;
- ARM64: GREEN.

The first implementation run exposed one fixture mistake: selection time 2300 still left seven
eligible rows, enough to satisfy a 2/2/2 raw partition floor. The negative fixture was corrected to
a selection time that genuinely leaves only five eligible rows. Production planning logic was not
changed.

## Authority boundary

The planner contains no:

- provider/network access;
- SQLite queries;
- wall-clock reads;
- economic superiority test;
- PnL/profit optimization;
- PAPER execution;
- action selection;
- promotion/registry mutation;
- signer;
- transaction submission;
- LIVE mode.

## Following work

After #209 seals, the first-champion host command can be thin and explicit:

1. verify/read #206 proof workspace;
2. build #201 logical bundle;
3. build/read #209 plan using an explicit horizon and captured selection timestamp;
4. decode an explicit #207 hydration policy;
5. call #208 using the #209 validation policy, horizon, selection time, and TEST floor;
6. derive selection reference from the authenticated plan fingerprint;
7. publish machine-readable status.

That leaves no hand-authored fold timestamps in the production proof path.

LIVE remains disabled.
