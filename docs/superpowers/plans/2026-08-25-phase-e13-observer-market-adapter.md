# Phase E13 Observer Market Replay Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict read-only adapter from the Rust observer SQLite market history into deterministic B2-compatible market feature points without future leakage or invented evidence.

**Architecture:** Add an isolated `shreks_brain.observer_market` package. Immutable E13 models represent persisted candidate/snapshot/window evidence; `ObserverMarketStore` opens SQLite read-only, validates the required schema, resolves exact candidate identity, selects one caller-prioritized source/pair path, and reconstructs current/1m/5m/15m B2 market points. No safety, wallet, paper, registry, promotion, provider-network, signing, or live authority is added.

**Tech Stack:** Python 3.12 standard library (`sqlite3`, `pathlib`, dataclasses), existing sealed B2 `MarketFeaturePoint`, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-e13-observer-market-adapter-design.md`

## Global Constraints

- Schema identifier is exactly `e13-observer-market-v1`.
- SQLite access is read-only URI mode; a missing database path must not be created.
- Provider priority, current staleness, and local-range lookback are caller supplied.
- Current, anchors, local range, and pair metadata never use rows after `as_of_unix_ms`.
- Anchors use the same source and pair path as the selected current row.
- Missing valid anchors remain `None`; no interpolation or synthetic points.
- No existing observer/storage, B2 feature behavior, paper execution, registry, promotion, provider network, Rust executor, signing/submission, or live path changes.
- Phase F remains disabled.

---

### Task 1: Immutable E13 evidence models

**Files:**
- Create: `python/tests/test_observer_market_models.py`
- Create: `python/src/shreks_brain/observer_market/models.py`

**Interfaces:**
- Produces `OBSERVER_MARKET_SCHEMA_VERSION`, `ObserverMarketReadPolicy`, `ObserverCandidateIdentity`, `ObserverMarketSnapshot`, and `ObservedMarketWindow`.

- [ ] **Step 1: Write failing model tests**

Tests instantiate valid models and reject empty versions/sources, duplicate source priority, negative IDs/timestamps/counts, non-finite or negative market values, invalid pair-creation timestamps, mismatched window schema/policy/candidate/source/pair attribution, and future snapshot timestamps.

- [ ] **Step 2: Run the focused tests**

Run: `cd python && python -m pytest tests/test_observer_market_models.py -q`

Expected RED: import failure because `shreks_brain.observer_market` does not exist.

- [ ] **Step 3: Implement minimal frozen/slotted models**

Use strict validators consistent with existing project model conventions. `ObservedMarketWindow` stores the exact raw snapshots; B2 conversion happens later.

- [ ] **Step 4: Run full Python tests**

Run: `cd python && python -m pytest -q`

Expected GREEN.

- [ ] **Step 5: Commit**

Commit message: `feat: add E13 observer market models`

---

### Task 2: Read-only schema and candidate resolution

**Files:**
- Create: `python/tests/test_observer_market_store.py`
- Create: `python/src/shreks_brain/observer_market/store.py`

**Interfaces:**
- Produces `ObserverMarketReadError` and `ObserverMarketStore`.
- `ObserverMarketStore.resolve_candidate(mint, *, pair_address=None, discovery_source=None) -> ObserverCandidateIdentity`.

- [ ] **Step 1: Write failing read-only/candidate tests**

Create temporary SQLite databases with only the exact required E13 schema. Prove:

- missing path raises and is not created;
- missing required table/column fails closed;
- future additive columns are tolerated;
- one exact candidate resolves;
- absent candidate fails;
- duplicate mint candidates fail unless caller filters disambiguate;
- returned values are strict E13 models.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd python && python -m pytest tests/test_observer_market_store.py -q`

Expected RED: `ObserverMarketStore` / store module missing.

- [ ] **Step 3: Implement read-only open, schema inspection, and exact resolution**

Open using a `file:` URI with `mode=ro` and `uri=True`. Query `sqlite_master`/`PRAGMA table_info` without migrations or writes. Use parameterized SQL only.

- [ ] **Step 4: Run focused and full Python tests**

Run focused file, then `cd python && python -m pytest -q`.

Expected GREEN.

- [ ] **Step 5: Commit**

Commit message: `feat: read observer candidates safely`

---

### Task 3: Deterministic current/anchor market replay

**Files:**
- Modify: `python/tests/test_observer_market_store.py`
- Modify: `python/src/shreks_brain/observer_market/store.py`

**Interfaces:**
- `ObserverMarketStore.load_window(candidate_id, as_of_unix_ms, policy) -> ObservedMarketWindow`
- `build_market_feature_points(window) -> tuple[MarketFeaturePoint, MarketFeaturePoint | None, MarketFeaturePoint | None, MarketFeaturePoint | None]`

- [ ] **Step 1: Add failing window-selection tests**

Fixtures must include multiple providers, pair paths, equal-distance anchor ties, rows inside/outside every B2 age window, stale current rows, future rows, missing anchors, local-range rows, and nullable pair-created metadata.

Assert:

- source priority chooses current path;
- anchors never cross source or pair;
- exact B2 windows are respected;
- closest-to-target selection is deterministic;
- tie-break is newer timestamp then lower row ID;
- future rows never influence any output;
- stale current fails closed using caller threshold;
- missing anchors are `None`;
- local high/low use only caller lookback and selected path;
- pair-created fallback uses newest non-null historical value at/before as-of;
- malformed persisted values fail closed;
- B2 points preserve exact observed values.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd python && python -m pytest tests/test_observer_market_store.py -q`

Expected RED: window methods missing.

- [ ] **Step 3: Implement minimal deterministic replay**

Read only the bounded historical interval needed by current/anchors/local range. Never interpolate. Construct `ObserverMarketSnapshot` before any B2 conversion so database corruption is rejected at the E13 boundary.

- [ ] **Step 4: Run focused and full Python tests**

Run focused file, then full suite.

Expected GREEN.

- [ ] **Step 5: Commit**

Commit message: `feat: replay observer market windows`

---

### Task 4: Public API, authority firewall, cumulative audit, and seal

**Files:**
- Create: `python/src/shreks_brain/observer_market/__init__.py`
- Create: `python/tests/test_observer_market_public_api.py`
- Replace this plan with the final verification record after behavior is frozen.

**Interfaces:**
- Public exports are exactly the E13 schema constant, five E13 models/errors/store symbols, and `build_market_feature_points`.

- [ ] **Step 1: Write failing public-API/firewall tests**

Assert exact `__all__`, fresh-process import success, no imports from paper execution, registry mutation, promotion application, provider-network clients, signing/submission, or live executor packages, and no public method capable of writes or live execution.

- [ ] **Step 2: Verify RED**

Run: `cd python && python -m pytest tests/test_observer_market_public_api.py -q`

Expected RED because package exports are absent.

- [ ] **Step 3: Add minimal `__init__.py` exports**

No other behavior changes.

- [ ] **Step 4: Run full repository verification**

Run full Python suite, Rust/workspace CI, repository safety, and fresh-process import firewall through GitHub Actions.

- [ ] **Step 5: Audit scope**

Compare sealed E12 `2eb7a85606d23be70799f8f594bbc7c8164f0944` to E13 behavior head. Allowed changes only:

- E13 design / verification docs;
- `python/src/shreks_brain/observer_market/`;
- `python/tests/test_observer_market_*.py`.

Any other path blocks sealing.

- [ ] **Step 6: Replace this plan with immutable verification record**

Record behavior head, RED/GREEN anchors, CI run IDs, exact test counts, scope audit, authority boundary, and the statement that Phase F remains disabled.

- [ ] **Step 7: Commit the seal document only**

Commit message: `docs: seal E13 verification record`

- [ ] **Step 8: Prove seal invariant and final CI**

Behavior head -> seal candidate must be exactly one commit changing only this verification document. Final exact-head CI must be GREEN before the E13 head is treated as immutable.