# Phase D6 Research Dataset Export Verification Record

**Base:** sealed D5 head `d5242675b9969ee0f5e04c3e153995bf630bfa4c`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-d6-research-dataset-export-design.md`, introduced by commit `f3636b6e15d405fe9c8feb91e7a89360c919b570`.

**Implementation plan:** introduced by commit `5f3d2ebbab3828163371b9593eb73ca146d1fcce`.

## Implemented scope

D6 adds a pure Python research-export boundary under `shreks_brain.research` with schema `d6-research-v1`.

The exporter:

- accepts immutable caller-supplied B2 market features, D5 wallet features, regime, score, decision, and future-label evidence,
- requires one coherent point-in-time candidate snapshot before a row can exist,
- preserves `REJECT`, `WATCH`, and `ENTER` candidate decisions rather than filtering rejected opportunities,
- emits one logical row per `(candidate_mint, as_of_unix_ms)`,
- exposes exactly 93 decision-time feature/provenance columns and 98 `label_*` columns,
- keeps all seven future horizons at 60, 300, 900, 1800, 3600, 14400, and 86400 seconds,
- preserves pending labels as null future metrics rather than fabricated zeros,
- serializes D5 wallet-strength audit evidence as canonical JSON,
- sorts rows deterministically by `(as_of_unix_ms, candidate_mint)`,
- computes a logical SHA-256 fingerprint over canonical rows with exact finite-float encoding,
- writes explicit-schema Parquet with Zstandard compression and dataset metadata through a lazy PyArrow adapter.

`pyarrow==25.0.*` is isolated behind the `research` extra and the development extra. Importing `shreks_brain.research`, building logical rows, validating chronology, and computing logical dataset identity do not eagerly import PyArrow.

D6 performs no SQLite read, provider/RPC call, historical replay, setup recomputation, model training, strategy promotion, execution, signing, or live-money action.

## TDD evidence

### Initial RED

The initial public model/API RED contract was committed as `0fa0fec99f11eb98c3b31d976e09aa7a7687ccb6`.

CI `32751835546` behaved exactly as intended:

- repository safety: GREEN,
- Python: RED during collection only because `shreks_brain.research` did not yet exist,
- failures were limited to the two new D6 import/collection paths.

### Initial GREEN

Commit `1dfb55a842b004a380c3ad2d866ecabd1ee7a833` implemented immutable outcome-label/manifest validation and the D6 public surface while leaving dataset/Parquet behavior intentionally unimplemented until its own RED existed.

CI `32752076867` was GREEN across repository safety, Python, Rust tests, and workspace metadata validation.

### Behavioral RED

The complete dataset/Parquet behavior contract was committed as `2cf37e79b8d9fde40a060df76510e9e3a65b136d`.

CI `32752706033` produced exactly the intended D6 behavioral RED:

- `33 failed, 1635 passed`,
- snapshot-reconciliation tests failed because those invariants were not implemented yet,
- fixed column-contract tests failed because feature/label tuples were still empty,
- row/dataset/Parquet tests failed at the intentional `NotImplementedError` stubs,
- no predecessor failure or malformed test fixture obscured the contract.

### GREEN implementation

Commit `d23c67f473597dee465bead5a990f705dbd7100e` implemented the complete D6 behavior in one atomic production commit:

- `python/src/shreks_brain/research/models.py`,
- `python/src/shreks_brain/research/dataset.py`,
- `python/src/shreks_brain/research/parquet.py`,
- `python/pyproject.toml` optional research dependency wiring.

CI `32754329412` is GREEN across:

- repository safety,
- Python tests: `1668 passed`, including real PyArrow 25.0.1 Parquet round-trip/fingerprint tests,
- Rust tests,
- workspace metadata validation.

No behavior repair commit was required after the atomic GREEN implementation.

## Exact D5 -> D6 implementation diff

Before this documentation seal, the exact changed-file set is:

```text
docs/superpowers/plans/2026-08-24-phase-d6-research-dataset-export.md
docs/superpowers/specs/2026-08-24-phase-d6-research-dataset-export-design.md
python/pyproject.toml
python/src/shreks_brain/research/__init__.py
python/src/shreks_brain/research/dataset.py
python/src/shreks_brain/research/models.py
python/src/shreks_brain/research/parquet.py
python/tests/test_research_dataset.py
python/tests/test_research_models.py
python/tests/test_research_parquet.py
python/tests/test_research_public_api.py
```

No predecessor production file changed. An accidental temporary placeholder ref was immediately reset before the GREEN commit and is absent from the reachable D5 -> D6 diff.

## Point-in-time and leakage properties proven

- B2 market features must use the sealed `b2-v1` schema.
- D5 wallet features must use the sealed `d5-wallet-v1` schema.
- candidate mint must agree across wallet features and decision evidence.
- market, wallet, regime, score, and decision evidence must share the exact `as_of_unix_ms`.
- score source timestamp must equal the B2 market-feature source timestamp.
- score and decision feature-schema versions must agree with B2.
- market, score, and decision safety decisions must agree.
- score and decision must agree on score policy, setup, setup policy, setup state, regime, and total score.
- supplied regime policy and final regime must reconcile with scoring/decision evidence.
- D6 candidate rows accept only pre-entry `REJECT`, `WATCH`, or `ENTER`; lifecycle `HOLD`, `REDUCE`, and `EXIT` belong to later position/performance research.
- every row contains exactly seven labels in canonical horizon order.
- every label baseline must equal the row decision timestamp.
- a discovery-anchored A9 checkpoint cannot be silently relabeled as a later decision-anchored target.
- pending future evidence cannot contain checkpoint/completion timestamps or outcome metrics.
- completed labels require due-or-later checkpoint evidence and monotonic completion chronology.
- non-finite outcome metrics fail closed.
- feature and label column contracts are disjoint; no decision-time feature column begins with `label_`.
- duplicate `(candidate_mint, as_of_unix_ms)` identities fail closed.
- `REJECT`, `WATCH`, and `ENTER` rows are all retained and deterministic input ordering does not change dataset ordering.
- logical dataset identity is path-independent and input-order-independent while changing when a feature or label changes.
- Parquet schema/types are explicit rather than inferred from the first row, nullable values remain nullable, and list-valued audit/reason fields survive round-trip.

## Scope boundaries

D6 is dataset infrastructure, not evidence of profitability. It does not replay historical storage, generate missing historical labels, train or select a model, change B7/B8/B9/C behavior, create a `TradeIntent`, size capital, sign or submit a transaction, or enable live trading.

Phase D now has the wallet/market research representation required by the build-order exit criterion. Phase E must still construct historical replay, baselines, chronological validation, and post-cost evaluation before any new wallet-driven or learned strategy can be considered useful.

## Final seal procedure

This verification record and an additions-only README D6 section are the only tracked documentation changes permitted after the GREEN implementation. After the validated seal commit is attached, no further tracked D6 writes are allowed. Fresh exact-head repository-safety, Python, Rust, and workspace-metadata CI must then pass.

As with the sealed D5 precedent, the eventual final D6 commit SHA and final exact-head CI run are recorded in draft PR metadata rather than back-written into tracked files, avoiding a self-referential seal commit that would invalidate its own recorded SHA.
