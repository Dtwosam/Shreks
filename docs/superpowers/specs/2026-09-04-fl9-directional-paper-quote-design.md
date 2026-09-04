# FL9 Directional PAPER Quote Evidence — Design

**Date:** 2026-09-04

## Status

Correction after immutable comparison evidence bundle merge
`240d22dbda0a316220ae8ef3deae11a811a7276d` (#184).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The deterministic comparison path originally carried one generic PAPER quote per event row.

That is safe only while all compared candidates share one posture.

Real chronological comparison does not preserve that condition. After different prior decisions/fills, one candidate can be FLAT while another is OPEN on the same FL8.1 event.

The observer already stores Jupiter quote evidence directionally:

- ENTRY: quote asset -> candidate token;
- EXIT: candidate token -> quote asset.

Those routes have different input amounts, output amounts, execution prices, price impact, route availability, and capacity meaning.

Using one quote for both BUY and HOLD/REDUCE/SELL would therefore create false execution evidence.

## Corrected runtime contract

`FastDeterministicCampaignPaperEvidence` gains optional:

- `entry_quote`;
- `exit_quote`.

The existing `quote` field remains only as a mutually exclusive compatibility path for already-sealed fixture/static callers.

Rules:

- legacy `quote` cannot coexist with directional quotes;
- BUY consumes only `entry_quote` in directional mode;
- HOLD/REDUCE/SELL consume only `exit_quote`;
- SKIP consumes neither;
- missing required direction fails closed.

Dynamic candidate-ledger risk behavior is unchanged.

## Corrected comparison-row contract

`FastDeterministicComparisonEvidenceRow` supports either:

1. legacy single quote; or
2. directional quote mode.

Directional comparison mode requires both ENTRY and EXIT quotes because candidate posture may differ at runtime.

Both quotes independently require:

- exact mint/quote-mint attribution;
- decision clock <= quote clock <= evaluation clock.

The binder copies both directions into every candidate campaign row.

## Same-population matrix invariant

All candidates must share, positionally:

- FL8.1 row;
- source identity;
- state version;
- evaluation clock;
- legacy quote if legacy mode is used;
- ENTRY quote;
- EXIT quote;
- MarketRegime;
- dynamic risk environment.

Strategy evidence, entry authority, decisions, fills, and candidate-ledger account state may still diverge.

## Immutable bundle supersession

No real FL9 comparison bundle existed when the ambiguity was found.

Therefore bundle schema v1 is superseded before economic evidence is collected.

`FAST_DETERMINISTIC_COMPARISON_BUNDLE_SCHEMA_VERSION = 2`.

V2:

- forbids legacy single-quote rows;
- requires explicit ENTRY and EXIT quotes;
- stores them separately in the canonical sidecar;
- uses separate `entry_quote_source_version` and
  `exit_quote_source_version` provenance.

A v1 bundle is not valid FL9 superiority evidence.

## Observer mapping boundary

The following hydrator may map persisted observer ENTRY/EXIT evidence into the two directional campaign quote records, but it must preserve direction and raw provenance.

It must not:

- infer EXIT capacity from an ENTRY quote;
- use forecast prices as PAPER fills;
- swap ENTRY/EXIT identities when one direction is unavailable;
- manufacture a route when the persisted route is unavailable.

## Authority boundary

This correction adds no provider/network/database reads, execution authority, superiority evaluation, promotion, signing/submission, or LIVE authority.

## TDD

Intentional RED:
`190fa2542caf082e56b91c6951c694b361176556`.

Tests require:

1. BUY selects ENTRY quote;
2. OPEN actions select EXIT quote;
3. SKIP consumes neither;
4. legacy and directional modes are mutually exclusive;
5. bundle v2 rejects legacy rows;
6. bundle v2 round-trips separate quote directions and source provenance;
7. matrix preflight locks both directions.

## Following slice

Build the point-in-time observer/evidence hydrator on the v2 directional bundle contract, then produce non-fixture evidence over a real chronological FL8.1 population.

Only real candidate + deterministic PAPER runs may feed the sealed FL9 superiority evaluator.
