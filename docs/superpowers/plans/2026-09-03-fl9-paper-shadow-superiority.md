# FL9 PAPER/Shadow Superiority Proof — Implementation Plan

**Date:** 2026-09-03

Base: SEALED FL9 policy implementation `1731ce4f9cb5943b7b9971b2150db03ae5a9a6c4`.

Design: `docs/superpowers/specs/2026-09-03-fl9-paper-shadow-superiority-design.md`.

## Goal

Build the missing measurement-only path:

```text
FL7 Fast PAPER decisions/executions
        ↓
sealed C1/C3 execution + ledger evidence
        ↓
Fast PAPER → E11 adapter
        ↓
sealed E11 build_evaluated_trades
        ↓
sealed E5 after-cost evaluation
        ↓
FL9 candidate vs required deterministic baselines
        ↓
canonical promotion-free superiority report
```

Fixtures validate the pipeline only. They cannot establish real edge or profitability.

## Task 1 — RED public Fast PAPER evaluation adapter contracts

Create tests first:

`python/tests/test_fast_paper_evaluation_adapter.py`

Lock adapter imports from `shreks_brain.paper_evaluation.fast` while continuing to import sealed `build_evaluated_trades` from `shreks_brain.paper_evaluation`:

- `FAST_PAPER_EVALUATION_ADAPTER_VERSION`
- `FAST_PAPER_SCORE_POLICY_SENTINEL`
- `FastPaperEvaluationIdentity`
- `FastPaperEntryEvaluationContext`
- `FastPaperExecutionEvidenceInput`
- `extract_fast_paper_evaluation_evidence`

RED assertions:

1. exact version/sentinel;
2. identity validates SHA, lexical unique allowed component versions;
3. opening BUY + later SELL created through the existing C1/C3/Fast PAPER adapters normalize into exact E11 evidence;
4. `build_evaluated_trades` consumes the adapter result unchanged;
5. setup name comes from the opening assessment strategy family;
6. market regime comes only from the explicit point-in-time entry context;
7. score policy is the explicit Fast Lane not-applicable sentinel;
8. entry decision policy is the actual opening assessment strategy version;
9. actual component journal strategy version must equal authorizing assessment version;
10. candidate-level E11 strategy attribution remains the explicit evaluation identity;
11. REDUCE/SELL use the exact authorizing assessment;
12. failed booked execution costs are retained;
13. positive orphan cost makes downstream normalization fail closed;
14. duplicate ledger sequences, duplicate contexts, wrong mint/side/action, non-APPLIED updates, and DEFERRED execution are rejected;
15. no future labels or synthetic fill inputs appear in the API.

Expected RED: import/collection errors because the adapter API does not exist.

## Task 2 — Implement the pure Fast PAPER → E11 adapter

Create:

`python/src/shreks_brain/paper_evaluation/fast.py`

Do **not** modify the sealed `python/src/shreks_brain/paper_evaluation/__init__.py` public API. The adapter is additive at `python/src/shreks_brain/paper_evaluation/fast.py` only.

Implementation rules:

- no filesystem/network/database/wall-clock access;
- never call execution engine;
- never derive a quote/fill;
- read only supplied immutable Fast PAPER/C1/C3 evidence;
- mirror the sealed E11 journal/execution reconciliation logic rather than weakening it;
- preserve failed execution and orphan-cost behavior;
- canonical-sort output using the same E11 ordering.

Run targeted tests and full Python suite.

## Task 3 — RED run-evidence + superiority contracts

Create tests before production package:

```text
python/tests/test_fast_policy_run_evidence.py
python/tests/test_fast_policy_superiority.py
python/tests/test_fast_policy_proof_codec.py
python/tests/test_fast_policy_proof_authority.py
```

Lock package imports:

- `FAST_POLICY_PROOF_SCHEMA_NAME`
- `FAST_POLICY_PROOF_SCHEMA_VERSION`
- `FastPolicyRunEvidence`
- `FastPolicySuperiorityPolicy`
- `FastPolicyProofDecision`
- `FastPolicyProofGateStatus`
- `FastPolicyProofGateCode`
- `FastPolicyProofGateResult`
- `FastPolicySuperiorityReport`
- `build_fast_policy_run_evidence`
- `evaluate_fast_policy_superiority`
- `encode_fast_policy_superiority_report`
- `decode_fast_policy_superiority_report`

### Run-evidence RED assertions

1. event-population fingerprint excludes assessment/action content;
2. two runs over identical Fast PAPER update records but different actions have equal population fingerprints and different action-journal fingerprints;
3. every material record requires an assessment;
4. decision count equals material update count;
5. counts/distinct markets/span reconcile to loop state;
6. E5 evaluation candidate version must match;
7. every closed evaluated trade lies within the loop evidence window;
8. exact candidate/run identity and canonical SHA-256 fingerprint are retained;
9. no wall clock.

### Superiority RED assertions

Use deterministic fixture E5 evidence only to prove logic.

1. required baselines must be present exactly once;
2. undeclared/duplicate baselines rejected;
3. candidate and baselines must share exact E5 policy object;
4. candidate and baselines must share event-population fingerprint;
5. best baseline = highest after-cost net expectancy; lexical version tie-break;
6. candidate beats best baseline by configured margin → `SUPERIOR`;
7. below-margin candidate → `FAILED`;
8. missing required baseline → `INSUFFICIENT_EVIDENCE`;
9. insufficient decisions/markets/span/trades/mints → `INSUFFICIENT_EVIDENCE`;
10. undefined expectancy/profit factor where required → `INSUFFICIENT_EVIDENCE`;
11. expectancy/profit-factor/drawdown/cost/winner-concentration threshold misses → `FAILED`;
12. population or policy contradiction → `FAILED`;
13. gate order is lexical and deterministic;
14. repeated identical input yields identical report fingerprint;
15. report contains no promotion/live/runtime field or method.

### Codec RED assertions

- canonical compact sorted JSON;
- exact field set;
- reject unknown/missing fields;
- reject noncanonical JSON;
- recompute and validate fingerprint;
- round trip exact equality.

### Authority RED assertions

Source/package forbidden tokens include:

- `requests`, `httpx`, `urllib`, `socket`;
- `sqlite3`;
- `subprocess`;
- `datetime.now`, `time.time`;
- `promote`, `RegistryStatus`, `ChampionChallengerRegistry`;
- `TradeIntent`;
- `submit_transaction`, `sign_transaction`;
- `RuntimeMode`, `Live`.

The proof package may import only immutable evidence/loop models and Python standard-library hashing/JSON/math/dataclass/enum utilities.

Expected RED: package missing.

## Task 4 — Implement run evidence

Create:

```text
python/src/shreks_brain/fast_policy_proof/models.py
python/src/shreks_brain/fast_policy_proof/engine.py
python/src/shreks_brain/fast_policy_proof/__init__.py
```

Run-evidence builder:

- consumes exact `FastPaperLoopState` and exact `TradingEvaluationEvidence`;
- population fingerprint material excludes assessments;
- action-journal fingerprint includes exact recorded assessment material;
- validates event identities, material assessment coverage, evidence window, candidate identity;
- computes run evidence fingerprint from all immutable fields with fingerprint zeroed.

## Task 5 — Implement superiority evaluation

In `engine.py`:

1. validate candidate/baseline exact types and uniqueness;
2. determine required baseline coverage;
3. verify comparison population and E5 policy equality;
4. compute candidate sample/economic gates;
5. require required baselines to have enough closed-trade evidence and defined expectancy;
6. choose best baseline by `(-expectancy, version)` equivalently maximum expectancy then lexical version;
7. compute after-cost expectancy advantage;
8. produce all gate codes exactly once in lexical order;
9. apply FAIL > INSUFFICIENT > PASS decision precedence;
10. produce canonical report fingerprint.

No function mutates registry, champion, model, runtime, or money state.

## Task 6 — Implement canonical codec

Create:

`python/src/shreks_brain/fast_policy_proof/codec.py`

Pure string encode/decode only.

- sorted compact JSON;
- no NaN/Infinity;
- exact schema/field sets;
- enum string wire values;
- report fingerprint validation;
- encode(decode(payload)) must equal payload exactly.

## Task 7 — Candidate CI and scope audit

Expected branch scope:

```text
docs/superpowers/specs/2026-09-03-fl9-paper-shadow-superiority-design.md
docs/superpowers/plans/2026-09-03-fl9-paper-shadow-superiority.md
python/src/shreks_brain/paper_evaluation/fast.py
python/src/shreks_brain/fast_policy_proof/__init__.py
python/src/shreks_brain/fast_policy_proof/models.py
python/src/shreks_brain/fast_policy_proof/engine.py
python/src/shreks_brain/fast_policy_proof/codec.py
python/tests/test_fast_paper_evaluation_adapter.py
python/tests/test_fast_policy_run_evidence.py
python/tests/test_fast_policy_superiority.py
python/tests/test_fast_policy_proof_codec.py
python/tests/test_fast_policy_proof_authority.py
```

No Rust/runtime/provider/storage/deployment files.

Require repository safety, Python, Rust, and ARM64 GREEN even though production changes are Python-only.

## Task 8 — Clean TDD history

After a fully GREEN candidate:

- freeze final tree;
- reconstruct exactly:
  1. final design;
  2. final plan;
  3. consolidated intentional RED tests;
  4. final implementation;
- preserve exact final tree;
- force-move only `build/fl9-paper-shadow-superiority`;
- compare to sealed base;
- run fresh clean-head CI 4/4.

## Task 9 — Guarded merge and merged-main seal

- update PR with RED → implementation evidence;
- mark ready;
- guarded merge using exact clean head SHA;
- require push-triggered merged-main 4/4 GREEN;
- mark the **FL9 proof infrastructure** SEALED.

Do **not** mark the FL9 economic exit satisfied unless real non-fixture PAPER/shadow evidence is available and produces `SUPERIOR`.

If real evidence remains absent, record FL9 economic exit as **EVIDENCE PENDING** and do not claim profitability.

LIVE remains disabled.
