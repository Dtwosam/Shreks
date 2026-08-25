# Phase E12 Paper Proof Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministically prove whether a challenger with a sealed E8 historical/shadow eligibility assessment also has sufficient restart-safe E11 paper evidence under explicit paper-specific thresholds, without granting registry or live-money authority.

**Architecture:** Add isolated `shreks_brain.proof` models/engine/codec/store. The engine rebuilds exact E11 trades for one paper run, requires exact equality with sealed E10 source evidence, then evaluates explicit paper sample/economic/risk gates while preserving E8 and current E6 provenance. Persistence is append-only canonical JSON.

**Tech Stack:** Python 3.12 standard library, existing immutable E6/E8/E10/E11 contracts, pytest, GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e12-paper-proof-gate-design.md`

## Global Constraints

- Base exactly on sealed E11 head `1b19a6dc5828be33e4c9553a06b3f7379396ddfc`.
- Schema version is exactly `e12-paper-proof-v1`.
- Do not modify sealed E6/E8/E10/E11 behavior.
- `PaperProofPolicy` has no defaults; thresholds remain caller-supplied.
- Rebuild paper trades only through sealed E11 `build_evaluated_trades(...)`.
- Require exact E11-derived trade tuple equality with E10 `TradingEvaluationEvidence.trades` before trusting paper metrics.
- Corrupt/missing E11 provenance and orphan-cost reconciliation errors propagate fail-closed as `ValueError`.
- E12 adds no registry mutation, trade generation/execution, signing/submission, mode change, live enablement, capital sizing, or profitability claim.
- Every behavior task follows RED -> minimal GREEN -> exact-head full CI before advancing.

---

### Task 1: Immutable E12 proof contracts and fingerprinting

**Files:**
- Create: `python/src/shreks_brain/proof/models.py`
- Create: `python/src/shreks_brain/proof/fingerprint.py`
- Test: `python/tests/test_proof_models.py`

**Interfaces:**
- Produces:
  - `PAPER_PROOF_SCHEMA_VERSION = "e12-paper-proof-v1"`
  - `PaperProofDecision`
  - `PaperProofGateStatus`
  - `PaperProofGateCode`
  - `PaperProofPolicy`
  - `PaperProofGateResult`
  - `CandidateProofAssessment`
  - `sha256_canonical(value: object) -> str`

- [ ] **Step 1: Write failing model-contract tests**

Lock:

```python
assert PAPER_PROOF_SCHEMA_VERSION == "e12-paper-proof-v1"
assert tuple(PaperProofDecision) == (
    PaperProofDecision.SUFFICIENT,
    PaperProofDecision.INSUFFICIENT_EVIDENCE,
    PaperProofDecision.FAILED,
)
```

Construct a valid `PaperProofPolicy` and assert every constructor parameter has no default using `inspect.signature`.

Require `PaperProofGateCode` to contain exactly these lexical codes:

```text
E8_ASSESSMENT_ELIGIBLE
E8_REGISTRY_PROVENANCE
MAX_PAPER_COST_BURDEN_PCT
MAX_PAPER_DRAWDOWN_PCT
MAX_PAPER_SINGLE_WINNER_SHARE
MIN_PAPER_DISTINCT_MINT_COUNT
MIN_PAPER_EVALUATION_SPAN
MIN_PAPER_NET_EXPECTANCY_PCT
MIN_PAPER_PROFIT_FACTOR
MIN_PAPER_TRADE_COUNT
PAPER_EVIDENCE_PROVENANCE
```

Reject blank versions, negative integer thresholds, non-finite floats, percentages outside `[0, 100]`, winner share outside `[0, 1]`, malformed SHA-256 values, duplicate/missing/out-of-order gates, wrong exact enum types, invalid timestamps, and a decision inconsistent with gate precedence.

Assert fingerprint determinism and exact-float sensitivity:

```python
assert sha256_canonical({"x": 0.1}) == sha256_canonical({"x": 0.1})
assert sha256_canonical({"x": 0.1}) != sha256_canonical({"x": 0.10000000000000002})
```

- [ ] **Step 2: Commit test-only RED and run full CI**

Expected Python failure: `ModuleNotFoundError: No module named 'shreks_brain.proof'`. Rust/workspace and repository safety must remain GREEN.

Commit message: `test: lock E12 paper proof contracts`.

- [ ] **Step 3: Implement minimal immutable contracts**

Use frozen/slotted dataclasses. `PaperProofDecision` values are exactly:

```text
SUFFICIENT
INSUFFICIENT_EVIDENCE
FAILED
```

`CandidateProofAssessment` fields:

```python
schema_version: str
policy_version: str
candidate_version: str
candidate_fingerprint_sha256: str
registry_fingerprint_sha256: str
e8_assessment_fingerprint_sha256: str
paper_run_id: str
paper_ledger_fingerprint_sha256: str
paper_evaluation_fingerprint_sha256: str
paper_trade_evidence_fingerprint_sha256: str
evaluated_at_unix_ms: int
gates: tuple[PaperProofGateResult, ...]
decision: PaperProofDecision
assessment_fingerprint_sha256: str
```

Gate precedence is FAIL -> FAILED, otherwise INSUFFICIENT -> INSUFFICIENT_EVIDENCE, otherwise SUFFICIENT.

`sha256_canonical` recursively converts floats to `float.hex()` before compact sorted JSON hashing, following the existing E8 provenance pattern.

- [ ] **Step 4: Run focused then full exact-head CI and require GREEN**

- [ ] **Step 5: Commit**

Commit message: `feat: add E12 paper proof contracts`.

---

### Task 2: Pure paper-proof evaluator

**Files:**
- Create: `python/src/shreks_brain/proof/engine.py`
- Test: `python/tests/test_proof_engine.py`

**Interfaces:**
- Consumes:
  - E6 `ChampionChallengerRegistry`, `RegistryStatus`
  - E8 `PromotionAssessment`, `PromotionDecision`
  - E10 `TradingEvaluationEvidence`
  - E11 `PaperEvaluationLedger`, `build_evaluated_trades`
  - Task 1 E12 models
- Produces:

```python
def evaluate_candidate_proof(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    e8_assessment: PromotionAssessment,
    paper_run_id: str,
    paper_ledger: PaperEvaluationLedger,
    paper_evaluation: TradingEvaluationEvidence,
    policy: PaperProofPolicy,
    evaluated_at_unix_ms: int,
) -> CandidateProofAssessment: ...
```

- [ ] **Step 1: Write failing evaluator tests**

Use exact immutable fixture objects. Cover:

1. all gates PASS -> `SUFFICIENT`;
2. E8 `INSUFFICIENT_EVIDENCE` -> E8 gate INSUFFICIENT and overall `INSUFFICIENT_EVIDENCE`;
3. E8 `INELIGIBLE` -> E8 gate FAIL and overall `FAILED`;
4. candidate missing from registry raises `ValueError`;
5. E8 candidate fingerprint mismatch -> provenance FAIL;
6. E8 registry fingerprint mismatch -> provenance FAIL;
7. candidate no longer current CHALLENGER -> provenance FAIL;
8. E10 candidate mismatch -> paper provenance FAIL;
9. E10 trades differ from exact E11 rebuilt trades -> paper provenance FAIL;
10. E11 orphan-cost/missing-provenance reconciliation errors propagate `ValueError`;
11. trade count below minimum -> INSUFFICIENT;
12. distinct mint count below minimum -> INSUFFICIENT;
13. paper span below minimum -> INSUFFICIENT;
14. undefined expectancy/profit factor -> INSUFFICIENT;
15. expectancy below threshold -> FAIL;
16. profit factor below threshold -> FAIL;
17. drawdown above threshold -> FAIL;
18. cost burden above threshold -> FAIL;
19. no positive paper trade -> winner-share INSUFFICIENT;
20. largest-winner share above threshold -> FAIL;
21. deterministic gate lexical ordering/fingerprint;
22. `evaluated_at_unix_ms` earlier than latest referenced E8/paper evidence raises `ValueError`.

For a proven paper tuple compute:

```text
trade_count = len(trades)
distinct_mints = len(set(trade.candidate_mint for trade in trades))
span_ms = max(closed_at) - min(opened_at)
single_winner_share = max(positive net_pnl) / sum(positive net_pnl)
```

- [ ] **Step 2: Commit evaluator RED and run full CI**

Expected Python failure: missing `proof.engine.evaluate_candidate_proof`; Rust/workspace and repository safety GREEN.

Commit message: `test: lock E12 paper proof evaluator`.

- [ ] **Step 3: Implement minimal evaluator**

Validation rules:

```python
if type(registry) is not ChampionChallengerRegistry: raise ValueError(...)
if type(e8_assessment) is not PromotionAssessment: raise ValueError(...)
if type(paper_ledger) is not PaperEvaluationLedger: raise ValueError(...)
if type(paper_evaluation) is not TradingEvaluationEvidence: raise ValueError(...)
if type(policy) is not PaperProofPolicy: raise ValueError(...)
```

Find exact E6 candidate by version. Rebuild trades through:

```python
trades = build_evaluated_trades(
    paper_run_id,
    candidate_version,
    paper_ledger.entry_provenance,
    paper_ledger.executions,
    paper_ledger.closures,
    paper_ledger.orphan_costs,
)
```

Do not catch E11 `ValueError` reconciliation failures.

Paper provenance gate passes only when `paper_evaluation.candidate_version == candidate_version` and `paper_evaluation.trades == trades`.

Only when paper provenance passes may E12 trust `paper_evaluation.report.metrics` for expectancy/profit-factor/drawdown/cost-burden gates. A provenance FAIL makes all downstream metric gates FAIL with a stable message rather than scoring mismatched data.

Latest evidence timestamp is the max of E8 `evaluated_at_unix_ms` and every rebuilt paper trade close timestamp; E12 evaluation cannot precede it.

Build the assessment with a zero assessment fingerprint, then replace it with `sha256_canonical` over canonical assessment material excluding the stored fingerprint.

- [ ] **Step 4: Run focused evaluator tests then full exact-head CI and require GREEN**

- [ ] **Step 5: Commit**

Commit message: `feat: evaluate E12 paper proof`.

---

### Task 3: Canonical assessment store, public API, and immutable seal

**Files:**
- Create: `python/src/shreks_brain/proof/codec.py`
- Create: `python/src/shreks_brain/proof/store.py`
- Create: `python/src/shreks_brain/proof/__init__.py`
- Test: `python/tests/test_proof_store.py`
- Test: `python/tests/test_proof_public_api.py`
- Modify after behavior GREEN only: `docs/superpowers/plans/2026-08-25-phase-e12-paper-proof-gate.md`

**Interfaces:**

```python
class CandidateProofAssessmentStore:
    def load(self) -> tuple[CandidateProofAssessment, ...]: ...
    def append(
        self, assessment: CandidateProofAssessment
    ) -> tuple[CandidateProofAssessment, ...]: ...
```

Public exports exactly:

```text
PAPER_PROOF_SCHEMA_VERSION
PaperProofDecision
PaperProofGateStatus
PaperProofGateCode
PaperProofPolicy
PaperProofGateResult
CandidateProofAssessment
CandidateProofAssessmentStore
evaluate_candidate_proof
```

- [ ] **Step 1: Write store/codec RED tests**

Lock:

- missing file -> empty tuple without creating the file;
- canonical compact JSON + exactly one trailing newline;
- exact top-level and nested field sets;
- enum `.value` encoding;
- deterministic lexical assessment order by `(evaluated_at_unix_ms, candidate_version, policy_version, paper_run_id, assessment_fingerprint_sha256)`;
- identical append byte-idempotence;
- conflicting same identity rejection;
- malformed JSON/schema/enums/SHA/non-finite values rejection;
- unknown/missing fields rejection;
- stale/tampered assessment fingerprint rejection;
- non-canonical persisted order rejection;
- atomic `.tmp` cleanup;
- no delete/rewrite/update/registry/live methods.

- [ ] **Step 2: Run RED and implement codec/store minimally**

Use the sealed E8/E10/E11 persistence pattern: exact field checks, typed reconstruction, independent fingerprint recomputation, `fsync`, `os.replace`.

Identity is exactly:

```text
(candidate_version, policy_version, paper_run_id, evaluated_at_unix_ms)
```

- [ ] **Step 3: Run focused store tests and full CI to GREEN**

- [ ] **Step 4: Write public API / import firewall RED tests**

Assert exact `__all__` and that `CandidateProofAssessmentStore` public callable surface is exactly `load`, `append`.

Assert no public name contains authority fragments:

```text
registry_store
record_status
promote
promotion_apply
trade_intent
execute
sign
submit
live
delete
overwrite
rewrite
```

Fresh subprocess import must not eagerly load `sklearn` or `pyarrow`.

- [ ] **Step 5: Implement export-only `__init__.py` and run full CI to establish behavior head**

Record exact behavior SHA, CI run id, Python count/time, Rust/workspace result, and repository-safety result.

- [ ] **Step 6: Cumulative E11 -> E12 scope audit**

Allowed paths only:

- E12 design/verification docs;
- `python/src/shreks_brain/proof/`;
- `python/tests/test_proof_*.py`.

Any change to E6/E8/E10/E11, paper/risk/execution, provider, observer, Rust executor, or live paths is a stop-and-investigate condition.

- [ ] **Step 7: Rewrite this plan as final verification record**

Record every RED/GREEN head, exact CI evidence, behavior head, scope audit, authority boundary, and explicit statement that `SUFFICIENT` is not promotion or live-money permission.

- [ ] **Step 8: Prove behavior-head -> seal candidate is one commit / one file**

Only this verification document may differ.

- [ ] **Step 9: Run final exact-head CI and require all lanes GREEN**

- [ ] **Step 10: Freeze stacked draft PR**

Update PR metadata with final seal SHA, behavior SHA, CI identities/test counts, scope audit, and authority boundary. Keep draft and intentionally unmerged.