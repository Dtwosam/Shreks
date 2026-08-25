# Phase E11 Paper Evaluation Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve complete paper execution provenance across restarts and deterministically convert fully reconciled closed paper positions into sealed E5 `EvaluatedTrade` evidence without inventing missing costs, fills, setup, or regime data.

**Architecture:** Add a new isolated `shreks_brain.paper_evaluation` package. Pure model/engine code captures C5/C1/C3 evidence and performs strict reconciliation; codec/store code persists that evidence in canonical append-only JSON. Existing C1/C3/C5/E5/E6/E10 behavior remains untouched.

**Tech Stack:** Python 3.12 standard library, existing immutable Shreks contracts, pytest, GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e11-paper-evaluation-bridge-design.md`

## Global Constraints

- Base exactly on sealed E10 head `f31d34382170b3fac8d5073299c8ef2e7e81b8ca`.
- Schema version is exactly `e11-paper-evaluation-v1`.
- Never infer setup/regime, quote/reference price, costs, candidate identity, run identity, or missing fills.
- `paper_run_id` is caller-supplied and non-empty.
- Use exact E6 `RegistryCandidate` attribution and require matching strategy version on captured ledger evidence.
- Favorable signed slippage is not a negative cost; E5 execution friction is `max(0, signed_slippage_usd)` summed over successful fills.
- Any positive orphan failed-entry cost makes candidate/run E5 normalization fail closed.
- Do not modify sealed C1/C3/C5/C6/E5/E6/E7/E8/E9/E10 behavior.
- No registry mutation, promotion, trade generation/execution, signing/submission, LIVE enablement, or profitability claim.
- Every behavior task follows test-first RED -> minimal GREEN -> exact-head CI before advancing.

---

### Task 1: Immutable E11 evidence contracts

**Files:**
- Create: `python/src/shreks_brain/paper_evaluation/models.py`
- Test: `python/tests/test_paper_evaluation_models.py`

**Interfaces:**
- Consumes: `MarketRegime`, `PaperExecutionState`, `PaperLedgerReasonCode`, `TradeSide`.
- Produces:
  - `PAPER_EVALUATION_SCHEMA_VERSION: str = "e11-paper-evaluation-v1"`
  - `PaperEntryProvenance`
  - `PaperPositionExecutionEvidence`
  - `PaperClosedPositionEvidence`
  - `PaperOrphanCostEvidence`
  - `PaperEvaluationCapture`
  - `PaperEvaluationLedger`

- [ ] **Step 1: Write failing model-contract tests**

Create tests that instantiate valid values and independently reject: blank run/candidate/strategy/intent/mint/position/provider strings; malformed candidate/document SHA-256; negative timestamps/sequences/notionals/quantities/costs; invalid enum types; fill fields that are only partially present; successful fill states without positive fill evidence; FAILED execution evidence carrying fill fields; closure with non-positive fill counts or close-before-open; duplicate identities inside capture/ledger; non-canonical execution sequence ordering; and candidate/strategy disagreement inside one capture.

Representative contract:

```python
entry = PaperEntryProvenance(
    paper_run_id="paper-run-1",
    candidate_version="candidate-v1",
    candidate_fingerprint_sha256="a" * 64,
    strategy_version="strategy-v1",
    intent_idempotency_key="entry-1",
    mint="mint-a",
    decision_as_of_unix_ms=1_000,
    setup_name="fresh_launch",
    market_regime=MarketRegime.HOT,
    score_policy_version="score-v1",
    decision_policy_version="decision-v1",
    paper_execution_policy_version="paper-v1",
)
assert entry.market_regime is MarketRegime.HOT
```

- [ ] **Step 2: Commit and run RED CI**

Commit only `python/tests/test_paper_evaluation_models.py`. Expected Python failure: `ModuleNotFoundError: No module named 'shreks_brain.paper_evaluation'`; Rust/workspace and repository safety remain GREEN.

- [ ] **Step 3: Implement minimal immutable contracts**

Use frozen/slotted dataclasses. `PaperPositionExecutionEvidence` has all fill-specific fields paired: either all are `None` for FAILED no-fill evidence or all required fill fields are present for PARTIAL/FILLED evidence. `PaperEvaluationCapture` and `PaperEvaluationLedger` enforce tuple element exact types, unique identities, and deterministic sequence/order invariants.

- [ ] **Step 4: Run exact-head CI and require GREEN**

Run full repository CI. Do not begin Task 2 until Python, Rust/workspace, and repository safety are GREEN.

- [ ] **Step 5: Commit behavior head**

Commit message: `feat: add E11 paper evaluation evidence models`.

---

### Task 2: C5 capture and E5 normalization engine

**Files:**
- Create: `python/src/shreks_brain/paper_evaluation/engine.py`
- Test: `python/tests/test_paper_evaluation_engine.py`

**Interfaces:**
- Consumes:
  - `RegistryCandidate`
  - `PaperCycleResult`
  - Task 1 evidence models
  - sealed E5 `EvaluatedTrade`
- Produces:

```python
def extract_paper_evaluation_evidence(
    paper_run_id: str,
    candidate: RegistryCandidate,
    cycle: PaperCycleResult,
) -> PaperEvaluationCapture: ...


def build_evaluated_trades(
    paper_run_id: str,
    candidate_version: str,
    entry_provenance: tuple[PaperEntryProvenance, ...],
    executions: tuple[PaperPositionExecutionEvidence, ...],
    closures: tuple[PaperClosedPositionEvidence, ...],
    orphan_costs: tuple[PaperOrphanCostEvidence, ...],
) -> tuple[EvaluatedTrade, ...]: ...
```

- [ ] **Step 1: Write failing extraction tests**

Build real C5 cycle fixtures using sealed paper-loop APIs. Cover:
- selected DEFERRED entry emits entry provenance but no economic execution;
- later pending terminal fill can emit position execution evidence without fabricating missing provenance;
- immediate entry fill emits both provenance and execution evidence;
- partial/full exit emits execution evidence;
- `POSITION_CLOSED` emits closure snapshot from resulting C3 ledger;
- failed booked exit with network cost is linked to its open position;
- failed entry with positive booked cost and no position emits orphan-cost evidence;
- rejected/no-op ledger updates emit no economic evidence;
- candidate strategy mismatch fails closed.

- [ ] **Step 2: Commit and run RED CI**

Commit test only. Expected Python failure is absent engine function/module; Rust/workspace and repository safety stay GREEN.

- [ ] **Step 3: Implement minimal capture engine**

For each applied ledger update, identify the newly appended journal entry by comparing the terminal result intent key to `update.ledger.entries[-1]`; require exact key/mint/side/policy/strategy agreement. For a close, fetch the exact CLOSED position by `position_id` from the update ledger and copy final C3 accounting fields. Never synthesize a journal event from a result that C3 did not apply.

- [ ] **Step 4: Run extraction tests to GREEN**

Run focused E11 tests, then full CI.

- [ ] **Step 5: Write failing normalization/reconciliation tests**

Create directly constructed E11 evidence for:
- one complete profitable closed trade;
- one losing trade;
- partial buys and partial sells;
- adverse and favorable slippage;
- failed linked execution cost included in explicit costs;
- deterministic output ordering;
- open/incomplete position ignored;
- missing entry provenance rejected;
- mint/candidate/fingerprint/strategy mismatch rejected;
- BUY opener intent mismatch rejected;
- duplicate/non-increasing journal sequence rejected;
- fill-count mismatch rejected;
- summed explicit-cost mismatch rejected;
- closure-order mismatch rejected;
- positive orphan cost rejected.

Assert exact economics:

```text
entry_notional = sum(successful BUY filled_notional)
turnover = sum(successful BUY/SELL filled_notional)
friction = sum(max(0, signed_slippage_usd))
explicit_cost = sum(all linked booked execution explicit_cost_usd)
net_pnl = closure.realized_pnl_usd
gross_pnl = net_pnl + friction + explicit_cost
```

- [ ] **Step 6: Run RED and verify failure is missing normalization behavior**

Do not alter tests to match implementation shortcuts.

- [ ] **Step 7: Implement minimal normalization**

Use deterministic grouping by `(paper_run_id, position_id)`. Emit `EvaluatedTrade.position_id` as the original C3 position id, `candidate_mint` from closure/execution reconciliation, setup/regime from matching entry provenance, and authoritative open/close times from closure. Use E5 dataclass construction as the final arithmetic invariant gate.

- [ ] **Step 8: Run full exact-head CI and require GREEN**

All Python, Rust/workspace, and repository safety lanes must pass before Task 3.

- [ ] **Step 9: Commit**

Commit message: `feat: bridge paper outcomes to E5 trades`.

---

### Task 3: Canonical codec and restart-safe evidence store

**Files:**
- Create: `python/src/shreks_brain/paper_evaluation/codec.py`
- Create: `python/src/shreks_brain/paper_evaluation/store.py`
- Test: `python/tests/test_paper_evaluation_codec.py`
- Test: `python/tests/test_paper_evaluation_store.py`

**Interfaces:**
- Produces codec helpers internal to the package for exact document encode/decode, canonical JSON, and SHA-256 document fingerprint.
- Produces:

```python
class PaperEvaluationEvidenceStore:
    def load(self) -> PaperEvaluationLedger: ...
    def record_capture(self, capture: PaperEvaluationCapture) -> PaperEvaluationLedger: ...
    def record_cycle(
        self,
        paper_run_id: str,
        candidate: RegistryCandidate,
        cycle: PaperCycleResult,
    ) -> PaperEvaluationLedger: ...
    def evaluated_trades(
        self,
        paper_run_id: str,
        candidate_version: str,
    ) -> tuple[EvaluatedTrade, ...]: ...
```

- [ ] **Step 1: Write codec RED tests**

Lock exact document schema, enum `.value` encoding, sorted/compact canonical JSON, one trailing physical newline, exact nested key sets, fingerprint determinism, unknown/missing field rejection, malformed SHA rejection, invalid enum rejection, non-finite numeric rejection, duplicate identity rejection, non-canonical persisted ordering rejection, and stale document fingerprint rejection.

- [ ] **Step 2: Run RED and implement codec minimally**

The document fingerprint hashes canonical content with `document_fingerprint_sha256` replaced by 64 zeroes, then the physical document stores the computed digest. Decoder reconstructs exact Task 1 dataclasses and independently recomputes the fingerprint.

- [ ] **Step 3: Run focused codec tests GREEN and commit**

Commit message: `feat: encode E11 paper evaluation evidence`.

- [ ] **Step 4: Write store RED tests**

Cover missing-file empty ledger, restart recovery, record-cycle delegation, idempotent repeated capture, conflicting identity rejection, canonical append order, `.tmp` cleanup, atomic replace behavior, tampered-file rejection, and `evaluated_trades` delegation including orphan-cost fail-closed behavior.

- [ ] **Step 5: Run RED and implement store minimally**

Write to `<name>.tmp`, flush, `os.fsync`, `os.replace`, best-effort cleanup on OSError. `record_capture` merges only new immutable evidence by identity; exact repeats are no-ops; conflicts raise `ValueError`.

- [ ] **Step 6: Run full exact-head CI and require GREEN**

Do not advance on partial/focused GREEN only.

- [ ] **Step 7: Commit**

Commit message: `feat: persist E11 paper evaluation evidence`.

---

### Task 4: Explicit public API, authority firewall, and immutable seal

**Files:**
- Create: `python/src/shreks_brain/paper_evaluation/__init__.py`
- Create: `python/tests/test_paper_evaluation_public_api.py`
- Modify: `docs/superpowers/plans/2026-08-25-phase-e11-paper-evaluation-bridge.md` only for final verification record after behavior GREEN.

**Interfaces:**
- Public exports exactly:

```text
PAPER_EVALUATION_SCHEMA_VERSION
PaperEntryProvenance
PaperPositionExecutionEvidence
PaperClosedPositionEvidence
PaperOrphanCostEvidence
PaperEvaluationCapture
PaperEvaluationLedger
PaperEvaluationEvidenceStore
extract_paper_evaluation_evidence
build_evaluated_trades
```

- [ ] **Step 1: Write public API / authority RED tests**

Assert the exact `__all__` tuple. Assert `PaperEvaluationEvidenceStore` public callable surface is exactly `load`, `record_capture`, `record_cycle`, `evaluated_trades`. Assert no public names contain authority fragments such as `registry`, `promote`, `promotion`, `trade_intent`, `execute`, `sign`, `submit`, `live`, `delete`, `overwrite`, or `rewrite`.

- [ ] **Step 2: Run RED and implement export-only package API**

No behavior changes in this step.

- [ ] **Step 3: Run full CI to establish behavior head**

Record exact behavior SHA, CI run id, Python count/time, Rust/workspace result, and repository-safety result.

- [ ] **Step 4: Cumulative E10 -> E11 scope audit**

Allowed paths are only E11 design/verification docs, `python/src/shreks_brain/paper_evaluation/`, and `python/tests/test_paper_evaluation_*.py`. Any other changed path is a stop-and-investigate condition.

- [ ] **Step 5: Rewrite this plan as the final verification record**

Record each RED/GREEN commit and CI run, final behavior head, scope audit, authority boundary, and exact test counts. This documentation update must be the only post-behavior change.

- [ ] **Step 6: Prove behavior-head -> seal candidate is one commit / one file**

Compare exact SHAs and require only this verification document to differ.

- [ ] **Step 7: Run final exact-head CI**

Require Python, Rust/workspace, and repository safety GREEN on the seal candidate.

- [ ] **Step 8: Freeze the stacked draft PR**

Update PR metadata with final seal SHA, behavior SHA, CI identities, test counts, scope audit, and authority boundary. Keep PR draft and intentionally unmerged.
