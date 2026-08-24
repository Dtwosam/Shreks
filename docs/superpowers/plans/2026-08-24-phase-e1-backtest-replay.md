# Phase E1 Historical Backtest / Replay Implementation Plan

**Base:** sealed D6 head `d7ea5fbcd2eab893b540c940eab8d24ff40a3903`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-e1-backtest-replay-design.md`.

## Goal

Implement the pure `e1-replay-v1` historical setup -> B7 score -> B8 entry-decision replay core with a structural future-label boundary and D6-compatible outputs, without changing predecessor trading behavior.

## Anti-stall execution strategy

Use two TDD gates only:

1. **Model/API gate** — immutable replay inputs/policies/run contract and public exports.
2. **Behavior gate** — preflight, setup dispatch, score/decision reuse, future-label join, determinism, D6 compatibility.

Each RED is committed and observed in CI before its GREEN production code is written. Production changes for each GREEN are attached atomically rather than file-by-file.

Do not add E2/E3/E4/E5 functionality while E1 is open.

---

## Task 1 — Model and public API RED

### Test files

Create only:

```text
python/tests/test_backtest_models.py
python/tests/test_backtest_public_api.py
```

### Required tests

`test_backtest_public_api.py` asserts exact exports:

```text
BACKTEST_REPLAY_SCHEMA_VERSION
ReplaySetupKind
ReplayDecisionInput
ReplayOutcomeBundle
ReplayPolicySet
ReplayRun
replay_entry_decisions
```

`test_backtest_models.py` covers:

- schema string exactly `e1-replay-v1`,
- exact setup-kind values,
- immutable dataclasses,
- valid Fresh Launch / Graduation / First Pullback decision inputs,
- B2/D5 schema rejection,
- wallet candidate/as-of mismatch rejection,
- regime as-of mismatch rejection,
- market source-after-as-of and source-age mismatch rejection,
- setup/context compatibility,
- future local graduation rejection,
- graduation mint mismatch,
- pullback trough newer than market source rejection,
- exact seven-horizon outcome-bundle validation,
- outcome baseline mismatch rejection,
- replay policy-set type/version/compatibility validation,
- at least one setup policy required,
- ReplayRun action-count/order/timestamp reconciliation.

### RED verification

Commit tests only and require Python CI to fail because `shreks_brain.backtest` does not exist. Repository safety should remain green. Do not write production package code before this RED is observed.

---

## Task 2 — Model and public API GREEN

### Production files

Create atomically:

```text
python/src/shreks_brain/backtest/__init__.py
python/src/shreks_brain/backtest/models.py
python/src/shreks_brain/backtest/engine.py
```

`engine.py` may expose `replay_entry_decisions` as an intentional `NotImplementedError` stub at this gate because its behavior has not yet received its own RED.

### Models

Implement exactly the design:

- `BACKTEST_REPLAY_SCHEMA_VERSION = "e1-replay-v1"`,
- `ReplaySetupKind`,
- `ReplayDecisionInput`,
- `ReplayOutcomeBundle`,
- `ReplayPolicySet`,
- `ReplayRun`.

Use exact-type checks where the design requires sealed domain types. Reject bools where integer fields are required. No wall-clock/I/O.

### GREEN verification

Run full CI. Require repository safety, full Python, Rust/workspace all green before the behavior RED is attached.

---

## Task 3 — Replay behavior RED

### Test file

Create only:

```text
python/tests/test_backtest_replay.py
```

### Fixture policy

Use explicit tiny test policies for all three setup families plus B7/B8. Do not introduce production defaults.

Historical decision inputs must use valid sealed B2 and D5 vectors and one valid B6 regime assessment. Outcomes must be separate `ReplayOutcomeBundle` values.

### Required behavior tests

1. `decision_inputs` must be a non-empty tuple of exact replay-input values.
2. `outcome_bundles` must be a tuple of exact replay-bundle values.
3. duplicate decision identities reject the whole run.
4. duplicate outcome identities reject the whole run.
5. missing or extra outcome identities reject before any replay output.
6. an input setup kind with no configured setup policy rejects as run misconfiguration.
7. input order does not affect replay order/output.
8. output sort is `(as_of_unix_ms, candidate_mint)`.
9. Fresh Launch dispatch reuses `assess_fresh_launch` behavior.
10. Graduation dispatch reuses `assess_graduation_breakout` behavior.
11. First Pullback dispatch reuses `assess_first_pullback` behavior.
12. replay uses the supplied B7 `ScorePolicy` and B8 `DecisionPolicy` and preserves their version strings.
13. replay can produce and retain `REJECT`, `WATCH`, and `ENTER` results.
14. wallet features are preserved unchanged in resulting D6 snapshots but do not mutate B7/B8 logic.
15. changing only future outcome metrics cannot change setup-derived score or replayed decision.
16. future outcomes are attached only in resulting D6 `ResearchSnapshotInputs`.
17. replay output snapshots pass `build_research_dataset` unchanged.
18. `ReplayRun` action counts and min/max timestamps reconcile exactly.
19. repeated replay with identical inputs is domain-equal/deterministic.
20. importing/using replay requires no SQLite, provider, filesystem, PyArrow, or current-time dependency.

### RED verification

Commit behavior tests only. CI must fail at the intentional `NotImplementedError` replay stub or otherwise at missing E1 behavior; existing model/API tests and predecessor tests must remain green.

---

## Task 4 — Replay behavior GREEN

### Production file

Replace only:

```text
python/src/shreks_brain/backtest/engine.py
```

unless CI exposes a demonstrated model-contract defect, in which case repair only that exact defect with its failing test preserved.

### Implementation sequence

Inside `replay_entry_decisions`:

1. validate argument containers and exact domain types,
2. reject empty decision inputs,
3. build/validate unique decision identities,
4. build/validate unique outcome identities,
5. require exact identity-set equality,
6. require every used setup kind to have a configured setup policy,
7. sort decision inputs by `(as_of, candidate_mint)`,
8. for each input run only the selected existing setup evaluator,
9. call existing `score_candidate`,
10. call existing `decide_entry`,
11. only after decision exists retrieve the matching future outcome bundle,
12. construct sealed D6 `ResearchSnapshotInputs`,
13. count `REJECT/WATCH/ENTER`,
14. return validated `ReplayRun`.

No copied setup/scoring/decision formulas.

### Future-label isolation implementation rule

Keep the outcome lookup below setup/score/decision computation in code. Do not pass bundle/outcome objects into helper functions that evaluate setup, score, or decision.

### GREEN verification

Require full CI green. If a test fails, patch only the demonstrated issue. Do not broaden scope.

---

## Task 5 — Exact diff and integrity audit

Compare sealed D6 -> E1 GREEN.

Allowed implementation diff only:

```text
docs/superpowers/specs/2026-08-24-phase-e1-backtest-replay-design.md
docs/superpowers/plans/2026-08-24-phase-e1-backtest-replay.md
python/src/shreks_brain/backtest/__init__.py
python/src/shreks_brain/backtest/models.py
python/src/shreks_brain/backtest/engine.py
python/tests/test_backtest_models.py
python/tests/test_backtest_public_api.py
python/tests/test_backtest_replay.py
```

No predecessor production file, D6 schema file, pyproject dependency, Rust file, storage migration, setup/scoring/decision implementation, or README line may change before the documentation seal.

Audit these requirements explicitly:

- decision input type contains no future-label/outcome field,
- exact B2/D5 schema checks remain enforced,
- graduation availability uses local detection time,
- pullback structure cannot be newer than market source,
- exact identity join prevents label drift across candidate/timestamp,
- labels are read only after replayed decision exists,
- D6 snapshot constructor remains final cross-domain reconciliation gate,
- no E5 metric appears in ReplayRun,
- no wallet feature is injected into current score/decision behavior,
- no I/O or wall-clock read exists in backtest package.

---

## Task 6 — Documentation seal

After exact-head GREEN:

1. append an additions-only README section `## Historical decision replay`,
2. replace this plan with an E1 verification record,
3. build a detached seal commit parented to the GREEN implementation,
4. require detached diff to contain exactly README additions-only plus this verification-record replacement,
5. fast-forward the E1 branch to the audited seal,
6. run fresh exact-head repository safety, Python, Rust/workspace CI,
7. write final frozen SHA and exact-head CI only into stacked draft PR metadata; no tracked write after final CI.

## Exit criterion

E1 is sealed only when the frozen exact-head branch can deterministically recompute historical setup -> B7 score -> B8 entry decisions for all three existing setup families, attach future labels afterward through exact identity matching, emit D6-compatible snapshots, and pass full repository CI without changing any predecessor trading behavior.
