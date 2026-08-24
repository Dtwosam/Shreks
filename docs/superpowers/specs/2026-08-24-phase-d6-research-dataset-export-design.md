# Phase D6 Research Dataset Export Design

**Date:** 2026-08-24

## Goal

Create a deterministic, point-in-time-safe Parquet research dataset that joins the already-sealed B2 market features, D5 wallet features, regime/scoring/decision evidence, and future outcome labels without leaking future information into historical decision features or excluding rejected opportunities.

D6 is an export and validation boundary. It does not replay history, recompute trading logic, train a model, change entry eligibility, or grant wallet evidence trading authority.

## Source-of-truth alignment

The Shreks source of truth requires:

- Python-owned research dataset generation,
- Parquet for larger research datasets,
- point-in-time-safe features,
- future outcome labels at 1m, 5m, 15m, 30m, 1h, 4h, and 24h,
- rejected and merely observed candidates to remain in the learning dataset,
- reproducible evaluation with no future-information leakage.

D6 therefore exports one immutable row for each candidate decision snapshot and keeps decision-time evidence structurally separate from future labels.

## Base and scope

D6 bases exactly sealed D5 head `d5242675b9969ee0f5e04c3e153995bf630bfa4c`.

D6 adds a new pure research package under `shreks_brain.research` plus an optional Parquet dependency. It leaves these sealed behaviors unchanged:

- B1 safety,
- B2 `FEATURE_SCHEMA_VERSION == "b2-v1"`,
- B3-B5 setup evaluators,
- B6 regime evaluation,
- B7 scoring,
- B8 decisions,
- B9 risk and `TradeIntent`,
- C1-C6 paper execution/accounting/exit/orchestration,
- D1-D5 wallet observation, reconstruction, profiles, independence, and `d5-wallet-v1`,
- all Rust/storage/provider behavior,
- live-money authority.

No existing production decision path reads a D6 dataset.

## Architecture decision

D6 uses a **pure row-builder plus isolated Parquet writer** rather than a SQLite-direct exporter or full replay engine.

The caller supplies already-built immutable point-in-time domain objects. D6 validates that they describe one coherent historical candidate snapshot, flattens them into a canonical logical row, validates seven decision-anchored labels, sorts rows deterministically, fingerprints the logical dataset, and optionally writes it to Parquet.

This boundary is deliberate:

- storage access does not become hidden research logic,
- D6 can be unit-tested without SQLite or providers,
- Phase E replay can later construct the same D6 inputs from historical storage,
- the export contract remains stable even if the replay/storage implementation changes.

Files:

```text
python/src/shreks_brain/research/__init__.py
python/src/shreks_brain/research/models.py
python/src/shreks_brain/research/dataset.py
python/src/shreks_brain/research/parquet.py
```

## Dependency isolation

The Python base runtime currently has no mandatory third-party dependency. D6 preserves that property.

`python/pyproject.toml` adds:

```toml
[project.optional-dependencies]
research = ["pyarrow==25.0.*"]
dev = ["pytest>=8,<9", "pyarrow==25.0.*"]
```

`pyarrow` is imported only inside the Parquet adapter. Importing `shreks_brain.research`, building rows, validating chronology, and computing logical fingerprints must not require PyArrow.

The `research` extra owns physical Parquet output; the ordinary trading/runtime package remains dependency-free.

## Public API

D6 exposes exactly these public symbols from `shreks_brain.research`:

```text
RESEARCH_DATASET_SCHEMA_VERSION
RESEARCH_OUTCOME_HORIZONS_SECONDS
RESEARCH_FEATURE_COLUMNS
RESEARCH_LABEL_COLUMNS
ResearchOutcomeLabelStatus
ResearchExitability
ResearchOutcomeLabel
ResearchSnapshotInputs
ResearchDatasetManifest
build_research_row
build_research_dataset
write_research_parquet
```

`RESEARCH_DATASET_SCHEMA_VERSION` is exactly `"d6-research-v1"`.

`RESEARCH_OUTCOME_HORIZONS_SECONDS` is exactly:

```python
(60, 300, 900, 1800, 3600, 14_400, 86_400)
```

## Decision-anchored future labels

A9 durable outcome checkpoints are scheduled from candidate discovery. A D6 research snapshot may be taken later than discovery. D6 must therefore never assume that an A9 `5m` label from discovery is a `5m` label from an arbitrary later decision snapshot.

Every D6 label is explicitly anchored to the research row's decision timestamp.

```python
class ResearchOutcomeLabelStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class ResearchExitability(StrEnum):
    EXITABLE = "EXITABLE"
    NOT_EXITABLE = "NOT_EXITABLE"


@dataclass(frozen=True, slots=True)
class ResearchOutcomeLabel:
    horizon_seconds: int
    baseline_observed_at_unix_ms: int
    due_at_unix_ms: int
    status: ResearchOutcomeLabelStatus
    checkpoint_observed_at_unix_ms: int | None
    completed_at_unix_ms: int | None
    return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    liquidity_change_pct: float | None
    volume_m5_change_pct: float | None
    buys_m5_change: int | None
    sells_m5_change: int | None
    rug_or_dead_pool: bool | None
    exitability: ResearchExitability | None
```

Validation:

1. `horizon_seconds` must be one of the seven approved horizons and reject bools.
2. `baseline_observed_at_unix_ms` and `due_at_unix_ms` are non-negative integers.
3. `due_at_unix_ms` must equal `baseline_observed_at_unix_ms + horizon_seconds * 1000` exactly.
4. `PENDING` requires checkpoint/completion timestamps and every metric to be `None`.
5. `COMPLETED` requires `checkpoint_observed_at_unix_ms`, `completed_at_unix_ms`, and `return_pct`.
6. A completed checkpoint observation must be at or after `due_at_unix_ms`.
7. `completed_at_unix_ms` must be at or after `checkpoint_observed_at_unix_ms`.
8. Numeric metrics must be finite when present; integer deltas reject bools.
9. `rug_or_dead_pool` is `bool | None`; exitability is the explicit enum or `None`.

An existing A9 checkpoint may be adapted into D6 only when its actual baseline observation time equals the D6 row `as_of_unix_ms` and its due time matches the decision-anchored horizon. Otherwise later historical replay must derive a decision-anchored label from point-in-time market snapshots. D6 does not relabel discovery-anchored outcomes as decision-anchored outcomes.

## ResearchSnapshotInputs

One input object describes one historical candidate decision snapshot:

```python
@dataclass(frozen=True, slots=True)
class ResearchSnapshotInputs:
    candidate_mint: str
    market_features: FeatureVector
    wallet_features: WalletFeatureVector
    regime: RegimeAssessment
    score: ScoreAssessment
    decision: TradeDecision
    outcomes: tuple[ResearchOutcomeLabel, ...]
```

Structural requirements:

1. `candidate_mint` is non-empty.
2. Inputs use the exact sealed domain types, not duck-typed dictionaries.
3. `market_features.schema_version == "b2-v1"`.
4. `wallet_features.schema_version == "d5-wallet-v1"`.
5. Candidate mint equals both `wallet_features.candidate_mint` and `decision.mint`.
6. Market features, wallet features, regime, score, and decision share the exact same `as_of_unix_ms`.
7. `score.source_observed_at_unix_ms` equals `market_features.source_observed_at_unix_ms`.
8. Score and decision feature-schema versions equal the market feature schema.
9. Score/decision safety decisions agree with market safety decision.
10. Score and decision agree on score policy version, setup name, setup policy version, setup state, market regime, and total score.
11. Score regime-policy version equals the supplied regime policy version.
12. Score and supplied regime agree on the final market regime.
13. D6 candidate snapshots accept only pre-entry decision actions `REJECT`, `WATCH`, or `ENTER`; position lifecycle actions `HOLD`, `REDUCE`, and `EXIT` belong to a later position/performance dataset rather than this candidate-outcome table.
14. `outcomes` contains exactly seven labels, one per approved horizon, in canonical ascending horizon order.
15. Every label `baseline_observed_at_unix_ms` equals the common snapshot `as_of_unix_ms`.

Contradictory inputs fail closed. D6 never silently drops a mismatched domain object.

## One row per candidate decision snapshot

The logical row identity is:

```text
(candidate_mint, as_of_unix_ms)
```

A dataset rejects duplicate identities. Rows sort deterministically by:

```text
(as_of_unix_ms, candidate_mint)
```

`REJECT`, `WATCH`, and `ENTER` rows are all retained. No decision class is filtered by the D6 builder. This preserves rejected/observed opportunities for selection-bias and filter-opportunity-cost research.

## Column families

D6 uses one explicit flat schema. Physical column order is versioned and never inferred from dataclass field order at runtime.

### Identity and provenance

Columns include:

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
```

### B2 market feature family

D6 exports all public scalar B2 `FeatureVector` research fields, including market quality, participation, flow, momentum, structure, safety-soft flags, and the explicit market missing-feature list.

The B2 `missing_features` tuple becomes a list-valued Parquet column named `market_missing_features`.

### D5 wallet feature family

D6 exports all scalar D5 `WalletFeatureVector` summary fields, including wallet counts, confidence-weighted aggregates, independence/coordination summaries, creator/deployer activity, and the explicit wallet missing-feature list.

`strength_assessments` is audit evidence, not a flat model feature family. It is serialized as canonical JSON into:

```text
wallet_strength_assessments_json
```

Canonical JSON uses lexical wallet order already guaranteed by D5, `sort_keys=True`, and compact separators. Unknown values remain JSON `null`; no missing metric becomes zero.

### Regime family

D6 exports the supplied final regime and auditable aggregates:

```text
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
```

### Score and decision family

D6 exports:

```text
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

Reason-code columns contain stable enum values only, not free-form messages.

### Future label family

Every outcome column begins with `label_`.

For each horizon prefix:

```text
label_60s_
label_300s_
label_900s_
label_1800s_
label_3600s_
label_14400s_
label_86400s_
```

export:

```text
status
baseline_observed_at_unix_ms
due_at_unix_ms
checkpoint_observed_at_unix_ms
completed_at_unix_ms
return_pct
mfe_pct
mae_pct
liquidity_change_pct
volume_m5_change_pct
buys_m5_change
sells_m5_change
rug_or_dead_pool
exitability
```

Pending labels remain null except for status/baseline/due provenance.

## Feature/label isolation contract

D6 publishes two exact column-name tuples:

```python
RESEARCH_FEATURE_COLUMNS
RESEARCH_LABEL_COLUMNS
```

Rules:

- `RESEARCH_FEATURE_COLUMNS` contains no string starting with `label_`.
- `RESEARCH_LABEL_COLUMNS` contains only strings starting with `label_`.
- the two sets are disjoint,
- their ordered concatenation is the complete physical dataset schema,
- model-training code in later phases can select decision-time features without hand-maintaining an exclusion list for targets.

Outcome status/due/completion provenance stays in the label family because it was not decision-time evidence.

## Logical row builder

```python
def build_research_row(inputs: ResearchSnapshotInputs) -> dict[str, object]:
    ...
```

The row builder performs no I/O and no wall-clock reads. It only flattens validated immutable domain objects into the exact D6 schema.

Enum values become their stable string values. Tuples of reason/missing codes become immutable tuples in the logical row and list-valued columns when converted to Arrow.

Input ordering inside finding tuples is preserved because upstream engines already produce deterministic ordered findings. Wallet strength rows are emitted in D5's canonical lexical order.

## Dataset builder

```python
def build_research_dataset(
    snapshots: tuple[ResearchSnapshotInputs, ...],
) -> tuple[dict[str, object], ...]:
    ...
```

Requirements:

- input must be a tuple of exact `ResearchSnapshotInputs` values,
- empty datasets are rejected,
- duplicate `(candidate_mint, as_of_unix_ms)` identities are rejected,
- rows sort by `(as_of_unix_ms, candidate_mint)`,
- output is deterministic and independent of input ordering,
- no candidate is filtered by decision action.

## Logical fingerprint

Parquet bytes are not a stable dataset identity because writer versions and encoding choices may change physical bytes without changing the research records.

D6 therefore computes SHA-256 over canonical logical rows.

Canonicalization rules:

- schema column order is fixed,
- rows use deterministic dataset order,
- strings/integers/bools/null remain their JSON equivalents,
- finite floats are encoded by `float.hex()` strings for exact reproducibility,
- tuples/lists preserve order,
- canonical JSON uses UTF-8, `sort_keys=False`, compact separators, and no NaN/Infinity.

The fingerprint covers all feature and label columns and does not include output path, Parquet compression metadata, filesystem timestamps, or Arrow library version.

## ResearchDatasetManifest

```python
@dataclass(frozen=True, slots=True)
class ResearchDatasetManifest:
    schema_version: str
    row_count: int
    min_as_of_unix_ms: int
    max_as_of_unix_ms: int
    dataset_fingerprint_sha256: str
```

The manifest validates schema version, positive row count, ordered timestamp range, and a lowercase 64-character hexadecimal SHA-256 digest.

The manifest contains no output path so identical logical datasets written in different environments retain the same identity.

## Parquet writer

```python
def write_research_parquet(
    snapshots: tuple[ResearchSnapshotInputs, ...],
    path: str | Path,
) -> ResearchDatasetManifest:
    ...
```

Requirements:

1. Validate/build the complete logical dataset before touching the destination file.
2. Path must end with `.parquet`.
3. Create missing parent directories only after logical validation succeeds.
4. Lazy-import `pyarrow` and `pyarrow.parquet`; if unavailable, raise a `RuntimeError` that names the `research` extra.
5. Use one explicit versioned `pyarrow.Schema`; never infer column types from the first row.
6. Use Zstandard compression, dictionary encoding disabled, and statistics enabled.
7. Attach schema metadata containing:
   - `shreks_dataset_schema_version`,
   - `shreks_market_feature_schema_version`,
   - `shreks_wallet_feature_schema_version`,
   - `shreks_label_horizons_seconds`,
   - `shreks_row_count`,
   - `shreks_logical_sha256`.
8. Return the validated logical manifest.
9. Reading the Parquet file back with PyArrow must preserve row count, physical column order, nullable values, list-valued code fields, and metadata.

D6 does not fingerprint physical Parquet bytes.

## Error and missing-data behavior

D6 fails closed on structural contradictions and preserves legitimate uncertainty.

Reject:

- cross-mint feature/decision joins,
- as-of mismatches,
- unsupported B2/D5 schema versions,
- score/decision/regime semantic mismatches,
- non-pre-entry decisions,
- missing/duplicate/out-of-order horizon labels,
- label baseline mismatch,
- malformed pending/completed labels,
- non-finite metrics,
- duplicate dataset identities,
- empty dataset export,
- non-Parquet output path.

Preserve as null/unknown:

- existing nullable B2/D5 features,
- incomplete score components,
- D4 uncertainty surfaced by D5,
- pending future labels,
- optional outcome metrics such as rug/dead and exitability when evidence does not exist.

D6 never converts unknown to zero or false.

## Determinism and reproducibility

The same logical snapshot tuple must produce the same:

- row ordering,
- column ordering,
- canonical wallet audit JSON,
- logical SHA-256 fingerprint,
- manifest values,
- Parquet logical table contents.

Input snapshot order must not change any of those logical results.

Parquet byte-for-byte equality is deliberately not a contract.

## Testing strategy

D6 tests must prove:

1. exact public API and schema/version constants,
2. outcome-label pending/completed invariants,
3. exact seven decision-anchored horizons,
4. discovery-anchored/mismatched baselines are rejected,
5. B2/D5/regime/score/decision timestamp and semantic alignment,
6. REJECT/WATCH/ENTER are retained while HOLD/REDUCE/EXIT are rejected,
7. full scalar feature flattening and null preservation,
8. canonical wallet-strength JSON,
9. stable reason-code and missing-feature columns,
10. feature/label column sets are disjoint and complete,
11. deterministic row sorting and duplicate rejection,
12. fingerprint stability under input reordering,
13. fingerprint sensitivity to any feature or label change,
14. real PyArrow Parquet round-trip with explicit schema and metadata,
15. no PyArrow import is required merely to import/build logical D6 rows,
16. predecessor Python and Rust suites remain green.

## Non-goals

D6 does not:

- read SQLite directly,
- call providers or RPC,
- reconstruct historical snapshots,
- backfill missing labels,
- reinterpret discovery-anchored labels as decision-anchored,
- change B2 or D5 schemas,
- add a Smart Wallet Cluster trading setup,
- modify scoring, decisions, risk, sizing, exits, or paper execution,
- train or tune a model,
- implement backtesting/replay,
- claim profitability,
- create a signer, transaction, or live-money path.

Phase E replay/evaluation can later produce D6 inputs from stored historical state and use the published feature/label separation to test whether wallet evidence improves unseen post-cost results.