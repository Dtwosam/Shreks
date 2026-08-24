# Phase D5 Smart-Wallet Features Design

**Date:** 2026-08-24

## Goal

Expose point-in-time wallet intelligence to the Python feature layer without mutating the sealed `b2-v1` market feature schema, inventing independence, or granting wallet evidence any trading authority.

D5 combines current candidate-specific D2 reconstruction chronology, D3 confidence-weighted wallet histories, D4 relationship evidence, and optional D1 creator/deployer observations into one parallel versioned wallet feature vector suitable for later Smart Wallet Cluster setup research and Phase D6 dataset export.

## Source-of-truth alignment

The master design requires wallet features inside reproducible point-in-time research features and names these wallet-quality dimensions:

- number of independently strong wallets entering,
- weighted wallet quality,
- smart-wallet clustering,
- strong-wallet exits,
- creator/deployer activity.

The intended future signal is several independent wallets with meaningful, statistically credible histories accumulating the same token under favorable market conditions. D5 therefore preserves profile sample/confidence evidence and D4 uncertainty instead of reducing the wallet layer to `whale bought = bullish`.

## Base and scope

D5 bases exactly sealed D4 head `6cef1a3d2095569a74388963c4bfae415ba549fb`.

Production changes remain in `shreks_brain.features`. D1-D4 production behavior, `FEATURE_SCHEMA_VERSION == "b2-v1"`, `FeatureVector`, `FeatureInputs`, `build_feature_vector`, all existing setup/score/decision/risk interfaces, Rust/storage, and live-money behavior remain unchanged.

D5 ships no production wallet-strength thresholds and no default `WalletFeaturePolicy`.

## Architecture

D5 adds a separate `d5-wallet-v1` feature contract rather than widening `b2-v1` in place.

This avoids a silent schema change for existing B3-B9 consumers while still satisfying the build-order requirement that wallet intelligence become feature-engine data. Phase D6 can join market and wallet feature vectors by exact candidate mint and as-of timestamp; a later Smart Wallet Cluster setup can consume the D5 vector explicitly.

Files:

```text
python/src/shreks_brain/features/wallet_models.py
python/src/shreks_brain/features/wallet_engine.py
python/src/shreks_brain/features/__init__.py
```

## Public API

Append exactly these symbols after the sealed B2 feature API:

```text
WALLET_FEATURE_SCHEMA_VERSION
WalletHistoricalStrengthState
WalletFeaturePolicy
WalletFeatureInputs
WalletStrengthAssessment
WalletFeatureVector
build_wallet_feature_vector
```

`WALLET_FEATURE_SCHEMA_VERSION` is exactly `"d5-wallet-v1"`.

## WalletHistoricalStrengthState

Exact values:

```text
STRONG
NOT_STRONG
UNKNOWN
```

`UNKNOWN` is required when the active strength policy requires a metric that the profile does not contain and no already-known threshold failure proves `NOT_STRONG`.

## WalletFeaturePolicy

Immutable fields:

```python
@dataclass(frozen=True, slots=True)
class WalletFeaturePolicy:
    version: str
    entry_window_ms: int
    exit_window_ms: int
    creator_activity_window_ms: int
    minimum_effective_closed_sample_size: float
    minimum_evidence_sample_confidence: float
    minimum_median_return_pct: float
    minimum_win_rate: float
    maximum_rug_exposure_rate: float | None
    maximum_median_drawdown_pct: float | None
```

Validation:

- `version` non-empty,
- windows strictly positive integers and reject bools,
- minimum effective sample strictly positive finite,
- evidence confidence and win rate finite in `[0, 1]`, with minimum evidence confidence strictly positive,
- minimum median return strictly positive finite,
- optional maximum rug exposure finite in `[0, 1]`,
- optional maximum median drawdown finite in `[0, 100]`.

These values are research hypotheses, not production profitability claims.

## WalletFeatureInputs

Immutable fields:

```python
@dataclass(frozen=True, slots=True)
class WalletFeatureInputs:
    as_of_unix_ms: int
    candidate_mint: str
    reconstructions: tuple[WalletTradeReconstruction, ...]
    profiles: tuple[WalletProfile, ...]
    independence: WalletIndependenceAssessment
    observations: tuple[WalletObservation, ...]
    policy: WalletFeaturePolicy
```

Structural requirements:

1. `as_of_unix_ms` is non-negative and `candidate_mint` non-empty.
2. Every reconstruction is exactly at the D5 as-of time and for the same candidate mint.
3. Reconstruction wallets are unique.
4. Profiles are unique by wallet, exactly match the reconstruction wallet set, and use the exact D5 as-of time.
5. All profiles use one D3 profile-policy version; non-`None` context versions cannot be mixed.
6. D4 assessment uses the exact D5 as-of time and exactly the same wallet set.
7. Every supplied D1 observation targets the candidate mint and is locally observed no later than D5 as-of.
8. Inputs are caller-supplied only; D5 performs no external reads.

An empty reconstruction/profile wallet set is valid when the D4 assessment is correspondingly empty.

## WalletStrengthAssessment

For every candidate wallet, D5 emits a deterministic audit row:

```python
@dataclass(frozen=True, slots=True)
class WalletStrengthAssessment:
    wallet: str
    state: WalletHistoricalStrengthState
    effective_closed_sample_size: float
    evidence_sample_confidence: float
    median_return_pct: float | None
    win_rate: float | None
    rug_exposure_rate: float | None
    median_drawdown_pct: float | None
    failed_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]
```

Stable check names:

```text
effective_closed_sample_size
evidence_sample_confidence
median_return_pct
win_rate
rug_exposure_rate
median_drawdown_pct
```

Classification precedence:

1. evaluate every configured check,
2. if at least one known metric fails => `NOT_STRONG`,
3. else if at least one required configured metric is missing => `UNKNOWN`,
4. else => `STRONG`.

The first two core checks are always present in a valid D3 profile. Positive sample history is required by policy, so a wallet with no meaningful history cannot become `STRONG`.

Optional rug/drawdown checks are required only when their policy maximum is not `None`. Missing optional context then remains `UNKNOWN`, not a fabricated pass.

## Candidate activity chronology

D5 derives candidate entry/exit activity only from D2 episodes at the exact as-of timestamp.

A wallet is a **recent entrant** when at least one episode has:

```text
opened_at_unix_ms >= as_of_unix_ms - entry_window_ms
```

A wallet is a **recent exiter** when at least one CLOSED episode has:

```text
closed_at_unix_ms >= as_of_unix_ms - exit_window_ms
```

A wallet may legitimately appear in both sets when it exits and re-enters inside the configured windows. D5 does not overwrite that churn into a single direction.

OPEN, CLOSED, and UNRESOLVED chronology is consumed exactly as D2 produced it; D5 does not reconstruct trades again.

## Creator/deployer activity

D5 counts supplied D1 `CREATOR_ACTION` observations whose local availability time is inside:

```text
[as_of_unix_ms - creator_activity_window_ms, as_of_unix_ms]
```

The feature is named `creator_deployer_action_observation_count`. Zero means zero qualifying observations were supplied; it is not a claim that no creator/deployer activity happened outside the available evidence.

## Confidence-weighted wallet quality

D5 does not create a composite smart-wallet score.

For recent entrant wallets with positive D3 `evidence_sample_confidence` and known profile return/win-rate metrics, compute:

- `entry_quality_profile_sample_count`,
- `confidence_weighted_entry_median_return_pct` using deterministic weighted median of each wallet profile's already-confidence-weighted median return, weighted by `evidence_sample_confidence`,
- `confidence_weighted_entry_win_rate` using weighted mean of each wallet profile's already-confidence-weighted win rate, weighted by `evidence_sample_confidence`.

These are descriptive history aggregates, not expected return or candidate win probability.

For wallets classified `STRONG`, expose:

- `strong_wallet_count`,
- `strong_entry_wallet_count`,
- `strong_exit_wallet_count`,
- `confidence_weighted_strong_entry_count = sum(evidence_sample_confidence)`,
- `confidence_weighted_strong_exit_count = sum(evidence_sample_confidence)`.

The confidence-weighted counts remain bounded by their raw counts and represent evidence support, not probability.

## Independence and clustering features

D5 evaluates D4 pair states only among the current `STRONG` recent entrant set.

Expose:

```text
independently_strong_entry_wallet_count
strong_entry_all_pairs_independent_under_evidence
strong_entry_linked_pair_count
strong_entry_conflicting_pair_count
strong_entry_unknown_pair_count
strong_entry_coordination_cluster_count
strong_entry_max_independent_group_count_upper_bound
```

Rules:

- zero strong entrants => independently-strong count `0`, all-pairs flag `None`, all pair/cluster counts `0`;
- one strong entrant => independently-strong count `1`, all-pairs flag `True`;
- two or more strong entrants:
  - any `LINKED` or `CONFLICTING` pair => all-pairs flag `False` and exact independently-strong count `None`;
  - otherwise any `UNKNOWN` pair => all-pairs flag `None` and exact independently-strong count `None`;
  - only when every pair is `INDEPENDENT` => flag `True` and exact independently-strong count equals raw strong entrant count.

`strong_entry_coordination_cluster_count` counts D4 components containing at least two strong entrants, including components connected through non-entrant wallets.

`strong_entry_max_independent_group_count_upper_bound` counts D4 components containing at least one strong entrant. It remains explicitly an upper bound, not proof that separate components are independent.

## WalletFeatureVector

Immutable fields:

```python
@dataclass(frozen=True, slots=True)
class WalletFeatureVector:
    schema_version: str
    as_of_unix_ms: int
    candidate_mint: str
    wallet_feature_policy_version: str
    profile_policy_version: str | None
    profile_context_version: str | None
    relationship_policy_version: str
    wallet_count: int
    recent_entry_wallet_count: int
    recent_exit_wallet_count: int
    strong_wallet_count: int
    unknown_strength_wallet_count: int
    strong_entry_wallet_count: int
    strong_exit_wallet_count: int
    confidence_weighted_strong_entry_count: float
    confidence_weighted_strong_exit_count: float
    entry_quality_profile_sample_count: int
    confidence_weighted_entry_median_return_pct: float | None
    confidence_weighted_entry_win_rate: float | None
    independently_strong_entry_wallet_count: int | None
    strong_entry_all_pairs_independent_under_evidence: bool | None
    strong_entry_linked_pair_count: int
    strong_entry_conflicting_pair_count: int
    strong_entry_unknown_pair_count: int
    strong_entry_coordination_cluster_count: int
    strong_entry_max_independent_group_count_upper_bound: int
    creator_deployer_action_observation_count: int
    strength_assessments: tuple[WalletStrengthAssessment, ...]
    missing_features: tuple[str, ...]
```

`strength_assessments` are lexical by wallet. `missing_features` contains only nullable derived research fields that are actually unknown, in fixed order:

```text
confidence_weighted_entry_median_return_pct
confidence_weighted_entry_win_rate
independently_strong_entry_wallet_count
strong_entry_all_pairs_independent_under_evidence
```

## Determinism

All public outputs must be unchanged by input ordering.

- wallet strength rows sort lexically,
- recent entry/exit sets are sets keyed by wallet,
- profile weighted medians use `(value, wallet)` tie ordering,
- pair lookup uses canonical D4 lexical pair identities,
- cluster-derived counts use D4's already-deterministic component ordering.

## Fail-closed behavior

Reject:

- future D1 observations,
- reconstruction/profile/relationship as-of mismatch,
- candidate-mint mismatch,
- duplicate reconstruction/profile wallets,
- profile wallet-set mismatch,
- D4 wallet-set mismatch,
- mixed D3 profile-policy versions,
- mixed non-`None` D3 context versions,
- malformed tuples/domain objects.

Do not silently drop contradictory inputs.

## Non-goals

D5 does not:

- modify `b2-v1`,
- alter existing setup/score/decision/risk behavior,
- implement Smart Wallet Cluster entry eligibility,
- create a composite wallet score,
- rank or label wallets globally as “smart”,
- prove wallet ownership/control/identity,
- read providers/RPC/SQLite/wall clock,
- create `TradeIntent`, position size, signer, transaction, or live execution path,
- ship production thresholds.

A later setup integration may require multiple explicitly independent strong entrants from `d5-wallet-v1`; Phase E must then prove on unseen post-cost data whether the feature adds value.
