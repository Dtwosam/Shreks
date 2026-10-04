# V1 First-Champion Tradable-Universe Preselection Design

**Date:** 2026-10-04  
**Base main SHA:** `39985879d2c69d19e70fc086c4b5127e1af02418`  
**Status:** DESIGN — implementation authority only; no champion retry, Fast PAPER shadow, cutover, signing/submission, or LIVE authority

## Incident that motivates this slice

The consumed context-resolution retry reached the authorized V1 first-champion runner and failed closed during historical forecast-context hydration:

`observer candidate not found at point-in-time boundary`.

Read-only production evidence proved the failing decision was internally coherent:

- canonical FastEvent venue: `pump_swap`;
- future-path decision venue: `pump_swap`;
- matching canonical PumpSwap source evidence;
- verified `pump_fun_bonding_curve -> pump_swap` graduation before the decision;
- no PumpSwap observer candidate or exact PumpSwap market snapshot existed at the decision boundary.

The row was therefore valid FastEvent/FL4 evidence but lacked the point-in-time market evidence required by the already-sealed FL9 tradable-universe policy.

The current V1 first-champion plan preselects only by timestamp. It therefore admits rows that the sealed input-side tradable-universe policy would reject, and the mismatch is discovered much later during hydration.

## Goal

Add one deterministic, immutable, input-only preselection artifact for the score-free V1 first-champion chain.

The artifact must:

1. apply the existing `fl9-tradable-universe-v1` policy to V1 feature identities before chronological partitioning;
2. authenticate the exact accepted decision identities;
3. bind the candidate/snapshot identity selected by that policy for every accepted decision;
4. make every later training-bundle rebuild consume exactly that accepted identity population;
5. make context hydration consume the authenticated candidate binding instead of re-resolving candidate identity through a different rule;
6. remain outcome-neutral and target-blind.

## Non-goals

This slice does not:

- change liquidity, volume, freshness, migration, or venue thresholds;
- change forecast targets, model families, features, training policy, chronological split logic, TEST evaluation, champion selection, or economics projection;
- backfill historical observer evidence;
- invent or mutate token candidates;
- reinterpret a bonding-curve candidate as PumpSwap authority;
- inspect target values or model performance while choosing the cohort;
- authorize any new physical champion invocation;
- authorize Fast PAPER shadow, cutover, promotion, signing/submission, or LIVE.

## Source-of-truth eligibility

The only eligibility policy is the existing:

`Fl9TradableUniverseStore.assess(..., policy=Fl9TradableUniversePolicy())`.

No parallel candidate-only eligibility rule is introduced.

An accepted decision must therefore have, at the historical decision boundary:

- decision venue exactly `pump_swap`;
- verified Pump graduation known by the boundary;
- deterministically resolved candidate identity under the sealed FL9 policy;
- exact PumpSwap DexScreener snapshot no later than the boundary and no older than 60 seconds;
- liquidity at least $3,000;
- trailing 24-hour volume at least $1,000.

Missing, stale, ambiguous, contradictory, or below-threshold evidence remains ineligible.

## New immutable artifact

Schema:

`shreks.fast_first_champion_tradable_preselection`, version `1`.

Directory:

```
<artifact>/
  accepted.jsonl
  manifest.json
```

Each accepted row contains only input-side identity/provenance:

- `decision_signature`
- `decision_ordinal`
- `decision_sequence`
- `mint`
- `quote_mint`
- `venue`
- `decision_observed_at_unix_ms`
- `candidate_id`
- `snapshot_row_id`
- `assessment_fingerprint_sha256`

The manifest binds:

- schema/version;
- FL9 policy version and fingerprint;
- proof-workspace artifact fingerprint;
- feature-source JSONL SHA-256;
- minimum decision timestamp;
- observer database and WAL SHA-256 observed during artifact construction;
- assessed row count;
- eligible row count;
- canonical eligibility reason counts;
- accepted identity fingerprint;
- candidate-binding fingerprint;
- all-assessment evidence fingerprint;
- `accepted.jsonl` SHA-256;
- artifact fingerprint.

The artifact is immutable and refuses overwrite.

## Observer snapshot binding

The preselection is valid only for the exact observer database/WAL snapshot
against which its point-in-time assessments were constructed.

The canonical host-request writer must reject the preselection unless:

- the current observer database SHA-256 equals the preselection manifest;
- WAL presence/absence and SHA-256 equal the preselection manifest.

The host runner repeats the same equality check before capturing the selection
clock or building the chronological plan. Any database or WAL drift therefore
invalidates the preselection and requires a fresh preselection plus fresh host
request. It must not be silently re-assessed inside the consumed request.

Operationally, preselection construction, request creation, and the eventual
authorized host invocation must therefore use one deliberately stable observer
snapshot (for example, within a separately reviewed bounded quiescence/input
preparation ceremony).


## Selection bounds

The preselection artifact is not allowed to use the future host selection clock.

It assesses feature rows satisfying:

`decision_observed_at_unix_ms >= minimum_decision_observed_at_unix_ms`.

The later V1 evidence plan keeps the existing runtime selection boundary:

`decision_observed_at_unix_ms < selection_at_unix_ms - horizon_ms`.

Thus preselection is a target-blind superset of the final time-bounded cohort. The host run intersects accepted identities with the existing mature-time bound before building the plan.

## Candidate identity semantics

The preselection artifact records the `candidate_id` returned by the sealed FL9 tradable-universe assessment.

This matters because migrated PumpSwap sampling may legitimately reuse an existing candidate identity. Candidate-row `venue` is not independently promoted to market authority.

Historical market venue is authenticated by the exact market snapshot used by the FL9 policy.

Context hydration for this first-champion path must therefore use the preselection candidate binding for exit-quote identity. It must not re-resolve the candidate with a stricter `required_venue=record.venue` constraint.

The existing generic hydration API may retain its legacy resolver behavior when no authenticated preselection binding is supplied.

## Training population enforcement

The accepted identities must be enforced at every V1 bundle build:

1. host run before evidence-plan construction;
2. preparation before hydration;
3. nested first-champion file request before fitting/evaluation.

`build_fast_training_bundle_from_runtime_sources` gains an optional exact decision-identity restriction. When supplied:

- every requested identity must exist in the selected horizon economics overlay;
- the selected overlay rows, feature rows, future-path labels, and counterfactual provenance must reconcile exactly to the requested identity set;
- no non-selected identity may enter the returned bundle.

The unrestricted behavior remains unchanged for existing callers.

## Request and artifact binding

The V1 host request gains:

- `tradable_preselection_path`
- `expected_tradable_preselection_artifact_fingerprint_sha256`

The nested first-champion file request gains the same authenticated preselection input.

The host-run and preparation manifests bind at least:

- preselection artifact fingerprint;
- accepted identity fingerprint;
- candidate-binding fingerprint.

The host-run copies the preselection artifact into its immutable output. Preparation copies the same artifact into its immutable output before constructing hydration/fitting evidence.

Strict readers verify the copied artifact and all fingerprints.

## Hydration binding

The first-champion preparation passes the accepted decision -> candidate ID map to context hydration.

For every hydrated decision identity:

- the identity must be present in the authenticated preselection;
- the record mint/quote/venue/timestamp must equal the accepted identity exactly;
- the candidate ID must be positive;
- the preselection database/proof bindings must reconcile with preparation inputs.

No decision absent from preselection may produce a hydration context.

The generic hydration artifact schema remains unchanged. Candidate-binding authority is authenticated at the preparation-chain boundary instead: the preparation manifest binds the preselection artifact fingerprint and candidate-binding fingerprint, and strict preparation/host readback proves the hydration child belongs to that exact chain. This prevents reopening the context/champion chain against a different accepted population without forcing a generic hydration schema migration.

## Failure behavior

Fail closed on:

- preselection proof-workspace mismatch;
- preselection feature-source mismatch;
- policy fingerprint mismatch;
- duplicate accepted identity;
- accepted row with missing candidate/snapshot binding;
- requested bundle identity absent from economics/FL4/features;
- extra bundle identity outside preselection;
- hydration identity absent from preselection;
- copied preselection drift;
- source mutation during preselection construction;
- any existing destination/staging residue.

No fallback to unfiltered V1 population is permitted.

## Regression case from the consumed incident

Tests must include a decision with:

- valid PumpSwap FastEvent/feature identity;
- verified PumpSwap migration;
- no point-in-time PumpSwap candidate/snapshot;
- only a prior bonding-curve candidate.

Expected behavior:

`preselection_reason != eligible`

and the identity must be absent from:

- the filtered bundle;
- the chronological plan;
- hydration population;
- nested champion fitting/evaluation.

The failure must occur during preselection construction/inspection, before expensive champion preparation.

## Compatibility boundary

Existing callers that do not opt into the new decision-identity restriction keep current bundle behavior.

The score-free production V1 host writer/run path must require the new preselection artifact after this schema/version change. Old V1 request bytes remain historical evidence and are not silently reinterpreted.

## Authority boundary

This implementation creates no retry authority.

After implementation, tests, review, merge, exact release build, and deployment, a new separately reviewed authority seal is still required before any physical champion runner invocation.

Until then:

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_CONTEXT_RESOLUTION_RETRY_AUTHORITY=CONSUMED_FAILED_HISTORICAL_PUMPSWAP_COVERAGE_GAP
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```
