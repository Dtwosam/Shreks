# Fast Lane Learned PAPER Shadow Persisted Quote Resolver — Design

**Date:** 2026-09-26  
**Base main SHA:** `5ef3f110f10942c566c0a07e801e1d3d933b7659`  
**Migration plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Resolve one learned Fast Lane shadow cycle's execution economics strictly from
already-persisted observer quote evidence.

This slice is read-only. It does not fetch providers, mutate observer evidence,
write a PAPER ledger, start a service, or grant PAPER/LIVE execution authority.

## Exact read policy

Add:

`FastPaperShadowQuoteReadPolicy`

Fields:

- `version`;
- `candidate_id`;
- `probe_policy_version`;
- `taker`;
- `slippage_bps`;
- `entry_input_amount_raw`;
- `exit_input_amount_raw`;
- `max_quote_age_ms`;
- ordered `FastPaperShadowReductionRead` values mapping one target exposure
  fraction to one raw base input amount.

The read policy version must exactly equal
`FastPaperRuntimeManifest.route_evidence_version`.

Provider, quote mint, and quote decimals remain sourced from the exact runtime
manifest rather than duplicated in the read policy.

## Resolver

Add:

`resolve_fast_paper_shadow_cycle_input(...)`

Inputs:

- exact runtime manifest;
- exact `FastTrainingFeatureRecord`;
- exact `FastCampaignDecisionPosition`;
- exact quote read policy;
- evaluation timestamp;
- maximum exposure fraction;
- force-sell flag.

Output:

- exact `FastPaperShadowCycleInput`.

## Database authority

The resolver opens only `manifest.observer_database_path` with:

- SQLite URI `mode=ro`;
- `PRAGMA query_only = ON`;
- a bounded connection timeout.

It validates only the fixed columns required from:

- `token_candidates`;
- `token_mint_states`;
- `paper_quote_snapshots`.

It creates no tables and executes no writes.

## Candidate and decimal attribution

The policy's exact `candidate_id` must identify the feature row mint.

Base-token decimals are read from persisted mint-state evidence at or before the
evaluation time. Distinct conflicting decimal values fail closed.

The runtime manifest supplies quote-token decimals.

## Exact quote identity

For each requested quote the resolver matches all of:

- candidate id;
- purpose;
- manifest provider;
- policy probe version;
- input mint;
- output mint;
- taker;
- exact raw input amount;
- slippage bps.

Only rows satisfying:

`decision_observed_at <= quoted_at <= evaluated_at`

and:

`evaluated_at - quoted_at <= max_quote_age_ms`

are eligible.

The resolver selects the maximum eligible `quoted_at_unix_ms`. More than one
matching row at that exact latest timestamp is rejected as ambiguous rather
than broken by database row id.

Missing exact evidence fails closed. A persisted route-unavailable row is valid
and becomes explicit `UNAVAILABLE` shadow quote evidence.

## Price conversion

For executable ENTRY evidence:

`execution_price_quote = normalized_quote_input / normalized_base_output`

For executable EXIT/reduction evidence:

`execution_price_quote = normalized_quote_output / normalized_base_input`

The feature row's exact decision executable entry price is the reference price
for every executable quote.

ENTRY quantities:

- `quoted_base_quantity` = normalized output amount;
- `available_base_quantity` = normalized minimum output amount.

EXIT/reduction quantities:

- `quoted_base_quantity` = normalized input base amount;
- `available_base_quantity` = normalized input base amount.

All conversions use decimal arithmetic first, then require finite positive
float results.

## Reduction evidence

Reduction reads are valid only for OPEN positions. Targets must be strictly
increasing and lower than current exposure.

Each reduction target resolves through its own exact persisted EXIT quote
identity/input amount.

FLAT positions may not carry reduction reads.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
PROVIDER_NETWORK_ACCESS=FORBIDDEN
OBSERVER_DATABASE=READ_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EXECUTION=NOT_GRANTED
SHADOW_LEDGER_EXECUTION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## Following slice

After exact persisted quote resolution is merged, add the separate learned
shadow service entrypoint. That service will consume the canonical feature feed
and this resolver, but it will remain detached from `shreks.target` until a
later explicitly reviewed activation step.
