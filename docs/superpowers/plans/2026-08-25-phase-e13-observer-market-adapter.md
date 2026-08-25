# Phase E13 Observer Market Replay Adapter Verification Record

## Status

Phase E13 behavior is frozen at:

`c7e5e43efa0f6cf0ea9e2b9d94ef589a77a4f1d2`

Branch: `feat/phase-e13-observer-market-adapter`

Stacked draft PR: #37, based exactly on sealed E12 head:

`2eb7a85606d23be70799f8f594bbc7c8164f0944`

This record replaces the implementation plan after behavior verification. The seal commit must change only this document. E13 is not treated as immutable until the seal invariant and final exact-head GitHub Actions run are both verified.

## Goal Proven

E13 adds a strict read-only bridge from the persisted Rust observer SQLite market history into deterministic B2-compatible market feature points.

The implemented boundary:

- opens the existing observer database using SQLite URI `mode=ro`;
- validates the required `token_candidates` and `market_snapshots` schema while tolerating additive future columns;
- resolves exact candidate identity and fails closed on ambiguous candidate rows;
- uses caller-supplied source priority, current staleness, and local-range lookback;
- selects one source/pair path and never mixes anchors or local-range data across paths;
- reconstructs current, 1m, 5m, and 15m observations using the sealed B2 anchor windows;
- never uses rows after `as_of_unix_ms`;
- leaves missing anchors as `None` rather than interpolating or inventing evidence;
- preserves observed market values when converting to B2 `MarketFeaturePoint` objects;
- fails closed when persisted market evidence violates the E13 model contract.

Schema identifier is exactly:

`e13-observer-market-v1`

## Design and Plan Anchors

- Design commit: `ee18355b2e6ca2fd4229912052cf3603b245b7f9` — `docs: design E13 observer market adapter`
- Plan commit: `c2d80c4aedc0ffb855e2c60a285bee822fce7d3c` — `docs: plan E13 observer market adapter`

## TDD Evidence

### Task 1 — Immutable E13 evidence models

Canonical corrected RED:

- commit `e4d45f77bd055555ed8e80841df5ac814f4136b8`
- CI `32849364739`
- Python failed during collection exactly because `shreks_brain.observer_market` did not exist
- Rust GREEN
- repository safety GREEN

Implementation:

- `2e27bc2829c04ffdc03a2d73372f10b9a2d3c5f5` — `feat: add E13 observer market models`

The first GREEN candidate exposed a fixture-only timestamp contamination: an anchor fixture moved `observed_at_unix_ms` backward but left `source_observed_at_unix_ms` in the future relative to that row. Production correctly rejected the invalid snapshot. The fixture was corrected without weakening the model contract.

Task 1 GREEN:

- head `c931157113576eabf4ae59e6203a4c1ec6cec313`
- CI `32849633558`
- Python: `2117 passed in 7.43s`
- Rust GREEN
- repository safety GREEN

### Task 2 — Read-only schema and candidate resolution

Canonical corrected RED:

- commit `e82a0d42fb53d3979da9c4a14c5798291f459626`
- CI `32849976828`
- Python failed during collection exactly because `shreks_brain.observer_market.store` did not exist
- Rust GREEN
- repository safety GREEN

Implementation:

- `47579fa418be1a1079d31aaa97eb6852e0e0643d` — `feat: read observer candidates safely`

Task 2 GREEN:

- head `47579fa418be1a1079d31aaa97eb6852e0e0643d`
- CI `32850131896`
- Python: `2125 passed in 8.11s`
- Rust GREEN
- repository safety GREEN

### Task 3 — Deterministic current/anchor market replay

Canonical corrected RED:

- commit `678cd30c3ec3c98fe4452ebfcb40457c28daa7cb`
- CI `32850520055`
- Python failed during collection exactly because `build_market_feature_points` was not implemented/exportable from the store module
- Rust GREEN
- repository safety GREEN

The pre-implementation replay fixture was corrected only to prevent a deliberately too-young 1m-anchor row from accidentally changing the independent local-range high assertion. The anchor contract itself was not weakened.

Implementation:

- `8909f6e13074762ffddddf6c1e47018413199455` — `feat: replay observer market windows`

Task 3 GREEN:

- head `8909f6e13074762ffddddf6c1e47018413199455`
- CI `32850716106`
- Python: `2133 passed in 7.66s`
- Rust GREEN
- repository safety GREEN

### Task 4 — Public API and authority firewall

RED:

- commit `36c66d1ef4b919d89e6653439eeb079af9fbe7be`
- CI `32850899777`
- Python: `3 failed, 2134 passed in 6.90s`
- failures were limited to the intentionally absent package-level `__all__` / public exports and consequent package file lookup
- Rust GREEN
- repository safety GREEN

Minimal export-only implementation:

- `c7e5e43efa0f6cf0ea9e2b9d94ef589a77a4f1d2` — `feat: expose E13 observer market API`

Behavior-head GREEN:

- head `c7e5e43efa0f6cf0ea9e2b9d94ef589a77a4f1d2`
- CI `32852119612`
- Python: `2137 passed in 7.93s`
- Rust GREEN
- repository safety GREEN

The public API test also proves a fresh-process import does not load paper execution, registry, promotion, shadow, or related authority packages.

## Exact Public API

`shreks_brain.observer_market.__all__` is exactly:

1. `OBSERVER_MARKET_SCHEMA_VERSION`
2. `ObserverMarketReadPolicy`
3. `ObserverCandidateIdentity`
4. `ObserverMarketSnapshot`
5. `ObservedMarketWindow`
6. `ObserverMarketReadError`
7. `ObserverMarketStore`
8. `build_market_feature_points`

`ObserverMarketStore` exposes only two public callable methods:

- `resolve_candidate`
- `load_window`

Neither method grants write, execution, promotion, signing, submission, or live-trading authority.

## Cumulative Scope Audit

Compared sealed E12:

`2eb7a85606d23be70799f8f594bbc7c8164f0944`

to E13 behavior head:

`c7e5e43efa0f6cf0ea9e2b9d94ef589a77a4f1d2`

Result: `ahead_by=14`, `behind_by=0`, exactly 9 changed files.

Changed files are exactly:

- `docs/superpowers/plans/2026-08-25-phase-e13-observer-market-adapter.md`
- `docs/superpowers/specs/2026-08-25-phase-e13-observer-market-adapter-design.md`
- `python/src/shreks_brain/observer_market/__init__.py`
- `python/src/shreks_brain/observer_market/models.py`
- `python/src/shreks_brain/observer_market/store.py`
- `python/tests/test_observer_market_models.py`
- `python/tests/test_observer_market_public_api.py`
- `python/tests/test_observer_market_replay.py`
- `python/tests/test_observer_market_store.py`

No pre-existing Python trading behavior file changed. No Rust file changed. No observer writer/storage implementation changed. No provider networking path changed. No B2 feature arithmetic changed. No safety policy changed. No paper execution or ledger behavior changed. No E5 evaluation behavior changed. No E6 registry mutation changed. No E7 shadow behavior changed. No E8 promotion behavior changed. No E9/E10/E11/E12 sealed behavior changed. No runtime live-mode, signing, submission, or live executor path changed.

## Authority and Safety Boundary

E13 is evidence-only and read-only.

It does not:

- write to the observer database;
- migrate the observer schema;
- fetch provider data over the network;
- manufacture missing safety evidence;
- manufacture missing market anchors;
- make a trading decision;
- execute or simulate a paper fill;
- mutate a registry candidate;
- promote or auto-promote a challenger;
- sign or submit a transaction;
- enable live mode;
- grant any component live-money authority.

Phase F remains disabled.

## Seal Invariant

Behavior head is fixed at:

`c7e5e43efa0f6cf0ea9e2b9d94ef589a77a4f1d2`

The seal candidate must be exactly one commit after that head and must modify only this verification document. After that commit, final exact-head CI must have all three lanes GREEN before the seal head is considered immutable.
