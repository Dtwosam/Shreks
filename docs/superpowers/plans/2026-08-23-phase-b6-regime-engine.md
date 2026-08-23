# Phase B6 Regime Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a pure, explainable, point-in-time `HOT / NORMAL / WEAK / DEAD` Solana memecoin regime engine with optional downgrade-only recent after-cost strategy-performance evidence.

**Architecture:** Create a focused `shreks_brain.regime` package beside unchanged B2 and setup code. Task 1 establishes immutable market/performance/policy/assessment models. Task 2 adds the deterministic classifier and performance overlay. Task 3 seals stable imports and documentation. No storage/provider/execution integration is permitted.

**Tech Stack:** Python 3.12+, dataclasses, `StrEnum`, pytest, existing repository CI.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b6-regime-engine-design.md`

## Global Constraints

- Base is verified B5 head `c943fc0c34ae89f29d840287224e3bd84f4f1ac1`.
- Existing B2 remains exactly `b2-v1`.
- Regime labels are exactly `HOT`, `NORMAL`, `WEAK`, `DEAD`.
- Market evidence is primary; recent strategy performance can only downgrade.
- No future-dated market or performance evidence may influence a historical regime.
- Missing critical market evidence fails closed to `DEAD` through the evaluator; model construction still preserves unknown values.
- No production default policy instance.
- No SQLite/provider/wall-clock reads from regime code.
- No setup evaluator imports inside the regime package.
- No wallet intelligence, Smart Wallet Cluster, trade score, `TradeDecision`, `TradeIntent`, sizing, paper fill, wallet/signing, swap submission, or live execution.
- Existing B1/B2/B3/B4b/B5 behavior remains unchanged.

## Task 1 — Immutable regime domain contract

**Files:**
- `python/src/shreks_brain/regime/models.py`
- `python/tests/test_regime_models.py`

**Produced types:**

```python
MarketRegime
RegimeReasonCode
RegimeMarketWindow
RecentStrategyPerformance
RegimePolicy
RegimeFinding
RegimeAssessment
```

The model contract pins exact regime/reason ordering, strict timestamp/count validation, ordered policy bands, bounded executable fractions, optional missing market/performance evidence, frozen dataclasses, and a `RegimeAssessment` with no execution or future-outcome authority.

Status: **complete and GREEN**.

## Task 2 — Pure regime classifier and performance overlay

**Files:**
- `python/src/shreks_brain/regime/engine.py`
- `python/tests/test_regime_engine.py`

**Public function:**

```python
def assess_regime(
    market: RegimeMarketWindow,
    policy: RegimePolicy,
    performance: RecentStrategyPerformance | None = None,
) -> RegimeAssessment:
    ...
```

The implementation order is fixed:

```text
derive timestamp-safe metrics
critical source/data-quality gates
base DEAD market thresholds
base WEAK market thresholds
base HOT-all / NORMAL-mixed resolution
performance timestamp integrity
performance sample/expectancy completeness
performance downgrade-only overlay
assessment construction
```

The classifier deliberately uses no weighted score. It preserves every applicable weak/dead market finding in deterministic metric order. Critical future/stale/incomplete market evidence fails closed. Recent after-cost performance is downgrade-only: sufficiently sampled negative expectancy can reduce risk appetite, while strong recent performance can never manufacture a hotter base market.

Status: **complete and GREEN**.

## Task 3 — Stable public API, README, exact-head seal

**Files:**
- `python/src/shreks_brain/regime/__init__.py`
- `python/tests/test_regime_public_api.py`
- `README.md`
- this plan for predecessor verification evidence only

Stable public imports:

```python
MarketRegime
RecentStrategyPerformance
RegimeAssessment
RegimeFinding
RegimeMarketWindow
RegimePolicy
RegimeReasonCode
assess_regime
```

The public API test also proves existing Fresh Launch, Graduation/Breakout, and First Pullback entry points remain importable and unchanged.

Status: **implementation/package GREEN; documentation committed; final immutable exact-head CI remains the completion gate after this tracked-file commit**.

## Verification Evidence

- Task 1 RED: `2b0eb78cccba8c2453b34ec642f81cb8f1e46655` / CI `32667044252` — Python failed only because `shreks_brain.regime` did not exist; repository safety was GREEN.
- Task 1 GREEN: `37ebbcf608b250966d1072d63fb8020396865edc` / CI `32667100110` — Rust, Python, workspace metadata, and repository safety all GREEN.
- Task 2 RED: `8974cf7bde3691719534d7f53bc3b9d994d459f1` / CI `32667213823` — Python failed only because `shreks_brain.regime.engine` did not exist; repository safety was GREEN.
- Task 2 GREEN: `3c8d2f01aba20359d36d2954c09269ef6f4deb3d` / CI `32667269660` — full GREEN.
- Task 3 RED: `4cb9dea76cfdc2ac3f71188c279fce49fbeb8032` / CI `32667342996` — Python failed only because package-level regime exports were absent; repository safety was GREEN.
- Task 3 package GREEN: `93f5cfbcf69c133d13812fee8d186de8a6445df6` / CI `32667376191` — Rust, Python, workspace metadata, and repository safety all GREEN.
- README documentation commit: `b52c92061d9b113be084507096637a47f60fc1a8`.

The immutable final branch SHA and its fresh CI run are intentionally recorded only in draft PR #9 metadata after this plan is no longer modified, avoiding a self-referential tracked-document verification loop.

## Self-Review

- Spec coverage: model, point-in-time, base classification, downgrade-only performance, stable API, documentation, and no-execution requirements are implemented.
- No production default regime policy exists.
- B2 remains `b2-v1` and all existing setup behavior remains independent.
- No storage aggregation, provider call, wallet intelligence, scoring, decision, risk, paper, or execution work is hidden in this phase.
- Recent winning performance cannot upgrade the base market regime.
