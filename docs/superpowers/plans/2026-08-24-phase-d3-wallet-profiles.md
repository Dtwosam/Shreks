# Phase D3 Wallet Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic confidence-weighted wallet histories from D2 reconstructions while keeping sparse, inferred, mixed-asset, or missing research context explicit.

**Architecture:** Extend the existing pure Python `shreks_brain.wallets` package with immutable profile policy/context/output models plus one reducer. D3 consumes only caller-supplied D2 reconstructions and optional versioned point-in-time episode context; it performs no provider/storage reads and produces descriptive evidence rather than a wallet score.

**Tech Stack:** Python 3.12+, stdlib only, immutable dataclasses, existing `MarketRegime`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-d3-wallet-profiles-design.md`

## Global Constraints

- Base exactly sealed D2 head `3045062d0b36f3de49e029fa32d112ac874a141e`.
- Python owns D3 profile intelligence; Rust and D1/D2 behavior remain unchanged.
- Every D2 reconstruction must use the exact D3 profile as-of timestamp.
- Only CLOSED D2 episodes contribute to closed outcome metrics.
- Optional context uses local `observed_at_unix_ms`; future context fails closed.
- No provider/RPC/SQLite/wall-clock/FX/decimal reads inside profile construction.
- No wallet ranking, smart-wallet label, clustering, D5 feature, B/C trading change, signer, transaction submission, or live-money authority.
- No production evidence weights or confidence thresholds are shipped.
- Missing context never becomes zero/false.
- TDD RED -> exact failure -> GREEN.
- Minimize CI churn: one combined RED, one focused implementation GREEN, one final exact-head seal.

---

### Task 1: Combined D3 RED contract

**Files:**
- Create: `python/tests/test_wallet_profile_models.py`
- Create: `python/tests/test_wallet_profiles.py`
- Create: `python/tests/test_wallet_profile_public_api.py`

**Interfaces:**
- Consumes: existing D2 `WalletTradeReconstruction`, `WalletTradeEpisode`, `WalletTradeEpisodeState`, `WalletTradeEvidenceQuality`, and existing `MarketRegime`.
- Produces: the exact behavioral/public contract for D3 before production symbols exist.

- [ ] **Step 1: Write model/policy RED tests**

Pin a valid policy fixture:

```python
WalletProfilePolicy(
    version="d3-test-v1",
    direct_episode_weight=1.0,
    mixed_episode_weight=0.5,
    inferred_episode_weight=0.25,
    full_confidence_effective_sample_size=10.0,
)
```

Require validation failures for:

```python
WalletProfilePolicy(
    version="bad",
    direct_episode_weight=0.5,
    mixed_episode_weight=0.75,
    inferred_episode_weight=0.25,
    full_confidence_effective_sample_size=10.0,
)
```

and for non-finite/negative/boolean weights, zero direct weight, and non-positive full-confidence sample size.

Pin context validation with:

```python
WalletEpisodeProfileContext(
    wallet="wallet-a",
    candidate_mint="mint-a",
    episode_index=0,
    observed_at_unix_ms=2_000,
    context_version="ctx-v1",
    entry_quality_pct=80.0,
    entry_delay_from_candidate_discovery_ms=300,
    max_drawdown_pct=12.5,
    rug_exposed=False,
    regime=MarketRegime.NORMAL,
)
```

Require `entry_quality_pct` and `max_drawdown_pct` inside `0..100`, non-negative entry delay, tri-state rug evidence, valid enum regime, and immutable dataclasses.

- [ ] **Step 2: Write core aggregation RED tests**

Use D2-valid reconstruction fixtures and require:

```python
profile = build_wallet_profile(
    wallet="wallet-a",
    as_of_unix_ms=10_000,
    reconstructions=reconstructions,
    contexts=(),
    policy=policy,
)
```

Scenarios:

1. no reconstructions => all counts zero, effective sample `0.0`, evidence sample confidence `0.0`, weighted metrics `None`;
2. DIRECT `+30%`, MIXED `-10%`, INFERRED `+5%` closed episodes => effective sample `1.75`, confidence `0.175`, deterministic weighted median, weighted win rate, weighted hold median;
3. OPEN and UNRESOLVED episodes are counted but excluded from closed metrics;
4. halted D2 reconstruction increments `halted_reconstruction_count` without fabricating later history;
5. wrong wallet raises `ValueError`;
6. reconstruction as-of not exactly equal to profile as-of raises `ValueError`;
7. duplicate candidate-mint reconstruction raises `ValueError`;
8. future episode timestamps raise `ValueError`;
9. all closed episodes using one counter asset expose exact summed raw PnL and mint;
10. mixed counter assets make both aggregate raw-PnL fields `None`;
11. zero policy weight for all usable closed episodes leaves weighted metrics unknown.

- [ ] **Step 3: Write optional-context RED tests**

Require:

1. entry-quality, discovery-to-entry delay, max drawdown, and rug-exposure sample counts include only non-`None` fields;
2. their aggregates use the D2 episode evidence weight;
3. unknown rug exposure is excluded from its denominator rather than becoming false;
4. context may target only an existing CLOSED episode;
5. duplicate context identity raises `ValueError`;
6. context before episode close raises `ValueError`;
7. context after profile as-of raises `ValueError`;
8. mixed `context_version` values raise `ValueError`;
9. regime summaries include only known regimes in deterministic `HOT`, `NORMAL`, `WEAK`, `DEAD` order;
10. each regime summary has closed count, effective sample, weighted median return, and weighted win rate;
11. missing optional context leaves profile context metrics `None`, never zero.

- [ ] **Step 4: Add exact public API RED test**

Require `shreks_brain.wallets.__all__` to contain exactly the existing ten D2 symbols plus:

```text
WalletEpisodeProfileContext
WalletProfile
WalletProfilePolicy
WalletRegimeProfile
build_wallet_profile
```

- [ ] **Step 5: Commit the RED contract**

Commit only the three D3 test files.

Expected CI:

- repository safety GREEN,
- Rust/workspace GREEN,
- Python RED because the five D3 public symbols do not exist yet.

---

### Task 2: D3 immutable profile models

**Files:**
- Create: `python/src/shreks_brain/wallets/profile_models.py`
- Modify: `python/src/shreks_brain/wallets/__init__.py`
- Test: `python/tests/test_wallet_profile_models.py`
- Test: `python/tests/test_wallet_profile_public_api.py`

**Interfaces:**
- Consumes: `MarketRegime` from `shreks_brain.regime`.
- Produces: `WalletProfilePolicy`, `WalletEpisodeProfileContext`, `WalletRegimeProfile`, `WalletProfile`.

- [ ] **Step 1: Implement `WalletProfilePolicy`**

```python
@dataclass(frozen=True, slots=True)
class WalletProfilePolicy:
    version: str
    direct_episode_weight: float
    mixed_episode_weight: float
    inferred_episode_weight: float
    full_confidence_effective_sample_size: float
```

Validate finite numeric values, reject bools, require `0 <= inferred <= mixed <= direct <= 1`, direct `> 0`, and full-confidence sample `> 0`.

- [ ] **Step 2: Implement `WalletEpisodeProfileContext`**

```python
@dataclass(frozen=True, slots=True)
class WalletEpisodeProfileContext:
    wallet: str
    candidate_mint: str
    episode_index: int
    observed_at_unix_ms: int
    context_version: str
    entry_quality_pct: float | None
    entry_delay_from_candidate_discovery_ms: int | None
    max_drawdown_pct: float | None
    rug_exposed: bool | None
    regime: MarketRegime | None
```

Validate strings, non-negative identity/time/delay fields, finite percentages in `0..100`, bool-or-None rug evidence, and enum-or-None regime.

- [ ] **Step 3: Implement `WalletRegimeProfile`**

```python
@dataclass(frozen=True, slots=True)
class WalletRegimeProfile:
    regime: MarketRegime
    closed_episode_count: int
    effective_sample_size: float
    confidence_weighted_median_return_pct: float | None
    confidence_weighted_win_rate: float | None
```

Validate non-negative count/effective sample, finite median return when present, and win rate in `0..1` when present. Zero effective sample cannot claim weighted metrics.

- [ ] **Step 4: Implement `WalletProfile`**

Include exact fields from the design for identity/versioning, reconstruction/episode/evidence counts, effective sample/confidence, D2-derived weighted metrics, same-counter raw PnL, optional-context sample counts/aggregates, and regime summaries.

Validate:

- all counts non-negative,
- closed evidence-quality counts sum to closed count,
- episode-state counts sum to episode count,
- evidence sample confidence is finite `0..1`,
- weighted rates are finite `0..1`,
- context metric values cannot exist when their sample count is zero,
- same-counter PnL mint/value must be both present or both absent,
- regime summaries are unique and in deterministic enum order.

- [ ] **Step 5: Wire public exports**

Import the four models from `profile_models.py` and later `build_wallet_profile` from `profiles.py`; extend `__all__` without changing existing D2 names.

---

### Task 3: Pure confidence-weighted profile reducer

**Files:**
- Create: `python/src/shreks_brain/wallets/profiles.py`
- Modify: `python/src/shreks_brain/wallets/__init__.py`
- Test: `python/tests/test_wallet_profiles.py`

**Interfaces:**
- Consumes: D2 reconstruction/episode models and the four D3 profile models.
- Produces: `build_wallet_profile(...) -> WalletProfile`.

- [ ] **Step 1: Implement input normalization and structural validation**

Exact signature:

```python
def build_wallet_profile(
    *,
    wallet: str,
    as_of_unix_ms: int,
    reconstructions: tuple[WalletTradeReconstruction, ...],
    contexts: tuple[WalletEpisodeProfileContext, ...],
    policy: WalletProfilePolicy,
) -> WalletProfile:
    ...
```

Require tuples of exact domain objects, wallet match, exact reconstruction as-of match, unique candidate mints, and no episode timestamp after profile as-of.

Build a unique closed-episode index keyed by `(candidate_mint, episode_index)`.

Validate each context against that index, profile chronology, unique identity, and a single context version.

- [ ] **Step 2: Implement evidence weights**

Map:

```python
WalletTradeEvidenceQuality.DIRECT -> policy.direct_episode_weight
WalletTradeEvidenceQuality.MIXED -> policy.mixed_episode_weight
WalletTradeEvidenceQuality.INFERRED -> policy.inferred_episode_weight
```

No fallback branch may silently invent a weight.

- [ ] **Step 3: Implement deterministic weighted helpers**

Weighted median:

```python
def _weighted_median(rows: list[tuple[float, float, tuple[str, int]]]) -> float | None:
    usable = [row for row in rows if row[1] > 0.0]
    if not usable:
        return None
    usable.sort(key=lambda row: (row[0], row[2]))
    total = sum(weight for _, weight, _ in usable)
    threshold = total / 2.0
    cumulative = 0.0
    for value, weight, _ in usable:
        cumulative += weight
        if cumulative >= threshold:
            return value
    raise AssertionError("weighted median threshold must be reachable")
```

Weighted rate uses only positive-weight rows in its denominator and returns `None` when total usable weight is zero.

- [ ] **Step 4: Aggregate D2-derived metrics**

For CLOSED episodes only:

- count evidence qualities,
- sum effective sample weight,
- compute evidence sample confidence,
- weighted median return,
- weighted win rate,
- weighted median hold duration.

OPEN/UNRESOLVED episodes contribute only to state counts.

Count halted reconstructions separately.

- [ ] **Step 5: Aggregate raw counter PnL safely**

If and only if at least one CLOSED episode exists and every CLOSED episode has the same `counter_asset_mint`, return that mint plus exact sum of `estimated_realized_pnl_counter_raw`.

Otherwise return both raw aggregate fields as `None`.

- [ ] **Step 6: Aggregate optional research context**

For each optional field, include only contexts where that field is known. Use the target D2 episode's evidence weight.

Compute:

- weighted median entry quality,
- weighted median discovery-to-entry delay,
- weighted median max drawdown,
- weighted rug-exposure rate.

Record raw non-missing sample counts even when policy weight is zero.

- [ ] **Step 7: Build regime summaries**

Group known-regime contexts by `MarketRegime` in fixed order:

```python
(
    MarketRegime.HOT,
    MarketRegime.NORMAL,
    MarketRegime.WEAK,
    MarketRegime.DEAD,
)
```

For each non-empty group, compute closed count, effective sample size, weighted median D2 return, and weighted win rate.

- [ ] **Step 8: Run focused + full GREEN**

Run:

```bash
python -m pytest \
  python/tests/test_wallet_profile_models.py \
  python/tests/test_wallet_profiles.py \
  python/tests/test_wallet_profile_public_api.py -q
python -m pytest python/tests -q
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

Expected: all GREEN.

- [ ] **Step 9: Commit implementation**

Commit only:

```text
python/src/shreks_brain/wallets/__init__.py
python/src/shreks_brain/wallets/profile_models.py
python/src/shreks_brain/wallets/profiles.py
```

---

### Task 4: Documentation, verification record, and immutable seal

**Files:**
- Modify: `README.md` (append-only D3 section)
- Replace: `docs/superpowers/plans/2026-08-24-phase-d3-wallet-profiles.md` with verification record

**Interfaces:**
- Consumes: verified D3 behavior and CI evidence.
- Produces: durable architecture semantics plus final branch seal.

- [ ] **Step 1: Append README semantics**

Document:

- D3 consumes only D2 reconstructions plus optional caller-supplied versioned research context,
- exact as-of equality across reconstructions,
- CLOSED-only outcome aggregation,
- evidence-quality weighting and evidence-sample confidence are not wallet quality,
- no cross-counter raw PnL aggregation,
- context chronology/version rules,
- no ranking/clustering/smart-wallet feature/trading authority.

README must be additions-only relative to sealed D2.

- [ ] **Step 2: Replace this plan with concise verification record**

Record:

- sealed D2 base,
- RED commit/run and expected failure,
- GREEN commit/run and full test count,
- integrity properties proven,
- scope boundaries,
- final seal procedure.

Do not write the eventual final D3 SHA/run into tracked docs.

- [ ] **Step 3: Freeze tracked branch**

After the docs/verification commit, perform no further tracked writes.

- [ ] **Step 4: Audit exact D2 -> D3 diff**

Expected final files exactly:

```text
README.md
docs/superpowers/plans/2026-08-24-phase-d3-wallet-profiles.md
docs/superpowers/specs/2026-08-24-phase-d3-wallet-profiles-design.md
python/src/shreks_brain/wallets/__init__.py
python/src/shreks_brain/wallets/profile_models.py
python/src/shreks_brain/wallets/profiles.py
python/tests/test_wallet_profile_models.py
python/tests/test_wallet_profile_public_api.py
python/tests/test_wallet_profiles.py
```

Require README additions-only and no Rust/D1/D2 reconstruction/provider/B-C trading/signer/live-execution files changed.

- [ ] **Step 5: Run one fresh exact-head seal CI**

Require repository safety, Python, Rust tests, and workspace metadata all GREEN on the frozen exact head.

- [ ] **Step 6: Seal PR metadata only**

Put final D3 SHA, RED/GREEN/final CI run IDs, full-suite count, and exact diff audit in draft PR metadata. Leave the PR draft and unmerged.

D3 exit claim: Shreks can reproducibly summarize a wallet's available reconstructed history with explicit sample/evidence confidence and optional point-in-time research context, without asserting that the wallet is smart or useful for trading. D4 independence/clustering heuristics are next.
