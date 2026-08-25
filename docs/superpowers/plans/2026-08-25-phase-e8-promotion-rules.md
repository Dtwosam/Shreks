# Phase E8 Promotion Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, auditable promotion evaluator that can mark a registered challenger eligible/ineligible/insufficient under explicit caller-supplied gates, persist the assessment, and never self-promote or enable live money.

**Architecture:** Add `shreks_brain.promotion`. Immutable models define explicit thresholds and gate results; a pure evaluator consumes E6 registry + E5 report/trades + E7 shadow evidence + baseline reports; a canonical append-only store persists the content-addressed assessment. Registry mutation remains outside E8 and must use the resulting assessment fingerprint as the explicit E6 `decision_reference`.

**Tech Stack:** Python 3.12 standard library plus existing Shreks E5/E6/E7 domain packages; pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e8-promotion-rules-design.md`

## Global Constraints

- Base exactly sealed E7 `62ffff47a6bcb408d8696a56eda6535d13cdd186`.
- Schema exactly `e8-promotion-v1`.
- Every numeric threshold is caller-supplied; no production promotion defaults.
- Challenger must currently reconstruct to E6 `CHALLENGER`.
- E8-v1 requires complete model + E4 validation provenance because E7-v1 shadow evidence is model-backed.
- Exact E5 evaluation evidence must agree with E6 persisted candidate evidence.
- E7 shadow evidence must align with candidate/model provenance.
- Any current champion is automatically a required baseline.
- `FAIL` dominates `INSUFFICIENT`; both dominate `PASS` at the overall decision level.
- No `RegistryStore.record_status`, no registry mutation, no live mode, no wallet/signer, no transaction construction/submission.
- `ELIGIBLE` means eligible for a later explicit recorded E6 status operation only; it is not a live-money gate.

---

### Task 1: Promotion policy, gate, assessment, and fingerprint contract

**Files:**
- Create: `python/src/shreks_brain/promotion/models.py`
- Create: `python/src/shreks_brain/promotion/fingerprint.py`
- Create: `python/src/shreks_brain/promotion/__init__.py`
- Create: `python/tests/test_promotion_models.py`
- Create: `python/tests/test_promotion_public_api.py`

**Interfaces:**

Produce:

```python
PROMOTION_SCHEMA_VERSION = "e8-promotion-v1"

class PromotionDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class PromotionGateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT = "INSUFFICIENT"
```

`PromotionGateCode` must contain exactly:

```text
CURRENT_CHALLENGER
MODEL_VALIDATION_PROVENANCE
EVALUATION_MATCH
TRADE_EVIDENCE_RECONCILIATION
MIN_TRADE_COUNT
MIN_EVALUATION_SPAN
MIN_NET_EXPECTANCY_PCT
MIN_PROFIT_FACTOR
MAX_DRAWDOWN_PCT
MAX_COST_BURDEN_PCT
MAX_BRIER_SCORE
MAX_EXPECTED_CALIBRATION_ERROR
BASELINE_COVERAGE
BASELINE_EXPECTANCY_ADVANTAGE
MAX_SINGLE_WINNER_SHARE
SHADOW_PROVENANCE
MIN_SHADOW_DECISION_COUNT
MIN_SHADOW_DISTINCT_MINT_COUNT
MIN_SHADOW_SPAN
```

`PromotionPolicy` fields, all required/no defaults:

```python
version: str
min_trade_count: int
min_evaluation_span_ms: int
min_net_expectancy_pct: float
min_profit_factor: float
max_drawdown_pct: float
max_cost_burden_pct: float
max_brier_score: float
max_expected_calibration_error: float
required_baseline_versions: tuple[str, ...]
min_baseline_expectancy_advantage_pct: float
max_single_winner_share_of_positive_pnl: float
min_shadow_decision_count: int
min_shadow_distinct_mint_count: int
min_shadow_span_ms: int
```

`PromotionGateResult` fields:

```python
code: PromotionGateCode
status: PromotionGateStatus
observed_value: float | int | str | None
threshold_value: float | int | str | None
message: str
```

`PromotionAssessment` fields:

```python
schema_version: str
policy_version: str
candidate_version: str
candidate_fingerprint_sha256: str
registry_fingerprint_sha256: str
evaluation_fingerprint_sha256: str
trade_evidence_fingerprint_sha256: str
shadow_ledger_fingerprint_sha256: str
baseline_evaluation_identities: tuple[tuple[str, str], ...]
evaluated_at_unix_ms: int
gates: tuple[PromotionGateResult, ...]
decision: PromotionDecision
assessment_fingerprint_sha256: str
```

- [ ] **Step 1: Write model/public API tests before package exists**

Lock exact public API:

```python
assert set(promotion.__all__) == {
    "PROMOTION_SCHEMA_VERSION",
    "PromotionDecision",
    "PromotionGateStatus",
    "PromotionGateCode",
    "PromotionPolicy",
    "PromotionGateResult",
    "PromotionAssessment",
}
```

At Task 1 do not export the evaluator/store yet.

Tests require:

- every `PromotionPolicy` parameter has `inspect.Parameter.empty` default;
- integer thresholds reject bool/negative values;
- finite thresholds reject bool/NaN/infinity;
- percent/fraction upper bounds are enforced where applicable;
- required baseline versions are lexical, unique, non-empty, and may be empty;
- gate result uses exact enums and non-empty message;
- assessment requires exact schema, canonical gate order by `PromotionGateCode.value`, unique gate codes, canonical lexical baseline identities, lowercase SHA-256 values, and a decision consistent with gate statuses (`FAIL -> INELIGIBLE`; else `INSUFFICIENT -> INSUFFICIENT_EVIDENCE`; else `ELIGIBLE`).

Public API/source tests forbid exported names or source calls containing:

```text
record_status
record_status_event
RegistryStore
TradeIntent
PaperExecutionResult
enable_live
sign
submit
```

- [ ] **Step 2: Open E8 draft PR and run exact PR CI; require clean RED**

Expected Python result: collection errors only because `shreks_brain.promotion` is absent. Rust/workspace and repository safety stay green.

- [ ] **Step 3: Implement immutable models and internal canonical hashing**

`fingerprint.py` follows E7 conventions: compact sorted-key JSON, exact `.hex()` float normalization, enum values, tuple/list order preserved, mappings sorted by string key, SHA-256 UTF-8 bytes.

Do not add evaluator/store behavior yet.

- [ ] **Step 4: Run full CI and require GREEN**

Record exact head, run ID, Python count/runtime, Rust/workspace, and repository-safety evidence.

---

### Task 2: Pure promotion evaluator

**Files:**
- Create: `python/src/shreks_brain/promotion/engine.py`
- Modify: `python/src/shreks_brain/promotion/__init__.py`
- Create: `python/tests/test_promotion_engine.py`
- Create: `python/tests/test_promotion_evidence.py`
- Modify: `python/tests/test_promotion_public_api.py`

**Interface:**

```python
def evaluate_promotion(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    evaluation_report: TradingEvaluationReport,
    evaluated_trades: tuple[EvaluatedTrade, ...],
    shadow_ledger: ShadowEvidenceLedger,
    baseline_reports: tuple[TradingEvaluationReport, ...],
    policy: PromotionPolicy,
    evaluated_at_unix_ms: int,
) -> PromotionAssessment: ...
```

- [ ] **Step 1: Write evidence/provenance tests first**

Lock fail-closed behavior:

```text
exact input types only
candidate must exist
candidate current status must be CHALLENGER
candidate must have complete model + E4 validation provenance
evaluation report candidate/version/fingerprint/policy/headline metrics must match E6 candidate evidence
trade tuple entries must all match candidate_version
trade count/gross PnL/net PnL/turnover/total cost/win-loss-flat counts/average winner/average loser/win rate/cost burden must reconcile to E5 report metrics within existing E5 arithmetic tolerances
baseline report versions unique
baseline report cannot be challenger
baseline policy version must equal challenger evaluation policy version
shadow records used for candidate must match candidate fingerprint, strategy version, model version, and E7 schema
foreign-candidate shadow records in the same ledger are allowed but ignored
candidate shadow records with mismatched provenance fail closed
evaluated_at_unix_ms cannot precede latest candidate trade close, latest candidate shadow decision, or candidate registration
```

Compute canonical `trade_evidence_fingerprint_sha256` from the full canonical tuple of evaluated trade dataclass fields, including exact float normalization.

- [ ] **Step 2: Write gate/decision tests before implementation**

Use a hand-computed fixture that initially passes every gate. Then mutate one dimension at a time.

Gate semantics:

- `CURRENT_CHALLENGER`: FAIL if status is not challenger.
- `MODEL_VALIDATION_PROVENANCE`: FAIL when model/E4 provenance is absent or incomplete.
- `EVALUATION_MATCH`: FAIL on E6/E5 mismatch.
- `TRADE_EVIDENCE_RECONCILIATION`: FAIL on raw-trade/E5 mismatch.
- `MIN_TRADE_COUNT`: INSUFFICIENT below threshold.
- `MIN_EVALUATION_SPAN`: INSUFFICIENT below threshold.
- `MIN_NET_EXPECTANCY_PCT`: INSUFFICIENT if undefined; FAIL below threshold; PASS otherwise.
- `MIN_PROFIT_FACTOR`: INSUFFICIENT if undefined; FAIL below threshold; PASS otherwise.
- `MAX_DRAWDOWN_PCT`: FAIL above threshold.
- `MAX_COST_BURDEN_PCT`: INSUFFICIENT if undefined; FAIL above threshold.
- `MAX_BRIER_SCORE`: INSUFFICIENT if calibration missing; FAIL above threshold.
- `MAX_EXPECTED_CALIBRATION_ERROR`: INSUFFICIENT if calibration missing; FAIL above threshold.
- `BASELINE_COVERAGE`: required baselines missing -> INSUFFICIENT; wrong policy -> FAIL.
- `BASELINE_EXPECTANCY_ADVANTAGE`: required baseline expectancy undefined -> INSUFFICIENT; candidate advantage below threshold -> FAIL; all required baselines beaten -> PASS.
- current champion version is automatically added to the required baseline set when it is not the candidate.
- `MAX_SINGLE_WINNER_SHARE`: no positive winner -> INSUFFICIENT; share above threshold -> FAIL.
- `SHADOW_PROVENANCE`: FAIL on candidate shadow provenance mismatch; PASS otherwise.
- `MIN_SHADOW_DECISION_COUNT`: INSUFFICIENT below threshold.
- `MIN_SHADOW_DISTINCT_MINT_COUNT`: INSUFFICIENT below threshold.
- `MIN_SHADOW_SPAN`: INSUFFICIENT below threshold.

Decision precedence must be tested with mixed gates:

```python
any FAIL -> INELIGIBLE
no FAIL + any INSUFFICIENT -> INSUFFICIENT_EVIDENCE
all PASS -> ELIGIBLE
```

- [ ] **Step 3: Run exact PR CI and require RED only for missing evaluator**

The new tests may fail only because `evaluate_promotion`/engine behavior is absent.

- [ ] **Step 4: Implement pure evaluator**

Implementation requirements:

1. resolve/validate candidate and E6 status/provenance;
2. verify E5 report identity/headline evidence against E6;
3. validate and reconcile raw trade evidence;
4. canonicalize baseline reports and automatically require current champion when present;
5. validate candidate E7 shadow provenance and derive count/distinct mints/span;
6. derive trade sample/span/single-winner-share;
7. emit exactly one result per gate code in lexical code order;
8. derive overall decision from gate status precedence;
9. compute assessment fingerprint from every persisted assessment field except the fingerprint itself.

No file I/O, wall clock, random, network, sklearn, PyArrow, registry mutation, or execution path.

- [ ] **Step 5: Add import/source firewalls**

Require importing `shreks_brain.promotion` not to eagerly import sklearn/PyArrow and inspect promotion source for forbidden registry/live/execution calls.

- [ ] **Step 6: Run full CI and require GREEN**

Record exact evidence.

---

### Task 3: Canonical append-only promotion assessment store

**Files:**
- Create: `python/src/shreks_brain/promotion/codec.py`
- Create: `python/src/shreks_brain/promotion/store.py`
- Modify: `python/src/shreks_brain/promotion/__init__.py`
- Create: `python/tests/test_promotion_store.py`
- Modify: `python/tests/test_promotion_public_api.py`

**Interface:**

```python
class PromotionAssessmentStore:
    def __init__(self, path: str | Path) -> None: ...
    def load(self) -> tuple[PromotionAssessment, ...]: ...
    def append(self, assessment: PromotionAssessment) -> tuple[PromotionAssessment, ...]: ...
```

Final public API adds exactly `PromotionAssessmentStore` and `evaluate_promotion` to the Task 1 symbols.

- [ ] **Step 1: Write store tests first**

Lock:

- missing file -> empty tuple without creating file;
- append creates parents and survives restart;
- persisted top-level document is exactly:

```json
{"schema_version":"e8-promotion-v1","assessments":[]}
```

with canonical sorted compact JSON and trailing newline;
- identity `(candidate_version, policy_version, evaluated_at_unix_ms)`;
- identical append is byte-for-byte idempotent;
- same identity/different content fails closed;
- canonical assessment order `(evaluated_at_unix_ms, candidate_version, policy_version, assessment_fingerprint_sha256)`;
- decode requires exact field sets/enums/types;
- every assessment fingerprint is independently recomputed on load;
- malformed JSON, unknown fields/schema/enum, non-finite values, tampered gate content, tampered trade/shadow/baseline fingerprints, and tampered assessment fingerprint fail closed;
- atomic fsync + replace leaves no sibling `.tmp` after success;
- no delete/rewrite/promotion/registry/live method exists.

- [ ] **Step 2: Run exact PR CI and require RED only for missing store**

- [ ] **Step 3: Implement canonical codec/store**

Use the same canonical JSON conventions as E6/E7. On write error, best-effort remove the temporary sibling and re-raise.

- [ ] **Step 4: Run full CI and require GREEN**

This head becomes the E8 behavior head only after Python, Rust/workspace, and repository safety all pass.

---

### Task 4: Scope audit, verification record, immutable E8 seal

**Files:**
- Modify only: `docs/superpowers/plans/2026-08-25-phase-e8-promotion-rules.md`

- [ ] **Step 1: Cumulative scope audit**

Compare sealed E7 `62ffff47a6bcb408d8696a56eda6535d13cdd186` to E8 behavior head.

Allowed files:

- E8 design/plan docs;
- `python/src/shreks_brain/promotion/`;
- E8 promotion tests.

No modifications to E5 evaluation, E6 registry, E7 shadow, risk, paper execution, observer/executor, or live paths.

- [ ] **Step 2: Replace this plan with a verification record**

Include every RED/GREEN head + CI run, corrections, behavior-head Python count/runtime, scope audit, and explicit authority/profitability boundary.

- [ ] **Step 3: Audit behavior head -> seal candidate**

Require exactly one documentation file changed and zero production/test changes.

- [ ] **Step 4: Run final exact-head CI**

Require Python, Rust/workspace, and repository safety GREEN on the exact seal SHA.

- [ ] **Step 5: Update E8 PR body and freeze**

Confirm PR base is `feat/phase-e7-shadow-challenger` at sealed E7 SHA, PR head equals final E8 seal SHA, and no tracked changes occur afterward.

Phase E exits only after this seal. The seal proves the promotion evaluator is deterministic/auditable; it does **not** claim any current challenger actually meets a profitable policy and does not enable live money.