# Fast PAPER Shadow BUY Writer Multi-Horizon Economics — Design

**Date:** 2026-09-27  
**Base main SHA:** `f3ddfd26b56e2d08586f3ee96efd1390b44c9649`

## Purpose

Remove the remaining single-horizon assumption from the restart-safe learned
shadow BUY-authority writer.

The learned action policy already permits multiple forecast horizons. A BUY can
therefore select any horizon sealed into
`FastPaperRuntimeManifest.action_policy.horizons_ms`. The current writer
accepts one `FastDeterministicComparisonExecutionPolicy`, which would fail
closed whenever a valid learned BUY selected another horizon.

This slice makes the writer's execution-economics authority complete for the
active learned action policy before supervisor deployment wiring.

## Input contract

Replace the single writer input:

`execution_economics_policy`

with:

`execution_economics_policies:
tuple[FastDeterministicComparisonExecutionPolicy, ...]`.

The tuple is explicit authority, not a fallback list.

## Coverage rules

Before reading or deriving BUY authority, require:

- a non-empty exact tuple;
- every item is exact `FastDeterministicComparisonExecutionPolicy`;
- horizon values are unique;
- the set of policy horizons equals exactly
  `manifest.action_policy.horizons_ms`;
- no extra horizon and no missing horizon is permitted.

Policy order is not authority and may differ from the action-policy horizon
order.

## Decision selection

For an oldest pending BUY:

- require `decision.selected_horizon_ms` to be non-null;
- select the unique execution-economics policy with that exact horizon;
- pass only that exact policy to the existing persisted-evidence adapter.

No nearest horizon, first policy, default policy, or fallback selection is
allowed.

## Authority boundary

```text
LEARNED_HORIZON_AUTHORITY=ACTIVE_ACTION_POLICY_ONLY
EXECUTION_ECONOMICS=EXPLICIT_EXACT_HORIZON_MAP
HORIZON_FALLBACK=FORBIDDEN
BUY_AUTHORITY_DERIVATION=EXISTING_ADAPTER_ONLY
BUY_AUTHORITY_WRITE=UNCHANGED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- the public writer API to accept the horizon-policy tuple;
- exact full action-policy horizon coverage;
- duplicate horizon rejection;
- missing/extra horizon rejection;
- exact matching policy delegation for the learned BUY horizon;
- removal of the singular economics-policy authority parameter.

Current main is expected to fail the new writer horizon contract because it
accepts only one execution-economics policy.

## Following slice

Create one fingerprinted, score-free BUY-writer deployment policy artifact that
contains the exact horizon-policy tuple plus market/regime/safety policy,
operator-control path, release-local FL3 binary identity, risk-day start, and
explicit health/global-halt facts. Load it at supervisor bootstrap and invoke the
BUY-authority writer immediately before the existing BUY source publisher.
