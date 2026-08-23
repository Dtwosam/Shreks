# Phase B7 Deterministic Score Implementation Plan

**Goal:** Add a pure, versioned, explainable deterministic candidate scorer that combines current safety, money-flow, setup-quality, and liquidity/executability evidence without fabricating wallet intelligence or creating trade authority.

**Architecture:** `shreks_brain.scoring` sits beside unchanged B2, setup, and regime packages. It consumes one `FeatureVector`, one current setup assessment, one `RegimeAssessment`, and one explicit `ScorePolicy`, then returns an immutable `ScoreAssessment`.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b7-deterministic-score-design.md`

**Base:** verified B6 head `23edc450431ede1b9d83bacef89b9e46f1c61fe0`.

## Preserved constraints

- B2 remains exactly `b2-v1`.
- Score-v1 has exactly four candidate families: safety quality, money flow, setup quality, liquidity/executability.
- B6 regime is audit context and is not a weighted score family.
- Wallet quality is absent rather than zero-filled or fabricated before Phase D evidence exists.
- B1 safety decision and setup state remain independent from the score.
- Non-PASS/non-READY candidates may receive research scores but cannot be reclassified by B7.
- Missing positive-weight family evidence makes `total_score=None`; weights are never silently renormalized.
- All weights, penalties, and normalization ranges live in an explicit versioned `ScorePolicy`; no production policy instance exists.
- No SQLite/provider/wall-clock/outcome/PnL reads exist in scoring code.
- No entry threshold, `TradeDecision`, `TradeIntent`, sizing, risk, paper fill, wallet/signing, transaction submission, or live execution is introduced.

## Task 1 — Immutable scoring domain and policy — COMPLETE

Files:

- `python/src/shreks_brain/scoring/models.py`
- `python/tests/test_scoring_models.py`

Implemented and pinned:

- stable `ScoreReasonCode` ordering;
- frozen `ScoreFinding`, `ScorePolicy`, and `ScoreAssessment`;
- explicit four-family weight validation with sum-to-one tolerance `1e-12`;
- explicit soft-safety penalties and normalization ranges;
- zero-weight family ablation support;
- score bounds and enum/type validation;
- no wallet, probability, expected-return, decision, risk, execution, or future-outcome authority fields.

### Point-in-time contract correction

The initial pre-implementation plan text said `ScoreAssessment` should reject a source timestamp later than `as_of_unix_ms`. That contradicted the approved evaluator design: the scoring engine must be able to **preserve and audit** a contradictory future source timestamp so it can return `total_score=None` with `FEATURE_SOURCE_AFTER_AS_OF`.

The RED contract was corrected **before production model code**. `ScoreAssessment` therefore permits a non-negative future source timestamp as audit metadata; `score_candidate()` fails it closed deterministically. This is consistent with the B6 pattern of preserving contradictory evidence for evaluator-level reason codes rather than making it unrepresentable.

Verification:

- initial Task 1 RED: `43db41e14fa13e4bd1501fa643c743f87a556bde` / CI `32668016729` — Python failed because `shreks_brain.scoring` did not exist;
- corrected RED contract: `adc6bf71584cee3e9fb649b030c749ab8a05da64`;
- Task 1 GREEN: `d909a769988567184d8b99f04895eec227ed0869` / CI `32668115438` — Rust, Python, workspace metadata, and repository safety all green.

## Task 2 — Pure deterministic scoring engine — COMPLETE

Files:

- `python/src/shreks_brain/scoring/engine.py`
- `python/tests/test_scoring_engine.py`

Implemented and pinned:

- schema/timestamp/source-age/setup/regime compatibility gates;
- clamped piecewise-linear upward normalizers;
- inverse exit-impact normalization;
- safety quality from exactly the four existing B2 soft-safety booleans, without double-counting `safety_soft_finding_count`;
- money-flow family from volume velocity, five-minute buy fraction, and buy-pressure acceleration;
- setup confirmation-score pass-through for Fresh Launch, Graduation/Breakout, and First Pullback;
- liquidity/executability family from liquidity and exit price impact;
- missing evidence remains missing and never becomes zero;
- a missing positive-weight family blocks only the total, with no hidden renormalization;
- deliberately zero-weight missing families do not block the total;
- B1 `REJECT/INCOMPLETE` and setup `BLOCKED/WATCH` may still receive research scores while their original states are preserved;
- B6 regime is stored but does not change any score-v1 family or total;
- deterministic finding order and deterministic repeated outputs.

Canonical explicit test-policy arithmetic remains:

```text
safety quality                100.0 * 0.20
money flow                     50.0 * 0.30
setup quality                   80.0 * 0.30
liquidity / executability       50.0 * 0.20
------------------------------------------------
total score                     69.0
```

Verification:

- Task 2 RED: `26cd4f57a670909f4b772254ad075994d9a61b8a` / CI `32668200903` — Python failed only because `shreks_brain.scoring.engine` did not exist;
- Task 2 GREEN: `d5d3ac68246298e8573f0e0b19c29e5bab50fee4` / CI `32668271112` — Rust, Python, workspace metadata, and repository safety all green.

## Task 3 — Stable API, documentation, and seal — IMPLEMENTED

Files:

- `python/src/shreks_brain/scoring/__init__.py`
- `python/tests/test_scoring_public_api.py`
- `README.md`
- this verification record

Stable package API:

```python
ScoreAssessment
ScoreFinding
ScorePolicy
ScoreReasonCode
score_candidate
```

Regression coverage proves existing safety, feature, setup, and regime entry points remain importable and that `ScoreAssessment` has no wallet-quality, decision, risk, execution, outcome, or PnL authority.

Verification so far:

- Task 3 RED: `f2bc43ec29891a751e1bd90a1fa758c6071128a6` / CI `32668374906` — Python failed only because package-level scoring exports were absent;
- Task 3 package GREEN: `312ea40da69dfadacfb18c6944f89264a5c43b81` / CI `32668407786` — Rust, Python, workspace metadata, and repository safety all green;
- README scoring semantics: `61aace8f87a37293127e88a75d8a9a188f741e56`.

## Final-seal rule

This file intentionally does **not** name its own final branch SHA. After this last tracked-file commit, the branch must receive one fresh exact-head full CI run. The actual immutable final SHA/run belongs only in draft PR #10 metadata so recording verification cannot mutate the verified tree.

The final diff audit must show only the intended B7 files:

1. `README.md`
2. `docs/superpowers/specs/2026-08-23-phase-b7-deterministic-score-design.md`
3. `docs/superpowers/plans/2026-08-23-phase-b7-deterministic-score.md`
4. `python/src/shreks_brain/scoring/models.py`
5. `python/src/shreks_brain/scoring/engine.py`
6. `python/src/shreks_brain/scoring/__init__.py`
7. `python/tests/test_scoring_models.py`
8. `python/tests/test_scoring_engine.py`
9. `python/tests/test_scoring_public_api.py`

No B2, setup, regime, Rust, storage, provider, wallet, decision, risk, paper, or execution file is permitted in the final B7 diff.