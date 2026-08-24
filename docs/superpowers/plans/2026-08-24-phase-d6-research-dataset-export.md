# Phase D6 Research Dataset Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `d6-research-v1` candidate research dataset contract and optional PyArrow Parquet writer that preserve rejected/observed candidates and keep decision-time features structurally separate from future labels.

**Architecture:** Add a new `shreks_brain.research` package with immutable D6 label/snapshot/manifest models, a pure row/dataset builder, and a lazy PyArrow adapter. The builder consumes only sealed B2/D5/regime/score/decision objects plus decision-anchored outcome labels; it performs no storage/provider/wall-clock reads. Parquet support remains isolated behind the `research` optional dependency.

**Tech Stack:** Python 3.12+, stdlib dataclasses/enum/json/hashlib/pathlib, PyArrow `25.0.*` only in the research adapter, pytest 8.x, existing B2/D5/B6/B7/B8 domain types.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-d6-research-dataset-export-design.md`

## Global Constraints

- Base exactly sealed D5 head `d5242675b9969ee0f5e04c3e153995bf630bfa4c`.
- `FEATURE_SCHEMA_VERSION` remains exactly `"b2-v1"`.
- `WALLET_FEATURE_SCHEMA_VERSION` remains exactly `"d5-wallet-v1"`.
- D6 schema is exactly `RESEARCH_DATASET_SCHEMA_VERSION == "d6-research-v1"`.
- Approved outcome horizons are exactly `(60, 300, 900, 1800, 3600, 14_400, 86_400)` seconds.
- Every future label is anchored to the research decision `as_of_unix_ms`; discovery-anchored A9 labels cannot be silently reused when their actual baseline differs.
- `REJECT`, `WATCH`, and `ENTER` candidate snapshots remain in the dataset; `HOLD`, `REDUCE`, and `EXIT` are rejected from this candidate-outcome contract.
- Unknown feature/label evidence remains `None`; it never becomes zero or false.
- `RESEARCH_FEATURE_COLUMNS` and `RESEARCH_LABEL_COLUMNS` are disjoint and together define the complete versioned physical schema.
- Logical SHA-256 fingerprints are over canonical logical rows, not Parquet bytes.
- Base Python runtime dependencies remain empty; PyArrow lives only in `research`/`dev` extras.
- No SQLite/provider/RPC/wall-clock reads inside D6.
- No replay, model training, setup/scoring/decision/risk change, signer, transaction submission, or live-money authority.
- TDD RED -> exact failure -> GREEN -> frozen exact-head seal.

---

### Task 1: Combined D6 RED public/model contract

**Files:**
- Create: `python/tests/test_research_models.py`
- Create: `python/tests/test_research_public_api.py`

**Interfaces:**
- Consumes: sealed `FeatureVector`, `WalletFeatureVector`, `RegimeAssessment`, `ScoreAssessment`, `TradeDecision` types only as fixture dependencies.
- Produces the executable contract for:
  - `RESEARCH_DATASET_SCHEMA_VERSION`
  - `RESEARCH_OUTCOME_HORIZONS_SECONDS`
  - `ResearchOutcomeLabelStatus`
  - `ResearchExitability`
  - `ResearchOutcomeLabel`
  - `ResearchSnapshotInputs`
  - `ResearchDatasetManifest`

- [ ] **Step 1: Write the exact public API RED test**

Create `python/tests/test_research_public_api.py`:

```python
from shreks_brain import research


def test_research_public_api_is_exact():
    assert research.__all__ == (
        "RESEARCH_DATASET_SCHEMA_VERSION",
        "RESEARCH_OUTCOME_HORIZONS_SECONDS",
        "RESEARCH_FEATURE_COLUMNS",
        "RESEARCH_LABEL_COLUMNS",
        "ResearchOutcomeLabelStatus",
        "ResearchExitability",
        "ResearchOutcomeLabel",
        "ResearchSnapshotInputs",
        "ResearchDatasetManifest",
        "build_research_row",
        "build_research_dataset",
        "write_research_parquet",
    )
    assert research.RESEARCH_DATASET_SCHEMA_VERSION == "d6-research-v1"
    assert research.RESEARCH_OUTCOME_HORIZONS_SECONDS == (
        60,
        300,
        900,
        1800,
        3600,
        14_400,
        86_400,
    )
```

- [ ] **Step 2: Write outcome-label RED tests**

In `python/tests/test_research_models.py`, import the D6 types and pin:

```python
from dataclasses import FrozenInstanceError
import math
import pytest

from shreks_brain.research import (
    RESEARCH_DATASET_SCHEMA_VERSION,
    RESEARCH_OUTCOME_HORIZONS_SECONDS,
    ResearchDatasetManifest,
    ResearchExitability,
    ResearchOutcomeLabel,
    ResearchOutcomeLabelStatus,
)


def pending_label(*, horizon: int = 60, baseline: int = 1_000_000):
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=baseline + horizon * 1_000,
        status=ResearchOutcomeLabelStatus.PENDING,
        checkpoint_observed_at_unix_ms=None,
        completed_at_unix_ms=None,
        return_pct=None,
        mfe_pct=None,
        mae_pct=None,
        liquidity_change_pct=None,
        volume_m5_change_pct=None,
        buys_m5_change=None,
        sells_m5_change=None,
        rug_or_dead_pool=None,
        exitability=None,
    )


def completed_label(*, horizon: int = 60, baseline: int = 1_000_000):
    due = baseline + horizon * 1_000
    return ResearchOutcomeLabel(
        horizon_seconds=horizon,
        baseline_observed_at_unix_ms=baseline,
        due_at_unix_ms=due,
        status=ResearchOutcomeLabelStatus.COMPLETED,
        checkpoint_observed_at_unix_ms=due + 500,
        completed_at_unix_ms=due + 1_000,
        return_pct=12.5,
        mfe_pct=20.0,
        mae_pct=-4.0,
        liquidity_change_pct=5.0,
        volume_m5_change_pct=-10.0,
        buys_m5_change=7,
        sells_m5_change=-3,
        rug_or_dead_pool=False,
        exitability=ResearchExitability.EXITABLE,
    )
```

Require:

1. exact enum values `PENDING / COMPLETED` and `EXITABLE / NOT_EXITABLE`,
2. frozen/slots dataclasses,
3. only the seven horizons are accepted and bool horizon is rejected,
4. due timestamp equals baseline + horizon exactly,
5. pending label forbids every future timestamp/metric,
6. completed label requires checkpoint timestamp, completion timestamp, and return,
7. checkpoint cannot predate due,
8. completion cannot predate checkpoint,
9. non-finite numeric metrics are rejected,
10. integer deltas reject bool,
11. rug flag and exitability use exact types.

Use targeted mutations, for example:

```python
with pytest.raises(ValueError, match="due_at_unix_ms"):
    ResearchOutcomeLabel(
        **{**completed_label().__dict__, "due_at_unix_ms": 123}
    )
```

Because slots dataclasses do not expose `__dict__`, construct mutation dictionaries with `dataclasses.fields()`/`getattr()` in a helper rather than relying on `__dict__`:

```python
from dataclasses import fields


def values_of(value):
    return {field.name: getattr(value, field.name) for field in fields(value)}
```

- [ ] **Step 3: Write manifest RED tests**

Pin:

```python
manifest = ResearchDatasetManifest(
    schema_version=RESEARCH_DATASET_SCHEMA_VERSION,
    row_count=2,
    min_as_of_unix_ms=100,
    max_as_of_unix_ms=200,
    dataset_fingerprint_sha256="a" * 64,
)
```

Require rejection of wrong schema, zero row count, min > max, uppercase/non-hex/wrong-length digest, bool timestamps/counts, and mutation after construction.

- [ ] **Step 4: Run the focused RED contract**

Run in CI/local equivalent:

```bash
python -m pytest \
  python/tests/test_research_models.py \
  python/tests/test_research_public_api.py -q
```

Expected: collection failure only because `shreks_brain.research` does not exist yet. No predecessor test should fail.

- [ ] **Step 5: Commit the RED contract**

Commit only the two new test files:

```bash
git add python/tests/test_research_models.py python/tests/test_research_public_api.py
git commit -m "test: define D6 research dataset contract"
```

---

### Task 2: D6 model layer and snapshot alignment

**Files:**
- Create: `python/src/shreks_brain/research/models.py`
- Create: `python/src/shreks_brain/research/__init__.py`
- Extend: `python/tests/test_research_models.py`

**Interfaces:**
- Consumes exact sealed types:
  - `shreks_brain.features.FeatureVector`
  - `shreks_brain.features.WalletFeatureVector`
  - `shreks_brain.regime.RegimeAssessment`
  - `shreks_brain.scoring.ScoreAssessment`
  - `shreks_brain.decision.TradeDecision`
- Produces the immutable D6 input/label/manifest models and constants used by dataset/parquet tasks.

- [ ] **Step 1: Add snapshot fixture helpers and failing alignment tests**

Build one coherent fixture by using existing predecessor test helper patterns to instantiate B2/D5/B6/B7/B8 immutable values. The final D6 input must have:

```python
ResearchSnapshotInputs(
    candidate_mint="mint-a",
    market_features=market_features,
    wallet_features=wallet_features,
    regime=regime,
    score=score,
    decision=decision,
    outcomes=tuple(
        pending_label(horizon=horizon, baseline=AS_OF)
        for horizon in RESEARCH_OUTCOME_HORIZONS_SECONDS
    ),
)
```

Pin failures for each structural rule independently:

```text
candidate mint mismatch
market/wallet/regime/score/decision as-of mismatch
unsupported market schema
unsupported wallet schema
score source timestamp mismatch
score feature schema mismatch
decision feature schema mismatch
safety decision mismatch
score-policy mismatch
setup-name mismatch
setup-policy mismatch
setup-state mismatch
regime-policy mismatch
market-regime mismatch
total-score mismatch
HOLD/REDUCE/EXIT decision action
outcomes not tuple
missing horizon
duplicate horizon
out-of-order horizons
label baseline != snapshot as-of
```

Also require valid `REJECT`, `WATCH`, and `ENTER` snapshots.

- [ ] **Step 2: Implement exact D6 constants/enums/labels**

In `models.py` define:

```python
RESEARCH_DATASET_SCHEMA_VERSION = "d6-research-v1"
RESEARCH_OUTCOME_HORIZONS_SECONDS = (
    60,
    300,
    900,
    1800,
    3600,
    14_400,
    86_400,
)
```

Implement `ResearchOutcomeLabelStatus`, `ResearchExitability`, `ResearchOutcomeLabel`, `ResearchSnapshotInputs`, and `ResearchDatasetManifest` exactly as the design specifies. Use explicit validation helpers that reject bool where integer/numeric evidence is required.

Do not import PyArrow in this file.

- [ ] **Step 3: Create the package public surface**

Create `research/__init__.py` importing model symbols now and reserving the full final `__all__` order. Dataset/parquet imports may target modules created in subsequent tasks; do not attach this GREEN commit until all imports exist, or temporarily keep the Task-2 focused tests importing `research.models` directly while `research.__init__` remains absent. The preferred branch-safe sequence is to build Task 2-4 production blobs detached and attach them together after syntax validation, avoiding a broken intermediate package import.

- [ ] **Step 4: Run model tests**

Run:

```bash
python -m pytest python/tests/test_research_models.py -q
```

Expected: all model/snapshot tests pass once the package imports are complete.

- [ ] **Step 5: Review fail-closed precedence**

Confirm known contradictions raise `ValueError`; legitimate nullable metrics remain accepted. Specifically prove a mismatched discovery baseline cannot be accepted merely because its horizon/status are otherwise valid.

---

### Task 3: Canonical row schema, flattening, and logical fingerprint

**Files:**
- Create: `python/src/shreks_brain/research/dataset.py`
- Create: `python/tests/test_research_dataset.py`

**Interfaces:**
- Consumes: `ResearchSnapshotInputs`.
- Produces:
  - `RESEARCH_FEATURE_COLUMNS: tuple[str, ...]`
  - `RESEARCH_LABEL_COLUMNS: tuple[str, ...]`
  - `build_research_row(inputs) -> dict[str, object]`
  - `build_research_dataset(snapshots) -> tuple[dict[str, object], ...]`
  - internal manifest/fingerprint helper used by Parquet writer.

- [ ] **Step 1: Write feature/label isolation RED tests**

Require:

```python
assert RESEARCH_FEATURE_COLUMNS
assert RESEARCH_LABEL_COLUMNS
assert not set(RESEARCH_FEATURE_COLUMNS) & set(RESEARCH_LABEL_COLUMNS)
assert all(not name.startswith("label_") for name in RESEARCH_FEATURE_COLUMNS)
assert all(name.startswith("label_") for name in RESEARCH_LABEL_COLUMNS)
```

Build one row and assert:

```python
assert tuple(row) == RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
```

- [ ] **Step 2: Pin exact feature column families**

The explicit feature tuple must contain, in order:

```text
dataset_schema_version
candidate_mint
as_of_unix_ms
market_feature_schema_version
wallet_feature_schema_version
market_source_observed_at_unix_ms
market_source_age_ms
safety_policy_version
wallet_feature_policy_version
wallet_profile_policy_version
wallet_profile_context_version
wallet_relationship_policy_version
regime_policy_version
score_policy_version
decision_policy_version
setup_name
setup_policy_version
market_token_age_seconds
market_price_usd
market_liquidity_usd
market_liquidity_change_5m_pct
market_exit_price_impact_pct
market_volume_m5_usd
market_volume_h1_usd
market_volume_velocity_ratio
market_tx_count_m5
market_tx_count_h1
market_buy_fraction_m5
market_buy_fraction_h1
market_buy_sell_ratio_m5
market_buy_sell_ratio_h1
market_buy_pressure_acceleration
market_return_1m_pct
market_return_5m_pct
market_return_15m_pct
market_momentum_acceleration_1m_vs_5m
market_distance_from_local_high_pct
market_range_position_pct
market_safety_soft_finding_count
market_safety_liquidity_weak
market_safety_holder_concentration_elevated
market_safety_creator_concentration_elevated
market_safety_exit_price_impact_elevated
market_missing_features
wallet_count
wallet_recent_entry_wallet_count
wallet_recent_exit_wallet_count
wallet_strong_wallet_count
wallet_unknown_strength_wallet_count
wallet_strong_entry_wallet_count
wallet_strong_exit_wallet_count
wallet_confidence_weighted_strong_entry_count
wallet_confidence_weighted_strong_exit_count
wallet_entry_quality_profile_sample_count
wallet_confidence_weighted_entry_median_return_pct
wallet_confidence_weighted_entry_win_rate
wallet_independently_strong_entry_wallet_count
wallet_strong_entry_all_pairs_independent_under_evidence
wallet_strong_entry_linked_pair_count
wallet_strong_entry_conflicting_pair_count
wallet_strong_entry_unknown_pair_count
wallet_strong_entry_coordination_cluster_count
wallet_strong_entry_max_independent_group_count_upper_bound
wallet_creator_deployer_action_observation_count
wallet_missing_features
wallet_strength_assessments_json
regime
regime_base
regime_source_observed_at_unix_ms
regime_window_started_at_unix_ms
regime_source_age_ms
regime_window_seconds
regime_candidate_count
regime_candidate_rate_per_hour
regime_executable_fraction
regime_median_liquidity_usd
regime_median_volume_m5_usd
regime_performance_sample_count
regime_performance_net_expectancy_after_costs_pct
regime_performance_applied
regime_reason_codes
safety_decision
setup_state
market_regime
score_safety_quality
score_money_flow
score_setup_quality
score_liquidity_executability
total_score
decision_action
required_score_threshold
score_reason_codes
decision_reason_codes
```

This explicit list is the versioned D6 contract; implementation must not generate it dynamically from dataclass fields.

- [ ] **Step 3: Pin exact label columns**

For each horizon in `RESEARCH_OUTCOME_HORIZONS_SECONDS`, append exactly:

```python
suffixes = (
    "status",
    "baseline_observed_at_unix_ms",
    "due_at_unix_ms",
    "checkpoint_observed_at_unix_ms",
    "completed_at_unix_ms",
    "return_pct",
    "mfe_pct",
    "mae_pct",
    "liquidity_change_pct",
    "volume_m5_change_pct",
    "buys_m5_change",
    "sells_m5_change",
    "rug_or_dead_pool",
    "exitability",
)
```

Expected name: `f"label_{horizon}s_{suffix}"`.

- [ ] **Step 4: Write flattening and uncertainty tests**

Require `build_research_row` to preserve every scalar, enum value, `None`, missing-feature tuple, reason-code tuple, and seven label families. Test both a fully pending row and a mixed completed/pending label row.

Require `wallet_strength_assessments_json` to equal compact canonical JSON. Decode it and prove each D5 audit row retains state, metrics, failed checks, and missing checks.

- [ ] **Step 5: Write dataset ordering/identity tests**

Require:

```text
empty tuple -> ValueError
non-tuple input -> ValueError
non-ResearchSnapshotInputs member -> ValueError
duplicate (mint, as_of) -> ValueError
reversed input order -> same sorted logical dataset
REJECT/WATCH/ENTER all retained
```

- [ ] **Step 6: Write fingerprint tests**

Expose manifest generation internally through the Parquet writer or a private helper tested indirectly. Pin these properties:

```text
same logical rows in different input order -> same SHA-256
change one B2 feature -> different SHA-256
change one D5 feature -> different SHA-256
change one decision action -> different SHA-256
change one future label metric -> different SHA-256
same rows written to different paths -> same manifest fingerprint
```

Float canonicalization must use `float.hex()` recursively before JSON encoding.

- [ ] **Step 7: Implement dataset.py minimally**

Use literal column tuples, deterministic mappings, `json.dumps(..., sort_keys=True, separators=(",", ":"))` for wallet audit JSON, and a recursive canonicalizer for fingerprinting.

No PyArrow imports are allowed in `dataset.py`.

- [ ] **Step 8: Run focused logical dataset tests**

Run:

```bash
python -m pytest \
  python/tests/test_research_models.py \
  python/tests/test_research_dataset.py \
  python/tests/test_research_public_api.py -q
```

Expected: all pass without requiring an import of `pyarrow` from D6 logical modules.

---

### Task 4: Optional PyArrow Parquet adapter

**Files:**
- Create: `python/src/shreks_brain/research/parquet.py`
- Modify: `python/pyproject.toml`
- Create: `python/tests/test_research_parquet.py`
- Complete: `python/src/shreks_brain/research/__init__.py`

**Interfaces:**
- Consumes canonical rows/manifest helpers from `dataset.py`.
- Produces `write_research_parquet(snapshots, path) -> ResearchDatasetManifest`.

- [ ] **Step 1: Add isolated dependency extras**

Change only optional dependencies:

```toml
[project.optional-dependencies]
research = ["pyarrow==25.0.*"]
dev = ["pytest>=8,<9", "pyarrow==25.0.*"]
```

Leave `[project].dependencies = []` unchanged.

- [ ] **Step 2: Write lazy-import boundary test**

Use a subprocess or monkeypatch of `builtins.__import__` to prove importing `shreks_brain.research.models` and `shreks_brain.research.dataset` does not request a module whose name starts with `pyarrow`.

Also test the adapter's missing-dependency error by monkeypatching import inside the writer and requiring a `RuntimeError` message containing `shreks-brain[research]`.

- [ ] **Step 3: Write path/validation ordering tests**

Require:

```text
empty/invalid dataset raises before destination parent is created
non-.parquet suffix raises ValueError
valid nested path creates missing parent directories
```

- [ ] **Step 4: Define one explicit Arrow schema**

In `parquet.py`, build `pa.schema([...])` from the exact D6 columns. Use these physical types:

```text
string -> pa.string()
non-negative timestamps/counts -> pa.int64()
signed count deltas -> pa.int64()
float/percentage/ratio/score -> pa.float64()
bool/nullable bool -> pa.bool_()
missing/reason-code tuples -> pa.list_(pa.string())
wallet_strength_assessments_json -> pa.string()
```

Every nullable logical field is nullable in Arrow. Identity/version/schema fields and required enum/status/baseline/due fields are non-nullable.

- [ ] **Step 5: Write a real round-trip test**

Inside the test function import:

```python
import pyarrow.parquet as pq
```

Write a dataset containing at least:

- one `REJECT` row,
- one `WATCH` row,
- one `ENTER` row,
- pending labels,
- completed labels,
- nullable B2/D5/score/regime values.

Read back with `pq.read_table(path)` and assert:

```python
assert table.num_rows == 3
assert tuple(table.column_names) == RESEARCH_FEATURE_COLUMNS + RESEARCH_LABEL_COLUMNS
```

Verify metadata exactly contains:

```text
shreks_dataset_schema_version=d6-research-v1
shreks_market_feature_schema_version=b2-v1
shreks_wallet_feature_schema_version=d5-wallet-v1
shreks_label_horizons_seconds=60,300,900,1800,3600,14400,86400
shreks_row_count=3
shreks_logical_sha256=<manifest digest>
```

Verify list columns and `None` values survive round trip.

- [ ] **Step 6: Implement writer**

Implementation sequence:

```python
rows = build_research_dataset(snapshots)
manifest = _build_manifest(rows)
path = Path(path)
if path.suffix != ".parquet":
    raise ValueError("path must end with .parquet")
pa, pq = _load_pyarrow()
path.parent.mkdir(parents=True, exist_ok=True)
table = pa.Table.from_pylist(_arrow_rows(rows), schema=_schema(pa, manifest))
pq.write_table(
    table,
    path,
    compression="zstd",
    use_dictionary=False,
    write_statistics=True,
)
return manifest
```

Build/validate rows before creating parent directories. `_load_pyarrow()` catches `ImportError` and raises a stable research-extra message.

- [ ] **Step 7: Complete exact public API**

`research/__init__.py` must expose only the 12 symbols pinned in Task 1 and import no PyArrow module at package import time.

- [ ] **Step 8: Run all D6 focused tests**

Run:

```bash
python -m pytest python/tests/test_research_*.py -q
```

Expected: all D6 tests pass.

---

### Task 5: Full-suite GREEN and compatibility audit

**Files:**
- No new production scope.
- May modify only D6 files/tests for defects demonstrated by concrete failures.

**Interfaces:**
- Verifies D6 did not mutate predecessor behavior.

- [ ] **Step 1: Run full Python suite**

Run:

```bash
python -m pip install -e './python[dev]'
python -m pytest python/tests -q
```

Expected: predecessor 1572 tests plus all D6 tests pass.

- [ ] **Step 2: Run Rust/workspace suite**

Run:

```bash
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: all pass; D6 has no Rust change.

- [ ] **Step 3: Audit D5 -> D6 changed files**

The implementation diff before final seal may contain only:

```text
docs/superpowers/specs/2026-08-24-phase-d6-research-dataset-export-design.md
docs/superpowers/plans/2026-08-24-phase-d6-research-dataset-export.md
python/pyproject.toml
python/src/shreks_brain/research/__init__.py
python/src/shreks_brain/research/models.py
python/src/shreks_brain/research/dataset.py
python/src/shreks_brain/research/parquet.py
python/tests/test_research_models.py
python/tests/test_research_dataset.py
python/tests/test_research_parquet.py
python/tests/test_research_public_api.py
```

No predecessor production file may be changed.

- [ ] **Step 4: Freeze implementation behavior**

Once full exact-head CI is GREEN, no production/test behavior changes are allowed during the seal. Any later failure reopens a new demonstrated repair cycle rather than silently altering the green implementation.

---

### Task 6: Atomic documentation seal

**Files:**
- Modify additions-only: `README.md`
- Replace implementation-plan contents with verification record: `docs/superpowers/plans/2026-08-24-phase-d6-research-dataset-export.md`

**Interfaces:**
- Records exact RED/GREEN/final CI evidence without changing D6 behavior.

- [ ] **Step 1: Prepare README section off-branch**

Append a `## Point-in-time research dataset export` section documenting:

```text
D6 schema d6-research-v1
one row per (candidate_mint, as_of_unix_ms)
REJECT/WATCH/ENTER preservation
decision-anchored future labels
seven approved horizons
feature/label column separation
logical SHA-256 fingerprint
optional PyArrow research extra
no SQLite/replay/model/trading-authority change
```

Do not edit predecessor README lines.

- [ ] **Step 2: Replace plan with verification record off-branch**

Record exact:

```text
sealed D5 base SHA
design/plan SHA
RED contract SHA and RED CI behavior
GREEN implementation SHA and test count
all exact changed files
label-leakage properties proven
final frozen head and exact-head CI
non-goals/live-money boundary
```

- [ ] **Step 3: Build detached seal commit**

Create README and verification-record blobs/tree/commit with the GREEN implementation as parent. Do not move the branch yet.

- [ ] **Step 4: Audit detached seal**

Compare GREEN implementation -> detached seal. Require exactly:

```text
README.md: additions only, deletions == 0
docs/superpowers/plans/2026-08-24-phase-d6-research-dataset-export.md: verification replacement
```

Reject the detached seal if any predecessor README deletion/rewrite or third file appears.

- [ ] **Step 5: Attach seal and run exact-head CI**

Only after the detached diff is exact, fast-forward the D6 branch to the seal commit and require repository safety, Python, Rust/workspace CI all GREEN.

- [ ] **Step 6: Update stacked draft PR metadata only**

D6 PR base is `feat/phase-d5-smart-wallet-features`, head is `feat/phase-d6-research-dataset-export`. Record the final evidence in PR metadata; do not create a tracked-file change after the final CI.

## Plan self-review

- Spec coverage: every design section is mapped to Tasks 1-6, including decision-anchored labels, rejected-candidate retention, column isolation, deterministic fingerprinting, optional dependency isolation, and Parquet metadata/round-trip.
- Placeholder scan: no TBD/TODO/"implement later" steps remain.
- Type consistency: public names/signatures match the D6 design; all seven horizons use one shared constant; the writer consumes the same `ResearchSnapshotInputs` tuple used by the logical builder.
- Scope: D6 ends at export. Historical replay/backtesting/model training remain Phase E work.