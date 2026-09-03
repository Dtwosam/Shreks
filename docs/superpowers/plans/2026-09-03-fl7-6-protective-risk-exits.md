# FL7.6 Fast PAPER Protective Risk Exits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect sealed C4 protective exits to the Fast PAPER event/action path, with protective SELL precedence and restart-safe trailing-stop state, without duplicating stop, execution, fill, or accounting logic.

**Architecture:** Add a Fast PAPER protected-event wrapper that obtains a normal FL7.4 strategy approval, evaluates sealed C4 with a protective-only C4 policy, and returns the final assessment to sealed FL7.1 before the event is recorded. Add an additive FL7.6 protected runtime wrapper and protected checkpoint schema that nests the sealed FL7.5 runtime and persists C4 `ExitState` high-water state; old FL7.5 checkpoint constants/functions remain unchanged.

**Tech Stack:** Python 3.12 dataclasses/stdlib, existing `shreks_brain.exits`, `shreks_brain.fast_paper`, `shreks_brain.paper_validation`, SQLite checkpoint table, pytest, GitHub Actions four-gate CI.

**Spec:** `docs/superpowers/specs/2026-09-03-fl7-6-protective-risk-exits-design.md`

## Global Constraints

- Base is sealed merged-main `092c3026b59a4e0f3464f115c571407c78052076` with merged-main CI `33762471582` four-gate green.
- LIVE remains disabled.
- C4 `assess_exit` remains the only protective trigger/precedence authority.
- FL7.4 `apply_fast_paper_position_action` remains the only Fast PAPER open-position execution boundary.
- C1/C3 remain the only fill/accounting authorities.
- FL7.5 `FAST_PAPER_RUNTIME_STATE_VERSION == "fl7.5-v1"` and `FAST_PAPER_CHECKPOINT_SCHEMA_VERSION == "fl7.5-fast-paper-state-v1"` must remain unchanged.
- No production defaults for stop/risk thresholds.
- No provider/RPC, signer, transaction, or LIVE authority.
- No SQLite migration.
- TDD order is mandatory: tests -> exact RED proof -> production code -> candidate green -> clean exact-head green -> guarded merge -> merged-main green.

---

### Task 1: Define the FL7.6 protected-event contract in tests

**Files:**
- Create: `python/tests/test_fast_paper_protective_exits.py`
- Later create: `python/src/shreks_brain/fast_paper/protective_models.py`
- Later create: `python/src/shreks_brain/fast_paper/protective.py`
- Later modify: `python/src/shreks_brain/fast_paper/__init__.py`

**Interfaces:**
- Consumes: sealed `ExitPolicy`, `ExitExecutionContext`, `ExitState`, `assess_exit`, `FastPaperLoopState`, `FastPaperMaterialUpdate`, `FastPaperPositionActionApproval`, `PaperPosition`, `FeatureVector`.
- Produces:
  - `FAST_PAPER_PROTECTIVE_EXIT_VERSION = "fl7.6-v1"`
  - `FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY = "protective-risk"`
  - `FastPaperProtectiveExitError`
  - `FastPaperPositionApprovalEvaluator`
  - `FastPaperProtectiveExitPolicy`
  - `FastPaperProtectiveEventResult`
  - `create_fast_paper_protective_exit_state`
  - `run_fast_paper_protective_event`

- [ ] **Step 1: Write RED tests for stable public contract and protective-only policy**

Tests must import the names above from `shreks_brain.fast_paper` and assert:

```python
assert FAST_PAPER_PROTECTIVE_EXIT_VERSION == "fl7.6-v1"
assert FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY == "protective-risk"
```

Construct valid protective C4 policies with `take_profit_levels=()`, all flow/momentum fields `None`, and `wallet_distribution_enabled=False`.

Require construction failure when any one forbidden strategy-style C4 rule is enabled:

```python
with pytest.raises(ValueError, match="protective"):
    FastPaperProtectiveExitPolicy(
        version="protective-v1",
        exit_policy=replace(base_exit_policy, take_profit_levels=(TakeProfitLevel(...),)),
    )
```

Repeat for wallet, flow pair, and momentum pair.

- [ ] **Step 2: Write RED tests for strategy passthrough**

Create an OPEN C3 PAPER position, C4 `FeatureVector`, C4 `ExitExecutionContext`, and initial C4 `ExitState`.

For no protective trigger:

```python
result = run_fast_paper_protective_event(... strategy_evaluator=returns_hold_approval)
assert result.event_result.outcome is FastPaperEventOutcome.ASSESSED
assert result.applied_approval is result.strategy_approval
assert result.applied_approval == original_hold_approval
assert result.protective_triggered is False
assert result.next_protective_state == result.protective_assessment.next_state
```

Repeat with explicit REDUCE approval and assert the exact caller-supplied `target_base_quantity` is preserved.

- [ ] **Step 3: Write RED tests for each protective override**

Use one focused test each for:

- hard stop;
- trailing stop;
- max hold;
- global halt;
- route unavailable;
- liquidity below minimum;
- exit impact above maximum;
- exit capacity below minimum.

Each must require:

```python
assert result.protective_triggered is True
assert result.applied_approval.assessment.action is FastPaperAction.SELL
assert result.applied_approval.target_base_quantity == authoritative_position.quantity
assert result.applied_approval.assessment.strategy_family == "protective-risk"
assert result.applied_approval.assessment.strategy_version == protective_policy.version
assert result.applied_approval.assessment.reasons[0] == "protective:<EXPECTED_C4_REASON>"
```

For max hold/global halt, deliberately make ordinary C4 market/execution evidence stale and prove sealed C4 forced-exit semantics are preserved.

- [ ] **Step 4: Write RED test for C4 protective precedence and audit reasons**

Trigger several protective conditions simultaneously and assert the first reason follows sealed C4 precedence. Assert the original strategy action and ordered reasons are appended as:

```text
strategy_action:<ACTION>
strategy:<original reason 1>
strategy:<original reason 2>
```

- [ ] **Step 5: Write RED tests for replay/non-material no-op semantics**

Use call counters in a real Python closure, not mocks.

For non-material update:

```python
assert result.event_result.outcome is FastPaperEventOutcome.IGNORED_NON_MATERIAL
assert evaluator_calls == 0
assert result.strategy_approval is None
assert result.applied_approval is None
assert result.protective_assessment is None
assert result.next_protective_state == input_state
```

Apply a material event once, then replay the exact update against the returned event-loop state. Require `REPLAYED`, zero new evaluator calls, and unchanged protective state.

- [ ] **Step 6: Write RED tests for identity/authority failures**

Require typed failure for strategy approval whose assessment mismatches the triggering update on any of:

- source event ID;
- market key;
- sequence;
- decision timestamp;
- state version.

Require typed failure for position/mint mismatch and for protective evidence timestamps that do not equal update decision time.

- [ ] **Step 7: Write RED integration test through FL7.4/C1/C3**

Take a hard-stop protected result and pass `result.applied_approval` directly to sealed `apply_fast_paper_position_action(...)` with an executable Fast PAPER quote.

Require:

```python
assert position_result.outcome is FastPaperPositionOutcome.SOLD
assert authoritative_position_after.state is PaperPositionState.CLOSED
```

Do not duplicate fill/PnL assertions already owned by FL7.4/FL7.5.

- [ ] **Step 8: Commit Task 1 RED tests**

```bash
git add python/tests/test_fast_paper_protective_exits.py
git commit -m "test: define FL7.6 protective exit arbitration"
```

---

### Task 2: Define restart-safe protected-runtime checkpoint behavior in tests

**Files:**
- Create: `python/tests/test_fast_paper_protective_checkpoint.py`
- Later create: `python/src/shreks_brain/paper_validation/protected_models.py`
- Later modify: `python/src/shreks_brain/paper_validation/fast_checkpoint.py`
- Later modify: `python/src/shreks_brain/paper_validation/__init__.py`
- Modify: `python/tests/test_paper_validation_public_api.py`

**Interfaces:**
- Consumes sealed `FastPaperRuntimeState`, C4 `ExitState`, FL7.6 `FastPaperProtectiveExitPolicy`.
- Produces:
  - `FAST_PAPER_PROTECTED_RUNTIME_STATE_VERSION = "fl7.6-v1"`
  - `FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION = "fl7.6-fast-paper-protected-state-v1"`
  - `FastPaperProtectedRuntimeState`
  - `FastPaperProtectedCheckpointRecord`
  - protected checkpoint encode/decode/save/load/restart-equivalence functions.

- [ ] **Step 1: Write RED model invariant tests**

Build a sealed FL7.5 base runtime with one OPEN position and one FL7.4 position-action state. Wrap it with exactly one matching C4 protective state.

Require valid construction and reject:

- duplicate protective position IDs;
- missing OPEN position protective state;
- extra state for a closed/nonexistent position;
- mint mismatch;
- C4 policy-version mismatch;
- initialized time different from C3 opened time;
- protective state timestamp after base runtime time;
- high-water below weighted entry price.

- [ ] **Step 2: Write RED canonical protected-checkpoint roundtrip test**

Assert:

```python
payload1 = encode_fast_paper_protected_checkpoint(...)
payload2 = encode_fast_paper_protected_checkpoint(...)
assert payload1 == payload2
record = decode_fast_paper_protected_checkpoint(payload1)
assert record.state == protected_runtime
assert record.state.protective_states[0].high_water_price_usd.hex() == expected.hex()
```

Require canonical JSON, SHA-256, and safe finite float handling.

- [ ] **Step 3: Write RED schema-isolation tests**

Using the existing `paper_loop_checkpoints` DDL in a temp SQLite file:

1. save one sealed FL7.5 checkpoint under `run-a`;
2. require protected load/save under `run-a` to fail with schema-namespace conflict;
3. save one protected checkpoint under `run-b`;
4. require sealed FL7.5 load/save under `run-b` to fail;
5. if a legacy C6 row exists under `run-c`, require protected load/save under `run-c` to fail.

No migration may be added.

- [ ] **Step 4: Write RED behavioral trailing-stop restart proof**

Test sequence exactly:

1. OPEN position;
2. initialize C4 state;
3. evaluate a higher price so C4 raises high-water without exiting;
4. place that C4 state into `FastPaperProtectedRuntimeState`;
5. save checkpoint to file-backed SQLite;
6. load it after reopening;
7. require `validate_fast_paper_protected_restart_equivalence(...).equivalent is True`;
8. evaluate a lower price that breaches trailing drawdown through `run_fast_paper_protective_event`;
9. require full protective SELL using restored high-water state.

- [ ] **Step 5: Update exact paper_validation public API RED expectation**

Extend `EXPECTED_PUBLIC_API` with only the new protected-runtime names. The existing FL7.5 names remain present and unchanged.

- [ ] **Step 6: Commit Task 2 RED tests**

```bash
git add python/tests/test_fast_paper_protective_checkpoint.py python/tests/test_paper_validation_public_api.py
git commit -m "test: define FL7.6 protective restart persistence"
```

---

### Task 3: Prove intentional RED in canonical CI

**Files:** none beyond Tasks 1–2 tests.

- [ ] **Step 1: Open draft PR from the test-only head**

PR title:

```text
feat: add FL7.6 protective risk exits
```

Body records sealed FL7.5 base and states production FL7.6 API is intentionally absent.

- [ ] **Step 2: Require canonical RED shape**

Expected CI:

- Repository safety: GREEN;
- Rust workspace/tests: GREEN;
- ARM64 release build + bundle verification: GREEN;
- Python: RED only on imports/missing FL7.6 public API from the two new test modules and intentionally updated public API contract.

If Python fails for syntax, fixture, existing-test regression, or any reason other than absent FL7.6 production surface, fix RED before production implementation.

---

### Task 4: Implement protected-event arbitration minimally

**Files:**
- Create: `python/src/shreks_brain/fast_paper/protective_models.py`
- Create: `python/src/shreks_brain/fast_paper/protective.py`
- Modify: `python/src/shreks_brain/fast_paper/__init__.py`

**Interfaces:** exact Task 1 public contract.

- [ ] **Step 1: Implement `FastPaperProtectiveExitPolicy` validation**

Reject strategy-style C4 rules exactly as specified. Do not inspect or change allowed protective numeric thresholds.

- [ ] **Step 2: Implement result model and type alias**

`FastPaperProtectiveEventResult` validates version, event-result type, optional approval/assessment types, `ExitState`, and boolean trigger flag. For `ASSESSED`, approvals/protective assessment must be present; for replay/non-material they must be absent and `protective_triggered=False`.

- [ ] **Step 3: Implement state initializer as a thin C4 wrapper**

```python
def create_fast_paper_protective_exit_state(position, policy):
    validate types
    return create_exit_state(position, policy.exit_policy)
```

No high-water formula is copied.

- [ ] **Step 4: Implement protected event wrapper using a closure around sealed FL7.1**

Pseudo-code:

```python
captured = []

def evaluator(material_update):
    strategy = strategy_evaluator(material_update)
    validate_strategy_approval(material_update, position, strategy)
    validate_protective_times(material_update, features, context)
    protective = assess_exit(
        position,
        features,
        context,
        protective_state,
        protective_policy.exit_policy,
    )
    applied = resolve(strategy, position, protective, protective_policy)
    captured.append((strategy, applied, protective))
    return applied.assessment

event_result = run_fast_paper_event(state, update, evaluator)
```

If evaluator was not invoked, return no-op result with the original protective state.

If invoked exactly once, return the captured resolution and C4 `next_state`.

Any count other than zero/one is a typed internal-contract error.

- [ ] **Step 5: Implement protective SELL mapping**

For C4 `EXIT`, create a new `FastPaperActionAssessment` with:

```python
version=strategy.assessment.version
source_event_id=strategy.assessment.source_event_id
market_key=strategy.assessment.market_key
source_sequence=strategy.assessment.source_sequence
as_of_unix_ms=strategy.assessment.as_of_unix_ms
strategy_family=FAST_PAPER_PROTECTIVE_STRATEGY_FAMILY
strategy_version=protective_policy.version
action=FastPaperAction.SELL
reasons=protective_reason_tuple
```

Then create `FastPaperPositionActionApproval` by copying position/mint/quote/state identity and setting `target_base_quantity=position.quantity`.

For C4 HOLD, return the original strategy approval object unchanged.

For C4 REDUCE, raise `FastPaperProtectiveExitError`.

- [ ] **Step 6: Export exact public names**

Update `fast_paper/__init__.py` additively only.

- [ ] **Step 7: Commit protected-event implementation**

```bash
git add python/src/shreks_brain/fast_paper/protective_models.py python/src/shreks_brain/fast_paper/protective.py python/src/shreks_brain/fast_paper/__init__.py
git commit -m "feat: add FL7.6 protective exit arbitration"
```

---

### Task 5: Implement additive protected-runtime checkpointing

**Files:**
- Create: `python/src/shreks_brain/paper_validation/protected_models.py`
- Modify: `python/src/shreks_brain/paper_validation/fast_checkpoint.py`
- Modify: `python/src/shreks_brain/paper_validation/__init__.py`

**Interfaces:** exact Task 2 public contract.

- [ ] **Step 1: Implement protected runtime models**

Use the exact constants from Task 2. Validate one protective state per OPEN base-runtime position, position/mint/policy/time/high-water consistency, and no closed-position state.

Use `math.isclose(..., rel_tol=1e-12, abs_tol=1e-9)` only for the high-water-vs-entry lower-bound tolerance, matching preserved PAPER arithmetic strictness.

- [ ] **Step 2: Extend safe codec allow-list only**

Add these dataclass types to `_DATACLASS_TYPES`:

- C4 `ExitPolicy`;
- C4 `ExitState`;
- `FastPaperProtectiveExitPolicy`;
- `FastPaperProtectedRuntimeState`.

Do not add arbitrary types and do not permit dynamic import.

- [ ] **Step 3: Parameterize schema-namespace validation without changing FL7.5 behavior**

Replace the fixed helper internally with:

```python
def _require_schema_namespace(connection, run_id, expected_schema_version): ...
```

Keep `_require_fast_schema_namespace(...)` as a compatibility wrapper if useful, or update old FL7.5 call sites to pass exactly `FAST_PAPER_CHECKPOINT_SCHEMA_VERSION`.

Existing FL7.5 save/load behavior and errors must remain equivalent.

- [ ] **Step 4: Add protected encode/decode functions**

Use the same envelope fields and safe `_encode_value`/`_decode_value` machinery, but require `FAST_PAPER_PROTECTED_CHECKPOINT_SCHEMA_VERSION` and `FastPaperProtectedRuntimeState`.

- [ ] **Step 5: Add protected save/load functions**

Reuse the same append-only table and row shape. Require schema-exclusive run IDs and monotonic sequence semantics identical to FL7.5.

- [ ] **Step 6: Add protected restart-equivalence function**

Fingerprint `_encode_value(protected_state)` canonically and reconcile accounting from `protected_state.base_runtime_state.ledger` through existing `validate_paper_ledger`.

Return existing `FastPaperRestartValidationReport`.

- [ ] **Step 7: Export exact public names**

Update `paper_validation/__init__.py` and keep old FL7.5 names/constants unchanged.

- [ ] **Step 8: Commit protected checkpoint implementation**

```bash
git add python/src/shreks_brain/paper_validation/protected_models.py python/src/shreks_brain/paper_validation/fast_checkpoint.py python/src/shreks_brain/paper_validation/__init__.py
git commit -m "feat: persist FL7.6 protective state"
```

---

### Task 6: Verify candidate, fix only demonstrated defects, and audit scope

**Files:** all FL7.6 files.

- [ ] **Step 1: Require full Python suite green**

Run canonical Python suite through CI. Fix production code for behavior failures. Only update a test when the failure is an intentionally changed additive public-contract expectation, not to weaken semantics.

- [ ] **Step 2: Require all four canonical gates green on candidate head**

- Repository safety;
- Rust workspace/tests;
- Python suite;
- native ARM64 release build + bundle verification.

- [ ] **Step 3: Audit compatibility**

Confirm:

- C4 files unchanged;
- FL7.4 execution files unchanged except additive package export if needed;
- C1/C3 files unchanged;
- FL7.5 runtime/checkpoint constants unchanged;
- no migration;
- no provider/DB/runtime/LIVE authority changes;
- `fast_checkpoint.py` changes are additive protected codec/schema plumbing only.

- [ ] **Step 4: Audit changed-file scope**

Expected files are limited to:

1. FL7.6 design;
2. FL7.6 plan;
3. protective event test;
4. protective checkpoint test;
5. paper-validation public API test;
6. `fast_paper/protective_models.py`;
7. `fast_paper/protective.py`;
8. `fast_paper/__init__.py`;
9. `paper_validation/protected_models.py`;
10. `paper_validation/fast_checkpoint.py`;
11. `paper_validation/__init__.py`.

Any extra file requires explicit architecture justification or removal before merge.

---

### Task 7: Clean history, exact-head verification, guarded merge, and seal

**Files:** no semantic changes.

- [ ] **Step 1: Collapse post-RED authoring history if needed**

Preserve exactly:

```text
design -> plan -> RED -> implementation
```

The clean implementation commit must point to the already-green candidate tree; history cleanup must not change file content.

- [ ] **Step 2: Compare against sealed FL7.5 base**

Require:

```text
ahead_by = 4
behind_by = 0
```

and the expected 11-file scope.

- [ ] **Step 3: Require fresh exact-clean-head four-gate GREEN**

Do not mark ready or merge before this run is complete.

- [ ] **Step 4: Update draft PR body with RED/candidate/exact-head proof and mark ready**

Record exact SHAs, CI run IDs, scope audit, compatibility audit, and LIVE-disabled boundary.

- [ ] **Step 5: Guarded merge only the exact verified head**

Use `expected_head_sha=<clean verified head>`. Any branch drift aborts the merge.

- [ ] **Step 6: Require fresh push-triggered merged-main four-gate GREEN**

Only after all four gates are green may PR/body say `SEALED`.

- [ ] **Step 7: Record FL7 completion boundary**

After merged-main green, state:

- FL7.6 SEALED;
- FL7 software exit criterion satisfied for the implemented/tested Fast PAPER path;
- no profitability claim;
- no shadow acceptance claim;
- no LIVE readiness claim;
- LIVE remains disabled.
