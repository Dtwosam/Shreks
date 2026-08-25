# Phase E8 — Promotion Rules Verification Record

**Project:** Shreks  
**Phase:** E8 — Promotion rules  
**Base:** sealed E7 `62ffff47a6bcb408d8696a56eda6535d13cdd186`  
**Behavior head:** `ffcc781068af1aad8da56328721b3de934b07a47`  
**Schema:** `e8-promotion-v1`  
**Date:** 2026-08-25

## Purpose

E8 makes champion/challenger promotion eligibility deterministic, explicit, auditable, fail-closed, and persistable without granting any mechanism authority to promote a model, mutate registry status, create a trade, or enable live money.

`ELIGIBLE` means only that the supplied evidence satisfied the caller-supplied promotion policy at the recorded evaluation timestamp. It is not a registry promotion, live-mode permission, profitability claim, or authorization to execute money.

## Sealed behavior

E8 adds a deliberately small `shreks_brain.promotion` surface:

- immutable promotion policy, gate, and assessment contracts;
- explicit gate codes/statuses and `ELIGIBLE` / `NOT_ELIGIBLE` decisions;
- canonical SHA-256 evidence and assessment fingerprints;
- a pure `evaluate_promotion(...)` evaluator;
- an append-only `PromotionAssessmentStore` using canonical JSON, exact-schema decoding, independent fingerprint recomputation, identity conflict checks, idempotent identical appends, and fsync + atomic replace;
- import-firewall coverage so importing promotion does not eagerly load training/Parquet stacks;
- negative authority tests proving no registry mutation, trade-intent, signing, submission, or live-enable surface exists.

All promotion thresholds remain caller supplied. E8 invents no default profitability, drawdown, sample-size, shadow-age, or baseline threshold.

## TDD / CI evidence

### Task 1 — immutable contracts and canonical fingerprinting

- RED head `33c9a5bfdbffb7a1629b9d2ac4786d5bed5e52d3`
  - CI `32828954908`: expected failure while `shreks_brain.promotion` was absent/incomplete; Rust/workspace and repository safety remained outside the failure.
- Staged implementation head `2e4cfcce49598b66ecaa75cb4953b81ce86a0786`
  - CI `32829128178`: Python still failed at collection because the package public API had not yet exposed `PROMOTION_SCHEMA_VERSION`; Rust and repository safety passed.
- Staged canonical-fingerprint head `7bf03b427fdc0fabcbbd1d5d949461ba6dd6cf33`
  - CI `32829153548`: remained RED until the public package surface was wired.
- GREEN head `367a5911e37e97f919871e409873eab09cd79760`
  - CI `32829176767`: GREEN.

Correction: implementation was kept in small commits; the public `__init__` exposure was intentionally the final piece required to turn the Task 1 contract tests GREEN.

### Task 2 — pure promotion evaluator

- RED head `d4b03eced4f0f4e31ca473ff6470fa3a333d6e5e`
  - CI `32829513188`: expected evaluator RED before implementation.
- First implementation candidate `596ce1d7b8fa63cd90ff166e93405380d700f4d7`
  - CI `32829789508`: Python `1914 passed, 1 failed`; Rust/workspace and repository safety passed.
  - The sole failure was the import-firewall test checking the current pytest process, where `sklearn` had already been imported by unrelated earlier tests. This was test isolation, not promotion behavior.
- GREEN correction head `ca6ee12bb5df3fefa8aef4f90d885b7bd170876b`
  - CI `32829899521`: GREEN.

Correction: the import-firewall assertion was moved into an isolated subprocess so it measures imports caused by `shreks_brain.promotion` itself rather than pre-existing process state.

### Task 3 — append-only promotion assessment store

- RED head `511d768ed1abca6e26b266347f2da9b48d312263`
  - CI `32833442928`: Python failed as expected for the missing Task 3 store; Rust/workspace and repository safety passed.
- First implementation candidate `e8fc9b2ed3a235825440fd4dea453309501dffc2`
  - CI `32833658723`: Python `1922 passed, 4 failed`; repository safety passed and the failures were confined to the new store test harness.
  - The four failures came from tamper subcases reusing the same deliberately corrupted `promotion.json`, so later setup attempted to append through already-invalid state. The store was correctly failing closed.
- GREEN correction / E8 behavior head `ffcc781068af1aad8da56328721b3de934b07a47`
  - CI `32834061989`: GREEN.
  - Python: **1926 passed in 6.60s**.
  - Rust/workspace: GREEN.
  - Repository safety: GREEN.

Correction: each tamper subcase now recreates a clean persisted assessment before applying its mutation. No production code changed in the correction commit.

## Cumulative scope audit

Compared sealed E7 `62ffff47a6bcb408d8696a56eda6535d13cdd186` to E8 behavior head `ffcc781068af1aad8da56328721b3de934b07a47`.

The cumulative diff is limited to exactly these allowed areas:

- `docs/superpowers/specs/2026-08-25-phase-e8-promotion-rules-design.md`;
- this E8 plan / verification record;
- `python/src/shreks_brain/promotion/`;
- `python/tests/test_promotion_engine.py`;
- `python/tests/test_promotion_models.py`;
- `python/tests/test_promotion_public_api.py`;
- `python/tests/test_promotion_store.py`.

No modifications exist in E5 evaluation, E6 registry, E7 shadow, risk, paper execution, observer/executor, or live-execution paths.

## Authority boundary

E8 has **eligibility authority only**.

It does not:

- promote a challenger in the champion/challenger registry;
- mutate registry status or append registry status events;
- create or execute `TradeIntent` objects;
- sign or submit transactions;
- enable live mode;
- bypass risk, safety, paper/live parity, or the live-promotion gate;
- claim the current strategy has positive expectancy;
- claim any challenger currently satisfies a profitable promotion policy.

The master requirement remains unchanged: a newly trained model cannot directly self-promote into live control, and live trading remains disabled until independent proof satisfies all required gates.

## Profitability boundary

Passing E8 tests proves deterministic promotion-rule machinery, provenance, persistence, and authority separation. It does **not** prove a trading edge.

Positive expectancy after realistic costs, acceptable drawdown, sufficient independent sample size, stable provider/restart behavior, accounting/execution correctness, paper/live parity, and risk-halt reliability still require evidence from actual observation, replay, paper, and shadow results before any real-money activation.

## Seal procedure

This verification record is the only permitted change from the E8 behavior head to the seal candidate. After committing it:

1. audit behavior head -> seal candidate and require exactly this one documentation file changed;
2. run exact-head CI and require Python, Rust/workspace, and repository safety GREEN;
3. record the exact seal SHA and final CI run in PR #32;
4. freeze E8 with the PR left unmerged/draft, matching the existing stacked-phase workflow.

The final exact-head CI cannot be embedded in this commit without creating a new head; therefore the PR body is the post-run seal ledger for the exact seal SHA and CI run.
