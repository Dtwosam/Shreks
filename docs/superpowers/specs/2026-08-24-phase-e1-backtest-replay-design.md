# Phase E1 Historical Backtest / Replay Design

**Date:** 2026-08-24

## Goal

Create a deterministic Python replay core that recomputes the existing setup -> B7 score -> B8 entry-decision path at historical timestamps using only evidence that was available by each decision time.

E1 is the first evaluation-phase execution primitive. It produces replayed D6-compatible candidate snapshots for later baselines, chronological validation, and trading evaluation. It does not calculate profitability, train models, select a champion, or simulate live execution.

## Source-of-truth alignment

The project source of truth requires:

- E1: replay decisions using only data available at each historical timestamp,
- point-in-time-safe features with no future information,
- rejected/observed candidates retained for learning,
- a learning loop of `OBSERVE -> FEATURE SNAPSHOT -> DECISION -> FUTURE OUTCOME -> DATASET -> TRAIN -> VALIDATE -> PAPER/SHADOW -> COMPARE -> PROMOTE OR REJECT`,
- backtest/data-leakage tests,
- later E2 baselines, E3 model training, E4 chronological validation, and E5 after-cost trading evaluation.

E1 therefore recomputes historical entry decisions while keeping future outcomes outside the decision input type.

## Base and scope

E1 bases exactly sealed D6 head:

`d7ea5fbcd2eab893b540c940eab8d24ff40a3903`

E1 adds a new pure package under:

```text
python/src/shreks_brain/backtest/
```

E1 does not modify sealed B1-B9, C1-C6, D1-D6 behavior or schemas.

The existing D6 schema remains exactly `d6-research-v1` and B2 remains exactly `b2-v1`.

## Architectural choice

E1 recomputes the current three setup families before scoring and deciding. It does **not** merely feed historical stored scores into B8.

Why:

- a stored score freezes historical setup/scoring behavior and cannot validate changes to those policy layers,
- the current setup evaluators are already deterministic and point-in-time aware,
- the existing B7 and B8 engines are the authoritative scoring/decision implementations,
- replay should compose those engines rather than duplicate formulas.

E1 still does not rebuild B1 safety or B2 features from provider/storage payloads. Caller-supplied `FeatureVector` values are already the versioned point-in-time feature boundary. Historical input assembly from SQLite/Parquet is separate adapter work and must not be hidden inside replay semantics.

## Supported decision path

For every replay case:

```text
historical decision-time evidence
    -> setup evaluator
    -> score_candidate
    -> decide_entry
    -> replayed TradeDecision
    -> join future outcome bundle
    -> ResearchSnapshotInputs
```

Supported current setup families:

- `fresh_launch_continuation`,
- `graduation_breakout`,
- `first_pullback`.

D5 wallet features are carried through every replay and into the resulting D6 snapshot, but E1 does not inject them into B7 or B8 because the sealed current score/decision path does not consume D5 wallet features. A future wallet-driven setup must be introduced explicitly and evaluated on unseen data rather than smuggled into E1.

## Public API

E1 exposes exactly:

```text
BACKTEST_REPLAY_SCHEMA_VERSION
ReplaySetupKind
ReplayDecisionInput
ReplayOutcomeBundle
ReplayPolicySet
ReplayRun
replay_entry_decisions
```

`BACKTEST_REPLAY_SCHEMA_VERSION` is exactly:

```text
e1-replay-v1
```

## ReplaySetupKind

```python
class ReplaySetupKind(StrEnum):
    FRESH_LAUNCH_CONTINUATION = "fresh_launch_continuation"
    GRADUATION_BREAKOUT = "graduation_breakout"
    FIRST_PULLBACK = "first_pullback"
```

The values intentionally equal the sealed setup names.

## ReplayDecisionInput

Future labels do not appear in this type.

```python
@dataclass(frozen=True, slots=True)
class ReplayDecisionInput:
    candidate_mint: str
    market_features: FeatureVector
    wallet_features: WalletFeatureVector
    regime: RegimeAssessment
    setup_kind: ReplaySetupKind
    graduation_context: GraduationContext | None
    pullback_context: PullbackContext | None
```

### Structural validation

1. `candidate_mint` is non-empty.
2. Types are exact sealed domain types rather than duck-typed dictionaries.
3. `market_features.schema_version == "b2-v1"`.
4. `wallet_features.schema_version == "d5-wallet-v1"`.
5. `wallet_features.candidate_mint == candidate_mint`.
6. wallet and market features share exact `as_of_unix_ms`.
7. regime shares exact market `as_of_unix_ms`.
8. market source observation cannot be after as-of and `source_age_ms` must exactly reconcile.
9. Fresh Launch requires both optional context fields to be `None`.
10. Graduation/Breakout requires `pullback_context is None`; its graduation context may be `None` because missing verified graduation is legitimate historical evidence and the existing setup evaluator will classify it.
11. A supplied graduation context must target the same mint and its decision-safe local `detected_at_unix_ms` must not be after replay as-of. Optional chain occurrence time is never used to backdate availability.
12. First Pullback requires `graduation_context is None`; its pullback context may be `None` because absence of observed structure is legitimate historical evidence.
13. A supplied pullback context's trough timestamp must not be after the B2 market source observation. This prevents a current feature snapshot from borrowing a newer trough.

The identity of a replay decision input is:

```text
(candidate_mint, market_features.as_of_unix_ms)
```

## ReplayOutcomeBundle

Future outcomes use a separate type and separate function argument so they cannot become setup/scoring inputs accidentally.

```python
@dataclass(frozen=True, slots=True)
class ReplayOutcomeBundle:
    candidate_mint: str
    as_of_unix_ms: int
    outcomes: tuple[ResearchOutcomeLabel, ...]
```

Requirements:

- non-empty candidate mint,
- non-negative as-of timestamp,
- exactly seven D6 `ResearchOutcomeLabel` values,
- canonical horizon order `60, 300, 900, 1800, 3600, 14400, 86400`,
- every label baseline equals the bundle as-of time.

Pending labels are valid. E1 does not require the future to have fully elapsed merely to replay a historical decision.

The bundle identity is the same `(candidate_mint, as_of_unix_ms)` pair as the decision input.

## ReplayPolicySet

```python
@dataclass(frozen=True, slots=True)
class ReplayPolicySet:
    version: str
    fresh_launch_policy: FreshLaunchPolicy | None
    graduation_breakout_policy: GraduationBreakoutPolicy | None
    first_pullback_policy: FirstPullbackPolicy | None
    score_policy: ScorePolicy
    decision_policy: DecisionPolicy
```

Validation:

- version non-empty,
- setup policies are exact expected policy types or `None`,
- at least one setup policy is configured,
- score and decision policies are exact sealed types,
- score policy must require the sealed B2 schema,
- decision policy's required score-policy version must equal the supplied score-policy version.

A replay input whose setup kind has no configured setup policy is a run-configuration error and fails closed with `ValueError`; it is not converted into a historical `REJECT` or `WATCH` because the strategy under test was not actually defined.

E1 ships no default policies or thresholds.

## Replay execution

```python
def replay_entry_decisions(
    decision_inputs: tuple[ReplayDecisionInput, ...],
    outcome_bundles: tuple[ReplayOutcomeBundle, ...],
    policies: ReplayPolicySet,
) -> ReplayRun:
    ...
```

### Preflight rules

Before executing any setup evaluator:

1. all arguments must use exact required container/domain types,
2. `decision_inputs` must be non-empty,
3. decision-input identities must be unique,
4. outcome-bundle identities must be unique,
5. outcome identities must exactly equal decision-input identities: no missing and no future-only extra bundle,
6. every setup kind used by the input set must have a configured setup policy.

Fail the entire replay before producing partial output if any preflight rule fails.

### Deterministic order

Replay cases sort by:

```text
(as_of_unix_ms, candidate_mint)
```

Input ordering must not affect output.

### Setup dispatch

For each decision input:

- Fresh Launch -> `assess_fresh_launch(market_features, fresh_launch_policy)`
- Graduation/Breakout -> `assess_graduation_breakout(market_features, graduation_context, graduation_breakout_policy)`
- First Pullback -> `assess_first_pullback(market_features, pullback_context, first_pullback_policy)`

No setup formula is copied into E1.

### Score and decision

After setup assessment:

```python
score = score_candidate(
    market_features,
    setup_assessment,
    regime,
    policies.score_policy,
)

decision = decide_entry(
    candidate_mint,
    score,
    policies.decision_policy,
)
```

E1 never modifies the returned B7/B8 domain objects.

### Future-label isolation

The implementation must compute setup, score, and decision before reading the matching `ReplayOutcomeBundle.outcomes` for that case.

Outcome metrics are never passed to:

- any setup evaluator,
- `score_candidate`,
- `decide_entry`.

A test must prove that changing only future outcome metrics leaves setup/score/decision outputs byte-for-byte/domain-equal while the attached D6 labels change.

## D6-compatible replay output

After the replayed decision exists, E1 joins the matching outcome bundle and constructs the sealed D6 object:

```python
ResearchSnapshotInputs(
    candidate_mint=...,
    market_features=...,
    wallet_features=...,
    regime=...,
    score=replayed_score,
    decision=replayed_decision,
    outcomes=outcome_bundle.outcomes,
)
```

This deliberately reuses D6's cross-domain reconciliation and label-baseline validation.

The returned snapshots can be passed unchanged to:

- `build_research_dataset`,
- `write_research_parquet`.

E1 does not create a second research-row schema.

## ReplayRun

```python
@dataclass(frozen=True, slots=True)
class ReplayRun:
    schema_version: str
    policy_set_version: str
    score_policy_version: str
    decision_policy_version: str
    snapshots: tuple[ResearchSnapshotInputs, ...]
    reject_count: int
    watch_count: int
    enter_count: int
    min_as_of_unix_ms: int
    max_as_of_unix_ms: int
```

Requirements:

- exact E1 schema version,
- non-empty policy/version strings,
- non-empty snapshots,
- snapshots unique and sorted by `(as_of_unix_ms, candidate_mint)`,
- every replayed decision action is pre-entry `REJECT`, `WATCH`, or `ENTER`,
- action counts exactly reconcile to snapshot count,
- timestamp bounds exactly match snapshots.

`ReplayRun` contains no return, PnL, expectancy, profit factor, drawdown, win rate, calibration, cost, or promotion metric. Those belong to E5.

## Point-in-time guarantees

E1 guarantees:

- no future labels exist in `ReplayDecisionInput`,
- B2/D5/regime evidence must align to the replay timestamp,
- future local graduation evidence is rejected,
- pullback structure newer than the market source is rejected,
- outcome identities/baselines must match decision identities exactly,
- setup/scoring/decision functions execute before outcome labels are joined,
- no wall-clock reads influence replay,
- no provider/storage/filesystem lookup can inject later information inside the replay core,
- output order is independent of input order.

E1 cannot prove that an external caller fabricated a point-in-time `FeatureVector`; that is why historical input assembly must preserve D6/B2 provenance and later E4 chronological validation must independently audit dataset splits and timing.

## What E1 is not

E1 does not:

- read SQLite or Parquet,
- discover candidate timestamps,
- rebuild B1 safety from raw provider data,
- rebuild B2 features from raw market snapshots,
- mutate D5 wallet features,
- invent a smart-wallet setup,
- simulate B9 risk sizing,
- simulate C1 fills or C3 accounting,
- replay C4/C5 position lifecycle,
- calculate returns/PnL/expectancy/drawdown,
- create E2 baselines,
- train E3 models,
- create E4 train/test splits,
- perform E5 evaluation,
- promote a champion/challenger,
- create a signer, transaction, or live-money path.

The narrower boundary is intentional: E1 proves historical decision reconstruction first. Evaluation layers can then consume deterministic replay output without being allowed to alter the historical decision path.

## Testing requirements

Tests must cover at least:

1. exact public API and immutable models,
2. malformed type/container rejection,
3. schema/as-of/source-age reconciliation,
4. candidate/wallet mismatch,
5. setup/context compatibility,
6. future graduation rejection,
7. future pullback-structure rejection,
8. policy compatibility and missing setup policy rejection,
9. exact identity-set join between decisions and outcomes,
10. exact seven-horizon outcome validation,
11. deterministic sorting and duplicate rejection,
12. all three setup-family dispatch paths,
13. existing setup -> B7 -> B8 engine reuse,
14. preservation of `REJECT`, `WATCH`, and `ENTER`,
15. future-label mutation cannot change replayed score or decision,
16. D6 `build_research_dataset` compatibility,
17. input-order independence,
18. no PyArrow/SQLite/provider import requirement for replay.

## Exit criterion

E1 is complete when Shreks can deterministically recompute the current setup -> score -> entry-decision path for a historical set of candidates using only point-in-time decision evidence, attach future labels only after those decisions exist, and emit D6-compatible snapshots that later evaluation phases can consume without re-running trading logic.
