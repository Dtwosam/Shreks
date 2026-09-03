# FL7.2 Fast Lane PAPER BUY — Design

## Status

Design for build-order phase **FL7.2 BUY**. FL7.1 is sealed at merged-main commit `c870d90d30168c236736b8690c63ee082b0ade07` with four-gate CI run `33742529186` green.

LIVE remains disabled.

## Goal

Connect a point-in-time Fast Lane `BUY` assessment to the preserved PAPER risk, fill, and ledger foundations without fabricating legacy setup/score evidence and without weakening the FL3 economics boundary.

A successful FL7.2 path must preserve all of the following at once:

- the exact decision timestamp;
- the exact base quantity whose economics were assessed in Rust;
- the Rust-approved maximum acceptable entry price in native quote units;
- current executable capacity for that exact base quantity;
- assumed landing latency and quote freshness;
- current PAPER risk guardrails for the exact landing notional;
- realistic PAPER slippage/fee/network-cost accounting;
- authoritative immutable PAPER ledger booking;
- no LIVE transaction authority.

## Non-goals

FL7.2 does not:

- change any FL6 strategy evaluator;
- introduce production strategy thresholds;
- create a live signer, transaction, submission path, or LIVE authority;
- replace the existing PAPER execution engine or ledger;
- implement SKIP persistence (FL7.3);
- implement open-position HOLD/REDUCE/SELL orchestration (FL7.4);
- solve all partial-fill/restart/reconciliation work reserved for FL7.5;
- manufacture a legacy `TradeDecision`, deterministic score, setup state, or regime solely to satisfy the old B9 risk API.

## Why the legacy risk entrypoint cannot be called directly

The preserved `assess_entry_risk` API accepts a legacy `TradeDecision.ENTER` and validates legacy decision-policy, feature-schema, safety, setup, regime, and score fields before applying portfolio/health/liquidity guardrails.

Fast Lane `BUY` assessments do not contain those legacy artifacts. Constructing a fake legacy decision would create evidence that never existed and would make risk audit trails misleading.

FL7.2 therefore adds a **parallel Fast Lane entry-risk entrypoint** that reuses the preserved `RiskPolicy`, `RiskContext`, `RiskState`, `RiskFinding`, stable `RiskReasonCode`, `TradeIntent`, sizing caps, and PAPER-only mode, but consumes truthful Fast Lane metadata directly.

The existing `assess_entry_risk` behavior and the legacy `RiskReasonCode` enum remain unchanged.

## Stable risk-enum compatibility

The first implementation candidate attempted to add `REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP` directly to the legacy `RiskReasonCode` enum. The existing Python regression suite correctly rejected that change because the enum's exact public member sequence is a sealed compatibility contract.

The final design preserves the legacy enum byte-for-byte and adds Fast Lane-specific typed evidence in `risk/fast_entry.py` instead:

- `FastEntryRiskReasonCode.REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP`;
- `FastEntryRiskFinding`.

Existing guardrail rejections continue to use preserved `RiskFinding/RiskReasonCode` values. Only the new exact-size rejection uses the Fast Lane-specific finding. Approved Fast Lane risk continues to use preserved `RiskReasonCode.RISK_APPROVED` evidence.

This isolates new Fast Lane semantics without mutating legacy public contracts.

## Exact-size invariant

FL3 `ExecutionEconomics` is evaluated for an explicit `base_quantity`. Fixed costs mean a different quantity can have different economics even if price is unchanged.

Therefore FL7.2 must never silently resize a Fast Lane `BUY` after Rust approved it.

The bridge carries:

- `intended_base_quantity` — exact Rust-assessed quantity;
- `decision_executable_entry_price_quote` — executable price used by the decision economics;
- `maximum_acceptable_entry_price_quote` — FL3 reprice/abort boundary;
- the exact entry cost assumptions needed to reconstruct the approved maximum total entry spend.

At landing, the intended quantity is priced using the executable quote actually available then. The resulting USD notional is passed to Fast Lane risk as an **exact requested notional**. Risk may approve that exact amount or reject it; it may not shrink it.

If current risk caps cannot support the full Rust-assessed size, the action is rejected and no position is opened.

## Native quote units versus preserved USD PAPER accounting

FL3 economics are intentionally quote-unit agnostic. Pump/PumpSwap markets commonly quote in a non-USD asset, while the preserved PAPER ledger is USD-denominated.

FL7.2 keeps economic boundary checks in native quote units and converts only at the PAPER compatibility boundary.

`FastPaperBuyQuote` therefore carries:

- `mint`;
- `quote_mint`;
- `reference_price_quote`;
- `execution_price_quote`;
- `quoted_base_quantity`;
- `available_base_quantity`;
- point-in-time `quote_to_usd_rate` (USD per one quote unit);
- quote provider/state/timestamp.

For an executable quote:

`execution_price_usd = execution_price_quote * quote_to_usd_rate`

`requested_notional_usd = intended_base_quantity * execution_price_usd`

The adapter then creates the existing `PaperQuote` with equivalent USD prices and notional/capacity values and delegates fill math to `execute_paper_intent`.

No conversion rate is inferred or fetched inside the evaluator. Missing/invalid conversion evidence fails closed.

## Maximum-price and maximum-total-spend invariant

A raw landing price below the Rust maximum is necessary but not sufficient if actual PAPER fees are worse than the costs assumed by FL3.

The approval therefore carries the exact entry-side cost assumptions used by Rust:

- `expected_entry_variable_cost_bps` — effective fee + expected impact + expected slippage + expected latency;
- `expected_entry_fixed_cost_quote` — network + priority + expected failure cost in quote units.

The approved maximum total entry spend is reconstructed as:

`max_total_quote = intended_qty * max_entry_price_quote * (1 + expected_variable_bps / 10_000) + expected_fixed_quote`

After the preserved PAPER execution engine produces a **pure** fill result but before the ledger is mutated, FL7.2 computes:

`actual_total_quote = filled_notional_usd / quote_to_usd_rate + explicit_cost_usd / quote_to_usd_rate`

The execution is ledger-booked only when:

`actual_total_quote <= max_total_quote`

This catches the case where raw execution price remains acceptable but realized simulated fee/network burden exceeds the cost envelope used to approve the trade.

The execution price already embodies landing price movement/impact/slippage. Those effects are not charged a second time in `actual_total_quote`.

## Landing latency and quote freshness

The preserved `PaperFillPolicy` remains authoritative for:

- assumed landing latency;
- maximum quote lag;
- swap fee;
- network fee;
- partial-fill settings.

The compatibility `TradeIntent.as_of_unix_ms` remains the original Fast Lane decision timestamp, even though Fast Lane risk is evaluated at the current execution-attempt timestamp. This allows `execute_paper_intent` to enforce the existing landing-latency window honestly.

Fast Lane risk records both clocks:

- `decision_at_unix_ms`;
- `evaluated_at_unix_ms`.

Risk context must match the evaluation clock.

FL7.2 may return `DEFERRED` before landing eligibility or while a valid quote is still pending. It does not sleep or poll internally.

## Fast Lane risk request

New additive public risk contract:

`FastEntryRiskRequest`

Fields:

- `mint`;
- `source_event_id`;
- `decision_at_unix_ms`;
- `evaluated_at_unix_ms`;
- `strategy_name`;
- `strategy_version`;
- `action_assessment_version`;
- `state_version`;
- `requested_notional_usd`.

`assess_fast_entry_risk(request, context, policy, RuntimeMode.PAPER)`:

1. validates request/context identity;
2. uses `RiskPolicy.required_decision_policy_version` as the compatibility fence for the Fast Lane action-assessment version;
3. uses `RiskPolicy.required_feature_schema_version` as the compatibility fence for the Fast Lane state version;
4. applies the same preserved health, halt, portfolio, loss, liquidity, impact, freshness, and duplicate-intent guardrails;
5. computes the existing risk-sized upper bound using the preserved sizing formula;
6. rejects with `FastEntryRiskReasonCode.REQUESTED_NOTIONAL_EXCEEDS_RISK_CAP` when `requested_notional_usd` exceeds that bound;
7. otherwise approves **exactly** `requested_notional_usd`;
8. creates a preserved PAPER `TradeIntent` with the original decision timestamp.

The compatibility `TradeIntent.score_policy_version` is set to an explicit `not-applicable:fast-lane` sentinel. This is not a synthetic score; it is a truthful compatibility marker.

The compatibility `TradeIntent.decision_policy_version` is the actual Fast Lane action-assessment version.

The new exact-size reason is intentionally **not** added to legacy `RiskReasonCode`.

## Fast PAPER BUY approval

`FastPaperBuyApproval` contains:

- version;
- the sealed FL7.1 `FastPaperActionAssessment`;
- `mint` and `quote_mint`;
- `state_version`;
- exact intended base quantity;
- decision executable entry price;
- maximum acceptable entry price;
- expected entry variable-cost bps;
- expected entry fixed cost in quote units.

Construction requires `assessment.action == BUY`.

## Fast PAPER BUY quote

`FastPaperBuyQuote` is a point-in-time execution bridge, not a provider adapter. Providers remain outside FL7.2.

For `EXECUTABLE` or `FAILED_AFTER_SUBMISSION` state, price, capacity, and quote-to-USD fields must all be present and positive.

Identity mismatch, future quote time, invalid units, or malformed numeric state fails closed.

## BUY execution order

`execute_fast_paper_buy(...)` follows this order:

1. validate argument types and decision/evaluation clocks;
2. preserve landing-latency behavior — no execution before eligibility;
3. reject missing/stale/late/mismatched quote evidence as appropriate;
4. require native execution price `<= maximum_acceptable_entry_price_quote`;
5. require both quoted and available base quantity `>= intended_base_quantity`;
6. convert the exact intended quantity at the landing quote to USD notional;
7. run Fast Lane entry risk for that exact notional at the current risk-context timestamp;
8. if risk rejects, stop with no PAPER execution or ledger change;
9. if the resulting intent key is already terminal in the ledger, return idempotent `ALREADY_PROCESSED`;
10. adapt the native quote to the existing USD `PaperQuote`;
11. call the preserved pure `execute_paper_intent`;
12. require a full fill to equal the intended base quantity within arithmetic tolerance;
13. for a full fill, compare actual total quote spend with the approved maximum total quote spend;
14. abort before ledger mutation if total spend exceeds the approved bound;
15. otherwise call preserved `apply_paper_execution`;
16. return the resulting risk/execution/ledger evidence.

## Partial fills

FL7.2 requires full quoted and available capacity for the Rust-assessed quantity before execution. Therefore a valid FL7.2 BUY should resolve to a full fill when the preserved fill engine uses the constructed exact notional.

An unexpected `PARTIAL` result is treated as an invariant violation and is not ledger-booked in FL7.2. Full multi-step partial-entry reconciliation belongs to FL7.5, where accounting and restart semantics can be designed explicitly.

## Failed-after-submission cost

If the supplied quote state is `FAILED_AFTER_SUBMISSION` and it carries the price/capacity evidence required to form the exact intent, the preserved PAPER fill engine may produce its existing simulated submission failure and network-fee cost. That terminal failure is passed through the preserved ledger so the simulated cost is not erased.

## Outcomes

The FL7.2 result distinguishes at least:

- `DEFERRED`;
- `ABORTED_QUOTE_UNAVAILABLE`;
- `ABORTED_QUOTE_TOO_LATE`;
- `ABORTED_PRICE_ABOVE_MAXIMUM`;
- `ABORTED_INSUFFICIENT_CAPACITY`;
- `RISK_REJECTED`;
- `ALREADY_PROCESSED`;
- `ABORTED_TOTAL_COST_ABOVE_MAXIMUM`;
- `EXECUTION_FAILED`;
- `FILLED`;
- `LEDGER_REJECTED`.

Malformed/contradictory input raises a typed fail-closed error instead of being converted into a trading outcome.

## Idempotency

The Fast Lane intent key is deterministic from stable action identity and strategy/version metadata, not from the transient landing quote.

Once an execution is terminal and its key is in `PaperLedger.processed_intent_keys`, replay returns `ALREADY_PROCESSED` before another fill attempt.

Active-intent duplication remains governed by `RiskContext.active_intent_keys`.

## Compatibility and scope

Final production changes are additive or export-only:

- new `risk/fast_entry.py` Fast Lane request/assessment/reason/finding implementation;
- export-only `risk/__init__.py` change;
- new FL7.2 buy models/engine under `shreks_brain.fast_paper`;
- export-only `fast_paper/__init__.py` change;
- tests and docs.

`risk/models.py` remains byte-identical to sealed main. The stable legacy `RiskReasonCode` enum is not modified.

Do not edit:

- existing `assess_entry_risk` semantics;
- existing PAPER fill math;
- existing PAPER ledger accounting;
- legacy `paper_loop` orchestration;
- providers or storage;
- Rust FL3/FL6 evaluator semantics;
- signer/submission/LIVE authority.

## TDD proof requirements

The RED contract must prove the new public API is absent before implementation.

GREEN tests must cover:

- exact-notional Fast Lane risk approval;
- exact-size risk-cap rejection using Fast Lane-specific typed evidence with no silent resize;
- stable legacy risk enum unchanged;
- kill switch / health guardrail rejection;
- action/state version compatibility fences;
- original decision timestamp retained on compatibility `TradeIntent`;
- landing-latency deferral;
- price-above-maximum abort;
- insufficient quoted/available base capacity abort;
- successful full BUY with exact intended base quantity and authoritative ledger position;
- raw-price-pass but total-cost-fail abort before ledger mutation;
- risk rejection leaves ledger unchanged;
- terminal replay returns already processed;
- failed-after-submission cost booking where complete evidence exists;
- malformed identity/time/unit inputs fail closed;
- existing risk, PAPER, and legacy paper-loop tests remain green.

## Exit criterion

FL7.2 is complete when a Fast Lane `BUY` can enter PAPER only when the exact Rust-assessed size remains executable at or below its economic boundary, current preserved risk guardrails approve that exact size, realistic landing/cost simulation succeeds, and the preserved PAPER ledger reconciles the result — with no LIVE path enabled.