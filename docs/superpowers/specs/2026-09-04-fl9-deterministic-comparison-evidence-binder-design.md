# FL9 Deterministic Comparison Evidence Binder — Design

**Date:** 2026-09-04

## Status

Design after:

- deterministic comparison catalog merge `a8e8b68a449ca48afacc94cd6d9b959d33fea822` (#181);
- shared PAPER risk-accounting merge `fb197845d734dcce053e5e1940aa06d9c9b85d29` (#182).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The sealed FL9 matrix can compare candidate runs only when each candidate sees the same immutable FL8.1 event population and the same contemporaneous market/PAPER facts.

The eight deterministic candidates can nevertheless diverge after the first decision:

- entry family;
- manager family;
- actions;
- fills;
- open positions;
- realized PnL;
- drawdown;
- loss streak.

Therefore account-state risk facts cannot be precomputed once and shared across candidates.

## Runtime risk boundary

Add `FastDeterministicCampaignRiskEnvironment` for candidate-independent facts:

- trading capital;
- explicit day-start clock;
- liquidity;
- expected price impact plus its notional;
- market-observation clock;
- data/execution health;
- kill switch;
- active-intent keys;
- operator entry halt.

Add pure:

`build_fast_deterministic_campaign_risk_context(ledger, environment, as_of_unix_ms=...)`

It combines the shared environment with the sealed shared
`derive_paper_risk_accounting_facts(...)` helper.

Immediately before a deterministic BUY is materialized, the chronological runner uses:

- starting ledger before the first step; or
- the candidate's authoritative current `latest_result.final_ledger`.

This creates the BUY `RiskContext` at the evidence evaluation clock.

Static `RiskContext` remains accepted for already-sealed fixture/test paths, but one evidence bundle cannot carry both a static context and a dynamic environment.

## Binder row

`FastDeterministicComparisonEvidenceRow` contains one exact FL8.1 record plus explicit evidence for all six FL6 component families:

Entry:
- Impulse Scalp;
- Micro Pullback;
- Pre-Graduation;
- Graduation Flow.

Manager:
- Wallet Cohort;
- Longer Runner.

It also carries shared:
- state version;
- evaluation clock;
- contemporaneous directional PAPER ENTRY and EXIT quotes;
- MarketRegime;
- dynamic risk environment.

Entry authority is keyed by exact catalog candidate version because execution authority may legitimately differ by candidate.

## Chronology

Before binding, require:

- evidence evaluation time >= FL8.1 decision time;
- quote mint/quote-mint attribution equals FL8.1;
- decision time <= quote time <= evaluation time;
- decision time <= market-risk observation time <= evaluation time;
- risk day start <= evaluation time.

No wall-clock read is allowed.

## Exact catalog coverage

Every row must contain entry authority for the exact eight catalog versions, in catalog lexical order, once each.

For each catalog manifest, the binder selects:

- FLAT evidence from its authenticated entry family;
- OPEN evidence from its authenticated manager family;
- the same FL8.1 record;
- the same quote/regime/risk environment;
- that candidate's explicit entry authority.

The resulting eight `FastDeterministicCandidateCampaignSpec` values preserve catalog order and are passed to the already-sealed same-population matrix.

## Same-population matrix rule

The matrix continues to permit candidate-specific:

- strategy evidence;
- static/dynamically resolved RiskContext;
- entry authority;
- decisions/fills/ledger outcomes.

It requires shared:

- FL8.1 record population;
- source identity;
- state version;
- evaluation clock;
- legacy quote when compatibility mode is used;
- ENTRY quote;
- EXIT quote;
- market regime;
- dynamic risk environment.

## Authority boundary

This slice has no:

- provider/network/DB access;
- hidden wall clock;
- strategy threshold selection;
- superiority evaluation;
- direct PAPER buy/sell execution;
- promotion;
- signing/submission;
- LIVE authority.

It binds explicit evidence and delegates to existing sealed components.

## TDD

Intentional RED began at `129b4e84dca9efcd21dd9eda5602b65278e8cf50` with missing binder API.

After #182 was identified as a prerequisite, the branch was merged forward from main and the RED contract was tightened to require candidate-ledger dynamic risk.

Tests prove:

1. exact eight-candidate expansion;
2. exact entry/manager evidence-family selection;
3. shared directional ENTRY+EXIT quote/record/risk environment;
4. exact catalog authority coverage;
5. stale/non-contemporaneous quote rejection;
6. wrapper delegates only to the sealed matrix;
7. a BUY after a completed prior round trip derives risk from that candidate's updated ledger;
8. no provider/superiority/direct execution/LIVE authority.

## Following slice

Seal this binder, then build the immutable real FL8.1 comparison evidence bundle/loader that supplies non-fixture chronological rows to the eight deterministic candidates and the learned candidate before invoking the existing FL9 superiority evaluator.
