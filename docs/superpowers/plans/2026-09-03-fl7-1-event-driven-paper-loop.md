# FL7.1 Event-Driven PAPER Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an immutable Python PAPER orchestration boundary where each new material Fast Lane event/state update can synchronously trigger exactly one validated action assessment without a timer gate.

**Architecture:** Add a new `shreks_brain.fast_paper` package rather than modifying the sealed legacy C5 PAPER loop. The engine consumes ordered update metadata plus a supplied evaluator callback, applies per-market replay/order rules, synchronously obtains an already-computed action assessment, validates identity, and journals it in immutable in-memory state. FL7.1 creates no fills, `TradeIntent`s, risk decisions, position mutations, or LIVE authority.

**Tech Stack:** Python 3.11+ dataclasses, `StrEnum`, `hashlib`, `json`, pytest; existing repository CI.

**Spec:** `docs/superpowers/specs/2026-09-03-fl7-1-event-driven-paper-loop-design.md`

## Global Constraints

- Base is sealed FL6.6 merge `73aa630ccfde07b5f67ff671ce815c4013ae0cb3`.
- Fresh merged-main base CI `33741283063` is four-gate GREEN.
- Rust remains owner of Fast Lane strategy evaluation; FL7.1 does not reimplement strategy logic in Python.
- The existing `paper`, `paper_loop`, `risk`, and `exits` packages remain unchanged.
- No production timing, strategy, risk, or fill defaults are introduced.
- No wall-clock, provider, DB, future-label, counterfactual, randomness, mutable-global, signer, submission, or LIVE authority is allowed.
- Exact event replay is idempotent and must not invoke the evaluator again.
- Conflicting replay and per-market ordering contradictions fail closed.

---

## File Structure

Create:

- `python/src/shreks_brain/fast_paper/models.py` — immutable public contracts and validation.
- `python/src/shreks_brain/fast_paper/engine.py` — deterministic fingerprint, replay/order application, synchronous evaluator invocation.
- `python/src/shreks_brain/fast_paper/__init__.py` — explicit public API exports.
- `python/tests/test_fast_paper_event_loop.py` — FL7.1 behavioral contract.

No existing production file is modified.

---

### Task 1: Freeze the public FL7.1 behavior in failing tests

**Files:**
- Create: `python/tests/test_fast_paper_event_loop.py`

**Interfaces:**
- Consumes: no FL7.1 production API yet.
- Produces expected symbols:
  - `FAST_PAPER_EVENT_LOOP_VERSION`
  - `FastPaperAction`
  - `FastPaperActionAssessment`
  - `FastPaperAssessmentMismatchError`
  - `FastPaperEventOutcome`
  - `FastPaperLoopConflictError`
  - `FastPaperLoopOrderError`
  - `FastPaperMaterialUpdate`
  - `create_fast_paper_loop_state`
  - `run_fast_paper_event`

- [ ] **Step 1: Write the failing contract tests**

Create helpers:

```python
from shreks_brain.fast_paper import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperAssessmentMismatchError,
    FastPaperEventOutcome,
    FastPaperLoopConflictError,
    FastPaperLoopOrderError,
    FastPaperMaterialUpdate,
    create_fast_paper_loop_state,
    run_fast_paper_event,
)


def update(
    event_id: str = "event-1",
    *,
    market_key: str = "MINT/SOL@pumpswap",
    sequence: int = 1,
    as_of: int = 1_000,
    material: bool = True,
) -> FastPaperMaterialUpdate:
    return FastPaperMaterialUpdate(
        source_event_id=event_id,
        market_key=market_key,
        source_sequence=sequence,
        as_of_unix_ms=as_of,
        state_version="fast-state-v1",
        is_material=material,
        material_reason="flow_changed" if material else None,
    )


def assessment(item: FastPaperMaterialUpdate, action=FastPaperAction.BUY):
    return FastPaperActionAssessment(
        version="assessment-v1",
        source_event_id=item.source_event_id,
        market_key=item.market_key,
        source_sequence=item.source_sequence,
        as_of_unix_ms=item.as_of_unix_ms,
        strategy_family="fixture",
        strategy_version="fixture-v1",
        action=action,
        reasons=("fixture_reason",),
    )
```

Tests must cover:

```python
def test_material_update_invokes_evaluator_once_and_journals_assessment(): ...
def test_material_updates_one_millisecond_apart_both_assess_without_timer_gate(): ...
def test_increasing_sequences_at_same_timestamp_both_assess(): ...
def test_non_material_update_advances_cursor_without_evaluation(): ...
def test_exact_material_replay_does_not_reinvoke_evaluator(): ...
def test_exact_non_material_replay_is_idempotent(): ...
def test_conflicting_replay_fails_closed(): ...
def test_stale_or_repeated_new_sequence_fails_closed(): ...
def test_timestamp_regression_fails_closed(): ...
def test_equal_sequence_on_different_markets_is_valid(): ...
def test_assessment_event_identity_mismatch_fails_closed(): ...
def test_assessment_market_sequence_and_timestamp_mismatch_fail_closed(): ...
def test_all_five_actions_cross_boundary_without_interpretation(): ...
def test_evaluator_exception_does_not_return_partial_state(): ...
def test_identical_inputs_produce_identical_result_and_state(): ...
def test_model_validation_rejects_invalid_material_reason_contract(): ...
```

Key assertions:

```python
assert result.outcome is FastPaperEventOutcome.ASSESSED
assert calls == 1
assert result.assessment.action is FastPaperAction.BUY
assert result.next_state.records[-1].assessment == result.assessment
```

Replay assertion:

```python
second = run_fast_paper_event(first.next_state, item, evaluator_that_must_not_run)
assert second.outcome is FastPaperEventOutcome.REPLAYED
assert second.next_state == first.next_state
assert second.assessment == first.assessment
```

No-timer assertion:

```python
first = run_fast_paper_event(state, update(sequence=1, as_of=1_000), evaluator)
second = run_fast_paper_event(
    first.next_state,
    update("event-2", sequence=2, as_of=1_001),
    evaluator,
)
assert first.outcome is FastPaperEventOutcome.ASSESSED
assert second.outcome is FastPaperEventOutcome.ASSESSED
assert calls == 2
```

- [ ] **Step 2: Run the RED test**

Run:

```bash
cd python && pytest -q tests/test_fast_paper_event_loop.py
```

Expected: collection/import FAIL because `shreks_brain.fast_paper` does not exist.

- [ ] **Step 3: Commit RED proof**

```bash
git add python/tests/test_fast_paper_event_loop.py
git commit -m "test: define FL7.1 event-driven PAPER loop contract"
```

---

### Task 2: Implement immutable public models

**Files:**
- Create: `python/src/shreks_brain/fast_paper/models.py`

**Interfaces:**
- Produces all immutable dataclasses/enums used by the engine.

- [ ] **Step 1: Implement action/outcome enums and update/assessment models**

Use:

```python
from dataclasses import dataclass
from enum import StrEnum

FAST_PAPER_EVENT_LOOP_VERSION = "fl7.1-v1"

class FastPaperAction(StrEnum):
    BUY = "BUY"
    SKIP = "SKIP"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"

class FastPaperEventOutcome(StrEnum):
    ASSESSED = "ASSESSED"
    IGNORED_NON_MATERIAL = "IGNORED_NON_MATERIAL"
    REPLAYED = "REPLAYED"
```

Implement frozen/slots dataclasses exactly as the spec:

```python
FastPaperMaterialUpdate
FastPaperActionAssessment
FastPaperMarketCursor
FastPaperEventRecord
FastPaperLoopState
FastPaperEventResult
```

Validation helpers must enforce non-empty strings, non-negative ints, bool type, tuple reason elements, and material-reason consistency.

- [ ] **Step 2: Implement focused error classes**

```python
class FastPaperLoopError(ValueError):
    pass

class FastPaperLoopConflictError(FastPaperLoopError):
    pass

class FastPaperLoopOrderError(FastPaperLoopError):
    pass

class FastPaperAssessmentMismatchError(FastPaperLoopError):
    pass
```

- [ ] **Step 3: Validate state internal consistency**

`FastPaperLoopState.__post_init__` must reject:

- unsupported version;
- duplicate market cursors;
- duplicate event IDs;
- records with invalid types;
- cursor timestamps/sequences that are earlier than the latest record for that market.

Keep validation deterministic and structural; do not query any external source.

---

### Task 3: Implement deterministic event application

**Files:**
- Create: `python/src/shreks_brain/fast_paper/engine.py`

**Interfaces:**
- Consumes models from Task 2.
- Produces:
  - `create_fast_paper_loop_state()`
  - `run_fast_paper_event(state, update, evaluator)`

- [ ] **Step 1: Implement canonical update fingerprint**

Use JSON with fixed keys/order and compact separators:

```python
payload = {
    "version": FAST_PAPER_EVENT_LOOP_VERSION,
    "source_event_id": update.source_event_id,
    "market_key": update.market_key,
    "source_sequence": update.source_sequence,
    "as_of_unix_ms": update.as_of_unix_ms,
    "state_version": update.state_version,
    "is_material": update.is_material,
    "material_reason": update.material_reason,
}
encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
return hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 2: Implement exact replay/conflict behavior**

Before checking market ordering, search the immutable record journal by event ID.

If found with equal fingerprint:

```python
return FastPaperEventResult(
    outcome=FastPaperEventOutcome.REPLAYED,
    source_event_id=update.source_event_id,
    assessment=record.assessment,
    next_state=state,
)
```

If found with different fingerprint:

```python
raise FastPaperLoopConflictError(...)
```

Never invoke the evaluator on either replay path.

- [ ] **Step 3: Implement per-market ordering**

For an existing cursor require:

```python
update.source_sequence > cursor.last_source_sequence
update.as_of_unix_ms >= cursor.last_as_of_unix_ms
```

Otherwise raise `FastPaperLoopOrderError`.

Different market keys use independent cursors.

- [ ] **Step 4: Implement non-material application**

For `is_material=False`:

- update/insert cursor;
- append journal record with `assessment=None`;
- return `IGNORED_NON_MATERIAL`;
- do not call evaluator.

- [ ] **Step 5: Implement synchronous material assessment**

Call:

```python
assessment = evaluator(update)
```

inside `run_fast_paper_event` with no timer, queue, sleep, or wall-clock read.

Validate assessment type and exact equality for:

```python
source_event_id
market_key
source_sequence
as_of_unix_ms
```

Mismatch raises `FastPaperAssessmentMismatchError` before a next state is built.

Then update cursor, append record, return `ASSESSED`.

- [ ] **Step 6: Keep state application atomic by construction**

Do not mutate state, cursors, or records in place. Build the next tuple/state only after evaluator and assessment validation succeed.

---

### Task 4: Export the public package API

**Files:**
- Create: `python/src/shreks_brain/fast_paper/__init__.py`

- [ ] **Step 1: Export only the FL7.1 contract**

```python
from .engine import create_fast_paper_loop_state, run_fast_paper_event
from .models import (
    FAST_PAPER_EVENT_LOOP_VERSION,
    FastPaperAction,
    FastPaperActionAssessment,
    FastPaperAssessmentMismatchError,
    FastPaperEventOutcome,
    FastPaperEventRecord,
    FastPaperEventResult,
    FastPaperLoopConflictError,
    FastPaperLoopError,
    FastPaperLoopOrderError,
    FastPaperLoopState,
    FastPaperMarketCursor,
    FastPaperMaterialUpdate,
)

__all__ = (...)
```

Do not export any production default evaluator, policy, timer, fill adapter, or LIVE integration.

---

### Task 5: Prove GREEN and compatibility

**Files:**
- Test: `python/tests/test_fast_paper_event_loop.py`
- Existing full suite: `python/tests/`

- [ ] **Step 1: Run focused GREEN test**

```bash
cd python && pytest -q tests/test_fast_paper_event_loop.py
```

Expected: PASS.

- [ ] **Step 2: Run full Python suite**

```bash
cd python && pytest -q
```

Expected: PASS, including existing PAPER ledger/risk/C5 loop tests.

- [ ] **Step 3: Run canonical repository CI on exact candidate head**

Require all four gates:

1. Repository safety
2. Rust workspace/tests
3. Python suite
4. Native ARM64 release build + bundle verification

- [ ] **Step 4: Audit phase scope**

Expected exact file set:

```text
python/src/shreks_brain/fast_paper/__init__.py
python/src/shreks_brain/fast_paper/models.py
python/src/shreks_brain/fast_paper/engine.py
python/tests/test_fast_paper_event_loop.py
docs/superpowers/plans/2026-09-03-fl7-1-event-driven-paper-loop.md
docs/superpowers/specs/2026-09-03-fl7-1-event-driven-paper-loop-design.md
```

No existing production file should differ.

- [ ] **Step 5: Clean authoring history**

After candidate four-gate GREEN, collapse post-RED authoring commits into one implementation commit while preserving:

```text
design -> plan -> RED -> implementation
```

Run fresh four-gate CI on the rewritten exact head.

- [ ] **Step 6: Guarded merge and merged-main seal**

Merge only with `expected_head_sha` equal to the freshly proven exact head.

Then require a fresh merged-main four-gate GREEN run before declaring FL7.1 SEALED.

---

## FL7.1 Completion Statement

FL7.1 is SEALED only after fresh merged-main four-gate GREEN proves that event-resolution PAPER assessment cadence is additive, deterministic, replay-safe, timer-free, and compatible with all existing PAPER/risk/accounting infrastructure.

Next build slice: FL7.2 BUY, routing approved `BUY` assessments through existing PAPER risk/executability/fill/ledger foundations while respecting maximum acceptable entry price, latency, intended notional, capacity, fees, slippage, and impact.

LIVE remains disabled.
