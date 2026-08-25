# Phase E15 Observer Paper Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert real point-in-time observer history into purpose-correct, restart-safe paper cycles and E11 evaluation evidence without synthetic fills or live authority.

**Architecture:** First add bidirectional entry/exit quote evidence to the explicit Rust safety collector and SQLite persistence. Then add an isolated Python `observer_campaign` package that reconstructs purpose-correct paper quotes, aggregate regime evidence, dynamic paper risk context, and Fresh Launch C5 cycle inputs. Finally add a restart-safe runner that reuses sealed C5/C6/E11 components and expose an authority-limited public API.

**Tech Stack:** Rust workspace (`shreks-core`, `shreks-storage`, `shreks-observer`), SQLite/rusqlite, Python 3.12 stdlib `sqlite3`, existing `shreks_brain` sealed engines, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e15-observer-paper-campaign-design.md`

## Global Constraints

- Base exactly on sealed E14 `72e18c82a8477936479fd13b4f00f52a71c0f59d`.
- Do not change B1 safety thresholds/precedence, B2 arithmetic, B6 regime classification, C5 orchestration, C6 accounting/checkpoint behavior, E11 normalization, E12 proof gates, E6 registry, E8 promotion, or live execution.
- No production numeric defaults; all thresholds/policies are caller supplied.
- Default Phase-A observer remains unchanged; E15 collection/runner is explicit opt-in only.
- Never reuse an EXIT quote as an ENTRY fill.
- No signed transaction, transaction instruction, credential, signing, submission, registry mutation, promotion, live-mode, or live-money authority.
- Every task follows RED -> exact failure inspection -> minimal GREEN -> full repository CI.
- Keep the stacked PR draft/unmerged; final seal is one verification-document-only commit after an immutable behavior head.

---

### Task 1: Purpose-attributed bidirectional quote persistence

**Files:**
- Modify: `crates/shreks-core/src/lib.rs`
- Create: `crates/shreks-storage/migrations/0009_paper_quote_purpose.sql`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: Rust core/storage tests

**Interfaces:**
- Produces `QuotePurpose::{Entry, Exit}` with stable `as_str()` values `entry` / `exit`.
- Produces `ShreksDb::insert_paper_quote_snapshot(candidate_id, purpose, probe_policy_version, request, snapshot)`.
- Existing `insert_exit_quote_snapshot(...)` remains available and unchanged for E14 callers.

- [ ] **Step 1: Write RED Rust tests for `QuotePurpose` and schema version 9.**

Require exact lowercase persistence vocabulary and additive migration from version 8 without changing existing `exit_quote_snapshots` rows.

- [ ] **Step 2: Write RED storage tests for generic paper quote persistence.**

Prove `ENTRY` and `EXIT` rows with identical request fields remain distinct by purpose; exact replay is idempotent; contradictory content at one semantic identity fails closed; raw u64 amounts remain canonical decimal text; route labels round-trip canonical JSON.

- [ ] **Step 3: Commit RED and require CI failure only on absent enum/migration/method.**

- [ ] **Step 4: Implement `QuotePurpose`, migration 0009, and generic insertion.**

Migration creates `paper_quote_snapshots` with foreign key to `token_candidates`, candidate/purpose/time index, exact purpose CHECK constraint, semantic unique constraint, and no transaction/signature fields.

- [ ] **Step 5: Keep E14 insertion behavior stable.**

`insert_exit_quote_snapshot` continues writing E14 `exit_quote_snapshots`; E15 generic persistence is additional rather than a silent schema switch.

- [ ] **Step 6: Run full CI and commit GREEN.**

---

### Task 2: Bidirectional explicit collector

**Files:**
- Modify: `crates/shreks-observer/src/safety_evidence.rs`
- Test: observer safety-evidence Rust tests

**Interfaces:**
- `SafetyEvidenceProbe` fields become `probe_policy_version`, `distribution_request`, `exit_quote_request`, `entry_quote_request: Option<QuoteRequest>`.
- `SafetyEvidenceCycleReport` adds `entry_quote_snapshots_stored`, `exit_quote_snapshots_stored`, `entry_quote_provider_failures`, `exit_quote_provider_failures`; retain total quote counts only if existing callers require them.

- [ ] **Step 1: Write RED collector tests for entry+exit identity.**

Prove exit input mint equals candidate, entry output mint equals candidate, entry input mint equals exit output mint, taker/slippage equality, purpose-correct persistence, no-route persistence, provider failure isolation, result identity rejection, and idempotence.

- [ ] **Step 2: Add regression tests that `free_observe_provider_plan` and `build_free_observer` still do not construct the safety/campaign collector.**

- [ ] **Step 3: Commit RED and inspect exact failure.**

- [ ] **Step 4: Implement minimal bidirectional collection.**

Call provider quote separately for each configured request and persist with `QuotePurpose::Entry` or `QuotePurpose::Exit`. Provider failures stay nonfatal/unknown.

- [ ] **Step 5: Run full CI and commit GREEN.**

---

### Task 3: Python observer-campaign evidence models and read-only store

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/models.py`
- Create: `python/src/shreks_brain/observer_campaign/store.py`
- Create: `python/tests/test_observer_campaign_models.py`
- Create: `python/tests/test_observer_campaign_store.py`

**Interfaces:**
- Produces `OBSERVER_PAPER_CAMPAIGN_SCHEMA_VERSION = "e15-observer-paper-v1"`.
- Produces immutable `ObserverPaperQuoteAsset`, `ObserverPaperQuoteIdentity`, `ObserverPaperQuoteEvidence`, `ObserverRegimeReadPolicy`, `ObserverPaperRiskEnvironment`.
- Produces `ObserverCampaignReadError` and `ObserverCampaignStore(path)`.
- Store public readers: `latest_paper_quote`, `latest_token_decimals`, `build_regime_market_window`.

- [ ] **Step 1: Write RED immutable model tests.**

Require exact enums/types, non-empty versions/mints/taker, u64 raw amounts, decimal bounds `[0,255]`, finite positive quote-asset USD value, exact purpose, and no authority-bearing fields.

- [ ] **Step 2: Write RED store tests.**

Prove missing DB is not created, required schema absence fails closed, additive future columns are allowed, latest reads never cross `as_of`, exact purpose/request attribution is mandatory, token decimals come from the latest Helius mint state at/before `as_of`, and future mint/quote rows are invisible.

- [ ] **Step 3: Write RED aggregate-regime tests.**

Use deterministic SQLite fixtures to prove candidate discovery cutoff, source priority, snapshot max age, no future rows, median calculation, missing median fields remain unknown, and executable breadth requires purpose-correct entry route availability plus B1 PASS evidence.

- [ ] **Step 4: Commit RED and verify missing-package/store failure.**

- [ ] **Step 5: Implement models/store only.**

SQLite access is `mode=ro`; all wide integers are canonical decimal text at the boundary.

- [ ] **Step 6: Run full CI and commit GREEN.**

---

### Task 4: Purpose-correct paper quote reconstruction

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/quotes.py`
- Create: `python/tests/test_observer_campaign_quotes.py`

**Interfaces:**
- Produces `ObserverPaperQuoteError`.
- Produces `build_entry_paper_quote(window, evidence, token_decimals, quote_asset)`.
- Produces `build_exit_paper_quote(window, evidence, token_decimals, quote_asset)`.

- [ ] **Step 1: Write RED exact arithmetic tests.**

ENTRY fixture: quote-asset raw input -> USD input, token raw output -> quantity, execution price = USD/quantity, reference price from current market point, quoted/available notional equal quote input USD.

EXIT fixture: token raw input -> quantity, quote-asset raw output -> USD output, execution price = USD/quantity, quoted/available notional based on input token quantity * current reference price.

- [ ] **Step 2: Prove no-route maps to `PaperQuoteState.UNAVAILABLE` without execution price.**

- [ ] **Step 3: Prove wrong purpose/mints/decimals/zero quantity/non-positive reference/malformed evidence fail closed.**

- [ ] **Step 4: Commit RED and inspect missing module/function failure.**

- [ ] **Step 5: Implement minimal conversion with no inferred stablecoin assumptions.**

- [ ] **Step 6: Run full CI and commit GREEN.**

---

### Task 5: Dynamic paper risk-context derivation

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/risk_context.py`
- Create: `python/tests/test_observer_campaign_risk_context.py`

**Interfaces:**
- Produces `ObserverPaperRiskContextError`.
- Produces `build_observer_risk_context(state, window, entry_quote, environment) -> RiskContext`.

- [ ] **Step 1: Write RED derivation tests.**

Prove open count and aggregate open cost basis from OPEN positions, daily realized PnL from journal rows after day start, active intent keys from processed/pending state, market age from current observer row, and entry price-impact/notional from purpose-correct entry quote evidence.

- [ ] **Step 2: Write RED drawdown/loss-streak tests.**

Reconstruct chronological closed-position outcomes; derive consecutive losses and last loss time. Drawdown is derived only when an auditable equity path exists; any required unmarked open position makes drawdown `None`, allowing sealed C4 to fail closed.

- [ ] **Step 3: Prove health flags have no optimistic defaults.**

Environment construction requires explicit booleans and positive trading capital.

- [ ] **Step 4: Commit RED, implement minimal derivation, run full CI, commit GREEN.**

---

### Task 6: Fresh-Launch observer cycle assembler

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/assembler.py`
- Create: `python/tests/test_observer_campaign_assembler.py`

**Interfaces:**
- Produces `ObserverPaperAssemblyError`.
- Produces `ObserverFreshLaunchPolicyBundle` carrying exact sealed `ObserverMarketReadPolicy`, `SafetyPolicy`, `ObserverSafetyProbeIdentity`, `ObserverRegimeReadPolicy`, `RegimePolicy`, `FreshLaunchPolicy`, `ScorePolicy`, `DecisionPolicy`, `RiskPolicy`, `ExitPolicy`, and quote-asset/entry-quote identities.
- Produces `ObserverPaperCycleAudit` containing exact market/safety/regime/feature fingerprints or stable serialized identities needed for replay audit.
- Produces `assemble_observer_paper_cycle(...) -> tuple[PaperCycleInput, ObserverPaperCycleAudit]`.

- [ ] **Step 1: Write RED clean-case assembly test.**

Load one candidate at one `as_of`, call sealed E14 safety, B2 features, B6 regime, dynamic risk context, build `FreshLaunchSetupInput`, purpose-correct entry/exit `PaperQuote` values, and exact C5 `PaperCycleInput`.

- [ ] **Step 2: Write RED fail-closed edge tests.**

Prove future observer data invisible, safety INCOMPLETE/REJECT remains present for sealed decision rejection, missing entry quote never becomes a synthetic fill, DEAD regime passes through unchanged, and wrong candidate/policy attribution fails.

- [ ] **Step 3: Prove V1 rejects unsupported Graduation/Pullback assembly rather than guessing contexts.**

- [ ] **Step 4: Commit RED and inspect failure.**

- [ ] **Step 5: Implement by composing only public sealed APIs.**

No threshold logic is duplicated.

- [ ] **Step 6: Run full CI and commit GREEN.**

---

### Task 7: Restart-safe campaign runner and E11 evidence bridge

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/runner.py`
- Create: `python/tests/test_observer_campaign_runner.py`

**Interfaces:**
- Produces `ObserverPaperCampaignError` and `ObserverPaperCampaignRunner`.
- Constructor requires observer DB path, E11 evidence path, exact `RegistryCandidate`, `paper_run_id`, initial `PaperLoopState`, policy bundle, and explicit risk environment.
- Public methods only: `load_state`, `run_cycle`, `evaluated_trades`.

- [ ] **Step 1: Write RED first-cycle test.**

Assemble cycle, run sealed C5, record exact E11 evidence, validate C6 accounting, save C6 checkpoint sequence 1, return the actual `PaperCycleResult`.

- [ ] **Step 2: Write RED restart-equivalence test.**

Two cycles uninterrupted must equal one cycle + process reconstruction + second cycle in final `PaperLoopState`, accounting report, E11 ledger fingerprint, and evaluated trades.

- [ ] **Step 3: Write RED idempotence/contradiction tests.**

Exact replay at a completed checkpoint is no-op only when evidence/state matches; sequence collision, registry attribution change, paper-run reuse with a different candidate, or E11 contradiction fails closed.

- [ ] **Step 4: Prove runner never calls E12 promotion/proof automatically and never imports live/signing/submission paths.**

- [ ] **Step 5: Commit RED, implement minimal runner, run full CI, commit GREEN.**

---

### Task 8: Public API, scope audit, immutable seal

**Files:**
- Create: `python/src/shreks_brain/observer_campaign/__init__.py`
- Create: `python/tests/test_observer_campaign_public_api.py`
- Replace plan with verification record: `docs/superpowers/plans/2026-08-25-phase-e15-observer-paper-campaign.md`

**Interfaces:**
- Export only E15 evidence/read/assembly/runner symbols.
- No public registry mutation, promotion, live execution, signing, submission, or transaction-build authority.

- [ ] **Step 1: Write RED exact-`__all__` and fresh-process authority-firewall tests.**

- [ ] **Step 2: Commit RED, implement export-only `__init__.py`, run full CI, and freeze resulting SHA as E15 behavior head.**

- [ ] **Step 3: Compare sealed E14 -> E15 behavior head and audit every changed file.**

Expected scope: E15 docs/tests; additive QuotePurpose/core contract; migration/generic quote persistence; explicit safety collector extension; isolated Python `observer_campaign`. No default observer, B1/B2/B6/C5/C6/E11/E12/registry/promotion/live path behavior changes.

- [ ] **Step 4: Replace this plan with a verification record containing all RED/GREEN anchors, CI run IDs/counts, exact public API, scope audit, and authority/profitability boundary.**

- [ ] **Step 5: Commit only that document as `docs: seal E15 verification record`.**

- [ ] **Step 6: Verify behavior-head -> seal is exactly one commit / one file, then require fresh exact-seal full CI GREEN.**

- [ ] **Step 7: Update the stacked draft PR body with immutable base/behavior/seal metadata and leave it draft/unmerged.**
