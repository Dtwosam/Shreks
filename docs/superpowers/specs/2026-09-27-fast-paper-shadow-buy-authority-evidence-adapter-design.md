# Fast PAPER Shadow BUY Authority Persisted-Evidence Adapter — Design

**Date:** 2026-09-27  
**Base main SHA:** `baa1f4caf7ae94aafca636f698a354486f71f1b4`

## Purpose

Add the read-only point-in-time adapter that supplies the existing BUY-authority
producer from already-persisted Fast PAPER/observer evidence and the durable
operator risk-control state.

This slice does not write the BUY-authority record and does not execute PAPER.

## Inputs

The adapter consumes exact current:

- Fast PAPER runtime manifest;
- isolated shadow ledger binding/execution policy/checkpoint/runtime state;
- sealed learned BUY decision evidence and matching feature row;
- existing `FastPaperShadowQuoteReadPolicy`;
- existing observer market/regime/safety read policies;
- existing deterministic comparison execution-economics policy;
- existing quote/USD source directory;
- durable operator risk-control state path;
- release-local `shreks-fast-entry-authority` binary path;
- explicit risk-day start and explicit data/execution-health facts.

## Persisted quote binding

Resolve the exact point-in-time ENTRY/EXIT evidence only through
`resolve_fast_paper_shadow_cycle_input(...)`.

The resolved ENTRY and EXIT quotes must equal the quotes already sealed in the
learned decision evidence. Any drift, ambiguity, staleness, or changed database
history fails closed.

If either exact route is unavailable, return `None`; do not manufacture BUY
economics.

## Entry economics

Use the BUY decision's selected horizon and exact resolved quantities with
`build_fast_champion_entry_execution_evidence(...)`.

The adapter must bind the runtime manifest's exact champion and the explicit
execution-economics policy. It must not duplicate forecast or FL3 formulas.

The resulting exact `FastOfflineEntryExecution` is handed to the already-sealed
BUY-authority producer, which remains the only FL3 max-entry derivation boundary.

## Market and risk facts

Read the exact candidate market window through `ObserverMarketStore.load_window`
at the decision evaluation timestamp and require the runtime quote mint.

Read the exact persisted ENTRY quote through `ObserverCampaignStore.latest_paper_quote`
using the same candidate/provider/probe/taker/amount/slippage identity as the
Fast PAPER quote-read policy. Its timestamp must match the sealed ENTRY quote.

Use:

- candidate liquidity from the exact current market row;
- ENTRY price-impact evidence from the exact persisted ENTRY quote;
- price-impact notional from the exact ENTRY raw quote amount, runtime quote
  decimals, and the already-authenticated quote/USD source record.

No USD rate is invented.

## Regime

Build aggregate regime evidence only through
`ObserverCampaignStore.build_regime_market_window(...)`, then classify only
through `assess_regime(...)`.

Use no future performance/counterfactual evidence. Performance input remains
`None`.

## Operator controls

Read only through `load_operator_risk_control_state(...)`.

A missing/corrupt/symlinked state fails closed. A control update after the
decision evaluation timestamp cannot be backdated into the decision and fails
closed.

The resulting risk environment carries:

- kill switch = explicit global risk halt OR durable operator kill switch;
- operator entry halt = durable operator halt flag;
- no external active-intent claims.

## Provenance

The adapter computes a deterministic SHA-256 source fingerprint over the exact
consumed decision, feature, quote/USD, market, regime, execution-economics, and
operator-control provenance.

It then delegates to
`produce_fast_paper_shadow_buy_authority_source_record(...)`.

## Authority boundary

```text
OBSERVER_DATABASE=READ_ONLY_EXISTING_ADAPTERS
OPERATOR_CONTROL_STATE=READ_ONLY
QUOTE_USD=AUTHENTICATED_EXISTING_SOURCE
BUY_EXECUTION_ECONOMICS=SEALED_CHAMPION_PLUS_FL3
BUY_LEDGER_RISK=SEALED_PRODUCER
BUY_AUTHORITY_RECORD_BUILD=GRANTED
BUY_AUTHORITY_RECORD_WRITE=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
FUTURE_LABELS_COUNTERFACTUALS=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- one public persisted-evidence adapter API/version;
- exact quote resolver reuse and decision-quote drift refusal;
- selected-horizon champion execution-economics reuse;
- exact market liquidity and persisted price-impact hydration;
- exact authenticated quote/USD reuse for impact notional;
- aggregate regime reuse with no performance input;
- durable operator halt/kill-switch propagation;
- deterministic source provenance;
- delegation to the existing BUY-authority producer;
- no source write, execution, scoring, provider network, signing, or LIVE
  authority.

Current main is expected to fail during Python collection because the adapter
module/public API does not exist yet.

## Following slice

After this read-only adapter is sealed, add the smallest write-once adapter cycle
that selects the oldest unexecuted learned BUY, invokes this adapter, and writes
the authenticated BUY-authority source record with restart-safe exact collision
read-back. Then wire that cycle before the existing BUY source publisher in the
supervisor.
