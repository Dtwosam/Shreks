# FL9 Shared PAPER Risk Accounting Facts — Design

**Date:** 2026-09-04

## Status

Design after deterministic comparison catalog merged as
`a8e8b68a449ca48afacc94cd6d9b959d33fea822` (PR #181).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

Real deterministic comparison candidates can diverge in PAPER posture, fills,
realized PnL, drawdown, and loss streak.

Therefore one precomputed `RiskContext` cannot honestly be shared across all
eight candidates.

The repository already has the correct accounting derivation in
`observer_campaign.risk_context`, but those ledger calculations are private to
the observer path. Copying them into FL9 would create two risk-accounting
semantics.

## Purpose

Extract candidate-independent PAPER-ledger accounting facts into one pure
public PAPER helper, then make the existing observer risk builder consume that
same helper unchanged.

This slice does not yet construct deterministic FL9 `RiskContext`. It seals
the shared accounting primitive first.

## API

Add:

`PaperRiskAccountingFacts`

Fields:

- `open_position_count`;
- `aggregate_open_risk_usd`;
- `daily_realized_pnl_usd`;
- `rolling_drawdown_pct`;
- `consecutive_losses`;
- `last_loss_at_unix_ms`.

Add:

`derive_paper_risk_accounting_facts(ledger, day_started_at_unix_ms)`.

## Exact semantics

### Open risk

OPEN positions only.

- count = number of exact OPEN `PaperPosition` values;
- aggregate open risk = sum of `open_cost_basis_usd`.

### Daily realized PnL

Sum `PaperLedgerEntry.realized_pnl_delta_usd` for journal entries whose
`booked_at_unix_ms >= day_started_at_unix_ms`.

The helper does not invent a day boundary. Caller supplies it.

### Rolling drawdown

Preserve the existing observer algorithm exactly:

1. if any OPEN position lacks `unrealized_pnl_usd`, return `None`;
2. start equity at `ledger.starting_cash_usd`;
3. append equity after each journal realized-PnL delta, in ledger sequence;
4. append current equity plus total OPEN unrealized PnL;
5. compute maximum peak-to-current percentage drawdown;
6. if the peak is non-positive or the result is non-finite, return `None`.

Do not substitute the ledger summary field for the journal path: the path is
required for maximum drawdown.

### Consecutive losses

Preserve existing observer semantics:

- use CLOSED positions only;
- sort by `(closed_at_unix_ms, position_id)`;
- scan backward;
- count consecutive positions with negative realized PnL;
- stop at first non-negative close;
- `last_loss_at_unix_ms` is the most recent losing close time.

## Validation

- exact `PaperLedger` required;
- explicit non-negative day-start clock required;
- output dataclass validates non-negative counts/risk and valid optional
  drawdown/loss timestamp.

The helper intentionally does not require
`day_started_at_unix_ms <= ledger.as_of_unix_ms`: an immutable ledger can be
older than the current evaluation clock when no transaction has occurred since
day start. Higher-level risk builders validate their own evaluation clocks.

## Observer refactor

`build_observer_risk_context` must call
`derive_paper_risk_accounting_facts` and produce the same exact tested
`RiskContext` as before.

Remove the private duplicate drawdown/loss-streak functions from observer code.

## Authority boundary

The helper has no:

- market/provider evidence;
- risk thresholds;
- action decisions;
- PAPER execution;
- ledger mutation;
- database/network access;
- promotion;
- signing/submission;
- LIVE authority.

It is a pure read-only derivation from an already-authoritative PAPER ledger.

## TDD

RED first.

Tests prove:

1. existing observer fixture yields count=1, open risk=101, daily realized=-12,
   same exact drawdown, one-loss streak at t=400;
2. unmarked OPEN position yields drawdown `None`;
3. day boundary changes only daily realized selection;
4. newest non-loss closes reset the streak;
5. deterministic repeat;
6. observer builder outputs remain unchanged after refactor;
7. observer source consumes the shared helper and no longer owns duplicate
   drawdown/loss calculations;
8. shared helper source has no provider/risk-policy/PAPER execution/LIVE
   authority.

## Following slice

Build deterministic campaign risk context dynamically from:

- each candidate's actual current `PaperLedger`;
- this shared accounting helper;
- explicit contemporaneous market/risk-environment facts.

Then the comparison evidence binder can share market evidence while account
state remains candidate-specific and authoritative.
