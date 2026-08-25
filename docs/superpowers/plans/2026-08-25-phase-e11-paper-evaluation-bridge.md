# Phase E11 — Paper Evaluation Bridge Verification Record

## Seal identity

- Sealed base: Phase E10 head `f31d34382170b3fac8d5073299c8ef2e7e81b8ca`.
- Behavior head: `32c0f7f843e405819e36560f0e6d1c7a3bcab28f`.
- Schema: `e11-paper-evaluation-v1`.
- Stacked branch: `feat/phase-e11-paper-evaluation-bridge`.
- Draft PR: #35.

E11 preserves the paper evidence required to reconstruct fully reconciled closed paper positions as sealed E5 `EvaluatedTrade` values after restart. It does not infer missing setup/regime provenance, fills, reference prices, execution costs, candidate identity, or paper-run identity. A positive execution cost that cannot be attributed to a position is retained as orphan-cost evidence and blocks candidate/run normalization rather than being silently discarded.

## Verified behavior

### Immutable evidence contracts

E11 adds frozen/slotted evidence contracts for selected-entry provenance, position-linked terminal execution evidence, closed-position accounting snapshots, orphan execution costs, per-cycle captures, and the cumulative restart ledger.

The contracts enforce exact enum types, lower-case SHA-256 digests, finite numeric values, paired fill fields, terminal execution coherence, canonical tuple ordering, unique identities, candidate/strategy attribution, and exact schema versioning.

TDD evidence:

- RED `8a9cc6f682235aa7a3f516900362e9e6eddd0fe6`, CI `32838526502`: Python failed only because `shreks_brain.paper_evaluation` did not exist; Rust/workspace and repository safety remained GREEN.
- First implementation `af01de80f8c6e9a460f88d85104a2fb56c45f460`, CI `32838659353`: one model test exposed that a raw string can compare equal to a Python `StrEnum` member, allowing `"FILLED"` through a membership check.
- Correction `93bd1f60c71a71db8874684b1dba35e7c7c89f08`, CI `32838811305`: switched the affected gate to exact enum typing. Python `1992 passed in 5.84s`; Rust/workspace GREEN; repository safety GREEN.

### C5/C3 paper evidence extraction

`extract_paper_evaluation_evidence` consumes the actual C5 cycle result and C3 applied ledger update. Economic evidence is emitted only from terminal journal entries that C3 actually applied.

It reconciles journal key, mint, side, execution state, paper policy, strategy, reason code, costs, filled notional, and filled quantity against the execution result. Selected entries preserve original setup/regime and policy provenance. Pending terminal entries may add position execution evidence later without fabricating missing decision provenance. `POSITION_CLOSED` captures the exact final C3 closed-position state.

A failed submission with a booked fee and no position becomes `PaperOrphanCostEvidence`; it is not omitted from the evidence set.

TDD evidence:

- RED `1ae3b55c7ac31d86d8e564c865ee8b27855419a8`, CI `32839209927`: Python failed only because `paper_evaluation.engine` was absent; Rust/workspace and repository safety GREEN.
- GREEN `09c7ab7ae33140293b297563e113fdc700041dfc`, CI `32840026228`: Python `1998 passed in 6.81s`; Rust/workspace GREEN; repository safety GREEN.

### E5 trade normalization

`build_evaluated_trades` emits only complete, reconciled closed trades. Open/incomplete positions are ignored until closure evidence exists; contradictory evidence fails closed.

Economics are fixed as:

```text
entry_notional_usd = sum(successful BUY filled_notional_usd)
turnover_usd = sum(successful BUY/SELL filled_notional_usd)
execution_friction_usd = sum(max(0, signed_slippage_usd))
explicit_cost_usd = sum(all linked booked execution explicit_cost_usd)
net_pnl_usd = authoritative C3 closure.realized_pnl_usd
gross_pnl_usd = net_pnl_usd + execution_friction_usd + explicit_cost_usd
```

Favorable slippage cannot become a negative friction credit. Failed position-linked execution fees remain in explicit costs. Entry provenance must match the opening BUY intent. Journal sequences, fill counts, closure costs, close identity, mint, candidate fingerprint, strategy, and closing sequence must reconcile. Any positive orphan cost for the requested run/candidate blocks normalization.

The sealed E5 `EvaluatedTrade` constructor remains the final arithmetic invariant gate.

TDD evidence:

- RED `324364126b939dea3f734047df3b189ff3bca9b0`, CI `32840262625`: Python failed only because `build_evaluated_trades` was missing.
- GREEN `0554dd5c2469d42a49769e52fc0f5e02912f0688`, CI `32840548054`: Python `2017 passed in 7.05s`; Rust/workspace GREEN; repository safety GREEN.

### Canonical restart codec

The evidence document uses exact top-level and nested key sets, enum `.value` strings, compact/sorted canonical JSON, and exactly one trailing physical newline.

`document_fingerprint_sha256` is the SHA-256 of canonical document content with that field replaced by 64 zeroes. Decode reconstructs the exact typed ledger first and independently recomputes the digest before accepting persisted state. Unknown/missing fields, malformed enums or SHA values, non-finite numbers, non-canonical order, duplicate identities, and stale fingerprints fail closed.

TDD evidence:

- RED `4a0e1fa39ddef92e8979495ebf5ddba77de981b1`, CI `32840705620`: Python failed only because `paper_evaluation.codec` was missing.
- Initial implementation `5b6ac1c51e49ef53f780d4afad86945633254b56`, CI `32840863164`: production correctly rejected duplicate identity; one test was over-specific about the error-message word (`"duplicate"` versus the model's `"identities must be unique"`). Result: `2028 passed, 1 failed`.
- Test-only assertion correction `d765b84ca3466121e35a6253c3d86dff22a18eab`, CI `32841014951`: Python `2029 passed in 6.45s`; Rust/workspace GREEN; repository safety GREEN.

### Append-only restart-safe evidence store

`PaperEvaluationEvidenceStore` exposes only `load`, `record_capture`, `record_cycle`, and `evaluated_trades`.

A missing file returns a valid empty sealed ledger without creating a file. Existing state is strict-decoded and fingerprint-verified. New captures are unioned by immutable identity. Exact repeats are byte-for-byte idempotent and do not rewrite the file; an existing identity with different content fails closed. A paper-run ID cannot silently change candidate version, candidate fingerprint, or strategy across cycles.

Writes use a sibling `.tmp`, flush, `os.fsync`, and `os.replace`, with best-effort temporary cleanup on write failure. `evaluated_trades` reloads persisted evidence before reconstructing E5 trades, proving restart recovery instead of relying on process memory.

TDD evidence:

- RED `c570dcdf674f36f80dcf19b0b45896b97d42d884`, CI `32841189507`: Python failed only because `paper_evaluation.store` was missing; repository safety GREEN.
- GREEN `6702ded60e75c14c7bf97b028aa6157f2eea9f3a`, CI `32841296902`: Python `2038 passed in 7.13s`; Rust/workspace GREEN; repository safety GREEN.

### Public API and authority firewall

The public package API is exactly:

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

The package surface exposes no registry store/status mutation, promotion evaluator/store, trade intent, runtime LIVE switch, signing, or submission capability. A fresh-process import check proves importing `shreks_brain.paper_evaluation` does not eagerly import `sklearn` or `pyarrow`.

TDD evidence:

- RED `75d75b8f63c855080247d72d9c9d8f502f24146d`, CI `32841539888`: `3 failed, 2039 passed`; all failures were exactly missing `__all__` / public E11 exports.
- GREEN behavior head `32c0f7f843e405819e36560f0e6d1c7a3bcab28f`, CI `32841620850`: Python `2042 passed in 7.60s`; Rust/workspace GREEN; repository safety GREEN.

## Cumulative E10 -> E11 scope audit

Exact compare: base `f31d34382170b3fac8d5073299c8ef2e7e81b8ca` -> behavior head `32c0f7f843e405819e36560f0e6d1c7a3bcab28f`.

Result: ahead by 16 commits, behind by 0. The only changed files are:

- `docs/superpowers/specs/2026-08-25-phase-e11-paper-evaluation-bridge-design.md`
- `docs/superpowers/plans/2026-08-25-phase-e11-paper-evaluation-bridge.md`
- `python/src/shreks_brain/paper_evaluation/__init__.py`
- `python/src/shreks_brain/paper_evaluation/codec.py`
- `python/src/shreks_brain/paper_evaluation/engine.py`
- `python/src/shreks_brain/paper_evaluation/models.py`
- `python/src/shreks_brain/paper_evaluation/store.py`
- `python/tests/test_paper_evaluation_codec.py`
- `python/tests/test_paper_evaluation_engine.py`
- `python/tests/test_paper_evaluation_models.py`
- `python/tests/test_paper_evaluation_normalization.py`
- `python/tests/test_paper_evaluation_public_api.py`
- `python/tests/test_paper_evaluation_store.py`

No sealed C1 paper execution, C3 paper accounting, C5 loop, C6 runtime, E5 evaluation math, E6 registry, E7 shadow, E8 promotion, E9/E10 evidence infrastructure, Rust execution, provider, risk, signing, submission, or LIVE path changed.

## Authority boundary

E11 is evidence infrastructure only. It cannot mutate champion/challenger state, promote a candidate, create or submit an order, sign a transaction, enable LIVE mode, or move capital. Persisted paper evidence remains observational input to later evaluation/promotion decisions.

## Profitability boundary

E11 closes an evidence-integrity gap; it does **not** prove the current strategy has positive expectancy. A technically valid E11 ledger or `EvaluatedTrade` sequence is not evidence by itself that live-money gates have passed. Phase F remains disabled until the source-of-truth profitability, sample-size, drawdown, cost realism, execution, restart, provider-health, risk-halt, and paper/live-parity criteria are actually satisfied.

## Seal procedure

Behavior is frozen at `32c0f7f843e405819e36560f0e6d1c7a3bcab28f`.

This verification-record update is the only allowed post-behavior change. The behavior-head -> seal-candidate compare must therefore be exactly one commit and this one documentation file. The final exact-head CI run is recorded in PR #35 after it completes; embedding that future CI identity in this same commit would itself create a new head and invalidate the exact-head seal.
