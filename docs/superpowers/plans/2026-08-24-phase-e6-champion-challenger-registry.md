# Phase E6 Champion / Challenger Registry — Verification Record

**Base:** sealed A10 `d36ec5fd3d650f0c8d55c56fd461f371e910d8f3`  
**Design:** `docs/superpowers/specs/2026-08-24-phase-e6-champion-challenger-registry-design.md`  
**Schema:** `e6-registry-v1`

## Verified boundary

E6 is a Python registry/audit layer only. It durably records evaluated strategy/model provenance plus explicit `CHALLENGER`, `CHAMPION`, and `RETIRED` history. It does not decide whether performance is good enough for promotion, does not run a challenger, does not create trade intents, and does not enable live money. E7 owns shadow/paper challenger operation; E8 owns promotion rules.

The registry reuses sealed E3/E4/E5 evidence instead of recomputing training, validation, or trading metrics. Model-backed candidates preserve E3 training identity/fingerprint/window, E4 chronological-validation identity/fingerprint, exact feature identity, and the E5 after-cost evaluation fingerprint/headline metrics. Strategy-only candidates are supported without inventing fake ML provenance.

## Task 1 — Contract and provenance normalization

Tests-only RED head: `940a32bd77c866d1ae8f7795b38e2bbbaf25686f`  
RED CI: `32785340953`

Expected result: Python collection failed only because `shreks_brain.registry` did not yet exist; Rust/workspace and repository safety were unaffected/green.

Initial implementation head: `b5246de1f42fa637f1f54f6d15c5d67761b05d7b`  
CI: `32785495169`

That run exposed one diagnostic-order defect: 1 test failed while 1827 passed because half-present training timestamps raised the generic partial-model-provenance error before the more precise training-timestamp error. The fail-closed rule itself was correct.

Corrected GREEN head: `8083ae13560342f07c70e865e4ecca6c9b113c1f`  
GREEN CI: `32785612761`

Verified:

- exact small public registry API;
- immutable registry/evaluation/status models;
- registration starts `CHALLENGER` only;
- model-backed E3/E4/E5 provenance alignment;
- strategy-only candidate support;
- partial or mismatched provenance fails closed;
- deterministic material candidate fingerprint;
- no automatic promotion/live-authority surface.

## Task 2 — Durable canonical store

Tests-only RED head: `14fae23b9e0b216581a4f73953d353d727e6b79f`  
RED CI: `32785755396`

Expected result: Python collection failed only because `RegistryStore` was intentionally absent.

Initial store implementation head: `03fe5f4e1e8066c1fced75abacecaaa66104fb8c`  
CI: `32785941007`

That run had 1833 passing tests and one test-fixture failure. The fixture created a conflicting candidate with an invalid material fingerprint, so the production store correctly rejected tampering before reaching the later candidate-version conflict assertion. Production behavior was left unchanged.

Fixture-corrected GREEN head: `7664ec180ff492523dc19488711ed83a11ea88b8`  
GREEN CI: `32786108928`

Verified:

- missing file -> deterministic empty registry;
- canonical JSON persistence;
- atomic sibling-temp-file + `os.replace` writes;
- candidate registration idempotency;
- conflicting candidate identity fails closed;
- candidate and registry fingerprints are independently recomputed on load;
- invalid/truncated/tampered documents fail closed;
- restart reconstruction preserves exact state;
- no deletion/history-rewrite API.

## Task 3 — Explicit status history

Tests-only RED head: `b691adf4ab6755847de232867dbd047a9c257319`  
RED CI: `32786277333`

Expected result: 6 new tests failed only because `RegistryStore.record_status` / `record_status_event` did not yet exist; 1834 existing Python tests passed, Rust/workspace passed, and repository safety passed.

GREEN behavior head: `0a787fbe556b0599b604a3c0b95db3e141346a8d`  
GREEN CI: `32786757663`  
Python: **1840 passed in 5.67s**  
Rust/workspace: GREEN  
Repository safety: GREEN

Verified:

- caller must explicitly supply candidate, requested status, decision reference, timestamp, and reason;
- unknown candidate fails closed;
- event cannot predate candidate registration;
- no-op and mismatched prior-state transitions fail closed;
- event material is content-addressed and revalidated;
- duplicate identical event is idempotent;
- conflicting reuse of the same decision identity fails closed;
- at most one current champion is structurally permitted;
- the registry never auto-demotes an incumbent to make room for another champion;
- retirement/reactivation remains possible only through another explicit event;
- status mutation source contains no E5 metric-threshold logic, trade intent, or live-enablement authority.

## Cumulative scope audit

Compared sealed A10 `d36ec5fd3d650f0c8d55c56fd461f371e910d8f3` to E6 behavior head `0a787fbe556b0599b604a3c0b95db3e141346a8d`.

The behavior diff contains exactly 12 allowed files:

- this E6 plan/verification path;
- the E6 design spec;
- five files under `python/src/shreks_brain/registry/`;
- five E6 registry test files.

No observer, provider, strategy/setup, risk, paper execution, model-training, E5 evaluation, signer, transaction-submission, or live-execution file changed.

## Profitability and authority boundary

E6 makes model/strategy evidence attributable and tamper-evident, which is necessary for disciplined profitable iteration. It does **not** establish that any candidate is profitable and does not translate good expectancy, profit factor, drawdown, calibration, or other E5 values into promotion.

A `CHAMPION` status is an explicit governance record, not proof of profitability and not live-money authority. Real-money trading remains disabled.

## Final seal procedure

This verification record is the documentation seal candidate. After this docs-only commit, compare it to the behavior head to ensure no production/test behavior changed, run exact-head CI, confirm PR #30 still targets sealed A10 and its head equals the final seal SHA, then freeze E6. The exact final seal SHA/CI are recorded in PR #30 after that run so this tracked record does not require a self-referential follow-up commit.
