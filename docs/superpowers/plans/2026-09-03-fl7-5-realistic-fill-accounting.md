# FL7.5 Realistic Fill and Accounting — Implementation Plan

Base: SEALED FL7.4 merged main `168bcabc2faf8093870c9f788b7e0fb1794e3239`; merged-main CI `33760235149` four-gate GREEN.

## Goal

Prove event-resolution Fast PAPER fills/accounting remain exact across partial fills, repeated reductions, failures, restart restoration, fees, and slippage without changing C1/C3 economics.

## Planned scope

### Durable design/plan
- `docs/superpowers/specs/2026-09-03-fl7-5-realistic-fill-accounting-design.md`
- `docs/superpowers/plans/2026-09-03-fl7-5-realistic-fill-accounting.md`

### Python implementation
- Modify `python/src/shreks_brain/paper_validation/accounting.py`
  - extract public `validate_paper_ledger(PaperLedger)` with unchanged formulas/findings;
  - keep `validate_paper_accounting(PaperLoopState)` as compatibility wrapper.
- Add `python/src/shreks_brain/paper_validation/fast_models.py`
  - runtime/checkpoint/restart immutable models and invariants.
- Add `python/src/shreks_brain/paper_validation/fast_checkpoint.py`
  - safe canonical codec;
  - schema-isolated reuse of `paper_loop_checkpoints`;
  - encode/decode/save/load/restart equivalence;
  - `validate_fast_paper_accounting` delegation.
- Modify `python/src/shreks_brain/paper_validation/__init__.py`
  - additive public exports only.

### Tests
- Add `python/tests/test_fast_paper_accounting_reconciliation.py`
  - real FL7.1/FL7.2/FL7.4/C1/C3 scenario across partial reduction, second reduction, failed submission cost, checkpoint/reopen, post-restart close, fees/slippage, final accounting.
  - pending-exit preservation across restart.
  - fail-closed runtime-state/action-record mismatches.
- Add `python/tests/test_fast_paper_checkpoint.py`
  - canonical encode/decode;
  - file-backed append/load;
  - exact idempotent save;
  - sequence collision/regression;
  - mixed legacy/Fast run-id schema rejection;
  - checksum/corruption/unknown-tag rejection;
  - exact restart equivalence.
- Modify existing paper-validation public/API tests only where needed for `validate_paper_ledger` and new exports.

No Rust, provider, strategy, C1, C3, risk, signer, transaction, or LIVE files are planned.

## TDD sequence

### 1. RED contract
Commit only:
- design;
- plan;
- new FL7.5 test files and minimal public-API expectation updates.

Do not add production symbols yet.

Require CI:
- repository safety GREEN;
- Rust GREEN;
- ARM64 GREEN;
- Python RED only because FL7.5 public symbols/modules are absent.

### 2. Shared ledger validator
Implement `validate_paper_ledger` by moving the exact existing body from `validate_paper_accounting` after its current type check/wrapper. No formula, tolerance, status, finding, or metric changes.

Focused requirement:
- all legacy paper-validation tests remain green;
- direct ledger and wrapped legacy state produce identical reports.

### 3. Runtime state models
Implement:
- `FAST_PAPER_RUNTIME_STATE_VERSION = "fl7.5-v1"`
- `FAST_PAPER_CHECKPOINT_SCHEMA_VERSION = "fl7.5-fast-paper-state-v1"`
- `FastPaperRuntimeState`
- `FastPaperCheckpointRecord`
- `FastPaperRestartValidationReport`
- `FastPaperCheckpointError`

Runtime constructor validates exact OPEN-position coverage and event-record backing for pending BUY/exit authority.

### 4. Safe Fast checkpoint codec/storage
Implement explicit allow-listed dataclass/enum registries for only types reachable from `FastPaperRuntimeState`.

Reuse `paper_loop_checkpoints` with per-run schema exclusivity.

Do not import or expose raw SQLite handles.

### 5. Realistic reconciliation scenario
Use existing public domain functions only:

- `create_fast_paper_loop_state` / `run_fast_paper_event` for action records;
- `execute_fast_paper_buy` for entry;
- `create_fast_paper_position_action_state` / `apply_fast_paper_position_action` for exits;
- existing C1/C3 functions transitively through FL7.2/FL7.4;
- `validate_fast_paper_accounting` for independent reconciliation;
- file-backed SQLite checkpoint/reopen for restart proof.

Scenario ordering:
1. record BUY event and fill BUY;
2. create FL7.4 state for OPEN lifecycle;
3. record REDUCE event #1; capacity-limited execution yields C1 PARTIAL and C3 reduction;
4. record REDUCE event #2; fresh key/quantity reduction;
5. record SELL event with `FAILED_AFTER_SUBMISSION`; C3 books network fee only;
6. validate accounting;
7. checkpoint and fully reopen;
8. prove exact restart equivalence and prior terminal keys present;
9. record fresh SELL event and close remainder;
10. final reconciliation must report partial reductions and terminal failure while cash/PnL/cost identities remain valid.

### 6. Pending-authority restart scenario
Checkpoint while a REDUCE/SELL remains pending before latency eligibility. Restore and prove:
- exact same assessment/source event;
- exact same target base quantity;
- exact same original assessment timestamp;
- subsequent eligible attempt derives the same idempotency key independent of quote repricing.

### 7. Candidate verification
Require one candidate full four-gate GREEN.

Audit changed filenames and patches for:
- no C1/C3 formula changes;
- no risk/strategy changes;
- no migration/runtime/provider/LIVE authority changes;
- `paper_validation/__init__.py` export-only;
- legacy C6 behavior preserved.

### 8. Clean history
Collapse post-RED authoring into one implementation commit if needed while preserving:

`design -> plan -> RED -> implementation`

Force-move only `build/fl7-5-realistic-fill-accounting` to the clean commit.

### 9. Exact-clean-head proof
Require fresh four-gate CI on the rewritten exact head.

Update draft PR with:
- RED proof;
- candidate proof;
- clean head;
- exact scope;
- architecture audit.

Mark ready only after exact-head GREEN.

### 10. Guarded merge and seal
Merge only with `expected_head_sha=<exact clean head>`.

Then require fresh push-triggered merged-main four-gate GREEN before writing `SEALED`.

LIVE remains disabled throughout.

## Completion statement boundary

A FL7.5 seal may claim:
- realistic Fast PAPER fill/accounting reconciliation is restart-safe under the covered deterministic scenarios;
- partial reductions, failures, fees/slippage, idempotency, and final closure reconcile through C1/C3/C6 authority.

It may not claim:
- profitability;
- production Fast Lane runtime acceptance;
- protective-exit completion (FL7.6);
- shadow proof;
- LIVE readiness.
