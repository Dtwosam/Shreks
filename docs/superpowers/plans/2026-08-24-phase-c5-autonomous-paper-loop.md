# Phase C5 Autonomous Paper Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic in-memory autonomous PAPER loop that reuses the existing setup -> score -> decision -> risk -> C1 execution -> C3 accounting -> C4 exit path across repeated cycles.

**Architecture:** `shreks_brain.paper_loop` owns orchestration state only. BUY intents come unchanged from B9. C4 exits persist token-quantity decisions across latency, but never persist SELL USD notional; each eligible SELL intent is rebuilt from the current quote execution price and routed through unchanged C1/C3.

**Tech Stack:** Python 3.12+, stdlib dataclasses/enums/hashlib only, pytest, existing Shreks domain packages.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-c5-autonomous-paper-loop-design.md`

## Global Constraints

- Base exactly on verified C4 head `bb6bb5041d929047d8b013af447f77c0697da4fc`.
- PAPER only; live execution remains impossible.
- Reuse B7/B8/B9/C1/C3/C4 unchanged.
- Support only Fresh Launch, Graduation/Breakout, First Pullback.
- At most one approved BUY attempt per cycle.
- No new BUY while a pending BUY exists; no BUY for an already-OPEN mint.
- Every OPEN C3 lifecycle has exactly one managed C4 record.
- Pending exits persist C4 `ExitAssessment`, never SELL intent/notional.
- SELL requested notional is always `authorized_target_quantity * same C1 quote execution_price`.
- A newer full EXIT may supersede pending REDUCE; weaker evidence cannot cancel pending EXIT.
- Terminal SELL attempts clear pending exit; later retry requires a fresh C4 decision.
- No provider/RPC/storage/wall-clock/RNG/signer/transaction code.
- Strict RED -> expected failure -> minimal GREEN.

---

### Task 1: Immutable C5 Models and State Invariants — COMPLETE

**Files:**
- `python/tests/test_paper_loop_models.py`
- `python/src/shreks_brain/paper_loop/models.py`

Evidence:
- RED `c24855c5e393361f9631c90c0013f1c8d189ced7`, CI `32713973816`, exact missing `shreks_brain.paper_loop`.
- GREEN `2e03b9f32548c68bce796e2de15883ce4ba7fb7e`, CI `32714098458`, all checks green.

---

### Task 2: BUY Orchestration and Pending Entry — COMPLETE

**Files:**
- `python/tests/test_paper_loop_entry.py`
- `python/src/shreks_brain/paper_loop/engine.py`

Evidence:
- RED `d88c2e92bb43754ead6042a5f72238020fb21ec4`, CI `32714474257`, exact missing `paper_loop.engine`.
- Initial GREEN candidate `fd9d84dcf2d7218d5b9bdb8e14948e8efa71151d` exposed one wrong `RuntimeMode` import.
- Corrected GREEN `cd71058884309543b5cb2a7b7b1221b7b08f6ee9`, CI `32714737071`, all checks green.

---

### Task 3: Persistent C4 Exit Decisions and Quantity-Safe SELL Execution

**Files:**
- Modify: `python/tests/test_paper_loop_models.py`
- Create: `python/tests/test_paper_loop_exit.py`
- Modify: `python/src/shreks_brain/paper_loop/models.py`
- Modify: `python/src/shreks_brain/paper_loop/engine.py`

**Interfaces:**
- `ManagedPaperPosition(..., pending_exit: ExitAssessment | None = None)`
- `run_paper_cycle(...)` monitors cycle-start positions and routes safe SELLs through C1/C3.

- [ ] **Step 1: Write RED model/exit tests**

Required model tests:

```python
def test_managed_position_accepts_matching_pending_reduce(): ...
def test_pending_hold_is_rejected(): ...
def test_pending_exit_identity_policy_and_time_must_match_managed_state(): ...
```

Required orchestration tests:

```python
def test_missing_observation_without_pending_does_not_invent_hold(): ...
def test_hold_updates_exit_state_and_marks_from_usable_price(): ...
def test_reduce_without_quote_persists_exit_decision(): ...
def test_pending_reduce_survives_next_cycle_and_latency_clock_does_not_reset(): ...
def test_pending_reduce_rebuilds_sell_notional_from_later_quote_price(): ...
def test_future_quote_is_not_consumed(): ...
def test_quote_before_original_decision_latency_keeps_pending_exit(): ...
def test_missing_execution_price_keeps_pending_without_fabricating_notional(): ...
def test_same_quote_execution_price_guarantees_fill_quantity_not_above_target(): ...
def test_quote_size_limit_books_only_actual_c1_c3_partial_quantity(): ...
def test_partial_below_tp_target_does_not_complete_level(): ...
def test_exact_tp_target_completes_only_after_c3_booking(): ...
def test_pending_reduce_is_superseded_by_newer_full_exit_without_backdating(): ...
def test_pending_full_exit_is_not_weakened_by_fresh_hold_or_reduce(): ...
def test_failed_after_submission_books_network_cost_clears_pending_and_not_tp(): ...
def test_late_quote_is_passed_to_c1_for_quote_too_late_terminal_evidence(): ...
def test_full_close_removes_managed_position_and_skips_mark(): ...
def test_exit_intent_reuses_earliest_lifecycle_buy_versions(): ...
def test_exit_idempotency_is_stable_across_quote_price_changes_for_same_decision(): ...
def test_missing_current_observation_can_retry_already_authorized_pending_exit(): ...
```

Critical quantity assertion:

```python
assert intent.requested_notional_usd == pytest.approx(
    pending_exit.target_quantity * quote.execution_price_usd
)
assert execution.fill is None or execution.fill.quantity <= pending_exit.target_quantity + 1e-12
```

- [ ] **Step 2: Commit RED and require failures caused by missing pending-exit/model/exit behavior**

Prior Task 1/2 and earlier phase suites must remain healthy.

- [ ] **Step 3: Implement model correction**

`ManagedPaperPosition.pending_exit` validates position/mint/policy, REDUCE/EXIT action, positive target, and decision time not later than current managed C4 state.

- [ ] **Step 4: Implement monitoring/pending-exit precedence**

For fresh C4 assessment:

```text
none + REDUCE/EXIT -> pending=fresh
pending REDUCE + fresh EXIT -> pending=fresh EXIT
pending EXIT + HOLD/REDUCE -> retain pending EXIT
pending REDUCE + HOLD/REDUCE -> retain original pending REDUCE
```

Always adopt fresh `assessment.next_state`; never backdate superseding evidence.

- [ ] **Step 5: Implement safe transient SELL bridge**

Only when quote is non-future, at/after `pending_exit.as_of + assumed_latency`, and has execution price:

```python
requested_notional_usd = pending_exit.target_quantity * quote.execution_price_usd
```

Build deterministic key from position/policy/decision timestamp/reason/target quantity. Reuse earliest linked BUY metadata. Keep `intent.as_of_unix_ms = pending_exit.as_of_unix_ms`.

- [ ] **Step 6: Execute through unchanged C1/C3 and acknowledge TP from booked before/after position**

Terminal SELL attempt clears pending exit. Full close removes managed record. Still-open position may be marked only from usable fresh C4 price evidence.

- [ ] **Step 7: Full CI GREEN**

---

### Task 4: Multi-Cycle Autonomous Lifecycle Regression

**Files:**
- Create: `python/tests/test_paper_loop_cycle.py`
- Modify only if needed: `python/src/shreks_brain/paper_loop/engine.py`

- [ ] **Step 1: Add repeated-cycle tests**

```python
def test_deferred_buy_fill_hold_latency_delayed_tp_and_final_exit(): ...
def test_later_emergency_exit_supersedes_unexecuted_tp_without_old_timestamp(): ...
def test_entry_slot_prevents_two_approvals_from_reusing_one_risk_snapshot(): ...
def test_same_cycle_replay_cannot_double_book_terminal_intents(): ...
def test_multiple_open_positions_are_all_monitored_independently(): ...
def test_live_runtime_or_execution_authority_never_appears(): ...
```

The lifecycle must include at least one partial SELL, one failed execution cost, TP acknowledgement from C3 quantity truth, and final ledger self-reconciliation.

- [ ] **Step 2: Commit tests; minimal C5-only fix if needed**
- [ ] **Step 3: Full CI GREEN**

---

### Task 5: Stable Public API, README, Verification Record, Seal

**Files:**
- Create: `python/tests/test_paper_loop_public_api.py`
- Create: `python/src/shreks_brain/paper_loop/__init__.py`
- Modify: `README.md`
- Replace this plan with completed verification record after package GREEN.

**Exact public API:**

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

- [ ] **Step 1: RED package export/regression tests**
- [ ] **Step 2: Export-only GREEN**
- [ ] **Step 3: README documents one path, pending-exit quantity safety, fill-confirmed TP, and live-disabled boundary**
- [ ] **Step 4: Replace plan with concise TDD verification record without final self-referential SHA/run**
- [ ] **Step 5: Freeze branch**
- [ ] **Step 6: Compare exact C4 -> C5 diff**
- [ ] **Step 7: Fresh full exact-head CI; require Python/Rust/workspace metadata/repository safety all green**
- [ ] **Step 8: Update draft PR #16 metadata only; leave unmerged**
