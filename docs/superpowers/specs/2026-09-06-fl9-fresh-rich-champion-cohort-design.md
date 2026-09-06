# FL9 Fresh Rich Champion Cohort — Design

**Date:** 2026-09-06  
**Base:** `1c75391b273f924865c43089234a46df8a1d40b0`

## Status

Implementation slice after physical #206 proof-workspace seal and production audit of the first 512-decision FL4 population.

The historical 512-decision population is retained as immutable audit evidence only. It must not participate in first-champion training, validation, TEST scoring, final runtime-artifact fitting, or later superiority proof.

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The historical FL4 v1 rows contain strong price/path evidence but were populated before source-backed execution annotations were wired into the production training path:

- `endpoint_cost_adjusted_return_bps` is absent from FL4;
- `route_unavailability_observed` is absent from FL4.

The production training-economics overlay now reconstructs requested-size PumpSwap entry/exit reserve projections and causal fee evidence, and the runtime training bundle already turns that overlay into authenticated FL5 BUY_NOW counterfactual outcomes. However, FL8 forecast training still reads the unannotated FL4 target fields directly.

Separately, the first-champion planner and final runtime-artifact fit currently consider every mature FL4 decision in the bundle. Merely collecting newer evidence would therefore allow the retired historical population to leak back into the champion.

## Goals

1. Project source-backed rich execution targets into the **in-memory runtime training bundle** without mutating historical FL4 rows.
2. Add one explicit fresh-cohort lower timestamp bound to the first-champion host request and evidence plan.
3. Apply that same lower bound to training, validation, TEST, and final runtime-artifact fitting.
4. Keep unknown economics unknown and preserve every existing fail-closed boundary.

## Runtime rich-target projection

`build_fast_training_bundle_from_runtime_sources(...)` already authenticates:

- proof-workspace feature identity;
- canonical FL4 label identity/fingerprint;
- training-economics overlay identity/fingerprint;
- explicit training execution-cost policy;
- exact FL4/overlay decision+horizon joins.

After those checks, the builder may create an in-memory `FuturePathTrainingLabelDataset` projection. SQLite is never updated.

For one exact FL4/overlay row:

### Endpoint cost-adjusted return

Use the existing pure FL5 `BUY_NOW` counterfactual outcome.

When `BUY_NOW.execution_status == EXECUTABLE`, its `return_bps` is exactly:

`(exit_net_quote / entry_total_quote - 1) * 10_000`

which is the sealed FL4 definition of `endpoint_cost_adjusted_return_bps`.

If BUY_NOW is not executable or is unknown, preserve the original FL4 target (normally `None`). Never synthesize zero.

### Route unavailability

Use only explicit requested-size endpoint projection evidence from the authenticated overlay:

- `EXIT_PROJECTION_UNAVAILABLE` -> `True`;
- an actual `exit_projection` -> `False`;
- unsupported venue, missing endpoint/reserve, or otherwise unknown endpoint projection -> preserve original FL4 value / `None`.

Fee availability does not decide route availability. A route projection can be present while fee evidence remains insufficient for cost-adjusted return.

### Fingerprint

Recompute the projected future-path logical fingerprint and let the normal FL8.1 bundle manifest fingerprint bind the projected targets. The original persisted FL4 fingerprint remains unchanged and remains independently authenticated by the overlay source check.

## Fresh cohort boundary

Add required `minimum_decision_observed_at_unix_ms` to the canonical first-champion host request.

The first-champion evidence plan only admits records satisfying:

`minimum_decision_observed_at_unix_ms <= decision_observed_at_unix_ms < selection_at_unix_ms - horizon_ms`

The 60/20/20 planner operates only on that fresh eligible population.

The lower bound is persisted in the evidence plan and therefore participates in its logical fingerprint.

## Final runtime-artifact fit

The first-champion builder currently refits runtime artifacts on every target-mature preselection record. That would reintroduce retired history even when the validation policy starts later.

For first-champion fitting, mature identities must also satisfy the exact earliest training-start boundary from the supplied validation policy.

Therefore the final champion and its validation evidence share the same fresh cohort floor.

## Host semantics

The host request writer requires `--minimum-decision-observed-at-unix-ms` explicitly. There is no default and no inference from historical outcome quality.

The intended production value is captured after the richer-data release is deployed. This guarantees the retired 512-decision population cannot become champion evidence.

## Preserved boundaries

This slice adds no:

- provider/network calls;
- historical DB mutation;
- FL4 overwrite/backfill;
- guessed fee/route evidence;
- strategy thresholds;
- PAPER execution;
- model self-promotion;
- signer/transaction submission;
- LIVE authority.

Missing evidence remains missing. The champion remains fail-closed when any required target has insufficient TEST evidence.

## Verification

Required coverage:

1. runtime bundle projects PumpSwap source-backed cost-adjusted and route targets while persisted FL4 remains unchanged;
2. unsupported/missing economics remains `None`;
3. projected future-path fingerprint differs when rich target values differ;
4. first-champion plan excludes every pre-cohort decision;
5. final runtime artifact excludes every pre-cohort decision;
6. host request codec/writer requires and fingerprints the cohort floor;
7. existing Python/Rust/repository-safety/native ARM64 gates remain green.

LIVE remains disabled.

## Implementation seal

Implementation PR #225 merged as `dcd06ecdaa50e09fb928b5f4ed37d37f379da2ff` after CI run `34003907152` passed all required gates:

- Python: 3,193 tests passed;
- Rust workspace: GREEN;
- repository safety: GREEN;
- native ARM64 release verification: GREEN.

This follow-up commit exists only to create the repository-standard `seal:` main commit required by the automatic immutable ARM64 release workflow. No implementation semantics are changed by this documentation seal.
