# FL9 Evidence Campaign PAPER Executor — Design

**Date:** 2026-09-04

## Status

Design for the next FL9 evidence slice after the campaign decision seam was SEALED.

Base: merged-main `2c16b293815e0f62082f3956633613b911fb8227`, merged-main CI `33817924405` four-gate GREEN.

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Turn a sealed Rust campaign decision batch into one real, replayable Fast PAPER candidate run using only explicit contemporaneous execution evidence and existing sealed PAPER/risk/accounting logic.

The output must be directly consumable by the SEALED FL9 superiority proof.

This slice establishes the learned-candidate PAPER side first. The following slice will run each required FL6 deterministic baseline through the exact same executor and identical event/quote population.

## Non-goals

This slice does **not**:

- fetch quotes;
- infer executable prices from observed trades;
- use forecast prices as PAPER fills;
- read providers, RPC, network, or operational SQLite;
- construct FL6 baseline decisions;
- compare/promote candidates;
- enable LIVE;
- claim profitability or economic superiority.

## Package boundary

Create a new package:

`python/src/shreks_brain/fast_campaign_paper/`

Do not add PAPER execution authority to the already-SEALED pure `shreks_brain.fast_campaign` package.

The new package may call SEALED PAPER/risk/evaluation functions, but has no network, provider, persistence, signer, transaction-submission, registry, promotion, or LIVE authority.

## Inputs

### Candidate identity

`FastCampaignPaperCandidateIdentity`

Fields:

- `version = "fl9-campaign-paper-v1"`
- `paper_run_id`
- `candidate_version`
- `candidate_fingerprint_sha256`
- `strategy_family`
- `strategy_version`
- `assessment_version`

The fingerprint is caller-supplied immutable candidate identity. This executor does not calculate or promote it.

### Per-event execution evidence

`FastCampaignPaperDecisionEvidence`

Fields:

- `source_event_id`
- `state_version`
- `evaluated_at_unix_ms`
- `quote` — exact `FastCampaignPaperQuoteEvidence | None`
- `risk_context` — exact `RiskContext | None`
- `entry_authority` — exact `FastCampaignPaperEntryAuthority | None`
- `market_regime` — exact `MarketRegime | None`

Every evidence row must match exactly one Rust `FastCampaignDecisionResult`.

Rows are in the same order as decision results and source_event_id must match positionally.

### Explicit quote evidence

`FastCampaignPaperQuoteEvidence` mirrors the sealed Fast PAPER BUY/position quote fields:

- provider;
- mint;
- quote_mint;
- observed_at_unix_ms;
- exact `PaperQuoteState`;
- reference_price_quote;
- execution_price_quote;
- quoted_base_quantity;
- available_base_quantity;
- quote_to_usd_rate.

For `EXECUTABLE` and `FAILED_AFTER_SUBMISSION`, complete price/capacity evidence is required by the sealed quote models.

`UNAVAILABLE` is explicit route-unavailability evidence and may omit price/capacity.

The executor never synthesizes a quote.

### BUY authority

`FastCampaignPaperEntryAuthority`

Fields:

- mint;
- quote_mint;
- intended_base_quantity;
- decision_executable_entry_price_quote;
- maximum_acceptable_entry_price_quote;
- expected_entry_variable_cost_bps;
- expected_entry_fixed_cost_quote.

This is decision-time sizing/economic authority. It is deliberately separate from the later actual PAPER quote.

A BUY result requires exact entry authority + exact RiskContext + MarketRegime.

### Policies

The executor receives exact caller-supplied SEALED objects:

- `PaperFillPolicy`;
- `RiskPolicy`;
- `FastPaperPositionActionPolicy`;
- `TradingEvaluationPolicy`.

No thresholds are invented by the executor.

### Starting ledger

Caller supplies one exact `PaperLedger`. This slice requires that ledger to contain no OPEN positions because no caller-supplied market→position mapping exists yet; closed historical positions are permitted. The executor does not create capital or silently reset accounting.

## Event population

Every Rust decision result is recorded via SEALED `run_fast_paper_event`.

The generated `FastPaperMaterialUpdate` is:

- source_event_id = decision result source_event_id;
- market_key = decision result market_key;
- source_sequence = decision result source_sequence;
- as_of_unix_ms = decision result as_of_unix_ms;
- state_version = per-event evidence state_version;
- is_material = true;
- material_reason = `"campaign_decision"`.

The evaluator returns the exact FL7 assessment translated from the Rust result.

This is critical: later FL6 baseline campaigns can use the exact same update population while returning different assessments, so `event_population_fingerprint_sha256` remains comparable.

## Position-state reconciliation

The executor maintains one tracked OPEN PAPER position per market key.

It fails closed if decision posture and authoritative PAPER ledger disagree.

### Flat actions

- `SKIP`: requires no tracked OPEN position.
- `BUY`: requires no tracked OPEN position.

### Open-position actions

- `HOLD`, `REDUCE`, `SELL`: require exactly one tracked OPEN position for the market.

### REDUCE quantity derivation

FL9 outputs remaining target exposure fraction; FL7.4 requires base quantity to exit.

Given:

- current exposure fraction `c > 0`;
- target exposure fraction `t`;
- authoritative current position base quantity `q`;

REDUCE exit quantity is:

`q * (1 - t / c)`

Requirements:

- `0 < t < c <= 1`; a zero remaining target is represented by `SELL`, not `REDUCE`;
- derived exit quantity finite and strictly between 0 and `q`.

No caller-supplied REDUCE quantity is accepted.

### SELL quantity

SELL exit quantity is exactly the authoritative current PAPER position quantity.

### HOLD

HOLD carries no exit quantity and may mark the position from explicit quote evidence.

## BUY execution

For BUY:

1. build exact `FastPaperBuyApproval` from assessment + entry authority;
2. convert quote evidence to exact `FastPaperBuyQuote`;
3. require risk_context timestamp == evaluated_at_unix_ms;
4. call SEALED `execute_fast_paper_buy`;
5. if a position is opened, capture returned position_id and create SEALED FL7.4 position-action state;
6. never retry inside the same event.

No fill-price arithmetic is implemented here.

## Position execution

For HOLD/REDUCE/SELL:

1. locate authoritative tracked PAPER position;
2. derive exit quantity when required;
3. build exact `FastPaperPositionActionApproval`;
4. convert quote evidence to exact `FastPaperPositionQuote`;
5. call SEALED `apply_fast_paper_position_action`;
6. update tracked position state from the returned sealed state;
7. if position closes, remove market tracking.

No fill-price arithmetic is implemented here.

## SKIP

SKIP only records the FL7.1 decision population. It performs no execution call.

## Evidence normalization

Collect only execution/ledger evidence actually produced by FL7.2/FL7.4.

For every applied entry/exit execution:

- create exact `FastPaperExecutionEvidenceInput`.

For every successfully opened BUY:

- create exact `FastPaperEntryEvaluationContext` using caller-supplied point-in-time MarketRegime.

At the end:

1. SEALED `extract_fast_paper_evaluation_evidence`;
2. SEALED `build_evaluated_trades`;
3. SEALED `evaluate_trading_performance`;
4. construct exact `TradingEvaluationEvidence`;
5. SEALED `build_fast_policy_run_evidence`.

No custom PnL, fill, slippage, cost, expectancy, drawdown, or proof math is implemented.

## Output

`FastCampaignPaperRunResult`

Contains:

- version;
- candidate identity;
- final `FastPaperLoopState`;
- final `PaperLedger`;
- ordered BUY results;
- ordered position-action results;
- SEALED `PaperEvaluationCapture`;
- SEALED `TradingEvaluationEvidence`;
- SEALED `FastPolicyRunEvidence`.

This result is the learned-candidate input to the already-SEALED superiority proof.

## Fail-closed rules

Reject:

- empty/malformed identity;
- decision/evidence length mismatch;
- event ID mismatch;
- duplicate event evidence;
- decision order regression;
- evidence evaluation time before decision;
- quote after evaluation;
- quote mint/pair mismatch through sealed adapters;
- BUY without entry authority/risk context/regime;
- non-BUY with entry authority;
- SKIP with an OPEN tracked position;
- BUY with an OPEN tracked position;
- HOLD/REDUCE/SELL without an OPEN tracked position;
- result current exposure inconsistent with flat/open ledger posture;
- REDUCE target exposure not strictly below current;
- invalid derived REDUCE quantity;
- SELL target exposure not zero;
- sealed execution/ledger rejection inconsistencies;
- unused entry evaluation contexts;
- candidate/strategy attribution mismatch.

Execution outcomes such as quote unavailable, risk rejected, price above maximum, or simulated execution failure are **not** structural errors; they remain sealed run evidence.

## Determinism

No wall-clock reads.

Same starting ledger + decisions + evidence + policies must produce equal immutable run results.

## Tests

1. SKIP-only campaign produces identical FL7 event population and zero trades.
2. BUY → HOLD → SELL with explicit executable quotes produces one closed evaluated trade.
3. E11/E5 metrics reconcile exactly with SEALED execution/ledger evidence.
4. REDUCE derives base exit quantity from current/target exposure fractions.
5. SELL uses full authoritative position quantity.
6. unavailable quote remains an aborted/deferred PAPER outcome, never a synthetic fill.
7. risk rejection remains evidence and never opens a position.
8. BUY/position quote identity/time drift fails closed.
9. flat/open posture mismatches fail closed.
10. same input produces equal run evidence fingerprints.
11. source firewall forbids network/provider/SQLite/subprocess/promotion/LIVE/signing.
12. package contains no custom PnL or expectancy calculations.

## Next slice

Add Rust FL6 baseline replay adapters over the exact same point-in-time event population, then run each required deterministic baseline through this executor.

Only after candidate + all required baselines have comparable real PAPER/shadow evidence does the SEALED superiority evaluator run.

FL9 economic exit stays **EVIDENCE PENDING** until that report returns `SUPERIOR`.

LIVE remains disabled.
