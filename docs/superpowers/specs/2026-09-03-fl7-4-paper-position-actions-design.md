# FL7.4 Fast Lane PAPER HOLD / REDUCE / SELL — Design

## Status

Design for build-order phase **FL7.4 HOLD/REDUCE/SELL**.

Base: FL7.3 is SEALED at merged-main commit `030198932943254034ddab351f76e9d91c9c923a` with fresh push-triggered merged-main CI run `33757018548` four-gate green.

LIVE remains disabled.

## Build-order requirement

The canonical build order says:

> **FL7.4 HOLD/REDUCE/SELL** — Continuously reevaluate open positions. Named horizons never force the system to wait.

FL7.4 must connect event-resolution Fast Lane open-position actions to the preserved PAPER execution/accounting foundations without inventing execution quantity, stale USD notional, legacy scoring evidence, or new accounting math.

## Goal

Add one deterministic Fast Lane PAPER position-action adapter that:

- accepts only `HOLD`, `REDUCE`, or `SELL` assessments;
- binds every action to one authoritative OPEN C3 `PaperPosition`;
- requires explicit base-quantity authority for `REDUCE`;
- requires full-position quantity authority for `SELL`;
- preserves the original action timestamp across latency-delayed exit attempts;
- uses current executable quote evidence to derive transient USD SELL notional;
- routes all actual exits through existing C1 `execute_paper_intent` and C3 `apply_paper_execution`;
- optionally marks a still-open position only from usable contemporaneous quote evidence;
- retains pending exit authority across material event churn using the already-proven C5 precedence rules;
- never waits for a named forecast horizon before accepting a newer material action assessment.

## Why REDUCE quantity must be explicit

The sealed Fast Lane action contract preserves direction and reasons:

```text
BUY / SKIP / HOLD / REDUCE / SELL
```

`FastPaperActionAssessment` does not carry a reduction fraction or target quantity. FL6.5 and FL6.6 also emit `REDUCE` direction without defining a canonical fraction. A default such as 25%, 50%, or one-half of remaining exposure would therefore fabricate strategy authority that does not exist.

FL7.4 must not invent this missing evidence.

For `REDUCE`, the caller supplies an explicit `target_base_quantity` that must be strictly positive and strictly below the authoritative current OPEN position quantity when the action is first authorized.

For `SELL`, the caller supplies `target_base_quantity` equal to the authoritative full OPEN position quantity at authorization time. This explicit equality proves full-exit authority instead of silently upgrading a directional `SELL` into an unspecified amount.

For `HOLD`, `target_base_quantity` must be `None`.

## Preserve the existing C5 quantity-safe SELL pattern

The sealed legacy C5 orchestration solved the same quantity/notional mismatch correctly:

- strategy/exit authority is expressed in token quantity;
- stable `TradeIntent` requests USD notional;
- the USD notional is transient and must use the same current quote execution price that C1 consumes;
- persisted execution authority is quantity, never stale USD notional.

FL7.4 reuses that exact invariant.

For authorized target quantity `Q`, current native quote execution price `Pq`, and quote-to-USD rate `R`:

```text
execution_price_usd = Pq * R
requested_notional_usd = Q * execution_price_usd
```

The adapted C1 quote uses the same `execution_price_usd`. Its quoted/available USD notional is derived from the current quoted/available base capacity times that same execution price.

Therefore C1 can never fill more than the authorized base quantity:

```text
filled_notional <= requested_notional
filled_quantity = filled_notional / execution_price_usd
filled_quantity <= Q
```

FL7.4 does not convert using weighted entry price, a stale earlier quote, a Fast Lane reference price, or a forecast price.

## Native quote evidence

Fast Lane execution economics are quote-unit-native, while preserved PAPER accounting is USD-denominated. FL7.4 mirrors the FL7.2 compatibility boundary rather than forcing Fast Lane strategy code to reason in USD.

New immutable quote input:

`FastPaperPositionQuote`

Fields:

- `provider`
- `mint`
- `quote_mint`
- `observed_at_unix_ms`
- `state: PaperQuoteState`
- `reference_price_quote`
- `execution_price_quote`
- `quoted_base_quantity`
- `available_base_quantity`
- `quote_to_usd_rate`

For `EXECUTABLE` and `FAILED_AFTER_SUBMISSION`, complete price/capacity evidence is required. For `UNAVAILABLE`, price/capacity fields may be absent; FL7.4 never fabricates them.

The adapter converts native values to the existing `PaperQuote` only at the compatibility boundary.

## Public contract

New package files:

- `python/src/shreks_brain/fast_paper/position_models.py`
- `python/src/shreks_brain/fast_paper/position.py`

Stable public names:

```python
FAST_PAPER_POSITION_ACTION_VERSION = "fl7.4-v1"
FAST_PAPER_EXIT_RISK_POLICY_SENTINEL = "not-applicable:fast-lane-exit"

class FastPaperPositionActionError(ValueError): ...

class FastPaperPositionOutcome(StrEnum):
    HOLD = "HOLD"
    HOLD_MARKED = "HOLD_MARKED"
    DEFERRED = "DEFERRED"
    ABORTED_QUOTE_UNAVAILABLE = "ABORTED_QUOTE_UNAVAILABLE"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    REDUCED = "REDUCED"
    SOLD = "SOLD"
    LEDGER_REJECTED = "LEDGER_REJECTED"

@dataclass(frozen=True, slots=True)
class FastPaperPositionActionPolicy:
    version: str
    max_slippage_bps: int

@dataclass(frozen=True, slots=True)
class FastPaperPositionActionApproval:
    version: str
    assessment: FastPaperActionAssessment
    position_id: str
    mint: str
    quote_mint: str
    state_version: str
    target_base_quantity: float | None

@dataclass(frozen=True, slots=True)
class FastPaperPositionQuote: ...

@dataclass(frozen=True, slots=True)
class FastPaperPositionActionState:
    version: str
    position_id: str
    pending_exit: FastPaperPositionActionApproval | None
    last_assessment_at_unix_ms: int

@dataclass(frozen=True, slots=True)
class FastPaperPositionActionResult:
    version: str
    outcome: FastPaperPositionOutcome
    position_id: str
    mint: str
    evaluated_at_unix_ms: int
    applied_assessment: FastPaperActionAssessment
    active_exit: FastPaperPositionActionApproval | None
    execution: PaperExecutionResult | None
    execution_ledger_update: PaperLedgerUpdate | None
    mark_ledger_update: PaperLedgerUpdate | None
    next_ledger: PaperLedger
    next_state: FastPaperPositionActionState

create_fast_paper_position_action_state(...)
apply_fast_paper_position_action(...)
```

No defaults are supplied for `max_slippage_bps`, reduction quantity, or quote conversion.

## Approval validation

`FastPaperPositionActionApproval` is action authority, not a fill.

Common requirements:

- version exactly `fl7.4-v1`;
- assessment is a `FastPaperActionAssessment`;
- action is one of `HOLD`, `REDUCE`, `SELL`;
- position/mint/quote/state identifiers are non-empty;
- timestamp/order metadata remain those of the underlying assessment.

Action-specific requirements:

- `HOLD`: `target_base_quantity is None`;
- `REDUCE`: finite positive `target_base_quantity` required;
- `SELL`: finite positive `target_base_quantity` required.

The dataclass cannot know the current ledger position quantity, so the authoritative REDUCE/SELL quantity relationship is enforced when first reconciling the approval against the ledger.

## Authoritative position identity

`apply_fast_paper_position_action` accepts the current immutable `PaperLedger`. It must locate `approval.position_id` and require:

- the position exists;
- state is `OPEN`;
- position mint equals approval mint;
- position quantity is strictly positive;
- approval timestamp is not before the current action state;
- evaluation timestamp is not before the approval timestamp or current ledger time.

The ledger remains the only authority for current position quantity and lifecycle state.

No mint-only fallback is permitted when a position ID is supplied.

## Initial quantity authorization

When an approval first becomes active exit authority:

### REDUCE

Require:

```text
0 < target_base_quantity < current_position.quantity
```

Equality is rejected because a full liquidation must be explicit `SELL`, not an ambiguously sized `REDUCE`.

### SELL

Require target quantity equal to current full position quantity within the same strict arithmetic tolerance used by preserved PAPER accounting.

This equality is checked when the SELL becomes pending. Once authorized, later partial fills may reduce current ledger quantity below the original target. The stored pending SELL authority remains valid for the still-open remainder; execution derives current attempt quantity as:

```text
authorized_attempt_quantity = min(pending.target_base_quantity, current_position.quantity)
```

For a pending `REDUCE`, the same `min(...)` cap prevents over-selling if the ledger quantity changed through an earlier authoritative partial fill before a later retry.

FL7.4 never increases a pending target after authorization.

## Event-driven pending-exit state

Named model horizons are not action timers. Every new material assessment may be supplied immediately.

However, a newer event must not reset a previously-authorized exit latency clock indefinitely. FL7.4 therefore preserves the established C5 precedence model.

`FastPaperPositionActionState.pending_exit` stores only quantity authority and decision metadata, never a USD SELL intent.

Reconciliation:

- no pending + fresh `HOLD` -> no pending exit;
- no pending + fresh `REDUCE` -> persist fresh reduction;
- no pending + fresh `SELL` -> persist fresh full sell;
- pending `REDUCE` + fresh `SELL` -> newer SELL supersedes reduction;
- pending `SELL` + fresh `HOLD`/`REDUCE` -> retain existing SELL;
- pending `REDUCE` + fresh `HOLD`/`REDUCE` -> retain original REDUCE;
- fresh action assessment may never be earlier than state `last_assessment_at_unix_ms`;
- a superseding SELL keeps its own newer timestamp; FL7.4 never backdates it.

`last_assessment_at_unix_ms` advances to the fresh assessment timestamp even when the pending authority is retained.

A terminal C1 SELL attempt clears pending authority. If the position remains OPEN, a later reduction/sell attempt requires a fresh Fast Lane assessment, leaving multi-reduction orchestration/restart reconciliation to FL7.5.

## HOLD behavior

A `HOLD` with no stronger pending exit causes no trade intent and no cash/accounting mutation.

If current quote evidence is usable for marking, FL7.4 may update only the C3 mark:

- quote mint identity must match;
- quote time must be `<= evaluated_at_unix_ms`;
- quote time must be `>= ledger.as_of_unix_ms` so the authoritative ledger clock does not regress;
- `reference_price_quote` must be available;
- convert with the supplied `quote_to_usd_rate`;
- call existing `mark_paper_position` using the quote observation timestamp.

If mark evidence is unavailable or too old for the current ledger clock, HOLD remains valid and the ledger is left unchanged. Missing mark evidence is not converted into a fabricated price.

If a stronger pending exit exists, a fresh HOLD does not cancel it; execution eligibility is evaluated for the retained pending exit.

## Quote and latency behavior for pending exits

For pending action time `T`, assumed latency `L`, quote time `Q`, and evaluation time `E`:

- no quote -> `DEFERRED`, retain pending;
- quote mint/position identity contradiction -> typed error, fail closed;
- `Q > E` -> typed error before consuming price fields;
- `Q < T + L` -> `DEFERRED`, retain pending;
- `UNAVAILABLE` quote -> `ABORTED_QUOTE_UNAVAILABLE`, retain pending while current decision remains authorized;
- missing required executable fields -> validation error;
- otherwise construct a transient SELL and pass the exact adapted quote to C1.

A quote beyond C1's `max_quote_lag_ms` is still passed to C1 once otherwise eligible so the existing execution engine remains authoritative for terminal quote-window semantics.

## Transient SELL intent

The SELL `TradeIntent` is never persisted in FL7.4 state.

Fields:

- `mint` = authoritative position mint;
- `side = SELL`;
- `requested_notional_usd` from authorized attempt quantity × current quote execution USD price;
- `max_slippage_bps` from explicit FL7.4 policy;
- `strategy_name` / `strategy_version` from the Fast Lane assessment;
- `score_policy_version = FAST_LANE_SCORE_POLICY_SENTINEL`;
- `decision_policy_version = assessment.version`;
- `risk_policy_version = FAST_PAPER_EXIT_RISK_POLICY_SENTINEL`;
- `reason` = first ordered Fast Lane reason (the full ordered reasons remain on the attached assessment/result);
- `execution_mode = RuntimeMode.PAPER`;
- `as_of_unix_ms = pending assessment.as_of_unix_ms`.

FL7.4 does not fabricate a legacy entry-risk approval for exits. The explicit sentinel records that entry-risk policy is not applicable to this open-position exit adapter. Protective risk exits remain a separate FL7.6 backstop.

## Deterministic exit idempotency

Exit idempotency key is SHA-256 over canonical versioned content:

```text
fl7.4-exit-v1
position_id
source_event_id
assessment.version
assessment.strategy_family
assessment.strategy_version
assessment.as_of_unix_ms
action
ordered reasons
target_base_quantity float.hex()
```

Quote price is intentionally excluded. Repricing the same authorized decision changes transient USD notional but not economic identity.

A superseding newer SELL has a different source event/timestamp and therefore a different key.

## Execution and accounting authority

Every actual reduction/sell goes only through:

```text
TradeIntent
  -> C1 execute_paper_intent
  -> C3 apply_paper_execution
```

C1 remains authoritative for:

- latency;
- quote windows;
- route state;
- executable capacity;
- partial-fill policy;
- slippage;
- swap/network cost;
- failed-after-submission cost.

C3 remains authoritative for:

- position quantity;
- proportional basis release;
- cash balance;
- realized PnL;
- accumulated costs;
- idempotent terminal journal;
- position lifecycle close.

FL7.4 implements no parallel fill, basis, PnL, or cost formula.

## Terminal result classification

After C1:

- `DEFERRED` -> retain pending, no ledger booking;
- duplicate terminal intent -> `ALREADY_PROCESSED`, do not duplicate accounting;
- terminal execution -> call C3;
- C3 `REJECTED` -> `LEDGER_REJECTED`;
- terminal execution with no filled quantity -> `EXECUTION_FAILED`;
- APPLIED fill leaving OPEN position with lower quantity -> `REDUCED`;
- APPLIED fill closing lifecycle -> `SOLD`.

A terminal attempt clears pending authority regardless of success/failure. A new economic attempt on an OPEN remainder requires a fresh material action assessment.

This intentionally keeps FL7.4 bounded. FL7.5 owns durable restart reconciliation, multiple sequential reductions, and broader recovery semantics.

## Post-execution marking

If the position remains OPEN after terminal/deferred processing and the same current quote has usable reference-price evidence whose observation time does not regress the ledger clock, FL7.4 may call C3 `mark_paper_position`.

`FastPaperPositionActionResult` keeps `execution_ledger_update` and `mark_ledger_update` separate so mark evidence never overwrites execution accounting evidence.

## Failure behavior

Fail closed on structural contradictions including:

- unsupported action (`BUY`/`SKIP`);
- missing/closed/wrong-mint position;
- invalid REDUCE/SELL quantity authority;
- position-state ID mismatch;
- assessment time regression;
- evaluation before assessment or ledger time;
- quote mint mismatch;
- future quote;
- non-finite/non-positive conversion or price/capacity evidence;
- malformed policy/slippage;
- stored state with impossible pending action/position mismatch.

Do not silently resize a fresh REDUCE or SELL approval to make it valid.

The only later quantity cap is `min(pending_authorized_target, current_remaining_quantity)` after the authority was already validated, which prevents over-selling an authoritative remainder rather than creating new authority.

## Non-goals

FL7.4 does not:

- change any Rust FL6 evaluator;
- choose a REDUCE fraction;
- add a learned action policy;
- alter C1 fill math;
- alter C3 ledger/accounting;
- alter legacy C4/C5 behavior;
- add persistence/restart recovery for pending Fast Lane exits;
- solve repeated partial reductions across restart (FL7.5);
- add protective stop logic (FL7.6 already owns preserved backstops);
- request provider/RPC data;
- read wall clock;
- create a signer/transaction/submission path;
- enable LIVE.

## TDD proof requirements

The RED test must import the FL7.4 public names before production files/exports exist and define behavior for:

1. stable public version/sentinels;
2. only HOLD/REDUCE/SELL approvals accepted;
3. HOLD has no target and no trade;
4. HOLD can mark from usable quote evidence without cash flow;
5. HOLD without usable mark evidence remains a no-op;
6. REDUCE requires explicit quantity and cannot equal/exceed current position;
7. SELL requires exact full-position quantity at first authorization;
8. no quote defers while retaining pending authority;
9. future quote fails closed before price use;
10. pre-latency quote defers without resetting decision time;
11. later eligible quote executes using original action timestamp;
12. same-price conversion is quantity-safe so C1 fill cannot exceed authorized base quantity;
13. successful REDUCE uses C3 to reduce quantity/release basis/book realized PnL and costs;
14. successful SELL uses C3 to close the position;
15. pending REDUCE + newer SELL promotes to SELL with newer timestamp;
16. pending SELL cannot be canceled by later HOLD/REDUCE;
17. pending REDUCE is not reset by later HOLD/REDUCE;
18. failed-after-submission terminal attempt books preserved network cost and clears pending;
19. terminal replay does not double-book ledger evidence;
20. identity/rate/NaN/negative contradictions fail closed;
21. every generated intent is PAPER-only;
22. existing Python suite remains green;
23. Rust, repository safety, and ARM64 remain unchanged/green.

## Expected scope

Exactly six FL7.4 files are expected:

1. `docs/superpowers/specs/2026-09-03-fl7-4-paper-position-actions-design.md`
2. `docs/superpowers/plans/2026-09-03-fl7-4-paper-position-actions.md`
3. `python/src/shreks_brain/fast_paper/position_models.py`
4. `python/src/shreks_brain/fast_paper/position.py`
5. `python/src/shreks_brain/fast_paper/__init__.py` — export-only
6. `python/tests/test_fast_paper_position_actions.py`

No Rust strategy, provider, storage, existing PAPER execution/ledger, legacy C4/C5, risk, deployment, signer, or LIVE authority file should change.

## Exit criterion

FL7.4 is complete when a fresh material Fast Lane open-position assessment can immediately preserve `HOLD`, authorize an explicit quantity-safe `REDUCE`, or authorize a full-position `SELL`; latency-delayed exits retain their original authority across intervening events; every actual exit is executed and accounted through the preserved PAPER engines; and no named horizon, fabricated reduction fraction, stale notional, or LIVE authority enters the path.
