# FL7.4 Fast Lane PAPER Position Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect event-resolution Fast Lane `HOLD`, explicit-quantity `REDUCE`, and full-position `SELL` assessments to the preserved PAPER execution and authoritative ledger without fabricated sizing, stale notional, or LIVE authority.

**Architecture:** Add a small `shreks_brain.fast_paper` position-action adapter. It keeps only action/quantity authorization and pending-exit state, derives transient SELL USD notional from the exact current quote price C1 consumes, and delegates every economic exit to existing `execute_paper_intent` then `apply_paper_execution`; C3 remains sole position/accounting authority.

**Tech Stack:** Python 3.12, immutable dataclasses, stdlib `hashlib`, existing Fast PAPER models, existing C1 PAPER execution, existing C3 PAPER ledger, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-fl7-4-paper-position-actions-design.md`

## Global Constraints

- Base is SEALED FL7.3 merged main `030198932943254034ddab351f76e9d91c9c923a` with merged-main CI `33757018548` four-gate green.
- LIVE remains disabled.
- `FastPaperActionAssessment` remains the action source; FL7.4 does not create another strategy evaluator.
- `REDUCE` quantity is explicit caller evidence. No default fraction may be inferred.
- `SELL` must explicitly authorize the full current OPEN position quantity when first accepted.
- Persist/retain token quantity authority, never stale USD notional.
- Every actual exit uses existing C1 execution and C3 accounting; no parallel fill/PnL/basis/cost math.
- Current quote evidence is supplied by the caller; FL7.4 performs no provider/RPC/storage/wall-clock work.
- Named forecast horizons never gate event-driven reevaluation.
- FL7.5, not FL7.4, owns broader restart/multi-reduction reconciliation.
- No production thresholds/defaults.

---

### Task 1: Freeze the FL7.4 RED public contract

**Files:**
- Create: `python/tests/test_fast_paper_position_actions.py`

**Interfaces:**
- Consumes: existing `FastPaperActionAssessment`, `PaperLedger`, `PaperFillPolicy`, `PaperQuoteState`, C1/C3 helpers.
- Produces: failing import/behavior contract for the FL7.4 public API.

- [ ] **Step 1: Add test helpers that create a real authoritative OPEN C3 position**

Use the existing public PAPER primitives rather than hand-constructing inconsistent ledger state:

```python
def _fill_policy() -> PaperFillPolicy:
    return PaperFillPolicy(
        version="paper-v1",
        assumed_latency_ms=100,
        max_quote_lag_ms=2_000,
        swap_fee_bps=30,
        network_fee_usd=0.01,
        allow_partial_fills=True,
        min_partial_fill_fraction=0.1,
    )


def _open_ledger() -> PaperLedger:
    ledger = create_paper_ledger(10_000.0, 1_000)
    intent = TradeIntent(
        mint="mint-a",
        side=TradeSide.BUY,
        requested_notional_usd=1_000.0,
        max_slippage_bps=500,
        strategy_name="impulse-scalp",
        strategy_version="1",
        score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
        decision_policy_version="assessment-v1",
        risk_policy_version="risk-v1",
        reason="test-open",
        idempotency_key="open-mint-a",
        execution_mode=RuntimeMode.PAPER,
        as_of_unix_ms=1_000,
    )
    quote = PaperQuote(
        provider="test",
        mint="mint-a",
        observed_at_unix_ms=1_100,
        state=PaperQuoteState.EXECUTABLE,
        reference_price_usd=10.0,
        execution_price_usd=10.0,
        quoted_notional_usd=1_000.0,
        available_notional_usd=1_000.0,
    )
    execution = execute_paper_intent(
        intent,
        PaperExecutionContext(1_100, ledger.processed_intent_keys, quote),
        _fill_policy(),
    )
    return apply_paper_execution(ledger, intent, execution).ledger
```

The resulting OPEN quantity is authoritative and should be read from the ledger inside each test rather than duplicated as a magic constant.

- [ ] **Step 2: Import the required FL7.4 public names before implementation exists**

```python
from shreks_brain.fast_paper import (
    FAST_PAPER_EXIT_RISK_POLICY_SENTINEL,
    FAST_PAPER_POSITION_ACTION_VERSION,
    FastPaperPositionActionApproval,
    FastPaperPositionActionError,
    FastPaperPositionActionPolicy,
    FastPaperPositionActionResult,
    FastPaperPositionActionState,
    FastPaperPositionOutcome,
    FastPaperPositionQuote,
    apply_fast_paper_position_action,
    create_fast_paper_position_action_state,
)
```

- [ ] **Step 3: Cover the behavioral matrix**

Tests must assert:

```text
1. public version = fl7.4-v1 and exit-risk sentinel is stable/non-empty
2. BUY/SKIP approvals rejected
3. HOLD rejects any target quantity
4. REDUCE/SELL reject missing/non-positive/non-finite target
5. HOLD creates no SELL and leaves cash/journal unchanged
6. usable HOLD reference quote marks only the position
7. REDUCE requires 0 < target < current authoritative quantity
8. SELL target must equal full current authoritative quantity
9. missing quote defers and preserves pending authorization
10. future quote fails closed before using price
11. pre-latency quote defers and preserves original assessment timestamp
12. eligible later quote creates PAPER-only SELL with original decision time
13. requested USD notional uses target quantity × exact execution quote price × conversion rate
14. C1 partial fill can never exceed target base quantity
15. successful REDUCE books C3 reduction/basis/cost/PnL evidence
16. successful SELL closes the authoritative position
17. pending REDUCE + newer SELL promotes to SELL
18. pending SELL + newer HOLD/REDUCE retains SELL
19. pending REDUCE + newer HOLD/REDUCE retains original REDUCE/time
20. FAILED_AFTER_SUBMISSION terminal path books C1/C3 network cost and clears pending
21. duplicate terminal replay never duplicates accounting
22. position/mint/quote/rate/time contradictions fail closed
23. no generated intent has LIVE mode
```

- [ ] **Step 4: Commit intentional RED**

Commit only the test after the design/plan commits:

```text
test: freeze FL7.4 paper position action contract
```

- [ ] **Step 5: Open a draft PR and run canonical CI**

Expected RED signature:

- Repository safety: GREEN
- Rust: GREEN
- Python: RED only because FL7.4 public imports are absent
- native ARM64 release build: GREEN

Do not write production FL7.4 code until this exact RED boundary is verified.

---

### Task 2: Add immutable FL7.4 models and validation

**Files:**
- Create: `python/src/shreks_brain/fast_paper/position_models.py`
- Modify: `python/src/shreks_brain/fast_paper/__init__.py` only after behavior implementation is ready
- Test: `python/tests/test_fast_paper_position_actions.py`

**Interfaces:**
- Produces: FL7.4 version constants, policy/approval/quote/state/result models and typed error.

- [ ] **Step 1: Define constants and enums**

```python
FAST_PAPER_POSITION_ACTION_VERSION = "fl7.4-v1"
FAST_PAPER_EXIT_RISK_POLICY_SENTINEL = "not-applicable:fast-lane-exit"

class FastPaperPositionActionError(ValueError):
    pass

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
```

- [ ] **Step 2: Define explicit policy**

```python
@dataclass(frozen=True, slots=True)
class FastPaperPositionActionPolicy:
    version: str
    max_slippage_bps: int
```

Require non-empty version and integer bps within `[0, 10_000]`.

- [ ] **Step 3: Define approval with action-specific target validation**

```python
@dataclass(frozen=True, slots=True)
class FastPaperPositionActionApproval:
    version: str
    assessment: FastPaperActionAssessment
    position_id: str
    mint: str
    quote_mint: str
    state_version: str
    target_base_quantity: float | None
```

Require:

```python
if version != FAST_PAPER_POSITION_ACTION_VERSION: reject
if action not in (HOLD, REDUCE, SELL): reject
if action is HOLD and target_base_quantity is not None: reject
if action in (REDUCE, SELL): require finite target > 0
```

Do not infer REDUCE or SELL quantity here.

- [ ] **Step 4: Define native quote model**

Mirror the FL7.2 quote boundary exactly in spirit:

```python
@dataclass(frozen=True, slots=True)
class FastPaperPositionQuote:
    provider: str
    mint: str
    quote_mint: str
    observed_at_unix_ms: int
    state: PaperQuoteState
    reference_price_quote: float | None
    execution_price_quote: float | None
    quoted_base_quantity: float | None
    available_base_quantity: float | None
    quote_to_usd_rate: float
```

For `EXECUTABLE` / `FAILED_AFTER_SUBMISSION`, require complete positive price/capacity evidence. Always require positive finite conversion rate.

- [ ] **Step 5: Define per-position pending state**

```python
@dataclass(frozen=True, slots=True)
class FastPaperPositionActionState:
    version: str
    position_id: str
    pending_exit: FastPaperPositionActionApproval | None
    last_assessment_at_unix_ms: int
```

Validate version, position identity, non-negative clock, and any pending approval belongs to the same position and is REDUCE/SELL with timestamp no later than state clock.

- [ ] **Step 6: Define result model**

```python
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
```

Keep execution booking and mark booking separate.

---

### Task 3: Implement deterministic action reconciliation and HOLD behavior

**Files:**
- Create: `python/src/shreks_brain/fast_paper/position.py`
- Test: `python/tests/test_fast_paper_position_actions.py`

**Interfaces:**
- Consumes: Task 2 models, authoritative `PaperLedger`.
- Produces: `create_fast_paper_position_action_state`, `apply_fast_paper_position_action`.

- [ ] **Step 1: Implement state creation**

```python
def create_fast_paper_position_action_state(
    position_id: str,
    as_of_unix_ms: int,
) -> FastPaperPositionActionState:
    return FastPaperPositionActionState(
        version=FAST_PAPER_POSITION_ACTION_VERSION,
        position_id=position_id,
        pending_exit=None,
        last_assessment_at_unix_ms=as_of_unix_ms,
    )
```

Validate through the dataclass; no wall clock.

- [ ] **Step 2: Resolve authoritative OPEN position by ID**

Implement a helper that rejects missing/CLOSED/mint-mismatched positions. Do not fall back to mint-only matching.

- [ ] **Step 3: Validate first-time REDUCE/SELL quantity authority**

Use strict arithmetic tolerance constants matching PAPER conventions:

```python
_REL_TOL = 1e-12
_ABS_TOL = 1e-9
```

Rules:

```python
REDUCE: target < position.quantity and not isclose(target, position.quantity)
SELL: isclose(target, position.quantity)
```

Never silently repair a fresh invalid target.

- [ ] **Step 4: Reconcile pending authority**

Implement exactly:

```python
if pending is None:
    active = None if fresh.action is HOLD else fresh
elif pending.action is SELL:
    active = pending
elif fresh.action is SELL:
    active = fresh
else:
    active = pending
```

The state clock always advances to the fresh assessment timestamp after validating it does not regress.

- [ ] **Step 5: Implement pure HOLD/no-pending result**

With no active pending exit:

- do not construct a `TradeIntent`;
- optionally mark only if the quote has usable reference evidence and quote time is within `[ledger.as_of_unix_ms, evaluated_at_unix_ms]`;
- call `mark_paper_position` with converted reference USD price and the quote's actual observation timestamp;
- return `HOLD_MARKED` when C3 applies a mark, otherwise `HOLD`.

No cash/journal entry is created by HOLD.

---

### Task 4: Implement quantity-safe transient SELL execution

**Files:**
- Modify: `python/src/shreks_brain/fast_paper/position.py`
- Test: `python/tests/test_fast_paper_position_actions.py`

**Interfaces:**
- Consumes: active pending REDUCE/SELL, caller quote, C1/C3 public APIs.
- Produces: truthful deferred/terminal REDUCE/SELL result.

- [ ] **Step 1: Validate exit quote chronology/identity**

Before consuming price fields:

```python
if quote is None: DEFERRED
if quote.mint != position.mint or quote.quote_mint != approval.quote_mint: error
if quote.observed_at_unix_ms > evaluated_at_unix_ms: error
if quote.observed_at_unix_ms < approval.assessment.as_of_unix_ms + fill_policy.assumed_latency_ms:
    DEFERRED
if quote.state is UNAVAILABLE:
    ABORTED_QUOTE_UNAVAILABLE
```

Retain pending authority for these non-terminal states.

- [ ] **Step 2: Derive current authorized attempt quantity**

```python
attempt_quantity = min(active.target_base_quantity, position.quantity)
```

This cap is allowed only after the stored approval was previously validated against an authoritative ledger position.

Require the result remains positive.

- [ ] **Step 3: Convert current quote to the existing C1 `PaperQuote`**

```python
execution_price_usd = quote.execution_price_quote * quote.quote_to_usd_rate
reference_price_usd = quote.reference_price_quote * quote.quote_to_usd_rate
requested_notional_usd = attempt_quantity * execution_price_usd
quoted_notional_usd = quote.quoted_base_quantity * execution_price_usd
available_notional_usd = quote.available_base_quantity * execution_price_usd
```

Use finite validation and never mix reference/execution prices.

- [ ] **Step 4: Build deterministic transient PAPER SELL**

```python
TradeIntent(
    mint=position.mint,
    side=TradeSide.SELL,
    requested_notional_usd=requested_notional_usd,
    max_slippage_bps=policy.max_slippage_bps,
    strategy_name=active.assessment.strategy_family,
    strategy_version=active.assessment.strategy_version,
    score_policy_version=FAST_LANE_SCORE_POLICY_SENTINEL,
    decision_policy_version=active.assessment.version,
    risk_policy_version=FAST_PAPER_EXIT_RISK_POLICY_SENTINEL,
    reason=active.assessment.reasons[0],
    idempotency_key=_exit_idempotency_key(active),
    execution_mode=RuntimeMode.PAPER,
    as_of_unix_ms=active.assessment.as_of_unix_ms,
)
```

Idempotency hash includes stable action/position/assessment/reasons/target quantity and excludes quote price.

- [ ] **Step 5: Delegate execution to C1**

```python
execution = execute_paper_intent(
    intent,
    PaperExecutionContext(
        evaluated_at_unix_ms=evaluated_at_unix_ms,
        processed_intent_keys=ledger.processed_intent_keys,
        quote=paper_quote,
    ),
    fill_policy,
)
```

If C1 returns `DEFERRED`, retain pending and do not book ledger.

- [ ] **Step 6: Delegate every terminal result to C3**

For non-DEFERRED C1 results:

```python
update = apply_paper_execution(ledger, intent, execution)
next_ledger = update.ledger
```

Clear pending authority after terminal execution attempt.

Classify:

- duplicate/NOOP terminal key -> `ALREADY_PROCESSED`;
- C3 rejected -> `LEDGER_REJECTED`;
- failed/no fill -> `EXECUTION_FAILED`;
- APPLIED and position remains OPEN with lower quantity -> `REDUCED`;
- APPLIED and position CLOSED -> `SOLD`.

- [ ] **Step 7: Keep mark evidence separate**

If position remains OPEN and current quote supports a non-regressing reference mark, call C3 marking after execution/defer processing and store it separately from `execution_ledger_update`.

---

### Task 5: Export API and prove GREEN

**Files:**
- Modify: `python/src/shreks_brain/fast_paper/__init__.py`
- Test: `python/tests/test_fast_paper_position_actions.py`

**Interfaces:**
- Produces: stable additive FL7.4 public API.

- [ ] **Step 1: Add export-only imports**

Export only the Task 2/3 public symbols. Do not alter FL7.1/7.2/7.3 behavior.

- [ ] **Step 2: Run focused tests**

Run the FL7.4 test module and require all tests green.

- [ ] **Step 3: Run full Python suite**

Require no existing regression, especially stable public enums and preserved PAPER accounting tests.

- [ ] **Step 4: Commit implementation**

After RED is proven, implementation/fix authoring may use temporary commits; final clean history will collapse them into one implementation commit.

---

### Task 6: Candidate audit, clean history, guarded merge, seal

**Expected files exactly:**

1. `docs/superpowers/specs/2026-09-03-fl7-4-paper-position-actions-design.md`
2. `docs/superpowers/plans/2026-09-03-fl7-4-paper-position-actions.md`
3. `python/src/shreks_brain/fast_paper/position_models.py`
4. `python/src/shreks_brain/fast_paper/position.py`
5. `python/src/shreks_brain/fast_paper/__init__.py`
6. `python/tests/test_fast_paper_position_actions.py`

- [ ] **Step 1: Audit diff before trusting CI**

Require `fast_paper/__init__.py` export-only and no Rust/provider/storage/PAPER/risk/legacy C4/C5/runtime authority changes.

- [ ] **Step 2: Run candidate canonical CI**

Require all four canonical gates GREEN.

- [ ] **Step 3: Reconstruct clean history**

Preserve exactly:

```text
design -> plan -> RED -> implementation
```

The clean implementation commit must point to the byte-identical candidate tree already proven green.

- [ ] **Step 4: Verify clean compare**

Require exactly four commits ahead of sealed FL7.3 and exactly six files.

- [ ] **Step 5: Run fresh exact-clean-head CI**

Require safety/Rust/Python/ARM64 all green on immutable clean head.

- [ ] **Step 6: Update PR proof body and mark ready**

Record intentional RED, candidate green, clean tree identity, exact scope, and authority audit.

- [ ] **Step 7: Guarded merge**

Merge only with `expected_head_sha` equal to the verified clean head.

- [ ] **Step 8: Require fresh push-triggered merged-main CI**

Confirm `main` points to returned merge SHA and require all four gates green.

- [ ] **Step 9: Mark FL7.4 SEALED only after merged-main proof**

LIVE remains disabled. Do not claim profitability or full FL7 completion; FL7.5/7.6 remain.

## Completion Claim Boundary

Do not call FL7.4 SEALED before both fresh exact-clean-head and fresh merged-main canonical CI are fully green.

Do not claim that FL7.4 chooses an optimal reduction size. It only executes an explicit reduction quantity supplied by the approved Fast Lane action boundary.
