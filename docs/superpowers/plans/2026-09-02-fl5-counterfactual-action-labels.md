# FL5 Counterfactual Action Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, research-only counterfactual action labels for BUY/SKIP/delay and HOLD/caller-sized REDUCE/SELL using only explicit contemporaneous execution evidence, then export them as a versioned Parquet research artifact.

**Architecture:** Python owns the pure counterfactual labeling and Parquet research schema. Rust/SQLite remain authoritative for canonical FastEvents and FL3/FL4 evidence. A later read-only adapter may join source evidence into Python inputs, but missing historical execution inputs remain unknown rather than reconstructed. No FL5 component receives trading authority.

**Tech Stack:** Python 3.11+, frozen dataclasses, canonical JSON/SHA-256 conventions already used by `shreks_brain.learning`/`research`, optional pinned PyArrow research dependency, existing SQLite evidence contracts, canonical four-gate GitHub CI.

**Spec:** `docs/superpowers/specs/2026-09-02-fl5-counterfactual-action-labels-design.md`

## Global Constraints

- Price observations are not fills. Every BUY/DELAY/HOLD/REDUCE/SELL utility requires explicit executable trade evidence at the requested quantity.
- `unknown` and `not_executable` are distinct states; neither is silently converted to zero economics.
- SKIP is an explicit zero within-opportunity baseline only; it does not model alternative portfolio opportunity cost.
- REDUCE quantity/fraction is caller-supplied; FL5 never invents 50% or any other default.
- Historical missing fees/slippage/latency/capacity/network/failure-cost evidence remains unknown; never backfill with current constants.
- Counterfactual labeling/export remains research-only and cannot modify strategy, PAPER, signing/submission, provider topology, deployment, or LIVE authority.
- Final completion requires exact-head and merged-main Repository safety, Rust, Python, and native ARM64 release verification.

---

### Task 1: Pure entry-action counterfactual contract

**Files:**
- Create: `python/tests/test_counterfactual_action_labels.py`
- Create: `python/src/shreks_brain/research/counterfactuals.py`
- Modify: `python/src/shreks_brain/research/__init__.py` only if public re-export is useful and surgical.

**Interfaces:**
- Produces versioned frozen evidence/outcome dataclasses, stable action/status literals, validation error, deterministic fingerprint helper, and entry-labeling function.

- [ ] **Step 1: Write intentional RED tests**

Cover:

1. executable BUY_NOW with exact all-in entry quote and executable horizon exit net quote produces exact net PnL and return bps,
2. SKIP is always an explicit zero baseline,
3. missing entry or exit evidence leaves BUY_NOW `unknown` with no utility values,
4. explicit `not_executable` remains distinguishable from unknown and exposes no fabricated PnL,
5. a future observed price without delayed executable buy evidence cannot create DELAY_ENTRY,
6. a caller-supplied delayed executable entry produces a deterministic DELAY_ENTRY row with positive delay,
7. mismatched quantities, invalid times, blank identities, unsupported side/status, and non-finite numerics fail closed,
8. repeated identical labeling produces identical ordered rows and SHA-256 fingerprint.

- [ ] **Step 2: Run exact-head RED proof**

Expected canonical gates:
- Repository safety GREEN,
- Rust workspace GREEN,
- ARM64 release GREEN,
- Python RED because the FL5 module/API is absent.

- [ ] **Step 3: Implement the minimum pure entry labeler**

Use frozen dataclasses and explicit validation. Do not select a “best” action. Return stable per-action rows in canonical order.

Formula for labelable entry actions:

```text
net_pnl_quote = exit_net_quote - entry_total_quote
return_bps = (exit_net_quote / entry_total_quote - 1) * 10_000
```

Unknown/not-executable actions retain `None` utility fields.

- [ ] **Step 4: Run focused Python tests and full four-gate CI GREEN**

- [ ] **Step 5: Commit implementation after GREEN**

---

### Task 2: Open-position HOLD / REDUCE / SELL counterfactuals

**Files:**
- Extend: `python/tests/test_counterfactual_action_labels.py`
- Extend: `python/src/shreks_brain/research/counterfactuals.py`

**Interfaces:**
- `OpenPositionCounterfactualContext`
- pure open-position labeling function.

- [ ] **Step 1: Write intentional RED tests**

Cover:

1. SELL_NOW requires executable sell evidence for the full held quantity,
2. SELL_NOW PnL/return uses supplied total position cost basis,
3. REDUCE_NOW requires an explicit caller-supplied positive quantity <= held quantity,
4. REDUCE cost basis is allocated pro rata and remaining quantity/basis are exact,
5. no default reduce fraction exists,
6. HOLD requires complete future horizon plus executable future sell evidence for the full held quantity,
7. unknown/non-executable future exit keeps HOLD utility unknown/non-executable,
8. quantity/source/time mismatches fail closed.

- [ ] **Step 2: Run RED**

Expected: focused Python failures only for missing open-position API/semantics.

- [ ] **Step 3: Implement minimal open-position labeler**

Formulas:

```text
sell_net_pnl_quote = sell_net_quote - position_cost_basis_quote
sell_return_bps = (sell_net_quote / position_cost_basis_quote - 1) * 10_000

reduced_cost_basis_quote = position_cost_basis_quote * reduce_quantity / position_quantity
reduce_realized_net_pnl_quote = reduce_sell_net_quote - reduced_cost_basis_quote
remaining_quantity = position_quantity - reduce_quantity
remaining_cost_basis_quote = position_cost_basis_quote - reduced_cost_basis_quote
```

No outcome for the remaining REDUCE position is invented without additional explicit evidence.

- [ ] **Step 4: Run focused + four-gate GREEN**

- [ ] **Step 5: Commit**

---

### Task 3: Executable delay and entry-price-efficiency semantics

**Files:**
- Extend: `python/tests/test_counterfactual_action_labels.py`
- Extend: `python/src/shreks_brain/research/counterfactuals.py`

- [ ] **Step 1: Write RED tests**

Assert that entry-price efficiency:

- compares only same requested quantity and same outcome horizon,
- uses all-in executable entry quote, not observed price extrema,
- can compare BUY_NOW against one or more explicitly supplied delayed entries,
- rejects a delayed record at/before the original action timestamp,
- does not synthesize a delayed entry from FL4 MFE/MAE or raw future prices.

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Implement minimal efficiency/delay comparison fields**

Keep output as raw research signal; do not add policy thresholds or autonomous action selection.

- [ ] **Step 4: Run focused + four-gate GREEN**

- [ ] **Step 5: Commit**

---

### Task 4: Dedicated FL5 Parquet v1 artifact

**Files:**
- Create: `python/src/shreks_brain/research/counterfactual_parquet.py`
- Create: `python/tests/test_counterfactual_parquet.py`
- Extend public research exports only if needed.

**Interfaces:**
- exact Arrow schema metadata,
- deterministic writer/reader,
- logical dataset fingerprint.

- [ ] **Step 1: Write RED round-trip/schema tests**

Assert:

1. schema name `shreks.counterfactual_action_labels`, schema version 1, label version 1,
2. one row per action alternative with source/provenance/executability fields,
3. stable deterministic row ordering,
4. exact write/read round trip,
5. same logical rows produce same SHA-256 fingerprint,
6. incompatible/missing metadata fails closed,
7. unknown optional economics remain null, never zero-filled.

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Implement using existing pinned PyArrow conventions**

Reuse lazy PyArrow import and exact metadata-validation style from `research/parquet.py`. Do not add a dependency outside the existing research extra.

- [ ] **Step 4: Run focused + four-gate GREEN**

- [ ] **Step 5: Commit**

---

### Task 5: Read-only canonical evidence adapter

**Files:**
- Create: `python/src/shreks_brain/research/counterfactual_source.py`
- Create: `python/tests/test_counterfactual_source.py`
- Modify only narrowly required research exports/config.

**Interfaces:**
- read-only SQLite access to FL4 labels and source-linked FL3/FastEvent evidence,
- produces pure FL5 evidence/context records only when historical executability can be proven.

- [ ] **Step 1: Write RED adapter tests**

Use temporary SQLite fixtures matching the authoritative migrations/contracts. Prove:

1. canonical decision/FL4 joins preserve identity/version/horizon,
2. missing optional FL4 capacity/cost annotations keep action executability unknown,
3. historical missing full execution-cost inputs are not backfilled from current protocol constants,
4. incomplete FL4 horizons cannot become HOLD/BUY outcome utility,
5. conflicting/mismatched source identities fail closed,
6. adapter opens source database read-only and performs no canonical writes.

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Implement the smallest read-only adapter**

Prefer existing schema/query vocabulary. Do not duplicate canonical replay or conflict policy; consume the durable evidence already proven by Rust/storage. If the persisted evidence cannot prove a requested execution action, emit `unknown`.

- [ ] **Step 4: Run focused + four-gate GREEN**

- [ ] **Step 5: Commit**

---

### Task 6: FL5 scope/proof closure

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-fl5-counterfactual-action-labels-design.md`
- Modify: `docs/superpowers/plans/2026-09-02-fl5-counterfactual-action-labels.md`

- [ ] **Step 1: Audit the full branch diff**

Confirm FL5 is confined to research/tests/docs plus any narrowly required read-only adapter surface. Confirm no strategy scoring, PAPER authority, signer/submission, provider fallback, systemd/deployment, release authority, or LIVE files changed.

- [ ] **Step 2: Verify determinism/source integrity**

Confirm repeated identical evidence produces identical labels/fingerprint and that price-only future observations cannot become executable counterfactual fills.

- [ ] **Step 3: Run exact-head four-gate CI**

Require all four canonical jobs GREEN on one exact SHA.

- [ ] **Step 4: Guarded merge exact verified head**

Use exact head SHA guard.

- [ ] **Step 5: Run fresh merged-main four-gate CI**

Do not declare FL5 complete before all four gates are GREEN on the merge commit.

- [ ] **Step 6: Record proof state**

Record exact head/run, merge SHA/run, scope audit, dataset schema/version, and statement that LIVE remains disabled.