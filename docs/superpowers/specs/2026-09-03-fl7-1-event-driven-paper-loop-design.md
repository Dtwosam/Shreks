# FL7.1 Event-Driven PAPER Loop Design

**Date:** 2026-09-03

## Goal

Implement the first slice of FL7 — Event-resolution PAPER action engine — by adding a deterministic PAPER orchestration boundary where every new **material** Fast Lane event/state update can synchronously produce a new action assessment without waiting for a checkpoint timer.

The build-order requirement is:

> A material event/state update may trigger a new action assessment immediately.

FL7.1 does **not** execute BUY/REDUCE/SELL fills yet. Execution semantics belong to FL7.2–FL7.6. This slice proves the event-resolution cadence, ordering, replay, and action-assessment boundary needed before capital/accounting behavior is connected.

## Base and proof

Base: sealed FL6.6 merged-main commit:

`73aa630ccfde07b5f67ff671ce815c4013ae0cb3`

Fresh merged-main proof:

`33741283063` — Repository safety, Python, Rust, and native ARM64 release verification all GREEN.

FL6 is therefore complete at the deterministic evaluator/contract layer. Profitability remains unproven until later PAPER/shadow evidence. LIVE remains disabled.

## Existing PAPER infrastructure to preserve

The repository already contains a mature Python PAPER foundation:

- `python/src/shreks_brain/paper/` — simulated execution and ledger/accounting,
- `python/src/shreks_brain/paper_loop/` — legacy C5 cycle orchestration,
- `python/src/shreks_brain/risk/` — entry risk and `TradeIntent` authority,
- `python/src/shreks_brain/exits/` — protective/legacy exit handling.

The legacy `paper_loop.engine.run_paper_cycle()` is intentionally setup/score/decision-cycle oriented. It remains a compatibility baseline and must not be silently rewritten to pretend it is the Fast Lane.

FL7.1 therefore adds a **new narrow package** rather than changing the sealed legacy PAPER loop.

## Architecture decision

Create:

```text
python/src/shreks_brain/fast_paper/
```

This package is a PAPER-only orchestration/control-plane boundary. It does **not** implement Fast Lane strategy logic in Python.

The low-latency strategy evaluator remains Rust-owned. FL7.1 consumes an evaluator callback supplied by the caller. In tests the callback is a deterministic stub; a later integration may bridge to the Rust Fast Lane evaluator without changing this event-loop contract.

The flow is:

```text
ordered Fast Lane material update
        |
        v
run_fast_paper_event(...)
        |
        +-- validate replay/order/time
        |
        +-- if non-material: record + advance cursor, no assessment
        |
        +-- if material: invoke supplied evaluator synchronously
        |
        +-- validate assessment identity/action
        |
        v
versioned FastPaperActionAssessment journal record
```

There is no sleep, checkpoint interval, named horizon timer, or wall-clock read in this engine.

## Scope

Create:

```text
python/src/shreks_brain/fast_paper/__init__.py
python/src/shreks_brain/fast_paper/models.py
python/src/shreks_brain/fast_paper/engine.py
python/tests/test_fast_paper_event_loop.py
```

Documentation:

```text
docs/superpowers/specs/2026-09-03-fl7-1-event-driven-paper-loop-design.md
docs/superpowers/plans/2026-09-03-fl7-1-event-driven-paper-loop.md
```

Do not modify:

- existing PAPER ledger/execution code,
- existing legacy `paper_loop` behavior,
- risk policy or `TradeIntent` authority,
- provider/storage ingestion,
- Rust Fast Lane evaluators,
- signer/submission code,
- deployment/runtime services,
- LIVE authority.

## Public version

```python
FAST_PAPER_EVENT_LOOP_VERSION = "fl7.1-v1"
```

No production strategy, risk, fill, or timing defaults are introduced.

## Action vocabulary

`FastPaperAction` is a wire/control-plane mirror of the already-sealed Fast Lane action vocabulary:

```python
class FastPaperAction(StrEnum):
    BUY = "BUY"
    SKIP = "SKIP"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
```

This enum does not make decisions. It only preserves the action value returned by the supplied evaluator so later FL7 slices can route it into PAPER risk/execution/accounting.

## Material update contract

```python
@dataclass(frozen=True, slots=True)
class FastPaperMaterialUpdate:
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    state_version: str
    is_material: bool
    material_reason: str | None
```

Semantics:

- `source_event_id` is the stable Fast Lane event/update identity supplied by the bridge;
- `market_key` is an opaque stable serialization of the canonical Fast Lane market identity — FL7.1 does not parse or reinterpret it;
- `source_sequence` is the canonical per-market order used by the upstream Fast Lane state;
- `as_of_unix_ms` is the point-in-time timestamp represented by the update;
- `state_version` identifies the upstream state/bridge contract;
- `is_material=True` means the caller requests a fresh action assessment for this update;
- material updates require a non-empty `material_reason`;
- non-material updates require `material_reason is None`.

Validation is structural only; FL7.1 does not invent what counts as economically material.

## Assessment contract

```python
@dataclass(frozen=True, slots=True)
class FastPaperActionAssessment:
    version: str
    source_event_id: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    strategy_family: str
    strategy_version: str
    action: FastPaperAction
    reasons: tuple[str, ...]
```

The supplied evaluator must return an assessment whose event identity, market, sequence, and point-in-time timestamp exactly match the update being processed.

The action assessment is auditable metadata. FL7.1 does not convert it to `TradeIntent`, position size, or fill.

Every assessment requires:

- non-empty assessment version,
- non-empty strategy family,
- non-empty strategy version,
- at least one non-empty reason,
- one of the five canonical actions.

## Evaluator boundary

The engine accepts:

```python
FastPaperEvaluator = Callable[[FastPaperMaterialUpdate], FastPaperActionAssessment]
```

For a new material update, `run_fast_paper_event()` invokes the evaluator **once, synchronously, inside the event application call**.

This is the FL7.1 proof of event-resolution cadence. The engine does not queue a timer-based decision for later.

If the evaluator raises, the exception propagates and no next state is returned. There is no partial mutable state to commit because state objects are immutable.

## State model

### `FastPaperMarketCursor`

```python
@dataclass(frozen=True, slots=True)
class FastPaperMarketCursor:
    market_key: str
    last_source_sequence: int
    last_as_of_unix_ms: int
```

One cursor per market proves that accepted new updates are strictly increasing in canonical sequence and non-decreasing in point-in-time timestamp.

### `FastPaperEventRecord`

```python
@dataclass(frozen=True, slots=True)
class FastPaperEventRecord:
    source_event_id: str
    update_fingerprint: str
    market_key: str
    source_sequence: int
    as_of_unix_ms: int
    is_material: bool
    assessment: FastPaperActionAssessment | None
```

Every accepted update is journaled in-memory, including non-material updates. Material records carry the returned assessment; non-material records carry `assessment=None`.

### `FastPaperLoopState`

```python
@dataclass(frozen=True, slots=True)
class FastPaperLoopState:
    version: str
    market_cursors: tuple[FastPaperMarketCursor, ...]
    records: tuple[FastPaperEventRecord, ...]
```

FL7.1 is an immutable deterministic state machine. Persistence into the existing PAPER accounting system comes later; this slice does not create a second durable ledger.

## Update fingerprint

Each update receives a deterministic SHA-256 fingerprint over a versioned canonical serialization of **all update fields**.

The serialization must be unambiguous. Use JSON with:

- explicit field names,
- fixed key ordering,
- compact separators,
- UTF-8 encoding.

The fingerprint is used only for replay conflict detection, not for market/event semantics.

## Replay and ordering semantics

### Exact replay

If `source_event_id` already exists and the incoming update fingerprint matches the stored fingerprint:

- do not invoke the evaluator again;
- return the previously recorded assessment, if any;
- return the existing state unchanged;
- result outcome = `REPLAYED`.

This gives deterministic retry/restart-overlap behavior without duplicate action assessments.

### Conflicting replay

If the same `source_event_id` arrives with a different update fingerprint:

- fail closed with `FastPaperLoopConflictError`;
- do not invoke the evaluator;
- do not produce a new state.

An event identity must never silently mean two different economic updates.

### New update ordering

For a new event ID on an existing market:

- `source_sequence` must be strictly greater than the market cursor;
- `as_of_unix_ms` must be greater than or equal to the market cursor timestamp.

Otherwise fail closed with `FastPaperLoopOrderError`.

Different markets have independent cursors, so equal source sequence values on different markets are valid.

Upstream FL1/FL2 remains responsible for canonical ordering and late-arrival policy. FL7.1 does not reorder events or rewind PAPER action history.

## Non-material updates

For `is_material=False`:

- validate replay/order exactly like any other update;
- do not invoke the evaluator;
- advance the market cursor;
- append a record with no assessment;
- outcome = `IGNORED_NON_MATERIAL`.

This matters because an ignored state update still advances canonical market state. A later older material update must not be accepted as though the ignored update never existed.

## Material updates

For a new `is_material=True` update:

1. validate order;
2. invoke evaluator immediately;
3. validate exact identity/time/action/reason contract;
4. advance cursor;
5. append record with assessment;
6. outcome = `ASSESSED`.

No minimum interval exists between assessments. Two material updates one millisecond apart, or at the same timestamp with increasing sequence, may each produce an assessment.

## Result contract

```python
class FastPaperEventOutcome(StrEnum):
    ASSESSED = "ASSESSED"
    IGNORED_NON_MATERIAL = "IGNORED_NON_MATERIAL"
    REPLAYED = "REPLAYED"

@dataclass(frozen=True, slots=True)
class FastPaperEventResult:
    outcome: FastPaperEventOutcome
    source_event_id: str
    assessment: FastPaperActionAssessment | None
    next_state: FastPaperLoopState
```

There is deliberately no fill, ledger update, position mutation, or risk result in FL7.1.

## Error types

Use focused exceptions:

```python
class FastPaperLoopError(ValueError): ...
class FastPaperLoopConflictError(FastPaperLoopError): ...
class FastPaperLoopOrderError(FastPaperLoopError): ...
class FastPaperAssessmentMismatchError(FastPaperLoopError): ...
```

Model constructor validation may raise `ValueError` before engine application.

Fail closed on:

- invalid/non-empty/version/type invariants,
- conflicting replay identity,
- stale/reversed per-market sequence,
- timestamp regression,
- assessment event/market/sequence/time mismatch,
- invalid action/reason metadata.

## Determinism and leakage

The engine must not read:

- wall clock,
- providers,
- databases,
- future labels,
- counterfactual labels,
- randomness,
- mutable global state.

Identical state + update + deterministic evaluator must produce identical result and journal state.

Exact replay must not re-run the evaluator.

## Compatibility

FL7.1 must not change the existing C5 `paper_loop` API or behavior. Existing PAPER tests remain part of the full Python suite.

The new package is additive so later FL7 slices can incrementally route:

- `BUY` through existing entry risk + PAPER fill + ledger,
- `SKIP` into auditable opportunity records,
- `HOLD/REDUCE/SELL` through existing/open-position PAPER accounting and protective exits.

## TDD proof requirements

Tests must prove at minimum:

1. one new material update invokes evaluator exactly once and records the assessment;
2. two material updates one millisecond apart both assess — no timer/checkpoint gate;
3. two increasing sequences at the same timestamp both assess;
4. non-material update does not invoke evaluator but advances the cursor;
5. exact material replay returns prior assessment without invoking evaluator again;
6. exact non-material replay is idempotent;
7. same event ID with changed content fails closed as conflict;
8. stale/repeated new sequence on one market fails closed;
9. timestamp regression with increasing sequence fails closed;
10. equal sequence on different markets is valid;
11. assessment event identity mismatch fails closed;
12. assessment market/sequence/timestamp mismatch fails closed;
13. all five action values can cross the boundary without interpretation;
14. evaluator exception cannot return a partially applied next state;
15. identical deterministic inputs produce identical state/result;
16. existing full Python suite remains green.

## Exit criterion for FL7.1

FL7.1 is complete when a material ordered Fast Lane update can synchronously produce and journal one validated PAPER action assessment at event resolution, with deterministic replay/order guarantees and no timer dependency, while the existing PAPER/risk/accounting authority remains unchanged.

FL7.2 then connects `BUY` assessments to existing PAPER risk, price/latency/capacity checks, fills, and ledger accounting.

LIVE remains disabled.
