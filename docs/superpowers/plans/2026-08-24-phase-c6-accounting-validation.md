# Phase C6 Accounting Validation and Restart Recovery Implementation Plan

**Goal:** Prove Phase C accounting and restart integrity without changing trading logic.

**Base:** verified C5 head `7f9e0b2e163e1f4c22855d9a14ecdadccdde5bea`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-c6-accounting-validation-design.md`.

## Global constraints

- PAPER only; live remains disabled.
- C1 fill, C3 ledger, C4 exits, and C5 orchestration stay authoritative and unchanged unless a proven predecessor defect is found.
- Rust storage owns migration 0006; Python uses the shared SQLite checkpoint table.
- No pickle/dynamic imports/eval/arbitrary deserialization.
- No wall-clock reads; persistence timestamps are explicit inputs.
- No provider/RPC/network/signer/transaction code.
- No production trading defaults.
- TDD RED -> exact failure -> GREEN.
- Minimize CI churn: three major RED/GREEN gates, then one final exact-head seal.

---

## Gate 1 — Operational schema + accounting validator

**Create/modify:**
- `crates/shreks-storage/migrations/0006_paper_loop_checkpoints.sql`
- `crates/shreks-storage/src/lib.rs`
- `crates/shreks-storage/tests/database.rs`
- `python/tests/test_paper_validation_accounting.py`
- `python/src/shreks_brain/paper_validation/models.py`
- `python/src/shreks_brain/paper_validation/accounting.py`

### RED

Tests must require:

- storage schema version 6,
- `paper_loop_checkpoints` table/index,
- accounting status enum and deterministic finding vocabulary,
- exact cash/realized/cost equations,
- per-position linked realized/cost/quantity equations,
- marked-equity identity `cash + market value - starting cash == realized + unrealized`,
- unmarked OPEN lifecycle => `INCOMPLETE`, not zero,
- counts for partial reductions, failures, wins, losses, flat closes, open/closed positions,
- tampered in-memory ledger object => `INVALID` rather than silent success.

Use real C1/C3 operations for economic fixtures.

### GREEN

Implement migration 0006, update Rust migration registry/schema tests, and add pure Python accounting validator/models. Do not add persistence codec/store yet.

---

## Gate 2 — Canonical checkpoint codec + SQLite persistence/restart

**Create:**
- `python/tests/test_paper_validation_checkpoint.py`
- `python/src/shreks_brain/paper_validation/checkpoint.py`

### RED

Tests must require:

- exact deterministic payload bytes for identical state,
- exact float/frozenset round-trip,
- only allow-listed dataclass/enum tags,
- unknown/malformed type tags rejected,
- checksum mismatch rejected before state decode,
- envelope/row metadata mismatch rejected,
- save fails if migration table missing,
- first insert atomic,
- same sequence + same payload idempotent,
- same sequence + different state collision rejected,
- lower new sequence rejected after a higher checkpoint,
- latest sequence loads,
- explicit checkpoint time cannot precede loop state,
- file-backed close/reopen restores exact `PaperLoopState`,
- restart equivalence report checks exact state/fingerprint/accounting metrics.

### GREEN

Implement canonical safe codec, checkpoint record/error, SQLite save/load, and restart equivalence. Use stdlib only.

---

## Gate 3 — Source-required accounting scenarios + public API

**Create:**
- `python/tests/test_paper_validation_scenarios.py`
- `python/tests/test_paper_validation_public_api.py`
- `python/src/shreks_brain/paper_validation/__init__.py`

**Modify only if required by a proven C6 defect:**
- C6 package files from Gates 1/2.

### Scenario coverage

Use real C1/C3/C5 paths to prove one durable run containing:

- multiple positions,
- at least one winning closed lifecycle,
- at least one losing closed lifecycle,
- a partial lifecycle reduction,
- failed-after-submission network cost,
- marked equity while positions remain open,
- checkpoint/reopen/restart,
- post-restart continuation,
- duplicate terminal intent protection,
- final accounting reconciliation.

### Public API

Exact exports:

```text
AccountingFinding
AccountingFindingCode
AccountingValidationReport
AccountingValidationStatus
PaperCheckpointError
PaperCheckpointRecord
RestartValidationReport
decode_paper_checkpoint
encode_paper_checkpoint
load_latest_paper_checkpoint
save_paper_checkpoint
validate_paper_accounting
validate_restart_equivalence
```

No storage internals/provider/live authority are exported.

---

## Documentation and seal

- Add README C6 accounting/restart semantics.
- Replace this plan with a concise verification record after implementation evidence is complete.
- Freeze branch.
- Compare exact C5 -> C6 diff and confirm only intended C6/storage/README files changed.
- Run one fresh full exact-head CI and require Python, Rust/workspace metadata, and repository safety all green.
- Put final SHA/run only in draft PR metadata, not tracked docs.
- Leave PR draft/unmerged.

**Phase C exit claim is allowed only after the final seal proves realistic autonomous paper trading plus complete/reconcilable durable history.**
