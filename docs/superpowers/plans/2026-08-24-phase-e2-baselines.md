# Phase E2 Baselines Verification Record

## Scope

Phase E2 adds deterministic evaluation baselines under `shreks_brain.baselines` without creating a second setup, scoring, or entry-decision engine. Every baseline calls the sealed E1 historical replay path and changes only explicit B8 numeric score thresholds plus derived provenance versions.

E2 is based exactly on sealed E1 head `6c441e13ad7c186d6356e861b45351be7f99d321`.

Design commit: `10f1b25fd4eb67f9112201d2dd6c865e437c38e3`  
Initial implementation-plan commit: `7ad22d4e1508fb42d0a1466918a6d3146cd02639`

## TDD evidence

### Model and public API RED

Commit: `b435979ba63f1d99dfcf41acd12b84f4c8009ec9`  
CI: `32758994871`

Python collection failed only because `shreks_brain.baselines` did not yet exist. Repository safety remained green. No E2 production package existed at this RED.

### Model and public API GREEN

Commit: `ac871d2d9de2e025ffb99841f32651b3aa8a4389`  
CI: `32760543547`

Added the immutable `e2-baselines-v1` model/public contract while leaving `build_baseline_suite` as an intentional behavior stub. Python, Rust/workspace, and repository safety all passed before behavior work began.

### Behavior RED

Commit: `f725591e856aa7ebb5077b6842d27d4396050258`  
CI: `32761006387`

Result: `6 failed, 1712 passed`. Every failure terminated at the intentional E2 `NotImplementedError`; the purity test already passed.

The RED covered:

- exact V0 equivalence to sealed E1;
- zero-score-threshold behavior;
- disabled-rule and explicit-`None` preservation;
- caller-specified signed threshold deltas and `[0, 100]` clamping;
- deterministic lexical variant ordering;
- candidate-population equality across baselines;
- deterministic replay/decision provenance;
- unchanged B7 score-policy provenance;
- direct D6 dataset compatibility;
- future-outcome leakage isolation;
- input/variant-order determinism;
- no SQLite, PyArrow, filesystem, network, random-number, or wall-clock dependency.

### Behavior implementation

Commit: `b42f830ffa9fcd2fb3786a2846f6210be2f463b2`  
CI: `32761098065`

The implementation changed only `python/src/shreks_brain/baselines/engine.py`. It derives immutable replay-policy variants with `dataclasses.replace` and delegates every candidate to E1 `replay_entry_decisions`.

That CI produced `1 failed, 1717 passed`. The single failure was not a production defect: the test incorrectly expected an explicitly disabled B8 setup to return `WATCH`, while sealed B8 correctly returns `REJECT` for `SETUP_DISABLED`. The E2 implementation had preserved predecessor semantics exactly.

### Demonstrated test-only repair and GREEN

Repair commit: `079dce27d9dc77891f8736e46472340667c0414e`  
CI: `32761299056`

The repair changed one test assertion from `WATCH` to sealed B8 `REJECT`; no production file changed.

Fresh verification result: `1718 passed` in Python, with repository safety, Rust tests, and workspace metadata all green.

## Verified baseline semantics

`v0` is the exact E1 replay under the caller-supplied base `ReplayPolicySet`.

`zero_score_threshold` derives a new replay/decision provenance version and maps every numeric HOT/NORMAL/WEAK B8 threshold to `0.0`. Explicit `None` thresholds remain `None`, and setup `enabled` flags are unchanged.

Each `THRESHOLD_DELTA` variant applies one finite non-zero signed score-point delta to numeric HOT/NORMAL/WEAK thresholds only, clamps the result to `[0.0, 100.0]`, preserves explicit `None` values and enabled flags, and is emitted in deterministic lexical order by variant name.

Derived variants reuse the exact base setup-policy objects and B7 `ScorePolicy`. They receive deterministic replay-policy and B8 decision-policy provenance. Future outcome values are never inspected while deriving a policy or replaying a decision; changing later return labels leaves the corresponding setup, score, and decision unchanged while the attached outcome evidence may differ.

Every baseline covers the same ordered `(as_of_unix_ms, candidate_mint)` population and produces snapshots directly accepted by the sealed D6 research-dataset builder.

E2-v1 intentionally includes no pseudo-random baseline. Random comparison is deferred until the chronological evaluation/metrics layer can define a meaningful seeded experiment instead of adding noise without an evaluation contract.

## Pre-seal diff audit

The exact sealed-E1 -> E2 GREEN diff contains only:

- `docs/superpowers/specs/2026-08-24-phase-e2-baselines-design.md`
- `docs/superpowers/plans/2026-08-24-phase-e2-baselines.md`
- `python/src/shreks_brain/baselines/__init__.py`
- `python/src/shreks_brain/baselines/models.py`
- `python/src/shreks_brain/baselines/engine.py`
- `python/tests/test_baseline_models.py`
- `python/tests/test_baseline_public_api.py`
- `python/tests/test_baseline_suite.py`

No E1/predecessor production file, `python/pyproject.toml`, Rust source, migration, or README file changed before the documentation seal.

## Explicit non-goals

E2 computes no return, PnL, expectancy, drawdown, win-rate, transaction-cost, or promotion metric. It adds no chronological split, model training or promotion, risk sizing, `TradeIntent`, paper/live execution, wallet/signing, transaction construction/submission, or live-money authority.

The final documentation-seal SHA and its exact-head CI evidence are recorded in PR metadata so this tracked verification record does not require a post-seal mutation.
