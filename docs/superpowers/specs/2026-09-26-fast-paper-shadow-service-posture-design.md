# Fast PAPER Shadow Service Durable Posture Hook — Design

**Date:** 2026-09-26  
**Base main SHA:** `37652166fbdea48abe0dd28635cbdac021f21284`

## Purpose

Allow execution-aware orchestration to evaluate learned decisions against an
explicit authenticated durable `FLAT/OPEN` posture instead of forcing every
supervised shadow decision to FLAT.

The original service entrypoint intentionally hard-coded FLAT while no isolated
ledger/posture authority existed. That authority now exists and is
restart-safe. Continuing to hard-code FLAT after an isolated BUY would create
stale learned decisions.

This slice adds only an explicit posture resolver hook. It does not itself load
or mutate the isolated ledger and does not enable execution.

## Contract

Extend `run_fast_paper_shadow_service_cycle(...)` with optional:

`position_resolver: Callable[[FastTrainingFeatureRecord], FastCampaignDecisionPosition] | None`

Semantics:

- `None` preserves the existing decision-only FLAT behavior exactly;
- when supplied, the resolver is called once for each feature record before
  quote-cycle resolution;
- the resolver result must be exact `FastCampaignDecisionPosition`;
- that exact position is passed to
  `resolve_fast_paper_shadow_cycle_input(...)`;
- invalid resolver output or resolver failure fails the row/cycle closed before
  decision commit;
- the service policy still carries no position, quantity, or ledger authority.

The hook deliberately accepts already-authenticated posture authority rather
than querying ledger state itself. A following orchestration slice may bind it
to `fast_paper_shadow_decision_position(...)` from the execution bootstrap.

## Reduction evidence

This hook does not manufacture REDUCE quote quantities. Existing service
`reduction_reads=()` behavior remains unchanged. Exact target-specific
persisted reduction evidence is a separate authority problem.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
DEFAULT_SHADOW_POSTURE=FLAT_UNCHANGED
OPTIONAL_POSTURE_AUTHORITY=EXPLICIT_CALLER_ONLY
SHADOW_LEDGER_READ=NOT_ADDED
SHADOW_LEDGER_MUTATION=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- optional exact posture resolver on the service cycle;
- default FLAT compatibility;
- exact supplied OPEN posture propagation;
- invalid supplied posture refusal before commit;
- no position fields added to service policy;
- no ledger/executor/scoring/provider/LIVE authority added.

Current main is expected to fail because the service cycle does not accept the
new `position_resolver` keyword.
