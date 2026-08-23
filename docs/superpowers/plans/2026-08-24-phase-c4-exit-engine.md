# Phase C4 Exit Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, point-in-time C4 exit engine that emits HOLD/REDUCE/EXIT with exact target quantity, structured reasons, trailing/take-profit state, and no execution authority.

**Architecture:** Add a standalone `shreks_brain.exits` package. Reuse B2 `FeatureVector` for market/flow/momentum evidence and C3 `PaperPosition` for position truth; add only size-aware exit execution evidence and immutable C4 state. Keep SELL intent construction out of C4 because the current USD-notional TradeIntent cannot safely guarantee a quantity reduction across price movement.

**Tech Stack:** Python 3.12+, stdlib dataclasses/enums/math only, pytest, existing Shreks B2/B8/C3 domain models.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-c4-exit-engine-design.md`

## Global Constraints

- Base exactly on verified C3 head `7393575e6b54033b335becaa484cf4a992857bc9`.
- Reuse `DecisionAction.HOLD / REDUCE / EXIT`; do not widen or alter B8 entry decision behavior.
- Reuse unchanged B2 `b2-v1` FeatureVector; no feature-schema widening.
- Reuse C3 PaperPosition as authoritative quantity/entry/lifecycle state; no accounting duplication.
- No production exit thresholds or default ExitPolicy instance.
- No provider/storage/wall-clock/RNG reads in exit logic.
- No SELL TradeIntent construction, C1 fill changes, C3 accounting changes, autonomous loop, persistence, wallet reconstruction, signer, transaction, or live-money path.
- Missing evidence stays unknown; no silent zero/healthy conversion.
- Every exit has exactly one primary reason plus auditable supporting findings.
- Strict RED -> expected failure -> minimal GREEN for every task.

---

### Task 1: Immutable Exit Domain and State Initialization

**Files:**
- Create: `python/tests/test_exit_models.py`
- Create: `python/src/shreks_brain/exits/models.py`

**Interfaces:**
- Produces: `ExitRouteState`, `ExitReasonCode`, `TakeProfitLevel`, `ExitPolicy`, `ExitExecutionContext`, `ExitState`, `ExitFinding`, `ExitAssessment`.
- Later engine consumes these directly.

- [ ] **Step 1: Write failing model-contract tests**

Pin:

```python
assert [member.value for member in ExitRouteState] == [
    "AVAILABLE", "UNAVAILABLE", "UNKNOWN"
]
assert DecisionAction.HOLD.value == "HOLD"
assert DecisionAction.REDUCE.value == "REDUCE"
assert DecisionAction.EXIT.value == "EXIT"
```

Validate:

- no default `ExitPolicy`,
- non-empty version/schema strings,
- optional rule semantics and paired-threshold validation,
- strictly increasing unique take-profit levels,
- fractions in `(0,1]`,
- size-aware impact percentage/notional pairing,
- optional wallet signal remains tri-state,
- `ExitState` policy/position identity and high-water chronology,
- assessment action/target invariants,
- exactly one primary finding matching `primary_reason`,
- assessment contains no TradeIntent/fill/signer/transaction/live fields.

- [ ] **Step 2: Commit RED and require CI collection failure**

Expected Python failure:

```text
ModuleNotFoundError: No module named 'shreks_brain.exits'
```

Prior Rust/workspace/safety layers must remain healthy.

- [ ] **Step 3: Implement minimal immutable models**

Required model shapes:

```python
class ExitRouteState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True, slots=True)
class TakeProfitLevel:
    name: str
    trigger_return_pct: float
    reduce_fraction_of_current_quantity: float

@dataclass(frozen=True, slots=True)
class ExitPolicy:
    version: str
    required_feature_schema_version: str
    max_market_data_age_ms: int
    max_execution_evidence_age_ms: int
    hard_stop_loss_pct: float | None
    take_profit_levels: tuple[TakeProfitLevel, ...]
    trailing_activation_return_pct: float | None
    trailing_stop_drawdown_pct: float | None
    max_hold_seconds: int | None
    flow_exit_max_buy_fraction_m5: float | None
    flow_exit_max_buy_pressure_acceleration: float | None
    momentum_exit_max_return_1m_pct: float | None
    momentum_exit_max_return_5m_pct: float | None
    min_liquidity_usd: float | None
    max_exit_price_impact_pct: float | None
    min_exit_capacity_fraction: float | None
    wallet_distribution_enabled: bool

@dataclass(frozen=True, slots=True)
class ExitExecutionContext:
    as_of_unix_ms: int
    observed_at_unix_ms: int
    route_state: ExitRouteState
    available_exit_notional_usd: float | None
    expected_exit_price_impact_pct: float | None
    price_impact_notional_usd: float | None
    wallet_distribution_detected: bool | None
    global_halt_active: bool

@dataclass(frozen=True, slots=True)
class ExitState:
    policy_version: str
    position_id: str
    mint: str
    initialized_at_unix_ms: int
    last_evaluated_at_unix_ms: int
    high_water_price_usd: float
    high_water_at_unix_ms: int
    completed_take_profit_levels: frozenset[str]
```

`ExitAssessment` must carry the exact fields defined by the design, with `next_state` and findings.

- [ ] **Step 4: Run full CI and require GREEN**

---

### Task 2: Deterministic Exit Assessment Engine

**Files:**
- Create: `python/tests/test_exit_engine.py`
- Create: `python/src/shreks_brain/exits/engine.py`

**Interfaces:**
- Produces:

```python
def create_exit_state(position: PaperPosition, policy: ExitPolicy) -> ExitState: ...

def assess_exit(
    position: PaperPosition,
    features: FeatureVector,
    execution: ExitExecutionContext,
    state: ExitState,
    policy: ExitPolicy,
) -> ExitAssessment: ...
```

- [ ] **Step 1: Write failing behavioral tests**

Use canonical C3 OPEN positions and B2 FeatureVectors to pin exact precedence and equality boundaries.

Required cases:

1. feature schema mismatch -> HOLD.
2. CLOSED position -> HOLD.
3. state identity mismatch -> HOLD.
4. state policy mismatch -> HOLD.
5. feature/context `as_of` mismatch -> HOLD.
6. chronology before position/state -> HOLD.
7. global halt -> full EXIT even with stale/missing price.
8. max hold equality -> full EXIT even with stale/missing price.
9. future/stale market data -> HOLD and no high-water advance.
10. future/stale execution evidence -> HOLD and no market triggers.
11. missing/non-positive current price -> HOLD.
12. route UNAVAILABLE -> full EXIT.
13. liquidity equality at minimum -> full EXIT.
14. size-aware impact equality at maximum -> full EXIT.
15. capacity equality at minimum fraction -> full EXIT.
16. hard-stop equality -> full EXIT.
17. trailing remains inactive below activation.
18. trailing activation equality passes; drawdown equality -> full EXIT.
19. explicit wallet distribution True + enabled -> full EXIT; None/False cannot trigger.
20. flow deterioration requires both configured known signals.
21. momentum deterioration requires both configured known signals.
22. earliest incomplete take-profit level only; fraction <1 -> REDUCE.
23. take-profit fraction 1 -> EXIT.
24. completed take-profit level is skipped.
25. emergency/full-exit reason outranks simultaneous take profit.
26. normal fresh evidence -> HOLD.
27. high-water update is `max(previous, current)` and never decreases.
28. findings contain exactly one primary and simultaneously triggered lower-priority conditions as supporting.

- [ ] **Step 2: Commit RED and require expected missing-engine failure**

Expected:

```text
ModuleNotFoundError: No module named 'shreks_brain.exits.engine'
```

- [ ] **Step 3: Implement minimal pure engine**

Fixed primary precedence must exactly follow the design. Use immediate compatibility/data-quality HOLDs; for usable evidence compute all trigger conditions, select the first by precedence, then attach lower-priority proven triggers as supporting findings.

Price-derived formulas:

```python
position_age_seconds = (as_of - position.opened_at_unix_ms) / 1000.0
price_return_pct = (price / position.weighted_entry_price_usd - 1.0) * 100.0
market_value = position.quantity * price
high_water = max(state.high_water_price_usd, price)
drawdown_pct = (price / high_water - 1.0) * 100.0
```

Capacity when known:

```python
capacity_fraction = min(1.0, available_exit_notional_usd / market_value)
```

- [ ] **Step 4: Run full CI and require GREEN**

---

### Task 3: Fill-Confirmed Take-Profit State Advancement

**Files:**
- Create: `python/tests/test_exit_acknowledgement.py`
- Modify: `python/src/shreks_brain/exits/engine.py`

**Interfaces:**
- Produces:

```python
def acknowledge_exit_fill(
    state: ExitState,
    decision: ExitAssessment,
    before_position: PaperPosition,
    after_position: PaperPosition,
) -> ExitState: ...
```

- [ ] **Step 1: Write failing acknowledgement tests**

Pin:

- HOLD cannot complete a take-profit level.
- non-take-profit EXIT/REDUCE cannot complete a take-profit level.
- mismatched state/decision/position IDs reject.
- quantity increase rejects.
- failed/no-fill (same quantity) leaves level incomplete.
- partial fill below decision target leaves level incomplete.
- exact target equality completes the triggered level.
- reduction beyond target completes the level.
- full close completes a take-profit level when the decision was take-profit driven.
- completed level set is immutable and idempotent.
- high-water evidence is preserved.

- [ ] **Step 2: Commit RED and require missing-function failure**

- [ ] **Step 3: Implement minimal acknowledgement helper**

Only actual C3 before/after quantity evidence may advance `completed_take_profit_levels`. Do not infer completion from a C1 decision or requested quantity alone.

- [ ] **Step 4: Run full CI and require GREEN**

---

### Task 4: Stable Public Exit API and Documentation

**Files:**
- Create: `python/tests/test_exit_public_api.py`
- Create: `python/src/shreks_brain/exits/__init__.py`
- Modify: `README.md`
- Replace this tracked plan with a concise verification record after package GREEN.

**Public API:**

```text
ExitAssessment
ExitExecutionContext
ExitFinding
ExitPolicy
ExitReasonCode
ExitRouteState
ExitState
TakeProfitLevel
acknowledge_exit_fill
assess_exit
create_exit_state
```

- [ ] **Step 1: Write package-level RED test**

Require exactly the eleven symbols above from `shreks_brain.exits`, plus a real create-state -> assess -> acknowledgement flow.

Assert public models/functions expose no `TradeIntent`, quote/fill, wallet secret, signer, transaction, live execution, persistence, or provider authority.

- [ ] **Step 2: Commit RED and require package-import failure**

- [ ] **Step 3: Add exact exports; run full CI GREEN**

- [ ] **Step 4: Document C4 semantics in README**

Document:

- first-class HOLD/REDUCE/EXIT decisions,
- exact precedence and emergency-over-profit behavior,
- no production thresholds,
- B2/C3 evidence reuse,
- size-aware exitability evidence,
- wallet evidence remains optional/unfabricated,
- take-profit completion only after actual booked reduction,
- mark/price is not an executable quote,
- C4 outputs quantity, not SELL TradeIntent,
- C5 owns safe quote-aware loop wiring.

- [ ] **Step 5: Replace plan with verification record and freeze branch**

The tracked verification record must contain predecessor SHA, architecture, RED/GREEN commits/runs, public API, and scope boundaries, but **not** final branch SHA/run.

After that commit, no further C4 branch writes.

- [ ] **Step 6: Exact-head seal**

On the frozen head:

1. run/fetch fresh full CI and require Rust/Python/workspace/safety green,
2. compare against final C3 head `7393575e6b54033b335becaa484cf4a992857bc9`,
3. require only intended C4 docs/package/tests/README files,
4. update stacked draft PR metadata only with final head/run/evidence,
5. leave PR draft and unmerged.

## Expected C4 diff

```text
README.md
docs/superpowers/plans/2026-08-24-phase-c4-exit-engine.md
docs/superpowers/specs/2026-08-24-phase-c4-exit-engine-design.md
python/src/shreks_brain/exits/__init__.py
python/src/shreks_brain/exits/models.py
python/src/shreks_brain/exits/engine.py
python/tests/test_exit_models.py
python/tests/test_exit_engine.py
python/tests/test_exit_acknowledgement.py
python/tests/test_exit_public_api.py
```

No B2, B8, risk, C1 execution, C3 accounting, Rust/storage/provider, signer, transaction, or live-execution implementation file should change.
