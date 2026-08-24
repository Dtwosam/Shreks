# Phase C5 Autonomous Paper Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic in-memory C5 state machine that autonomously reuses the existing setup -> score -> decision -> risk -> C1 paper execution -> C3 accounting -> C4 exit path across repeated paper cycles.

**Architecture:** Add a standalone `shreks_brain.paper_loop` package. The loop consumes already-normalized B2/regime/setup evidence, permits at most one new BUY attempt per cycle, persists one deferred BUY, initializes C4 state on booked lifecycle open, monitors cycle-start positions, and translates C4 token targets into quantity-safe SELL notional only from the same quote C1 consumes. C5 performs no provider/storage/live execution work and does not alter earlier trading math.

**Tech Stack:** Python 3.12+, stdlib dataclasses/enums/hashlib only, pytest, existing Shreks B2/B3-B9/C1/C3/C4 domain models.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-c5-autonomous-paper-loop-design.md`

## Global Constraints

- Base exactly on verified C4 head `bb6bb5041d929047d8b013af447f77c0697da4fc`.
- Reuse unchanged B2 `b2-v1` FeatureVector and B6 regime evidence.
- Support only Fresh Launch, Graduation/Breakout, and First Pullback; do not fabricate Smart Wallet Cluster.
- Reuse B7 scoring, B8 decision, B9 risk, C1 paper execution, C3 accounting, and C4 exit functions unchanged.
- Runtime is PAPER only; no live mode path.
- At most one new BUY intent/execution attempt per cycle.
- No new BUY while a pending BUY exists.
- No BUY for a mint already OPEN in C3.
- Every OPEN C3 position must have exactly one managed C4 state record.
- SELL notional must be `C4 target_quantity * same C1 quote execution_price`.
- No decision-price/reference-price conversion for SELL quantity targets.
- No production defaults for capital, thresholds, fill assumptions, or exit slippage.
- No provider/RPC/storage/wall-clock/RNG reads in C5.
- No C1 fill-model, C3 accounting formula, C4 exit-rule, signer, transaction, or live-money changes.
- Strict RED -> expected failure -> minimal GREEN per task.

---

### Task 1: Immutable C5 Models and State Invariants

**Files:**
- Create: `python/tests/test_paper_loop_models.py`
- Create: `python/src/shreks_brain/paper_loop/models.py`

**Interfaces:**
- Consumes stable models from `features`, `regime`, `setups`, `scoring`, `decision`, `risk`, `paper`, and `exits`.
- Produces all C5 immutable domain types except the two engine functions.

Required production shapes:

```python
class PaperLoopReasonCode(StrEnum):
    CYCLE_APPLIED = "CYCLE_APPLIED"
    CYCLE_BEFORE_STATE = "CYCLE_BEFORE_STATE"
    PENDING_ENTRY_DEFERRED = "PENDING_ENTRY_DEFERRED"
    PENDING_ENTRY_TERMINAL = "PENDING_ENTRY_TERMINAL"
    ENTRY_NOT_SELECTED = "ENTRY_NOT_SELECTED"
    ENTRY_OPEN_POSITION_EXISTS = "ENTRY_OPEN_POSITION_EXISTS"
    ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH = (
        "ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH"
    )
    ENTRY_RISK_REJECTED = "ENTRY_RISK_REJECTED"
    ENTRY_EXECUTION_DEFERRED = "ENTRY_EXECUTION_DEFERRED"
    ENTRY_EXECUTION_TERMINAL = "ENTRY_EXECUTION_TERMINAL"
    EXIT_OBSERVATION_MISSING = "EXIT_OBSERVATION_MISSING"
    EXIT_HOLD = "EXIT_HOLD"
    EXIT_QUOTE_MISSING = "EXIT_QUOTE_MISSING"
    EXIT_QUOTE_AFTER_CYCLE = "EXIT_QUOTE_AFTER_CYCLE"
    EXIT_QUOTE_BEFORE_LATENCY = "EXIT_QUOTE_BEFORE_LATENCY"
    EXIT_EXECUTION_PRICE_UNAVAILABLE = "EXIT_EXECUTION_PRICE_UNAVAILABLE"
    EXIT_EXECUTION_TERMINAL = "EXIT_EXECUTION_TERMINAL"
    EXIT_POSITION_CLOSED = "EXIT_POSITION_CLOSED"

@dataclass(frozen=True, slots=True)
class PaperLoopPolicy:
    version: str
    exit_max_slippage_bps: int

@dataclass(frozen=True, slots=True)
class FreshLaunchSetupInput:
    policy: FreshLaunchPolicy

@dataclass(frozen=True, slots=True)
class GraduationBreakoutSetupInput:
    context: GraduationContext | None
    policy: GraduationBreakoutPolicy

@dataclass(frozen=True, slots=True)
class FirstPullbackSetupInput:
    context: PullbackContext | None
    policy: FirstPullbackPolicy

@dataclass(frozen=True, slots=True)
class PaperEntryCandidate:
    mint: str
    features: FeatureVector
    regime: RegimeAssessment
    setup: FreshLaunchSetupInput | GraduationBreakoutSetupInput | FirstPullbackSetupInput
    score_policy: ScorePolicy
    decision_policy: DecisionPolicy
    risk_context: RiskContext
    risk_policy: RiskPolicy
    exit_policy: ExitPolicy

@dataclass(frozen=True, slots=True)
class PaperExitObservation:
    position_id: str
    features: FeatureVector
    execution_context: ExitExecutionContext

@dataclass(frozen=True, slots=True)
class ManagedPaperPosition:
    position_id: str
    exit_policy: ExitPolicy
    exit_state: ExitState

@dataclass(frozen=True, slots=True)
class PendingPaperEntry:
    intent: TradeIntent
    exit_policy: ExitPolicy
```

Results/state must implement the exact design fields for `PaperLoopFinding`, `PaperPendingEntryResult`, `PaperEntryResult`, `PaperExitResult`, `PaperCycleInput`, `PaperLoopState`, and `PaperCycleResult`.

- [ ] **Step 1: Write model-contract RED tests**

Pin enum order and no production defaults:

```python
def test_reason_code_order_and_policy_has_no_defaults():
    assert [code.value for code in PaperLoopReasonCode] == [
        "CYCLE_APPLIED",
        "CYCLE_BEFORE_STATE",
        "PENDING_ENTRY_DEFERRED",
        "PENDING_ENTRY_TERMINAL",
        "ENTRY_NOT_SELECTED",
        "ENTRY_OPEN_POSITION_EXISTS",
        "ENTRY_RISK_CONTEXT_ACTIVE_INTENTS_MISMATCH",
        "ENTRY_RISK_REJECTED",
        "ENTRY_EXECUTION_DEFERRED",
        "ENTRY_EXECUTION_TERMINAL",
        "EXIT_OBSERVATION_MISSING",
        "EXIT_HOLD",
        "EXIT_QUOTE_MISSING",
        "EXIT_QUOTE_AFTER_CYCLE",
        "EXIT_QUOTE_BEFORE_LATENCY",
        "EXIT_EXECUTION_PRICE_UNAVAILABLE",
        "EXIT_EXECUTION_TERMINAL",
        "EXIT_POSITION_CLOSED",
    ]
    with pytest.raises(TypeError):
        PaperLoopPolicy()
```

Validate:

```python
def test_cycle_input_requires_unique_candidate_quote_and_exit_ids():
    candidate = _candidate("Mint111")
    quote = _quote("Mint111")
    observation = _exit_observation("position-1")
    with pytest.raises(ValueError, match="candidate"):
        PaperCycleInput(1_000_000, (candidate, candidate), (), ())
    with pytest.raises(ValueError, match="quote"):
        PaperCycleInput(1_000_000, (), (), (quote, quote))
    with pytest.raises(ValueError, match="exit observation"):
        PaperCycleInput(1_000_000, (), (observation, observation), ())
```

Pin pending intent safety:

```python
def test_pending_entry_requires_paper_buy_intent():
    with pytest.raises(ValueError, match="PAPER BUY"):
        PendingPaperEntry(
            intent=replace(_buy_intent(), side=TradeSide.SELL),
            exit_policy=_exit_policy(),
        )
```

Pin result shape/invariants and forbid execution authority fields by scanning dataclass field names for `signer`, `secret`, `transaction`, `signature`, `provider`, `sqlite`, and `live_execution`.

- [ ] **Step 2: Commit RED and require expected missing-package failure**

Expected Python collection failure:

```text
ModuleNotFoundError: No module named 'shreks_brain.paper_loop'
```

- [ ] **Step 3: Implement minimal immutable models**

Use strict type/value validation matching established Shreks model style. `PaperCycleInput` validates tuple types and uniqueness. `PaperLoopState` validates pinned PAPER policies, one managed record per OPEN position, no managed record for a CLOSED position, and pending intent identity.

- [ ] **Step 4: Full CI must be GREEN**

---

### Task 2: State Creation, Setup Dispatch, and Autonomous BUY Path

**Files:**
- Create: `python/tests/test_paper_loop_entry.py`
- Create: `python/src/shreks_brain/paper_loop/engine.py`

**Interfaces:**
- Produces:

```python
def create_paper_loop_state(
    ledger: PaperLedger,
    loop_policy: PaperLoopPolicy,
    paper_fill_policy: PaperFillPolicy,
    managed_positions: tuple[ManagedPaperPosition, ...] = (),
    pending_entry: PendingPaperEntry | None = None,
) -> PaperLoopState: ...


def run_paper_cycle(
    state: PaperLoopState,
    cycle: PaperCycleInput,
) -> PaperCycleResult: ...
```

Task 2 implements entry behavior fully and returns no exit results when no cycle-start positions exist. Task 3 extends the same function with monitoring.

- [ ] **Step 1: Write RED tests for state creation and entry path**

Use a canonical fresh-launch fixture with a READY B2 vector and explicit policies:

```python
def _fresh_policy() -> FreshLaunchPolicy:
    return FreshLaunchPolicy(
        version="fresh-v1-test",
        min_age_seconds=60.0,
        max_age_seconds=900.0,
        max_source_age_ms=30_000,
        min_liquidity_usd=50_000.0,
        max_exit_price_impact_pct=5.0,
        max_return_5m_pct=80.0,
        min_tx_count_m5=50,
        min_volume_velocity_ratio=1.2,
        min_buy_fraction_m5=0.60,
        min_buy_pressure_acceleration=0.05,
        min_return_1m_pct=1.0,
        min_return_5m_pct=5.0,
        min_liquidity_change_5m_pct=0.0,
        min_distance_from_local_high_pct=-15.0,
        min_range_position_pct=60.0,
    )
```

Use the existing B7/B8/B9 test policy values so a canonical candidate is approved.

Required cases:

```python
def test_create_state_pins_policies_and_requires_exact_open_position_coverage(): ...
def test_cycle_before_state_returns_exact_previous_state_without_processing(): ...
def test_all_three_setup_wrappers_dispatch_to_existing_setup_engines(): ...
def test_watch_or_reject_candidate_never_creates_buy_intent(): ...
def test_risk_rejection_continues_to_next_candidate(): ...
def test_first_risk_approved_candidate_consumes_only_entry_slot(): ...
def test_later_candidates_still_get_setup_score_decision_but_no_risk_after_slot(): ...
def test_existing_open_mint_skips_risk_and_never_pyramids(): ...
def test_nonempty_active_intent_context_is_rejected_by_c5_coherence_gate(): ...
def test_immediate_terminal_buy_books_through_c1_and_c3_and_initializes_c4_state(): ...
def test_deferred_buy_is_persisted_with_its_exit_policy(): ...
def test_pending_buy_retry_deferred_preserves_exact_intent(): ...
def test_pending_buy_retry_terminal_books_and_consumes_cycle_entry_slot(): ...
def test_newly_opened_position_is_not_monitored_in_same_cycle(): ...
```

For a filled BUY quote:

```python
PaperQuote(
    provider="paper-test",
    mint="Mint111",
    observed_at_unix_ms=1_001_000,
    state=PaperQuoteState.EXECUTABLE,
    reference_price_usd=1.0,
    execution_price_usd=1.01,
    quoted_notional_usd=1_000.0,
    available_notional_usd=1_000.0,
)
```

Use a `PaperFillPolicy` with zero latency for the immediate-fill test and nonzero latency for pending tests.

- [ ] **Step 2: Commit RED and require missing-engine-function failure**

Expected Python failure should be import/attribute failure for `create_paper_loop_state` / `run_paper_cycle`, while prior suites remain healthy.

- [ ] **Step 3: Implement state creation and entry pipeline**

Core dispatch:

```python
def _assess_setup(candidate: PaperEntryCandidate):
    setup = candidate.setup
    if isinstance(setup, FreshLaunchSetupInput):
        return assess_fresh_launch(candidate.features, setup.policy)
    if isinstance(setup, GraduationBreakoutSetupInput):
        return assess_graduation_breakout(candidate.features, setup.context, setup.policy)
    if isinstance(setup, FirstPullbackSetupInput):
        return assess_first_pullback(candidate.features, setup.context, setup.policy)
    raise TypeError("unsupported setup input")
```

New candidate path:

```python
setup = _assess_setup(candidate)
score = score_candidate(candidate.features, setup, candidate.regime, candidate.score_policy)
decision = decide_entry(candidate.mint, score, candidate.decision_policy)
```

Only while the entry slot is free and mint is not OPEN and `active_intent_keys == frozenset()`:

```python
risk = assess_entry_risk(
    decision,
    candidate.risk_context,
    candidate.risk_policy,
    RuntimeMode.PAPER,
)
```

If approved, execute exactly `risk.intent` through C1. Terminal results go through C3; deferred results become `PendingPaperEntry(intent=risk.intent, exit_policy=candidate.exit_policy)`.

After a booked BUY opens a new position:

```python
exit_state = create_exit_state(position, candidate.exit_policy)
managed = ManagedPaperPosition(position.position_id, candidate.exit_policy, exit_state)
```

Do not monitor that newly opened lifecycle until the next cycle.

- [ ] **Step 4: Full CI must be GREEN**

---

### Task 3: C4 Monitoring, Quantity-Safe SELL Translation, C1/C3 Exit Booking

**Files:**
- Create: `python/tests/test_paper_loop_exit.py`
- Modify: `python/src/shreks_brain/paper_loop/engine.py`

**Interfaces:**
- Extends `run_paper_cycle` with cycle-start OPEN-position monitoring.
- Adds private helpers `_build_exit_intent`, `_exit_idempotency_key`, `_find_lifecycle_entry`, `_mark_if_usable`.

- [ ] **Step 1: Write RED exit orchestration tests**

Build an OPEN C3 lifecycle through the existing C1/C3 functions, then create a managed C4 state from it. Required cases:

```python
def test_missing_exit_observation_does_not_invent_hold_or_mutate_exit_state(): ...
def test_c4_hold_updates_exit_state_and_marks_from_usable_price(): ...
def test_c4_data_quality_hold_does_not_mark_from_unusable_price(): ...
def test_reduce_without_quote_keeps_position_and_records_quote_missing(): ...
def test_future_quote_is_not_used_to_construct_sell_intent(): ...
def test_quote_before_latency_does_not_construct_sell_intent(): ...
def test_missing_execution_price_does_not_fabricate_sell_notional(): ...
def test_sell_notional_uses_same_quote_execution_price_and_cannot_oversell_target(): ...
def test_quote_size_limit_produces_c1_partial_sell_and_c3_books_only_actual_quantity(): ...
def test_take_profit_partial_fill_below_target_does_not_complete_level(): ...
def test_take_profit_target_fill_completes_level_only_after_c3_booking(): ...
def test_emergency_exit_uses_full_c4_target_and_same_c1_c3_path(): ...
def test_failed_after_submission_books_network_cost_and_does_not_complete_tp(): ...
def test_full_close_removes_managed_position_and_skips_mark(): ...
def test_exit_intent_reuses_original_lifecycle_strategy_versions(): ...
def test_exit_idempotency_is_stable_for_same_decision_and_changes_with_new_as_of(): ...
def test_late_quote_is_sent_to_c1_and_classified_quote_too_late(): ...
```

Critical quantity assertion:

```python
assert intent.requested_notional_usd == pytest.approx(
    exit_assessment.target_quantity * quote.execution_price_usd
)
assert execution.fill is not None
assert execution.fill.quantity <= exit_assessment.target_quantity + 1e-12
```

TP acknowledgement assertion:

```python
assert "tp1" not in result.next_state.managed_positions[0].exit_state.completed_take_profit_levels
# after exact/over-target booked reduction:
assert "tp1" in completed
```

- [ ] **Step 2: Commit RED and require behavioral failures**

Expected failures should show that Task 2 has no exit orchestration yet, not unrelated suite failures.

- [ ] **Step 3: Implement minimal monitoring and safe SELL bridge**

For each cycle-start OPEN position:

```python
assessment = assess_exit(
    position,
    observation.features,
    observation.execution_context,
    managed.exit_state,
    managed.exit_policy,
)
```

Adopt `assessment.next_state` immediately.

For REDUCE/EXIT, only construct a SELL when quote is not future, quote is at/after `assessment.as_of_unix_ms + state.paper_fill_policy.assumed_latency_ms`, and `quote.execution_price_usd` is positive.

Requested notional:

```python
requested_notional_usd = assessment.target_quantity * quote.execution_price_usd
```

Metadata comes from earliest linked BUY journal entry. Idempotency:

```python
payload = "|".join((
    "c5-exit-v1",
    position.position_id,
    managed.exit_policy.version,
    str(assessment.as_of_unix_ms),
    assessment.primary_reason.value,
    assessment.target_quantity.hex(),
))
key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Execute through C1 and book terminal results through C3. After an APPLIED booking, call `acknowledge_exit_fill` using before/after C3 position snapshots. Remove managed state on full close. If still OPEN and C4 exposed usable current price, mark through C3 at cycle time and keep the acknowledged exit state.

- [ ] **Step 4: Full CI must be GREEN**

---

### Task 4: Multi-Cycle Autonomous Lifecycle and Point-in-Time Regression Tests

**Files:**
- Create: `python/tests/test_paper_loop_cycle.py`
- Modify only if required: `python/src/shreks_brain/paper_loop/engine.py`

**Interfaces:**
- Uses only public C5 models/functions plus earlier public domain models.

- [ ] **Step 1: Write RED/coverage tests for complete repeated cycles**

Pin complete lifecycles:

```python
def test_deferred_entry_then_fill_then_hold_then_take_profit_partial_then_final_exit(): ...
def test_later_emergency_exit_supersedes_unexecuted_prior_take_profit_request(): ...
def test_cycle_order_keeps_new_entry_unmonitored_until_next_cycle(): ...
def test_entry_slot_prevents_two_approved_candidates_from_reusing_same_risk_snapshot(): ...
def test_replayed_same_cycle_inputs_are_idempotent_via_c1_c3_keys(): ...
def test_no_live_runtime_mode_or_live_authority_is_constructed_anywhere(): ...
```

The complete lifecycle test must prove:

1. Cycle N: approved BUY deferred.
2. Cycle N+1: same BUY terminal fill opens C3 position and creates C4 state.
3. Cycle N+2: C4 HOLD and C3 mark.
4. Cycle N+3: TP REDUCE, quote-limited partial fill below target, TP remains incomplete.
5. Cycle N+4: fresh C4 assessment retries same TP level; booked target completes it.
6. Later cycle: full EXIT closes position and removes managed C4 state.
7. Final C3 cash/PnL/cost fields still self-reconcile through existing C3 model validation.

- [ ] **Step 2: Commit tests; if implementation already satisfies them require GREEN, otherwise minimal fix**

No test weakening. Any required production change must remain inside `paper_loop/engine.py` unless a proven earlier contract defect is discovered.

- [ ] **Step 3: Full CI must be GREEN**

---

### Task 5: Stable Public C5 API, README, Verification Record, and Seal

**Files:**
- Create: `python/tests/test_paper_loop_public_api.py`
- Create: `python/src/shreks_brain/paper_loop/__init__.py`
- Modify: `README.md`
- Replace this plan with a concise verification record after package GREEN.

**Public API:**

```text
FirstPullbackSetupInput
FreshLaunchSetupInput
GraduationBreakoutSetupInput
ManagedPaperPosition
PaperCycleInput
PaperCycleResult
PaperEntryCandidate
PaperEntryResult
PaperExitObservation
PaperExitResult
PaperLoopFinding
PaperLoopPolicy
PaperLoopReasonCode
PaperLoopState
PaperPendingEntryResult
PendingPaperEntry
create_paper_loop_state
run_paper_cycle
```

- [ ] **Step 1: Write package-level RED test**

```python
def test_public_api_is_exact():
    import shreks_brain.paper_loop as paper_loop
    assert tuple(paper_loop.__all__) == (
        "FirstPullbackSetupInput",
        "FreshLaunchSetupInput",
        "GraduationBreakoutSetupInput",
        "ManagedPaperPosition",
        "PaperCycleInput",
        "PaperCycleResult",
        "PaperEntryCandidate",
        "PaperEntryResult",
        "PaperExitObservation",
        "PaperExitResult",
        "PaperLoopFinding",
        "PaperLoopPolicy",
        "PaperLoopReasonCode",
        "PaperLoopState",
        "PaperPendingEntryResult",
        "PendingPaperEntry",
        "create_paper_loop_state",
        "run_paper_cycle",
    )
```

Require a real public create-state -> deferred entry -> terminal entry -> monitored exit flow. Scan public dataclass/function names/signatures for forbidden provider/storage/signer/transaction/live authority.

- [ ] **Step 2: Commit RED and require package-import failure**

- [ ] **Step 3: Add exact exports and full CI GREEN**

- [ ] **Step 4: README documentation**

Document:

- C5 reuses one setup/score/decision/risk/execution/accounting/exit path,
- B2 normalized evidence is the orchestration observation boundary,
- one BUY attempt per cycle protects point-in-time risk capacity,
- one deferred BUY is carried across cycles,
- no same-mint pyramiding in C5-v1,
- C4 state initializes only after booked lifecycle open,
- cycle-start positions are monitored every cycle when evidence exists,
- safe SELL notional uses same C1 execution price so filled token quantity cannot exceed C4 target,
- all SELLs use C1/C3 and TP progression is fill-confirmed,
- no production defaults, persistence, wallet intelligence, signer, transaction, or live mode.

- [ ] **Step 5: Replace plan with verification record and freeze branch**

Tracked verification record must contain predecessor SHA, architecture, RED/GREEN commits/run IDs, public API, and scope boundaries, but **not** the final branch SHA/run to avoid a self-referential seal loop.

After this commit, no further C5 branch writes.

- [ ] **Step 6: Exact-head seal**

On the frozen head:

1. fetch fresh full CI and require Python/Rust/workspace/repository-safety green,
2. compare against C4 final `bb6bb5041d929047d8b013af447f77c0697da4fc`,
3. require only intended C5 docs/package/tests/README files,
4. update the stacked draft PR body with final head/run/TDD/diff evidence only,
5. leave PR draft and unmerged.

## Expected C5 Diff

```text
README.md
docs/superpowers/plans/2026-08-24-phase-c5-autonomous-paper-loop.md
docs/superpowers/specs/2026-08-24-phase-c5-autonomous-paper-loop-design.md
python/src/shreks_brain/paper_loop/__init__.py
python/src/shreks_brain/paper_loop/engine.py
python/src/shreks_brain/paper_loop/models.py
python/tests/test_paper_loop_models.py
python/tests/test_paper_loop_entry.py
python/tests/test_paper_loop_exit.py
python/tests/test_paper_loop_cycle.py
python/tests/test_paper_loop_public_api.py
```

No B2/setup/scoring/decision/risk/C1/C3/C4 implementation file, Rust/storage/provider file, signer, transaction, or live-execution file should change.