# FL9 Point-in-Time Comparison Evidence Hydrator — Design

**Date:** 2026-09-04

## Status

Implementation slice after deterministic FL3 entry-authority merge
`a2d8919a7d675405d414e749ae1e241dfba90f59` (#186).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

The sealed FL9 comparison path can already:

- evaluate the exact FL8.1 chronological population;
- replay the eight authenticated deterministic FL6 candidate combinations;
- execute decisions through the same deterministic PAPER campaign;
- preserve directional ENTRY/EXIT quote evidence;
- derive PAPER entry authority through sealed FL3;
- write an immutable v2 comparison evidence bundle.

The missing seam is real point-in-time hydration.

This slice adds one strict Python hydrator that converts approved historical observer evidence plus explicit economic/context evidence into exact `FastDeterministicComparisonEvidenceRow` + provenance values.

It does not evaluate superiority.

## Inputs

The hydrator consumes:

- one exact `FastTrainingFeatureDataset`;
- the exact deterministic comparison catalog;
- one positional hydration input per FL8.1 row;
- a read-only observer database path;
- the explicit offline `shreks-fast-entry-authority` binary path.

Each hydration input contains only decision-time or explicitly point-in-time evidence:

- exact source event identity;
- observer candidate id;
- state version;
- evaluation clock;
- exact observer ENTRY quote identity;
- exact observer EXIT quote identity;
- explicit quote-asset mint/decimals/USD conversion;
- FL6.1 Impulse Scalp evidence;
- FL6.2 Micro Pullback evidence;
- FL6.3 Pre-Graduation evidence;
- FL6.4 Graduation Flow evidence;
- FL6.5 Wallet Cohort evidence;
- FL6.6 Longer Runner evidence;
- MarketRegime;
- shared deterministic risk environment;
- named source versions for forecast/horizon, execution costs, exit capacity, wallet evidence, graduation context, continuation forecast, regime, and risk environment.

No future label type is accepted.

## Observer reads

The hydrator uses the existing read-only `ObserverCampaignStore`.

For each FL8.1 row it loads as-of the explicit evaluation clock:

1. latest Helius token decimals for the exact observer candidate + mint;
2. latest persisted observer ENTRY quote for the exact supplied identity;
3. latest persisted observer EXIT quote for the exact supplied identity.

The store already guarantees:

- read-only database open;
- exact candidate-mint attribution;
- exact quote identity matching;
- `quoted_at_unix_ms <= as_of_unix_ms`;
- canonical raw u64 quote amounts.

Hydration adds the stronger FL9 chronology rule:

`decision_observed_at <= quote_observed_at <= evaluated_at`.

Missing decimals or either quote direction fails closed.

## Directional quote reconstruction

The hydrator reconstructs `FastCampaignPaperQuoteEvidence` directly in the FL8.1 quote denomination.

### ENTRY

Observer route:

`quote asset -> candidate token`

Compute:

- quote input quantity from raw ENTRY identity input amount + explicit quote-asset decimals;
- token output quantity from raw observer output amount + historical token decimals;
- execution price quote = quote input quantity / token output quantity;
- quoted/available base quantity = token output quantity.

### EXIT

Observer route:

`candidate token -> quote asset`

Compute:

- token input quantity from raw EXIT identity input amount + historical token decimals;
- quote output quantity from raw observer output amount + explicit quote-asset decimals;
- execution price quote = quote output quantity / token input quantity;
- quoted/available base quantity = token input quantity.

The quote reference price is the exact FL8.1 decision executable entry price. The USD bridge is the explicit quote-asset USD rate.

Unavailable persisted routes remain exact `PaperQuoteState.UNAVAILABLE` with no invented price/capacity fields.

ENTRY and EXIT directions are never substituted for one another.

## Same-execution-economics invariant

All four FL6 entry families on one FL8.1 row must use:

- all execution evidence absent; or
- the exact same `FastOfflineEntryExecution`.

Partial presence fails closed.

Any difference in:

- forecast exit price;
- forecast horizon provenance;
- cost model;
- intended base quantity;
- executable entry price;
- exit capacity;
- required edge;
- risk margin

must not be hidden behind family-specific inputs.

This makes the FL6 entry comparison a strategy-rule comparison on identical economic evidence rather than a comparison of different forecasts/costs.

## Risk/quote provenance

When the persisted ENTRY route is executable and carries price-impact evidence:

- `risk_environment.expected_price_impact_pct` must exactly match the observer ENTRY quote impact;
- `risk_environment.price_impact_notional_usd` must match the exact ENTRY quote input notional after quote-asset decimal/USD conversion.

If the route or impact evidence is absent, risk impact fields may not fabricate it.

All other risk-environment fields remain explicit shared evidence and are later combined with each candidate's own PAPER ledger accounting by the already-sealed dynamic risk-context builder.

## PAPER entry authority

If shared entry execution evidence exists, the hydrator calls only:

`derive_fast_deterministic_entry_authority_offline(...)`

for the exact FL8.1 record + shared execution evidence.

The resulting authority is attached to every catalog candidate because every entry family shares the same FL3 economic inputs in this hydration contract.

If FL3 returns no BUY authority because the maximum acceptable entry is already below the decision price, all candidates receive `None`.

If shared execution evidence has exit capacity below intended base quantity, the authority adapter also returns `None`, matching FL6's sealed `InsufficientExitCapacity` SKIP semantics instead of aborting hydration.

Any later deterministic BUY without authority still fails closed in PAPER execution.

## Provenance

Hydration emits one `FastDeterministicComparisonEvidenceProvenance` per row.

Directional quote sources are derived from the exact persisted observer identities:

- `observer:<provider>:<probe_policy_version>:entry`;
- `observer:<provider>:<probe_policy_version>:exit`.

Entry authority source is fixed to:

`fl3-execution-economics-v1`.

Forecast/cost/capacity/wallet/graduation/continuation/regime/risk source versions remain explicit caller-supplied identities and are validated against evidence presence.

## Output

`FastDeterministicComparisonHydrationResult` contains:

- hydration contract version;
- exact comparison rows;
- exact positional provenance rows.

Those outputs feed the already-sealed v2 immutable comparison bundle writer.

The hydrator itself does not write the bundle so evidence hydration and immutable artifact creation remain separate auditable seams.

## Authority boundary

The hydrator has no:

- provider/RPC/network client;
- database write path;
- hidden wall clock;
- future-label/counterfactual input;
- direct PAPER fill execution;
- superiority evaluation;
- model promotion;
- signing/submission;
- LIVE authority.

## TDD

Intentional RED:

`f906144d2a5c712ba6dd8a8fe4e309d3f5f35987`.

Tests require:

1. actual read-only observer store integration;
2. historical token-decimal hydration;
3. directional ENTRY price reconstruction;
4. directional EXIT price/capacity reconstruction;
5. eight catalog authorities derived through the FL3 adapter;
6. exact quote source provenance;
7. shared execution-economics enforcement;
8. source population mismatch rejection;
9. risk impact mismatch rejection;
10. source firewall.

## Following slice

Run this hydrator against a real FL8.1 chronological feature population using explicit production research forecast/cost/capacity context, write the immutable v2 evidence bundle, then execute the eight-candidate deterministic PAPER matrix.

Only after those sealed PAPER results exist may the FL9 superiority evaluator run.
