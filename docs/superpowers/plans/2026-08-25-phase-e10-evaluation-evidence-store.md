# Phase E10 Trading Evaluation Evidence Store Implementation Plan

**Goal:** Make the exact E5 source evidence required by E8 promotion restart-safe without duplicating derived E5 report state.

**Base:** sealed E9 `7bf83204f87b210d0f784911413d4870471ed740`

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e10-evaluation-evidence-store-design.md`

## Global constraints

- Store schema exactly `e10-evaluation-evidence-v1`.
- Do not change sealed E5 arithmetic, canonical ordering, calibration, segmentation, or fingerprint semantics.
- Persist only candidate version, E5 policy, raw evaluated trades, raw probability observations, and the existing E5 evaluation fingerprint.
- Reconstruct `TradingEvaluationReport` on every load by calling sealed `evaluate_trading_performance(...)`.
- Require recomputed E5 fingerprint to equal the persisted fingerprint.
- Physical JSON: sorted keys, compact separators, UTF-8, `ensure_ascii=False`, `allow_nan=False`, exactly one trailing newline.
- Writes: fsync + atomic replace + best-effort `.tmp` cleanup.
- Store is append-only; same identity/content is idempotent; conflicting content fails closed.
- Add no registry mutation, promotion, trade creation, signing/submission, or live authority.

---

## Task 1 — immutable evidence bundle + exact source codec

**Create:**
- `python/src/shreks_brain/evaluation/evidence.py`
- `python/src/shreks_brain/evaluation/codec.py`
- `python/tests/test_trading_evaluation_evidence_codec.py`

### RED

Write tests first for:

- exact `TradingEvaluationEvidence` bundle fields/types;
- source evidence round-trip;
- canonical trade order and observation order;
- report reconstruction equality with direct E5 evaluation;
- stale/tampered stored fingerprint rejection;
- source tampering rejection;
- exact top-level/evaluation/policy/trade/observation field sets;
- wrong schema and invalid SHA rejection;
- non-finite values rejected;
- candidate-version mismatches rejected;
- duplicate trade position ids and duplicate observation `(mint, as_of)` identities rejected;
- reordered persisted evidence rejected as non-canonical.

Run exact PR CI. Expected Python failure: `shreks_brain.evaluation.codec` / evidence contract absent. Rust/workspace and repository safety remain GREEN.

### GREEN

Implement:

```text
EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION = "e10-evaluation-evidence-v1"
TradingEvaluationEvidence
canonical_json(...)
build_evidence_document(...)
decode_evidence_document(...)
```

Codec explicitly maps every E5 policy/trade/observation field. Decode reconstructs exact E5 dataclasses and calls public sealed `evaluate_trading_performance(...)`; it never decodes a report from disk.

Persist source arrays only in sealed E5 canonical order. Reject non-canonical persisted ordering.

Commit implementation and require full Python suite GREEN.

---

## Task 2 — restart-safe append-only store

**Create:**
- `python/src/shreks_brain/evaluation/store.py`
- `python/tests/test_trading_evaluation_evidence_store.py`

### RED

Cover:

- missing file -> empty tuple;
- `get(...)` missing -> `None`;
- append -> fresh store instance -> exact source evidence + reconstructed report;
- same source evidence is idempotent;
- multiple different fingerprints for one candidate append in order;
- same candidate/fingerprint with conflicting source content fails closed;
- canonical file + single newline;
- malformed/tampered persisted file fails closed;
- invalid lookup args fail closed;
- atomic replace failure cleans `.tmp` and preserves prior file.

Expected RED: missing `shreks_brain.evaluation.store` only.

### GREEN

Implement public store API only:

```text
load()
get(candidate_version, evaluation_fingerprint_sha256)
append(candidate_version, trades, probability_observations, policy)
```

`append` derives the report via sealed E5 first, canonicalizes source arrays, then appends an immutable evidence bundle. Callers cannot inject a report or fingerprint.

Require full Python suite GREEN.

---

## Task 3 — package public API, authority firewall, scope audit, seal

**Modify:**
- `python/src/shreks_brain/evaluation/__init__.py`
- `python/tests/test_trading_evaluation_public_api.py`

**Create:**
- `python/tests/test_trading_evaluation_evidence_public_api.py`

### RED

Require additive public exports:

```text
EVALUATION_EVIDENCE_STORE_SCHEMA_VERSION
TradingEvaluationEvidence
TradingEvaluationEvidenceStore
```

Require exact public store method surface `{append, get, load}` and no delete/rewrite/update/registry/promotion/trade/sign/submit/live methods.

Expected RED: new package exports absent.

### GREEN

Add exports without removing or reordering sealed E5 symbols except for explicit additive E10 entries.

Run full Python suite and exact PR CI; require Python, Rust/workspace, and repository safety GREEN. Record behavior head SHA, CI id, Python count/runtime, and every TDD correction.

### Scope audit

Compare sealed E9 to E10 behavior head. Allowed changes only:

- E10 design/plan docs;
- `evaluation/evidence.py`;
- `evaluation/codec.py`;
- `evaluation/store.py`;
- additive `evaluation/__init__.py` exports;
- E10 evidence tests;
- additive extension of the exact E5 public-API expectation.

No changes to E5 engine/models/calibration logic, E6 registry, E7 shadow, E8 promotion, E9 learning, paper/risk, Rust execution, provider, observer, or live paths.

### Immutable seal

Replace this plan with the verification record. Behavior head -> seal candidate must change exactly this one documentation file and zero production/test files. Run final exact-head CI and require all lanes GREEN. Update stacked draft PR and leave it unmerged/frozen.