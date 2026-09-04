# FL9 Deterministic Campaign PAPER Evidence Selector — Design

**Date:** 2026-09-04

## Status

Design after chronological deterministic campaign driver merged as
`022e4de7e6dc210b7019721ab6055e89a0bab6d6` (PR #178).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The sealed campaign PAPER executor intentionally validates evidence by the
**actual decision action**:

- SKIP must carry no quote/risk/entry/regime evidence;
- BUY requires quote + RiskContext + entry authority + MarketRegime;
- HOLD/REDUCE/SELL require quote and reject BUY-only risk/entry/regime fields.

The chronological campaign driver currently asks callers to prebuild one final
`FastCampaignPaperDecisionEvidence` before the Rust row decision is known.

That cannot safely represent a general real campaign:

- a rich row with quote/risk/entry context would fail if Rust returns SKIP;
- an empty row suitable for SKIP would fail if Rust returns BUY;
- different candidates can return different actions on the same immutable row.

The solution must not weaken the sealed PAPER executor.

## Design

Add an immutable pre-decision evidence bundle:

`FastDeterministicCampaignPaperEvidence`

Fields:

- `source_event_id`;
- `state_version`;
- `evaluated_at_unix_ms`;
- optional exact `FastCampaignPaperQuoteEvidence`;
- optional exact `RiskContext`;
- optional exact `FastCampaignPaperEntryAuthority`;
- optional exact `MarketRegime`.

This bundle is explicit contemporaneous evidence, not a PAPER execution result.

It may contain a superset because the final action is not known yet.

## Action-aware materialization

Add pure:

`materialize_fast_deterministic_campaign_paper_evidence(decision, evidence)`

It returns exact sealed `FastCampaignPaperDecisionEvidence`.

Rules mirror the already-sealed executor contract without changing it:

### SKIP

Return:

- same source identity/state/evaluated clock;
- quote = null;
- risk = null;
- entry authority = null;
- regime = null.

Existing raw evidence is not interpreted; unused fields are omitted from the
action-specific sealed evidence.

### BUY

Require raw:

- quote;
- RiskContext;
- entry authority;
- MarketRegime.

Return all four unchanged.

Missing required evidence fails closed before PAPER replay.

### HOLD / REDUCE / SELL

Require raw quote.

Return:

- quote unchanged;
- BUY-only risk/entry/regime = null.

Missing quote fails closed before PAPER replay.

### Unsupported action

Fail closed.

## Chronological driver integration

Change `FastDeterministicCampaignRow.paper_evidence` to the new pre-decision
bundle.

After the authenticated Rust decision returns:

1. materialize action-specific sealed PAPER evidence;
2. call `apply_fast_deterministic_paper_session_step(...)`.

This preserves actual-action authority and makes the campaign row reusable for
different candidate actions.

## Same-population implication

This seam enables the next candidate-matrix slice to share the same
contemporaneous row evidence across candidates even when their actions differ.

The matrix can compare exact FL8.1 population and raw quote/context provenance,
while each candidate receives only the action-compatible subset accepted by the
sealed PAPER executor.

## Authority boundary

The selector:

- does not acquire quotes;
- does not calculate risk;
- does not change prices or quantities;
- does not decide actions;
- does not execute PAPER fills;
- does not alter ledger/evaluation logic;
- does not compare candidates;
- does not launch processes;
- has no runtime execution authority.

It only projects explicit contemporaneous evidence into the sealed
action-specific shape.

## TDD

RED first.

Tests prove:

1. rich raw evidence + SKIP materializes to all-null execution fields;
2. rich raw evidence + BUY preserves all exact fields;
3. BUY missing any required field fails closed;
4. rich raw evidence + HOLD/REDUCE/SELL preserves quote only;
5. position action missing quote fails closed;
6. source identity/clock are preserved exactly;
7. chronological campaign can use the same rich row evidence when row 1 BUY
   fails and row 2 remains FLAT;
8. a fake SKIP with rich raw evidence is accepted by sealed PAPER replay;
9. selector/driver contain no direct PAPER execution or external authority.

## Following slice

Build the deterministic candidate matrix over identical FL8.1 rows and shared
raw contemporaneous PAPER evidence, collect each final sealed
`FastPolicyRunEvidence`, prove same population, and pass baseline runs to the
existing FL9 superiority evaluator.
