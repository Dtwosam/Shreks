# Phase C1 Realistic Paper Execution Design

## Status

Approved for autonomous implementation under the standing Shreks project instruction.

## Goal

Implement source build-order Phase C1 and C2 together as repository Phase C1: a pure deterministic paper execution adapter that consumes the exact B9 `TradeIntent` interface and models contemporaneous quote timing, adverse/favorable slippage, swap/network costs, latency, unavailable routes, failed submissions, partial fills, and size-constrained exit liquidity.

This slice deliberately stops before Phase C3 position accounting. It produces economically complete execution results that the later authoritative paper ledger can apply and reconcile.

## Base and scope

Base: verified B9 head `be84a3b94dfd8d6a8decb489049cd8ee5adea0a3`.

Create `shreks_brain.paper` with immutable execution-domain models and one pure adapter:

```python
def execute_paper_intent(
    intent: TradeIntent,
    context: PaperExecutionContext,
    policy: PaperFillPolicy,
) -> PaperExecutionResult:
    ...
```

The function performs no storage, provider, network, balance, clock, random-number, or position-ledger I/O. The caller supplies point-in-time quote evidence and evaluation time explicitly.

Existing runtime, safety, features, setups, regime, scoring, decision, risk, Rust, storage, and provider behavior remain unchanged.

## Why C1 and C2 are one repository slice

The source build order separates the paper adapter from the realistic fill simulator, but an adapter that can consume `TradeIntent` without economically valid fill semantics would create misleading paper performance. The first paper boundary therefore includes both:

- exact `TradeIntent` consumption;
- deterministic realistic fill simulation.

Position ownership, realized/unrealized PnL, weighted entry, lifecycle state, and exits remain separate C3/C4 responsibilities.

## Non-goals

C1 does not add:

- authoritative positions;
- paper account balances;
- weighted average entry;
- realized/unrealized portfolio PnL;
- stop/take-profit/trailing/max-hold logic;
- autonomous trading loop;
- SQLite paper persistence;
- live quotes/providers inside the simulator;
- signer, wallet, route construction, transaction creation/submission;
- live trading.

## Design principles

### No random fake execution outcomes

C1 uses no RNG and no arbitrary fill-probability model. An unavailable route or failed submission must be represented explicitly by input evidence. Equal inputs produce equal results.

Random failures would make paper performance irreproducible and could manufacture either optimism or pessimism without market evidence.

### Never extrapolate a quote beyond the size it covers

An execution price may be used only for notional at or below `quoted_notional_usd`. The simulator also respects `available_notional_usd`. The effective fill capacity is:

```python
min(
    intent.requested_notional_usd,
    quote.quoted_notional_usd,
    quote.available_notional_usd,
)
```

This applies equally to BUY and SELL, so SELL intents naturally respect exit-liquidity constraints.

### Slippage is not charged twice

The execution price already contains the market-price effect of slippage. Slippage is recorded as audit/research evidence but is not added again to cash cost.

Explicit costs are swap fee plus network fee only.

## Enums

### `PaperQuoteState`

Exact public order:

```text
EXECUTABLE
UNAVAILABLE
FAILED_AFTER_SUBMISSION
```

Meaning:

- `EXECUTABLE`: route/fill evidence is usable if all required quote fields pass validation.
- `UNAVAILABLE`: no submission occurs; no network fee is charged.
- `FAILED_AFTER_SUBMISSION`: an attempted submission fails without a fill; network fee is charged because execution was attempted.

### `PaperExecutionState`

Exact public order:

```text
DEFERRED
FAILED
PARTIAL
FILLED
```

`DEFERRED` means execution is not terminal yet. It is used for expected latency and for waiting on a quote while the valid quote window remains open.

### `PaperExecutionReasonCode`

Exact deterministic order:

```text
INTENT_MODE_NOT_PAPER
DUPLICATE_INTENT
EVALUATION_BEFORE_INTENT
QUOTE_AFTER_EVALUATION
QUOTE_MINT_MISMATCH
LATENCY_PENDING
QUOTE_PENDING
QUOTE_BEFORE_LATENCY
QUOTE_WINDOW_EXPIRED
QUOTE_TOO_LATE
ROUTE_UNAVAILABLE
SIMULATED_SUBMISSION_FAILED
REFERENCE_PRICE_UNKNOWN
EXECUTION_PRICE_UNKNOWN
QUOTED_NOTIONAL_UNKNOWN
AVAILABLE_NOTIONAL_UNKNOWN
NO_EXECUTABLE_NOTIONAL
PARTIAL_FILL_DISABLED
PARTIAL_FILL_TOO_SMALL
SLIPPAGE_EXCEEDS_INTENT
FILL_PARTIAL
FILL_COMPLETE
```

Every result has exactly one current/terminal finding.

## Immutable domain models

All dataclasses are `@dataclass(frozen=True, slots=True)`.

### `PaperFillPolicy`

Exact fields:

```python
version: str
assumed_latency_ms: int
max_quote_lag_ms: int
swap_fee_bps: int
network_fee_usd: float
allow_partial_fills: bool
min_partial_fill_fraction: float
```

Validation:

- version is non-empty;
- latency and quote-lag values are non-negative integers;
- swap fee is an integer in `[0, 10_000]` bps;
- network fee is finite and non-negative;
- `allow_partial_fills` is bool;
- minimum partial fraction is finite in `(0, 1]`.

There is no production default `PaperFillPolicy`.

### `PaperQuote`

Exact fields:

```python
provider: str
mint: str
observed_at_unix_ms: int
state: PaperQuoteState
reference_price_usd: float | None
execution_price_usd: float | None
quoted_notional_usd: float | None
available_notional_usd: float | None
```

Validation:

- provider and mint non-empty;
- observed timestamp non-negative;
- state exact enum;
- present prices finite and strictly positive;
- present notionals finite and non-negative.

Optional quote economics remain representable for non-executable states. The engine requires all four economics for `EXECUTABLE` and returns stable missing-data reasons when they are absent.

Definitions:

- `reference_price_usd`: contemporaneous no-slippage/reference market price used only to measure signed slippage.
- `execution_price_usd`: price actually used for paper fill quantity/cash accounting.
- `quoted_notional_usd`: maximum notional for which that execution price is evidenced.
- `available_notional_usd`: route/liquidity capacity available to this intent.

### `PaperExecutionContext`

Exact fields:

```python
evaluated_at_unix_ms: int
processed_intent_keys: frozenset[str]
quote: PaperQuote | None
```

Validation:

- evaluation time non-negative;
- processed keys are a frozenset of non-empty strings;
- quote is `PaperQuote` or `None`.

This context is deliberately not a position ledger. Processed keys are supplied state used only to prevent duplicate adapter processing.

### `PaperExecutionFinding`

```python
code: PaperExecutionReasonCode
message: str
```

Code must be exact enum and message non-empty.

### `PaperFill`

Exact fields:

```python
intent_idempotency_key: str
mint: str
side: TradeSide
state: PaperExecutionState
requested_notional_usd: float
filled_notional_usd: float
unfilled_notional_usd: float
quantity: float
reference_price_usd: float
execution_price_usd: float
signed_slippage_bps: float
signed_slippage_usd: float
swap_fee_usd: float
network_fee_usd: float
explicit_cost_usd: float
net_cash_flow_usd: float
quote_provider: str
executed_at_unix_ms: int
```

Validation and invariants:

- state is only `PARTIAL` or `FILLED`;
- keys/mint/provider non-empty;
- side exact `TradeSide`;
- requested/filled quantities and prices finite with required positive/non-negative bounds;
- `filled_notional_usd > 0`;
- `0 <= unfilled_notional_usd < requested_notional_usd`;
- `filled + unfilled == requested` within `math.isclose(rel_tol=1e-12, abs_tol=1e-9)`;
- quantity equals `filled_notional / execution_price` within the same tolerance;
- slippage bps/usd finite and may be negative for favorable execution;
- fees/costs non-negative finite;
- explicit cost equals swap fee + network fee;
- quote timestamp non-negative;
- `FILLED` requires unfilled notional approximately zero;
- `PARTIAL` requires positive unfilled notional.

Cash-flow consistency is also validated:

BUY:

```python
net_cash_flow_usd == -(filled_notional_usd + explicit_cost_usd)
```

SELL:

```python
net_cash_flow_usd == filled_notional_usd - explicit_cost_usd
```

### `PaperExecutionResult`

Exact fields:

```python
policy_version: str
intent_idempotency_key: str
mint: str
side: TradeSide
state: PaperExecutionState
requested_notional_usd: float
evaluated_at_unix_ms: int
quote_observed_at_unix_ms: int | None
swap_fee_usd: float
network_fee_usd: float
explicit_cost_usd: float
net_cash_flow_usd: float
findings: tuple[PaperExecutionFinding, ...]
fill: PaperFill | None
```

Validation/invariants:

- names/keys non-empty;
- side and state exact enums;
- requested notional finite > 0;
- evaluation timestamp non-negative;
- optional quote timestamp non-negative;
- cost fields finite/non-negative;
- explicit cost equals swap + network fees;
- net cash flow finite;
- findings contains exactly one finding.

State semantics:

- `DEFERRED`: fill is `None`; all costs and net cash flow are zero.
- `FAILED`: fill is `None`; swap fee is zero. Pre-submission failures have zero network fee/net cash flow. `FAILED_AFTER_SUBMISSION` result has network fee equal to policy and net cash flow equal to negative network fee.
- `PARTIAL` or `FILLED`: fill is present and result cost/cash/timestamps match the fill exactly.

## Point-in-time and latency model

For one intent:

```python
eligible_at_unix_ms = intent.as_of_unix_ms + policy.assumed_latency_ms
deadline_unix_ms = eligible_at_unix_ms + policy.max_quote_lag_ms
```

Fixed timing rules:

1. `intent.execution_mode` must be `PAPER`; otherwise `FAILED / INTENT_MODE_NOT_PAPER`.
2. Processed idempotency key rejects duplicate processing before any market result is created.
3. Evaluation before intent timestamp is contradictory and fails.
4. If a quote is supplied with `observed_at_unix_ms > evaluated_at_unix_ms`, fail `QUOTE_AFTER_EVALUATION` immediately. Future quote evidence is never carried silently even while latency is pending.
5. If a quote is supplied for another mint, fail `QUOTE_MINT_MISMATCH` immediately.
6. If evaluation is before `eligible_at`, defer `LATENCY_PENDING`.
7. If no quote exists:
   - evaluation `<= deadline`: defer `QUOTE_PENDING`;
   - evaluation `> deadline`: fail `QUOTE_WINDOW_EXPIRED`.
8. If quote observation is before `eligible_at`:
   - evaluation `<= deadline`: defer `QUOTE_BEFORE_LATENCY`;
   - evaluation `> deadline`: fail `QUOTE_WINDOW_EXPIRED`.
9. If quote observation is after `deadline`, fail `QUOTE_TOO_LATE`.
10. Otherwise the quote is temporally eligible and route/economic evaluation continues.

Both latency and max quote lag may be zero. Boundary equality at `eligible_at` and `deadline` is valid.

## Route and failure semantics

For a temporally eligible quote:

### `UNAVAILABLE`

Return `FAILED / ROUTE_UNAVAILABLE` with:

```text
swap fee = 0
network fee = 0
explicit cost = 0
net cash flow = 0
fill = None
```

### `FAILED_AFTER_SUBMISSION`

Return `FAILED / SIMULATED_SUBMISSION_FAILED` with:

```text
swap fee = 0
network fee = policy.network_fee_usd
explicit cost = policy.network_fee_usd
net cash flow = -policy.network_fee_usd
fill = None
```

This lets the later ledger reconcile failed attempts that still consume network fees.

### `EXECUTABLE`

Require in fixed order:

```text
reference_price_usd
execution_price_usd
quoted_notional_usd
available_notional_usd
```

Missing values fail with their stable UNKNOWN reason.

## Capacity and partial fills

For executable evidence:

```python
effective_fill_notional = min(
    intent.requested_notional_usd,
    quote.quoted_notional_usd,
    quote.available_notional_usd,
)
```

If effective fill notional is zero, fail `NO_EXECUTABLE_NOTIONAL`.

If it is less than requested:

1. partial fills disabled -> fail `PARTIAL_FILL_DISABLED`;
2. `effective / requested < min_partial_fill_fraction` -> fail `PARTIAL_FILL_TOO_SMALL`;
3. otherwise result state is `PARTIAL`.

If effective fill notional equals requested, state is `FILLED`.

A quote covering more notional than is filled is acceptable and conservative. A quoted notional below the actual fill is impossible by construction.

## Side-aware slippage

Signed adverse slippage in bps:

BUY:

```python
signed_slippage_bps = (
    execution_price_usd / reference_price_usd - 1.0
) * 10_000.0
```

SELL:

```python
signed_slippage_bps = (
    1.0 - execution_price_usd / reference_price_usd
) * 10_000.0
```

Positive is adverse; negative is favorable.

If signed adverse slippage is strictly greater than `intent.max_slippage_bps`, fail `SLIPPAGE_EXCEEDS_INTENT` before constructing a fill. Equality passes.

Signed slippage dollars:

BUY:

```python
quantity * (execution_price_usd - reference_price_usd)
```

SELL:

```python
quantity * (reference_price_usd - execution_price_usd)
```

This is research/audit evidence only. It is not added to explicit costs because execution-price cash accounting already includes it.

## Cost and cash-flow model

For PARTIAL/FILLED execution:

```python
filled_notional_usd = effective_fill_notional
quantity = filled_notional_usd / execution_price_usd
swap_fee_usd = filled_notional_usd * policy.swap_fee_bps / 10_000.0
network_fee_usd = policy.network_fee_usd
explicit_cost_usd = swap_fee_usd + network_fee_usd
```

BUY:

```python
net_cash_flow_usd = -(filled_notional_usd + explicit_cost_usd)
```

SELL:

```python
net_cash_flow_usd = filled_notional_usd - explicit_cost_usd
```

The network fee is charged once for every partial/full simulated submission.

No token/network/Solana fee is silently invented beyond explicit policy values.

## Fixed execution precedence

`execute_paper_intent()` returns at the first current/terminal reason in this order:

```text
intent mode
processed-idempotency duplicate
evaluation timestamp
future quote check
quote mint check
latency pending
quote presence/window
quote pre-latency/too-late timing
route state
required quote economics
fill capacity
partial-fill permission/minimum
signed slippage ceiling
fill/cost arithmetic
PARTIAL or FILLED
```

This ordering is test-pinned.

## Duplicate processing semantics

`processed_intent_keys` means the adapter has already produced a terminal or accounting-relevant result for this intent. Reprocessing it returns `FAILED / DUPLICATE_INTENT` with zero new cost and no fill.

The paper adapter does not mutate the set. C3/C6 persistence and reconciliation later own durable processed-key state.

## SELL and exit-liquidity compatibility

Although B9 currently creates only BUY entry intents, `TradeIntent` already has BUY/SELL side vocabulary. C1 supports both sides so C4 exits can use the same paper execution boundary without replacement.

A SELL request is capacity-limited by the same `quoted_notional_usd` and `available_notional_usd`, so insufficient exit liquidity naturally becomes a partial or failed exit rather than a perfect-fill assumption.

C1 does not decide how much quantity should be sold; C3/C4 create the appropriate SELL intent later.

## No position/accounting authority in C1

`PaperExecutionResult` is economically self-contained but not authoritative portfolio state.

It provides enough evidence for C3 to record:

- whether submission filled, failed, or remains deferred;
- gross filled notional and quantity;
- explicit costs;
- signed slippage;
- cash effect;
- quote provider/time;
- unfilled remainder;
- failed-submission network cost.

C3 owns positions, weighted entry, realized/unrealized PnL, accumulated costs, and lifecycle state.

## Stable package API

`shreks_brain.paper` will export exactly:

```text
PaperExecutionContext
PaperExecutionFinding
PaperExecutionReasonCode
PaperExecutionResult
PaperExecutionState
PaperFill
PaperFillPolicy
PaperQuote
PaperQuoteState
execute_paper_intent
```

No default policy, ledger, or live executor is exported.

## Testing strategy

Strict TDD in three tasks.

### Task 1 — immutable execution models

Write tests first for:

- exact enum/reason orders;
- policy validation;
- quote/context validation;
- fill arithmetic/invariants for BUY and SELL;
- result state/cost/fill invariants;
- frozen dataclasses;
- absence of position/transaction/secret/outcome authority.

Expected RED: `shreks_brain.paper` missing.

### Task 2 — deterministic paper adapter

Write tests first for:

- PAPER-only input;
- duplicate processing;
- future/evaluation/mint contradictions;
- latency and quote-window boundary behavior;
- unavailable and failed-after-submission routes;
- missing quote economics;
- quote-size and route-capacity constraints;
- partial-fill disabled/minimum behavior;
- BUY/SELL side-aware slippage including favorable execution and equality threshold;
- swap/network fee arithmetic;
- failed-submission network fee accounting;
- BUY/SELL cash flow;
- deterministic repeated inputs;
- no quote extrapolation and SELL exit-liquidity constraint.

Expected RED: `shreks_brain.paper.engine` missing.

### Task 3 — stable exports/docs/seal

Write package-level import/regression tests first, then export the exact ten public symbols above.

README must document:

- exact B9 `TradeIntent` consumption;
- deterministic latency/quote window;
- no random fills;
- size-covered quote requirement;
- partial/full/unavailable/failed-after-submission behavior;
- side-aware slippage and explicit costs;
- failed attempt network cost;
- SELL capacity as exit-liquidity constraint;
- no position ledger yet;
- no live execution.

Run fresh exact-head CI, audit B9 -> C1 diff, record final SHA/run only in draft PR metadata, and leave PR draft/unmerged.

## Completion criteria

C1 is complete only when:

- exact B9 `TradeIntent` is the sole trade request interface;
- point-in-time latency/quote rules prevent future leakage;
- no execution price is extrapolated beyond quoted size;
- unavailable and failed-submission outcomes are explicit and deterministic;
- partial/full BUY and SELL fills are costed correctly;
- slippage is side-aware and not double-counted;
- failed submissions can carry network cost without a fill;
- output contains enough immutable economics for C3 accounting;
- no position ledger or live-money path exists;
- exact final branch head has fresh green Rust, Python, workspace metadata, and repository-safety CI;
- final diff contains only intended C1 files;
- draft PR remains unmerged.
