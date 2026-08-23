# Phase C1 Paper Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first paper-trading execution boundary: consume the exact B9 `TradeIntent`, apply deterministic point-in-time latency/quote/fill/cost rules, and return immutable execution economics for later C3 accounting.

**Architecture:** Create a focused `shreks_brain.paper` package beside the existing risk layer. Task 1 defines immutable execution-domain models; Task 2 adds one pure adapter with no I/O or RNG; Task 3 exposes the exact public API, documents the contract, and seals the branch with exact-head CI and a B9->C1 diff audit. Position ownership, exits, autonomous looping, persistence, and live execution stay out of scope.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, `math.isclose`, pytest, existing GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-c1-paper-execution-design.md`

## Global Constraints

- Base is verified B9 head `be84a3b94dfd8d6a8decb489049cd8ee5adea0a3`.
- Exact B9 `TradeIntent` is the sole trade request interface.
- `execute_paper_intent()` performs no storage, provider, network, balance, clock, RNG, or position-ledger I/O.
- Only `RuntimeMode.PAPER` intents execute in C1.
- A supplied quote after evaluation time fails immediately; no future evidence is carried forward.
- No quote price may be extrapolated beyond `quoted_notional_usd` or `available_notional_usd`.
- Slippage is represented in execution price and audit fields; it is not charged again as explicit cost.
- Explicit fill cost is swap fee plus network fee only.
- Failed-after-submission outcomes charge the configured network fee without a fill.
- BUY and SELL use the same capacity boundary; SELL therefore supports realistic exit-liquidity constraints later.
- No production `PaperFillPolicy` defaults.
- No positions, balances, realized/unrealized PnL, exits, autonomous loop, persistence, signer, transaction construction/submission, or live-money path.

---

### Task 1: Immutable paper execution domain

**Files:**
- Create: `python/src/shreks_brain/paper/models.py`
- Test: `python/tests/test_paper_models.py`

**Interfaces:**
- Consumes: `RuntimeMode`, B9 `TradeIntent`, `TradeSide`.
- Produces: `PaperQuoteState`, `PaperExecutionState`, `PaperExecutionReasonCode`, `PaperFillPolicy`, `PaperQuote`, `PaperExecutionContext`, `PaperExecutionFinding`, `PaperFill`, `PaperExecutionResult`.

- [ ] **Step 1: Write the failing model-contract test**

Create `python/tests/test_paper_models.py` and import Task-1 symbols from `shreks_brain.paper.models`.

Pin exact enum orders:

```python
assert tuple(item.value for item in PaperQuoteState) == (
    "EXECUTABLE",
    "UNAVAILABLE",
    "FAILED_AFTER_SUBMISSION",
)
assert tuple(item.value for item in PaperExecutionState) == (
    "DEFERRED",
    "FAILED",
    "PARTIAL",
    "FILLED",
)
assert tuple(item.value for item in PaperExecutionReasonCode) == (
    "INTENT_MODE_NOT_PAPER",
    "DUPLICATE_INTENT",
    "EVALUATION_BEFORE_INTENT",
    "QUOTE_AFTER_EVALUATION",
    "QUOTE_MINT_MISMATCH",
    "LATENCY_PENDING",
    "QUOTE_PENDING",
    "QUOTE_BEFORE_LATENCY",
    "QUOTE_WINDOW_EXPIRED",
    "QUOTE_TOO_LATE",
    "ROUTE_UNAVAILABLE",
    "SIMULATED_SUBMISSION_FAILED",
    "REFERENCE_PRICE_UNKNOWN",
    "EXECUTION_PRICE_UNKNOWN",
    "QUOTED_NOTIONAL_UNKNOWN",
    "AVAILABLE_NOTIONAL_UNKNOWN",
    "NO_EXECUTABLE_NOTIONAL",
    "PARTIAL_FILL_DISABLED",
    "PARTIAL_FILL_TOO_SMALL",
    "SLIPPAGE_EXCEEDS_INTENT",
    "FILL_PARTIAL",
    "FILL_COMPLETE",
)
```

Use this explicit policy fixture:

```python
PaperFillPolicy(
    version="paper-v1-test",
    assumed_latency_ms=250,
    max_quote_lag_ms=1_000,
    swap_fee_bps=30,
    network_fee_usd=0.01,
    allow_partial_fills=True,
    min_partial_fill_fraction=0.25,
)
```

Prove validation boundaries from the spec: non-empty version; non-negative integer latency/lag; fee bps `[0, 10000]`; finite non-negative network fee; boolean partial-fill flag; partial fraction `(0,1]`.

Use executable quote:

```python
PaperQuote(
    provider="paper-quote-test",
    mint="Mint111",
    observed_at_unix_ms=1_000_500,
    state=PaperQuoteState.EXECUTABLE,
    reference_price_usd=1.0,
    execution_price_usd=1.01,
    quoted_notional_usd=1_000.0,
    available_notional_usd=750.0,
)
```

Prove optional economics are allowed but present values validate strictly; quote/context dataclasses are frozen; processed keys must be a frozenset of non-empty strings.

Construct and validate canonical BUY fill:

```python
PaperFill(
    intent_idempotency_key="intent-key",
    mint="Mint111",
    side=TradeSide.BUY,
    state=PaperExecutionState.FILLED,
    requested_notional_usd=500.0,
    filled_notional_usd=500.0,
    unfilled_notional_usd=0.0,
    quantity=500.0 / 1.01,
    reference_price_usd=1.0,
    execution_price_usd=1.01,
    signed_slippage_bps=100.0,
    signed_slippage_usd=(500.0 / 1.01) * 0.01,
    swap_fee_usd=1.5,
    network_fee_usd=0.01,
    explicit_cost_usd=1.51,
    net_cash_flow_usd=-501.51,
    quote_provider="paper-quote-test",
    executed_at_unix_ms=1_000_500,
)
```

Construct a SELL partial fill with positive unfilled notional and positive cash flow. Prove BUY/SELL cash-flow invariants, quantity arithmetic, `filled + unfilled == requested`, explicit-cost arithmetic, valid PARTIAL/FILLED state pairing, and signed slippage fields may be negative.

Construct canonical `PaperExecutionResult` for DEFERRED, FAILED-after-submission, PARTIAL, and FILLED. Prove state invariants, exactly one finding, failed submission network cost semantics, and fill/result economics/timestamps must match.

Inspect fields and prove paper models contain none of:

```text
private_key
secret
wallet_secret
transaction
signature
realized_pnl
unrealized_pnl
average_entry
position
balance
```

- [ ] **Step 2: Verify RED**

Commit only `test_paper_models.py`, open a stacked draft PR, and require Python CI to fail only because `shreks_brain.paper` is missing. Existing Rust/workspace/repository-safety checks must remain green.

- [ ] **Step 3: Implement minimal models**

Create `python/src/shreks_brain/paper/models.py` exactly from the spec using focused validators and `math.isclose(rel_tol=1e-12, abs_tol=1e-9)` for arithmetic invariants.

Do not add the adapter, default policy, ledger, storage, or provider calls.

- [ ] **Step 4: Verify GREEN**

Run full PR CI and require Rust, Python, workspace metadata, and repository safety all green.

- [ ] **Step 5: Record evidence**

Record Task-1 RED/GREEN commit SHAs and CI IDs in the later verification record and PR metadata.

---

### Task 2: Deterministic realistic paper adapter

**Files:**
- Create: `python/src/shreks_brain/paper/engine.py`
- Test: `python/tests/test_paper_engine.py`

**Interfaces:**
- Consumes:

```python
TradeIntent
PaperExecutionContext
PaperFillPolicy
```

- Produces:

```python
def execute_paper_intent(
    intent: TradeIntent,
    context: PaperExecutionContext,
    policy: PaperFillPolicy,
) -> PaperExecutionResult:
    ...
```

- [ ] **Step 1: Write canonical intent/context fixtures and full-fill expectation**

Use a canonical PAPER BUY intent:

```python
TradeIntent(
    mint="Mint111",
    side=TradeSide.BUY,
    requested_notional_usd=500.0,
    max_slippage_bps=300,
    strategy_name="fresh_launch_continuation",
    strategy_version="fresh-test",
    score_policy_version="score-v1-test",
    decision_policy_version="decision-v1-test",
    risk_policy_version="risk-v1-test",
    reason="ENTRY_APPROVED",
    idempotency_key="intent-key",
    execution_mode=RuntimeMode.PAPER,
    as_of_unix_ms=1_000_000,
)
```

With latency 250ms, lag 1000ms, quote at `1_000_500`, reference `1.0`, execution `1.01`, quoted/available >= 500, expect `FILLED / FILL_COMPLETE`, quantity `500/1.01`, 100 bps adverse BUY slippage, $1.50 swap fee, $0.01 network fee, $1.51 explicit cost, and net cash flow `-501.51`.

- [ ] **Step 2: Write failing mode/idempotency/contradiction precedence tests**

Pin exact first reasons for:

```text
INTENT_MODE_NOT_PAPER
DUPLICATE_INTENT
EVALUATION_BEFORE_INTENT
QUOTE_AFTER_EVALUATION
QUOTE_MINT_MISMATCH
```

Prove a future-dated wrong-mint quote yields `QUOTE_AFTER_EVALUATION` first. All these results are FAILED with zero costs/fill.

- [ ] **Step 3: Write failing latency and quote-window tests**

For `eligible_at = 1_000_250` and `deadline = 1_001_250`, pin:

```text
LATENCY_PENDING
QUOTE_PENDING
QUOTE_BEFORE_LATENCY
QUOTE_WINDOW_EXPIRED
QUOTE_TOO_LATE
```

Boundary equality at eligible time and deadline must be accepted. Quote before eligible remains DEFERRED while evaluation <= deadline and becomes window-expired after deadline. Zero latency and zero lag must also work.

- [ ] **Step 4: Write failing route-state tests**

`UNAVAILABLE` -> `FAILED / ROUTE_UNAVAILABLE`, zero cost.

`FAILED_AFTER_SUBMISSION` -> `FAILED / SIMULATED_SUBMISSION_FAILED`, swap fee zero, network/explicit cost equal policy network fee, net cash flow negative network fee, no fill.

- [ ] **Step 5: Write failing quote-economics order tests**

For executable quote, remove one field at a time and pin fixed order:

```text
REFERENCE_PRICE_UNKNOWN
EXECUTION_PRICE_UNKNOWN
QUOTED_NOTIONAL_UNKNOWN
AVAILABLE_NOTIONAL_UNKNOWN
```

- [ ] **Step 6: Write failing capacity and partial-fill tests**

Effective fill is exactly:

```python
min(intent.requested_notional_usd, quote.quoted_notional_usd, quote.available_notional_usd)
```

Pin:

- zero capacity -> `NO_EXECUTABLE_NOTIONAL`;
- capacity below request with partial disabled -> `PARTIAL_FILL_DISABLED`;
- partial fraction below configured minimum -> `PARTIAL_FILL_TOO_SMALL`;
- equality at minimum fraction passes;
- quote cap 300 and available cap 400 for 500 request fills only 300;
- quote cap 800 and available cap 250 fills only 250;
- a quote never fills more notional than its evidenced `quoted_notional_usd`.

- [ ] **Step 7: Write failing BUY/SELL slippage tests**

Pin side-aware formulas:

```python
# BUY
(execution / reference - 1.0) * 10_000.0
# SELL
(1.0 - execution / reference) * 10_000.0
```

Test adverse, favorable, and exact-threshold equality for each side. Strictly greater than intent max slippage fails `SLIPPAGE_EXCEEDS_INTENT`; equality passes.

- [ ] **Step 8: Write failing cost/cash-flow and SELL-liquidity tests**

For partial/full BUY and SELL, assert:

```python
swap_fee = filled_notional * swap_fee_bps / 10_000
explicit_cost = swap_fee + network_fee
BUY cash = -(filled_notional + explicit_cost)
SELL cash = filled_notional - explicit_cost
```

Assert signed slippage dollars are audit-only and not added again to explicit costs.

Create a SELL intent requesting $500 with available exit notional $125 and minimum partial fraction <= 0.25; assert a $125 PARTIAL fill rather than a perfect exit.

- [ ] **Step 9: Write failing determinism and terminal-finding test**

Equal inputs must produce equal results. Every result carries exactly one finding. A case violating multiple downstream rules returns only the earliest fixed-precedence reason.

- [ ] **Step 10: Verify RED**

Commit only `test_paper_engine.py`; full PR CI must fail Python only because `shreks_brain.paper.engine` / `execute_paper_intent` is missing.

- [ ] **Step 11: Implement minimal adapter**

Create `python/src/shreks_brain/paper/engine.py` with immediate-return helpers and exact stage order:

```text
intent mode
processed duplicate
evaluation timestamp
future quote
quote mint
latency
quote presence/window
quote timing
route state
required economics
capacity
partial rules
slippage ceiling
fill/cost arithmetic
PARTIAL/FILLED
```

Use no RNG, wall clock, provider/storage calls, or mutations.

- [ ] **Step 12: Verify GREEN**

Run full PR CI and require all jobs green.

- [ ] **Step 13: Record evidence**

Record Task-2 RED/GREEN commit SHAs and CI IDs.

---

### Task 3: Stable package API, documentation, and immutable seal

**Files:**
- Create: `python/src/shreks_brain/paper/__init__.py`
- Test: `python/tests/test_paper_public_api.py`
- Modify: `README.md`
- Modify: this plan only for the final non-self-referential verification record

**Stable exports:**

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

- [ ] **Step 1: Write failing public API regression test**

Import all ten symbols from `shreks_brain.paper`. Assert `execute_paper_intent` is callable and canonical PAPER input returns `PaperExecutionResult` with `PaperFill`.

Also import representative stable symbols from runtime/safety/features/setups/regime/scoring/decision/risk to prove C1 does not break earlier layers.

Inspect public `PaperFill` / `PaperExecutionResult` fields and assert no position, wallet, signer, transaction, secret, realized/unrealized PnL, or live-execution authority exists.

- [ ] **Step 2: Verify RED**

Full CI must fail Python only because package-level paper exports are absent.

- [ ] **Step 3: Export exact API**

Create `python/src/shreks_brain/paper/__init__.py` and export exactly the ten spec symbols. Do not export default policies, internal helpers, ledgers, or live executors.

- [ ] **Step 4: Verify package GREEN**

Run full PR CI and require all jobs green.

- [ ] **Step 5: Document C1 semantics**

Add a focused README section documenting exact B9 `TradeIntent` consumption, deterministic latency/quote window, no RNG, size-covered quotes, partial/full/unavailable/failed-after-submission outcomes, side-aware slippage, explicit swap/network costs, failed-attempt network cost, SELL exit-capacity behavior, no position ledger yet, and no live execution.

- [ ] **Step 6: Replace this checklist with verification evidence**

Before the final exact-head CI, replace this tracked plan with a concise completed verification record containing only predecessor TDD SHAs/runs and architectural facts. Do **not** write the final branch SHA/run into a tracked file.

- [ ] **Step 7: Freeze and verify final head**

After the verification-record commit, make no further tracked branch writes. Run fresh full CI at that exact head and require Rust, Python, workspace metadata, and repository safety all green.

- [ ] **Step 8: Audit final diff**

Compare verified B9 `be84a3b94dfd8d6a8decb489049cd8ee5adea0a3` to the frozen C1 head. Expected files are exactly:

```text
README.md
docs/superpowers/plans/2026-08-23-phase-c1-paper-execution.md
docs/superpowers/specs/2026-08-23-phase-c1-paper-execution-design.md
python/src/shreks_brain/paper/__init__.py
python/src/shreks_brain/paper/models.py
python/src/shreks_brain/paper/engine.py
python/tests/test_paper_models.py
python/tests/test_paper_engine.py
python/tests/test_paper_public_api.py
```

No prior brain layer, Rust, storage, provider, position ledger, exit engine, signer, transaction, or live-execution implementation file may change.

- [ ] **Step 9: Seal PR metadata only**

Update the draft PR body with final immutable C1 head, final CI run, TDD RED/GREEN evidence, nine-file diff audit, and explicit statement that the PR remains draft/unmerged. Do not mutate the branch afterward.
