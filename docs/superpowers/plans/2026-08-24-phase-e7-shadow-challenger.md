# Phase E7 Shadow Challenger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic shadow-only challenger path that validates E6/E3 provenance, generates safety-preserving model decisions from current D6 rows, and persists tamper-evident evidence for later E8 evaluation.

**Architecture:** Add a focused `shreks_brain.shadow` package. A pure engine consumes an immutable E6 registry, one registered E3 challenger model, an exact D6 row, and an explicit shadow probability policy; it produces an immutable content-addressed decision record. A separate standard-library evidence store atomically appends canonical records without mutating E6 or executing trades.

**Tech Stack:** Python 3.12 standard library plus existing Shreks Python domain packages; sealed E3 pure-Python inference; pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-e7-shadow-challenger-design.md`

## Global Constraints

- Base exactly sealed E6 `5933416fa7136ee7594f89baf97da469bedac171`.
- Schema exactly `e7-shadow-v1`.
- Candidate must exist and currently reconstruct to E6 `CHALLENGER`.
- E7-v1 accepts model-backed candidates only and requires exact E6/E3 model provenance alignment.
- Caller supplies the versioned `enter_min_probability`; no production threshold default.
- Deterministic safety/setup/regime gates remain authoritative and cannot be overridden by model probability.
- Future D6 label values cannot affect probability, action, reason, decision-feature fingerprint, or record fingerprint.
- No wall-clock read, random source, network call, scikit-learn fit/import, PyArrow import, registry status mutation, `TradeIntent`, paper fill, signer, transaction construction/submission, or live authority.
- E8 owns economic eligibility and promotion.

---

### Task 1: Shadow contract and provenance firewall

**Files:**
- Create: `python/src/shreks_brain/shadow/models.py`
- Create: `python/src/shreks_brain/shadow/fingerprint.py`
- Create: `python/src/shreks_brain/shadow/__init__.py`
- Create: `python/tests/test_shadow_models.py`
- Create: `python/tests/test_shadow_public_api.py`

**Interfaces:**
- Consumes: `DecisionAction`, E6 `RegistryStatus`, sealed D6 schema constants.
- Produces:
  - `SHADOW_CHALLENGER_SCHEMA_VERSION = "e7-shadow-v1"`
  - `ShadowDecisionPolicy(version: str, enter_min_probability: float)`
  - `ShadowReasonCode`
  - immutable `ShadowDecisionRecord`
  - immutable `ShadowEvidenceLedger`
  - internal canonical SHA helpers used by Tasks 2-3.

- [ ] **Step 1: Write contract tests before the package exists**

Create tests that import the exact seven-symbol public API planned by the spec and assert:

```python
assert set(shadow.__all__) == {
    "SHADOW_CHALLENGER_SCHEMA_VERSION",
    "ShadowDecisionPolicy",
    "ShadowReasonCode",
    "ShadowDecisionRecord",
    "ShadowEvidenceLedger",
    "ShadowEvidenceStore",
    "evaluate_shadow_challenger",
}
```

`ShadowDecisionPolicy` must reject empty version, bool/non-finite probabilities, and values outside `[0, 1]`.

`ShadowReasonCode` must contain exactly:

```python
SAFETY_NOT_PASS
SETUP_BLOCKED
REGIME_DEAD
SETUP_WATCH
PROBABILITY_BELOW_ENTER_THRESHOLD
PROBABILITY_ENTER_APPROVED
```

Model tests must enforce non-empty identity/version fields, valid SHA-256 fields, finite probability/threshold values, exact entry-side `DecisionAction` values, and an internally consistent `ShadowEvidenceLedger` in canonical order.

Public API tests must also assert no exported `promote`, `record_status`, `TradeIntent`, `PaperExecutionResult`, `enable_live`, or transaction surface.

- [ ] **Step 2: Run exact PR CI and require a clean RED**

Expected Python result: collection errors caused only by missing `shreks_brain.shadow`; Rust/workspace and repository safety remain unaffected.

- [ ] **Step 3: Implement immutable models and deterministic fingerprint helpers**

`ShadowDecisionRecord` fields:

```python
schema_version: str
candidate_version: str
strategy_version: str
candidate_fingerprint_sha256: str
registry_fingerprint_sha256: str
model_version: str
model_training_fingerprint_sha256: str
target_horizon_seconds: int
target_minimum_return_pct: float
shadow_policy_version: str
enter_min_probability: float
candidate_mint: str
as_of_unix_ms: int
dataset_schema_version: str
decision_feature_fingerprint_sha256: str
setup_name: str
safety_decision: str
setup_state: str
market_regime: str
baseline_action: DecisionAction
positive_probability: float
challenger_action: DecisionAction
reason: ShadowReasonCode
record_fingerprint_sha256: str
```

`ShadowEvidenceLedger` fields:

```python
schema_version: str
records: tuple[ShadowDecisionRecord, ...]
ledger_fingerprint_sha256: str
```

Implement internal canonicalization that recursively converts floats to exact `.hex()` strings for hashing, tuples to ordered lists, and mappings to sorted-key dictionaries. Hash with SHA-256 over compact UTF-8 JSON. Persisted user-facing numeric fields remain normal JSON numbers; hexadecimal normalization is for fingerprint material only.

- [ ] **Step 4: Run full CI and require GREEN**

All predecessor Python/Rust/safety tests plus new model/API tests must pass.

- [ ] **Step 5: Commit coherent Task 1 GREEN**

No engine/store behavior belongs in this commit beyond import-safe stubs required solely to satisfy the locked public API; if a stub would hide missing behavior, keep the corresponding symbol unexported until its own RED gate and update the API expectation in that later gate instead.

---

### Task 2: Shadow decision engine and point-in-time leakage firewall

**Files:**
- Create: `python/src/shreks_brain/shadow/engine.py`
- Modify: `python/src/shreks_brain/shadow/__init__.py`
- Create: `python/tests/test_shadow_engine.py`
- Create: `python/tests/test_shadow_leakage.py`

**Interfaces:**
- Consumes:
  - `ChampionChallengerRegistry`
  - `TrainedLogisticRegressionModel`
  - exact D6 logical row `dict[str, object]`
  - `ShadowDecisionPolicy`
  - sealed `predict_positive_probability(model, row)`
- Produces:

```python
def evaluate_shadow_challenger(
    registry: ChampionChallengerRegistry,
    candidate_version: str,
    model: TrainedLogisticRegressionModel,
    row: dict[str, object],
    policy: ShadowDecisionPolicy,
) -> ShadowDecisionRecord: ...
```

- [ ] **Step 1: Write engine tests first**

Use real E6 candidate/registry objects and real E3 `TrainedLogisticRegressionModel` fixtures. Lock these failures/behaviors:

```python
# governance/provenance
missing candidate -> ValueError
current status != CHALLENGER -> ValueError
strategy-only candidate -> ValueError
model_version mismatch -> ValueError
training schema mismatch -> ValueError
training fingerprint mismatch -> ValueError
ordered model feature names != registry feature_columns -> ValueError
row as_of < candidate.registered_at_unix_ms -> ValueError

# row/baseline
row must be exact D6 physical shape/schema
baseline action must be REJECT/WATCH/ENTER

# hard-gate precedence
safety != PASS -> REJECT / SAFETY_NOT_PASS
safety PASS + setup BLOCKED -> REJECT / SETUP_BLOCKED
safety PASS + setup READY + regime DEAD -> REJECT / REGIME_DEAD
safety PASS + setup WATCH + non-DEAD -> WATCH / SETUP_WATCH
eligible READY + p < threshold -> WATCH / PROBABILITY_BELOW_ENTER_THRESHOLD
eligible READY + p >= threshold -> ENTER / PROBABILITY_ENTER_APPROVED
```

Include a case where baseline action is `WATCH` only because the incumbent score was below threshold, but the model probability exceeds the shadow threshold; expected challenger action is `ENTER`. This proves the baseline action is audit evidence rather than an accidental final gate.

- [ ] **Step 2: Write leakage tests before implementation**

Create two otherwise identical exact D6 rows whose `RESEARCH_LABEL_COLUMNS` are radically different (completed returns/MFE/MAE/rug/exitability versus pending/None) while all `RESEARCH_FEATURE_COLUMNS` remain identical.

Assert both evaluations produce identical:

```python
positive_probability
challenger_action
reason
decision_feature_fingerprint_sha256
record_fingerprint_sha256
```

Also assert the decision-feature fingerprint changes when a material decision-time feature changes.

- [ ] **Step 3: Run exact PR CI and require RED only for missing engine surface**

The failure must be attributable to absent `evaluate_shadow_challenger`/engine behavior, not predecessor regressions.

- [ ] **Step 4: Implement provenance validation and decision engine**

Validation order:

1. exact registry/model/row/policy types;
2. resolve registered candidate;
3. require current E6 status `CHALLENGER`;
4. require complete model-backed provenance;
5. align registry model version/training schema/training fingerprint/ordered feature names to supplied E3 model;
6. require D6 schema and `as_of >= registered_at`;
7. parse entry-side baseline action, safety decision, setup state, and market regime;
8. call sealed E3 probability inference;
9. apply the hard-gate/threshold precedence from the spec;
10. compute decision-feature fingerprint from the `RESEARCH_FEATURE_COLUMNS` projection only;
11. build the immutable record and compute its content fingerprint.

Do not inspect any `RESEARCH_LABEL_COLUMNS` value except the E3 predictor's existing physical-shape validation; no label is copied into fingerprint material or decision logic.

- [ ] **Step 5: Add source/import firewalls**

Tests inspect `shreks_brain.shadow` engine source and loaded modules to require absence of:

```text
record_status
RegistryStore
TradeIntent
RiskAssessment
PaperExecutionResult
execute_paper
sign
submit
enable_live
```

and require importing `shreks_brain.shadow` not to eagerly import `sklearn` or `pyarrow`.

- [ ] **Step 6: Run full CI and require GREEN**

Record exact SHA, CI run ID, Python count/runtime, Rust result, and safety result for the verification record.

---

### Task 3: Durable canonical shadow evidence store

**Files:**
- Create: `python/src/shreks_brain/shadow/store.py`
- Modify: `python/src/shreks_brain/shadow/__init__.py`
- Create: `python/tests/test_shadow_store.py`

**Interfaces:**
- Produces:

```python
class ShadowEvidenceStore:
    def __init__(self, path: str | Path) -> None: ...
    def load(self) -> ShadowEvidenceLedger: ...
    def append(self, record: ShadowDecisionRecord) -> ShadowEvidenceLedger: ...
```

- [ ] **Step 1: Write store tests first**

Lock:

- missing file -> empty valid ledger without creating a file;
- append persists and restart-load returns exact ledger;
- parent directory creation;
- canonical JSON uses sorted keys, compact separators, UTF-8, trailing newline;
- sibling `.tmp` is absent after successful atomic replace;
- identical record append is byte-for-byte idempotent;
- decision identity is `(candidate_version, candidate_mint, as_of_unix_ms, shadow_policy_version)`;
- same identity with different material content fails closed;
- canonical order is `(as_of_unix_ms, candidate_version, candidate_mint, shadow_policy_version, record_fingerprint_sha256)`;
- persisted record fingerprint is independently recomputed on load;
- ledger fingerprint is independently recomputed on load;
- invalid JSON, unknown fields/schema/enum, tampered material, and tampered top-level fingerprint fail closed;
- no delete, rewrite-history, promotion, execution, or live API exists.

- [ ] **Step 2: Run exact PR CI and require RED only for missing store**

Expected new failure: import/attribute error for `ShadowEvidenceStore`; existing engine/model tests stay green.

- [ ] **Step 3: Implement canonical codec/store**

The persisted document shape is exactly:

```json
{
  "schema_version": "e7-shadow-v1",
  "records": [],
  "ledger_fingerprint_sha256": "..."
}
```

Each record includes exactly the dataclass fields from Task 1. Decode using exact-field-set validation; reconstruct enums explicitly; reject booleans where numeric values are expected; reject non-finite floats; recompute each record fingerprint, then ledger invariants/fingerprint.

Use:

```python
with temporary.open("w", encoding="utf-8", newline="\n") as handle:
    handle.write(canonical_payload + "\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, self.path)
```

On write error, best-effort remove the temporary sibling and re-raise.

- [ ] **Step 4: Run full CI and require GREEN**

Record exact evidence.

---

### Task 4: Audit, documentation, and immutable E7 seal

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-phase-e7-shadow-challenger.md`
- Optionally modify on E7 branch only: `SHREKS_BUILD_ORDER.md` current-position block if a precise full-file replacement can be made without unrelated edits.
- Optionally append: `README.md` only if the change can be verified additions-only and remains concise.

- [ ] **Step 1: Cumulative scope audit**

Compare sealed E6 `5933416fa7136ee7594f89baf97da469bedac171` to E7 behavior head. Allowed files are E7 design/plan, `python/src/shreks_brain/shadow/`, E7 shadow tests, and narrowly scoped status docs. No changes to E3 inference, E6 registry, existing safety/setup/decision/risk/paper execution, Rust observer/executor, or live paths.

- [ ] **Step 2: Replace this implementation plan with a verification record**

Include all RED/GREEN SHAs and CI run IDs, any test-fixture corrections transparently, final behavior Python count/runtime, scope audit, and the explicit statement that E7 shadow evidence is not a profitability or promotion decision.

- [ ] **Step 3: Audit behavior head -> seal candidate**

Require docs-only changes. No production/test behavior may move after the behavior head is declared green.

- [ ] **Step 4: Run final exact-head CI**

Require Python, Rust/workspace, and repository safety GREEN on the exact seal candidate SHA.

- [ ] **Step 5: Update PR #31 body with final immutable evidence and freeze E7**

Confirm PR #31 base remains `feat/phase-e6-champion-challenger-registry`, base SHA remains the sealed E6 head, and PR head equals the final E7 seal SHA. Do not commit after the seal.

E8 may branch only from that exact immutable E7 seal.
