# Phase B4b Graduation/Breakout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, point-in-time Graduation/Breakout setup evaluator that consumes unchanged B2 features plus verified B4a graduation context, with no execution authority or production trading defaults.

**Architecture:** Keep `FeatureVector` at `b2-v1`. Add setup-specific immutable lifecycle/context, policy, finding, and assessment types to the existing setup models module, then add a pure `graduation_breakout.py` evaluator beside unchanged Fresh Launch logic. Stable exports remain under `shreks_brain.setups`; no Rust/storage/provider or execution changes are allowed in this phase.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing `shreks_brain.features` and `shreks_brain.safety` types, repository GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b4b-graduation-breakout-design.md`

## Global Constraints

- Base is verified B4a head `b50f80d82ca25aac2d1da99269c8f9ca54175525`.
- B2 schema remains exactly `b2-v1`; do not modify `python/src/shreks_brain/features/`.
- `detected_at_unix_ms` is the sole graduation decision clock; `occurred_at_unix_ms` is audit metadata only.
- Only `pump_graduation` with exact `pump_fun_bonding_curve -> pump_swap` transition is eligible lifecycle evidence.
- Setup state is shared `SetupState.BLOCKED / WATCH / READY`.
- B4b-v1 uses exactly 8 equal-weight confirmations.
- Missing evidence never becomes zero and never passes a condition.
- B1 safety `PASS` is mandatory; `REJECT` and `INCOMPLETE` cannot be overridden.
- No production default thresholds.
- No SQLite/provider reads from setup code.
- No `TradeDecision`, `TradeIntent`, sizing, paper fills, wallets, signers, Jupiter execution, or live-money path.
- B3 public behavior and imports must remain unchanged.

---

### Task 1: Immutable Graduation/Breakout model contract

**Files:**
- Create: `python/tests/test_graduation_breakout_models.py`
- Modify: `python/src/shreks_brain/setups/models.py`

**Interfaces:**
- Consumes: existing shared `SetupState` and validation helpers in `setups/models.py`.
- Produces:
  - `GRADUATION_BREAKOUT_SETUP_NAME = "graduation_breakout"`
  - `GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED = 8`
  - `GraduationBreakoutReasonCode`
  - `GraduationContext`
  - `GraduationBreakoutFinding`
  - `GraduationBreakoutPolicy`
  - `GraduationBreakoutAssessment`

- [ ] **Step 1: Write the failing model tests**

Create tests that import the seven B4b symbols above from `shreks_brain.setups.models` and prove:

```python
assert GRADUATION_BREAKOUT_SETUP_NAME == "graduation_breakout"
assert GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED == 8
assert GraduationBreakoutReasonCode.GRADUATION_NOT_VERIFIED.value == "GRADUATION_NOT_VERIFIED"
assert GraduationBreakoutReasonCode.ALL_CONFIRMATIONS_PASSED.value == "ALL_CONFIRMATIONS_PASSED"
```

Use a canonical `GraduationContext` fixture:

```python
GraduationContext(
    event_type="pump_graduation",
    provider="helius",
    mint="mint-a",
    quote_mint="So11111111111111111111111111111111111111112",
    from_venue="pump_fun_bonding_curve",
    to_venue="pump_swap",
    pool_address="pool-a",
    signature="sig-a",
    slot=2**64 - 1,
    detected_at_unix_ms=1_000_000,
    occurred_at_unix_ms=999_000,
)
```

Prove every identity string rejects `""` and whitespace-only values; slot rejects negative, float, and bool; timestamps reject negative/float/bool; `occurred_at_unix_ms=None` is valid. Prove context, policy, finding, and assessment are frozen.

Use an explicit policy fixture with:

```python
GraduationBreakoutPolicy(
    version="graduation-v1-test",
    min_seconds_since_graduation=30.0,
    max_seconds_since_graduation=900.0,
    max_source_age_ms=30_000,
    min_liquidity_usd=50_000.0,
    max_exit_price_impact_pct=5.0,
    min_tx_count_m5=50,
    min_volume_velocity_ratio=1.2,
    min_buy_fraction_m5=0.60,
    min_buy_pressure_acceleration=0.05,
    min_return_1m_pct=1.0,
    max_return_1m_pct=40.0,
    min_liquidity_change_5m_pct=0.0,
    min_distance_from_local_high_pct=-15.0,
    min_range_position_pct=60.0,
)
```

Prove version non-empty, numeric finiteness, non-negative fields, source-age/tx-count integer validation, bounded buy fraction/range position, non-positive distance-from-high threshold, `max_seconds_since_graduation > min_seconds_since_graduation`, and `max_return_1m_pct >= min_return_1m_pct`.

Prove assessment validation: exact setup name; non-empty policy/schema versions; non-negative `as_of_unix_ms`; optional non-negative graduation timestamp; optional finite non-negative `seconds_since_graduation`; confirmation counts bounded by required; score in `[0,100]`. Assert assessment fields contain no execution/future-outcome names (`trade_intent`, `side`, `notional`, `position_size`, `wallet`, `order`, `fill`, `signer`, `transaction`, `realized_pnl`, `mfe_pct`, `mae_pct`).

- [ ] **Step 2: Verify RED**

Run full CI via the branch push. Expected: Python fails only because B4b model symbols do not yet exist; Rust and repository safety remain green.

- [ ] **Step 3: Implement minimal immutable models**

Append the constants, enum, and dataclasses to `setups/models.py`. Reuse existing `_require_finite`, `_require_non_negative_finite`, `_require_non_negative_int`, and `_require_bounded_finite`. Add only a tiny `_require_non_empty_string(name, value)` helper if it reduces repeated validation; do not alter B3 semantics.

`GraduationBreakoutReasonCode` must include, in spec order:

```text
SAFETY_NOT_PASS
GRADUATION_NOT_VERIFIED
GRADUATION_EVENT_NOT_PUMP
GRADUATION_VENUE_TRANSITION_INVALID
GRADUATION_AFTER_AS_OF
POST_GRADUATION_WINDOW_EXPIRED
SOURCE_DATA_TOO_OLD
LIQUIDITY_BELOW_MINIMUM
EXIT_PRICE_IMPACT_TOO_HIGH
MOVE_TOO_EXTENDED
GRADUATION_TOO_RECENT
LIQUIDITY_UNKNOWN
EXIT_PRICE_IMPACT_UNKNOWN
TX_COUNT_M5_UNKNOWN
TX_COUNT_M5_BELOW_MINIMUM
VOLUME_VELOCITY_UNKNOWN
VOLUME_VELOCITY_BELOW_MINIMUM
BUY_FRACTION_M5_UNKNOWN
BUY_FRACTION_M5_BELOW_MINIMUM
BUY_PRESSURE_ACCELERATION_UNKNOWN
BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM
RETURN_1M_UNKNOWN
RETURN_1M_BELOW_MINIMUM
LIQUIDITY_CHANGE_5M_UNKNOWN
LIQUIDITY_CHANGE_5M_BELOW_MINIMUM
DISTANCE_FROM_LOCAL_HIGH_UNKNOWN
TOO_FAR_BELOW_LOCAL_HIGH
RANGE_POSITION_UNKNOWN
RANGE_POSITION_BELOW_MINIMUM
ALL_CONFIRMATIONS_PASSED
```

- [ ] **Step 4: Verify GREEN**

Run full repository CI. Expected: all jobs green.

- [ ] **Step 5: Commit**

Commit model tests and implementation as one coherent GREEN commit.

---

### Task 2: Pure Graduation/Breakout evaluator

**Files:**
- Create: `python/tests/test_graduation_breakout_setup.py`
- Create: `python/src/shreks_brain/setups/graduation_breakout.py`

**Interfaces:**
- Consumes: `FeatureVector`, `SafetyDecision`, Task 1 model types.
- Produces:

```python
def assess_graduation_breakout(
    features: FeatureVector,
    graduation: GraduationContext | None,
    policy: GraduationBreakoutPolicy,
) -> GraduationBreakoutAssessment:
    ...
```

- [ ] **Step 1: Write failing evaluator tests**

Build a canonical `FeatureVector` fixture with strong but non-extended values and explicit `b2-v1`, plus canonical context/policy fixtures. Prove:

1. all eight confirmations with valid context -> `READY`, `8/8`, `100.0`, final `ALL_CONFIRMATIONS_PASSED`;
2. `graduation=None` -> `BLOCKED / GRADUATION_NOT_VERIFIED` while feature confirmations still score;
3. wrong event -> `GRADUATION_EVENT_NOT_PUMP`;
4. wrong from/to venue -> `GRADUATION_VENUE_TRANSITION_INVALID`;
5. local detection after `as_of_unix_ms` -> `GRADUATION_AFTER_AS_OF` and no negative age exposed;
6. changing only `occurred_at_unix_ms` never changes state/age/score;
7. `SafetyDecision.REJECT` and `INCOMPLETE` -> `SAFETY_NOT_PASS` even with 8/8 confirmations;
8. equality at min/max graduation ages passes timing gates; below min -> `GRADUATION_TOO_RECENT`; above max -> `POST_GRADUATION_WINDOW_EXPIRED`;
9. stale source, low liquidity, excessive exit impact, or return above anti-chase ceiling -> corresponding hard blocker;
10. missing liquidity or exit impact -> `WATCH` when no hard blocker;
11. each of the eight confirmation fields independently below threshold -> `WATCH`, `7/8`, matching reason;
12. each confirmation `None` -> `WATCH`, matching `UNKNOWN` reason;
13. equality at every confirmation threshold passes;
14. deterministic multi-finding order follows the spec;
15. repeated calls with equal inputs return equal assessments;
16. no test uses `return_5m_pct` or `momentum_acceleration_1m_vs_5m` as a positive graduation confirmation.

- [ ] **Step 2: Verify RED**

Run full CI. Expected: Python fails only on missing `graduation_breakout` evaluator; Rust/safety green.

- [ ] **Step 3: Implement minimal evaluator**

Implementation order must be exact:

```text
hard lifecycle/safety gates
post-graduation timing
freshness/executability/anti-chase hard gates
missing executability evidence
8 confirmations
state resolution
READY marker
```

Do not short-circuit feature confirmation calculation for blocked candidates. Compute `seconds_since_graduation` only when context exists and detection is not in the future; otherwise expose `None` for contradictory future context. Use no wall clock.

Use a private `_confirm_minimum` helper analogous to B3 but typed to B4b reason codes/findings.

- [ ] **Step 4: Verify GREEN**

Run full repository CI. Expected: all jobs green and B3 tests unchanged.

- [ ] **Step 5: Commit**

Commit evaluator tests and implementation as one coherent GREEN commit.

---

### Task 3: Stable package API, documentation, exact-head seal

**Files:**
- Create: `python/tests/test_graduation_breakout_public_api.py`
- Modify: `python/src/shreks_brain/setups/__init__.py`
- Modify: `README.md`
- Modify: this plan file to record verification evidence

**Interfaces:**
- Produces stable imports from `shreks_brain.setups` for all B4b constants/types and `assess_graduation_breakout`.

- [ ] **Step 1: Write failing public API tests**

Import from `shreks_brain.setups`:

```python
GRADUATION_BREAKOUT_CONFIRMATIONS_REQUIRED
GRADUATION_BREAKOUT_SETUP_NAME
GraduationBreakoutAssessment
GraduationBreakoutFinding
GraduationBreakoutPolicy
GraduationBreakoutReasonCode
GraduationContext
SetupState
assess_graduation_breakout
```

Construct a ready public assessment and prove no execution fields exist. Also retain existing B3 public API test unchanged.

- [ ] **Step 2: Verify RED**

Run full CI. Expected: Python fails only because B4b symbols are not exported at package level.

- [ ] **Step 3: Export stable API**

Update `setups/__init__.py` without removing or renaming any B3 export. Import evaluator from `.graduation_breakout` and models from `.models`; update `__all__` deterministically.

- [ ] **Step 4: Verify package GREEN**

Run full repository CI.

- [ ] **Step 5: Document B4b**

Add README section explaining:

- protocol-verified B4a graduation context is required;
- local detection time is the decision clock;
- B2 remains `b2-v1`;
- 8 confirmations measure evidence completeness, not profit probability;
- no production threshold defaults;
- READY is not an order/trade instruction;
- no paper/live execution is enabled.

- [ ] **Step 6: Run exact-head full CI**

Record the final exact head and CI run ID only after Rust, Python, workspace validation, and repository safety are all green.

- [ ] **Step 7: Open stacked draft PR**

Create draft PR against `feat/phase-b4a-graduation-lifecycle`. Include design/spec path, RED/GREEN commits and CI runs, final head, unchanged B2 schema, 8-confirmation contract, local detection-time rule, no-production-default rule, and explicit no-execution scope. Keep unmerged.

## Self-Review

- Every spec requirement maps to Task 1, 2, or 3.
- No placeholder/TODO steps remain.
- Type names and signatures are consistent across all tasks.
- No Rust/B2/storage changes are required.
- The plan does not permit live trading or claim profitability.
- The plan preserves blocked-candidate confirmation scoring for later filter-value research.
