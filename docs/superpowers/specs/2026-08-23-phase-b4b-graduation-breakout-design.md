# Phase B4b Graduation/Breakout Design

**Status:** Approved in chat on 2026-08-23  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`  
**Base:** verified Phase B4a head `b50f80d82ca25aac2d1da99269c8f9ca54175525`

## 1. Purpose

Phase B4b implements Shreks' second explicit setup family: **Graduation/Breakout**.

The master design defines this setup as a token transitioning from random launch behavior into sustained liquidity and participation. Phase B4a now provides the prerequisite protocol-verified Pump.fun -> PumpSwap lifecycle evidence, including the first locally observed migration time, optional on-chain block time, pool, quote mint, signature, slot, provider, and venue transition.

B4b combines that verified lifecycle context with the existing B2 `FeatureVector` to produce a deterministic, auditable setup assessment. It does not place trades.

## 2. Design Amendment to the B4a Exit Sequence

The B4a design originally anticipated a separate lifecycle-feature phase before a later setup phase. The approved B4b design intentionally avoids that extra shared-schema step.

B4b does **not** create B2 `b2-v2` or add graduation fields to the common `FeatureVector`. Instead, Graduation/Breakout receives a small immutable setup-specific `GraduationContext` beside the existing unchanged B2 `FeatureVector`.

This collapses the previously anticipated lifecycle-feature/setup split into one B4b slice because:

1. only Graduation/Breakout currently requires verified graduation identity;
2. changing B2 would version every existing feature consumer for one setup-specific fact;
3. setup code can remain pure without querying SQLite;
4. the context boundary preserves B4a's normalized lifecycle truth without leaking provider payloads or storage rows into strategy logic.

If graduation/lifecycle data later proves broadly useful across several setup families, a future feature-schema version may promote measured lifecycle features into shared B2+ inputs. B4b does not pre-commit the system to that migration.

## 3. Profitability Hypothesis

B4b tests a narrow research hypothesis:

> after a protocol-verified Pump graduation, tokens that retain acceptable executability while showing sustained participation, volume velocity, buy pressure, short-term momentum, improving liquidity, and price structure near local highs may have better continuation expectancy than blindly buying the migration event.

This is not a claim of profitability. Numerical thresholds are explicit policy hypotheses and must later be calibrated on Shreks' own unseen, point-in-time, post-cost outcomes.

The setup intentionally avoids two forms of false confidence:

- treating PumpSwap pair presence as proof of graduation;
- treating the migration event itself as sufficient evidence to enter.

## 4. Inputs and Purity Boundary

Public evaluator:

```python
def assess_graduation_breakout(
    features: FeatureVector,
    graduation: GraduationContext | None,
    policy: GraduationBreakoutPolicy,
) -> GraduationBreakoutAssessment:
    ...
```

The evaluator is pure and deterministic.

It may consume only:

- the existing B2 `FeatureVector` (`b2-v1` remains unchanged);
- normalized B4a lifecycle context supplied by the caller;
- explicit versioned policy configuration.

It must not:

- query SQLite;
- call providers;
- inspect Rust structs or raw Pump/Helius payloads;
- infer graduation from venue/pair presence;
- use future outcome checkpoints, realized PnL, MFE, or MAE;
- create a trade intent, position size, fill, order, signer request, or transaction.

The upstream assembly layer is responsible for pairing the correct mint's feature vector and lifecycle context. B4b preserves the lifecycle mint in its assessment for auditability, but the current B2 vector has no mint field and therefore cannot independently cross-check identity.

## 5. `GraduationContext`

Immutable normalized context:

```python
@dataclass(frozen=True, slots=True)
class GraduationContext:
    event_type: str
    provider: str
    mint: str
    quote_mint: str
    from_venue: str
    to_venue: str
    pool_address: str
    signature: str
    slot: int
    detected_at_unix_ms: int
    occurred_at_unix_ms: int | None
```

Canonical values used by B4a are:

```text
event_type = pump_graduation
from_venue = pump_fun_bonding_curve
to_venue   = pump_swap
```

Structural validation requires:

- all string identity fields are non-empty;
- `slot` is a non-negative integer and not `bool`;
- `detected_at_unix_ms` is a non-negative integer;
- `occurred_at_unix_ms`, when present, is a non-negative integer.

`occurred_at_unix_ms` is audit metadata only in B4b-v1. It must never replace, backdate, or advance the decision clock.

## 6. Decision-Safe Graduation Time

`detected_at_unix_ms` is the only graduation timestamp used for eligibility timing.

For an evaluation at `features.as_of_unix_ms`:

```text
seconds_since_graduation =
    (features.as_of_unix_ms - graduation.detected_at_unix_ms) / 1000
```

If `detected_at_unix_ms > features.as_of_unix_ms`, the context is contradictory for that historical decision and the assessment is `BLOCKED`.

The optional transaction block time may be earlier than local detection and is useful for later research, but using it as the decision timestamp would introduce information Shreks had not necessarily observed yet. B4b therefore never uses it to make a candidate appear eligible earlier.

## 7. Stable Setup Identity and State

Setup name:

```text
graduation_breakout
```

B4b reuses the existing shared `SetupState` enum:

- `BLOCKED`
- `WATCH`
- `READY`

Semantics are unchanged:

- `BLOCKED`: a hard lifecycle, safety, freshness, executability, timing, or anti-chase condition prevents entry consideration now;
- `WATCH`: no hard blocker is proven, but the graduation is too recent, required evidence is missing, or one or more confirmations are not satisfied;
- `READY`: lifecycle, safety, timing, freshness, executability, anti-chase, and all B4b confirmations pass.

`READY` is setup eligibility only. It is not `ENTER` and carries no execution authority.

## 8. `GraduationBreakoutReasonCode`

Stable reason codes are evaluated in deterministic order.

### Hard blockers

- `SAFETY_NOT_PASS`
- `GRADUATION_NOT_VERIFIED`
- `GRADUATION_EVENT_NOT_PUMP`
- `GRADUATION_VENUE_TRANSITION_INVALID`
- `GRADUATION_AFTER_AS_OF`
- `POST_GRADUATION_WINDOW_EXPIRED`
- `SOURCE_DATA_TOO_OLD`
- `LIQUIDITY_BELOW_MINIMUM`
- `EXIT_PRICE_IMPACT_TOO_HIGH`
- `MOVE_TOO_EXTENDED`

### Watch / confirmation reasons

- `GRADUATION_TOO_RECENT`
- `LIQUIDITY_UNKNOWN`
- `EXIT_PRICE_IMPACT_UNKNOWN`
- `TX_COUNT_M5_UNKNOWN`
- `TX_COUNT_M5_BELOW_MINIMUM`
- `VOLUME_VELOCITY_UNKNOWN`
- `VOLUME_VELOCITY_BELOW_MINIMUM`
- `BUY_FRACTION_M5_UNKNOWN`
- `BUY_FRACTION_M5_BELOW_MINIMUM`
- `BUY_PRESSURE_ACCELERATION_UNKNOWN`
- `BUY_PRESSURE_ACCELERATION_BELOW_MINIMUM`
- `RETURN_1M_UNKNOWN`
- `RETURN_1M_BELOW_MINIMUM`
- `LIQUIDITY_CHANGE_5M_UNKNOWN`
- `LIQUIDITY_CHANGE_5M_BELOW_MINIMUM`
- `DISTANCE_FROM_LOCAL_HIGH_UNKNOWN`
- `TOO_FAR_BELOW_LOCAL_HIGH`
- `RANGE_POSITION_UNKNOWN`
- `RANGE_POSITION_BELOW_MINIMUM`

### Ready marker

- `ALL_CONFIRMATIONS_PASSED`

## 9. `GraduationBreakoutFinding`

B4b uses a dedicated immutable finding type rather than widening B3's existing `SetupFinding` annotation:

```python
@dataclass(frozen=True, slots=True)
class GraduationBreakoutFinding:
    code: GraduationBreakoutReasonCode
    message: str
    observed_value: float | int | str | None = None
    threshold_value: float | int | None = None
```

This avoids altering B3's stable public model merely to support a second reason-code enum.

Consumers use `code` for logic. Human-readable `message` text is explanatory only.

## 10. `GraduationBreakoutPolicy`

Immutable versioned policy with no production trading defaults:

```python
@dataclass(frozen=True, slots=True)
class GraduationBreakoutPolicy:
    version: str
    min_seconds_since_graduation: float
    max_seconds_since_graduation: float
    max_source_age_ms: int
    min_liquidity_usd: float
    max_exit_price_impact_pct: float
    min_tx_count_m5: int
    min_volume_velocity_ratio: float
    min_buy_fraction_m5: float
    min_buy_pressure_acceleration: float
    min_return_1m_pct: float
    max_return_1m_pct: float
    min_liquidity_change_5m_pct: float
    min_distance_from_local_high_pct: float
    min_range_position_pct: float
```

Validation:

- version is a non-empty string;
- all numeric policy values are finite;
- graduation ages, source age, liquidity, exit impact, transaction count, and volume velocity are non-negative;
- `max_seconds_since_graduation > min_seconds_since_graduation`;
- `min_buy_fraction_m5` is within `[0, 1]`;
- `min_range_position_pct` is within `[0, 100]`;
- `min_distance_from_local_high_pct <= 0`;
- `max_return_1m_pct >= min_return_1m_pct`.

The evaluator embeds no numerical trading thresholds. Tests instantiate explicit policies.

## 11. `GraduationBreakoutAssessment`

Immutable result:

```python
@dataclass(frozen=True, slots=True)
class GraduationBreakoutAssessment:
    setup_name: str
    policy_version: str
    feature_schema_version: str
    as_of_unix_ms: int
    graduation_mint: str | None
    graduation_detected_at_unix_ms: int | None
    seconds_since_graduation: float | None
    state: SetupState
    confirmation_score: float
    confirmations_passed: int
    confirmations_required: int
    findings: tuple[GraduationBreakoutFinding, ...]
```

`setup_name` is exactly `graduation_breakout`.

For B4b-v1:

```text
confirmations_required = 8
confirmation_score = confirmations_passed / 8 * 100
```

The score measures checklist completeness only. It is not confidence, win probability, expected return, position size, or final trade score.

When graduation is missing, graduation audit fields are `None`. When context exists, the assessment preserves its mint and local detection time even if the candidate is blocked.

## 12. Evaluation Order

The evaluator collects findings without short-circuiting confirmation calculation where the required feature evidence exists. This preserves research information for blocked candidates.

### 12.1 Hard lifecycle and safety gates

Evaluate in this fixed order:

1. B1 safety decision is not `PASS` -> `SAFETY_NOT_PASS`;
2. `graduation is None` -> `GRADUATION_NOT_VERIFIED`;
3. context exists but `event_type != "pump_graduation"` -> `GRADUATION_EVENT_NOT_PUMP`;
4. context exists but transition is not exactly `pump_fun_bonding_curve -> pump_swap` -> `GRADUATION_VENUE_TRANSITION_INVALID`;
5. context exists and `detected_at_unix_ms > features.as_of_unix_ms` -> `GRADUATION_AFTER_AS_OF`.

A wrong event or venue transition is never reinterpreted as weak evidence. B4b only models the verified Pump graduation setup described by B4a.

### 12.2 Post-graduation time window

If a valid decision-time graduation age can be computed:

- age above `max_seconds_since_graduation` -> hard `POST_GRADUATION_WINDOW_EXPIRED`;
- age below `min_seconds_since_graduation` -> watch `GRADUATION_TOO_RECENT`.

Boundary equality passes.

### 12.3 Freshness and executability hard gates

Evaluate:

1. `features.source_age_ms > max_source_age_ms` -> `SOURCE_DATA_TOO_OLD`;
2. known `features.liquidity_usd < min_liquidity_usd` -> `LIQUIDITY_BELOW_MINIMUM`;
3. known `features.exit_price_impact_pct > max_exit_price_impact_pct` -> `EXIT_PRICE_IMPACT_TOO_HIGH`;
4. known `features.return_1m_pct > max_return_1m_pct` -> `MOVE_TOO_EXTENDED`.

The one-minute return ceiling is deliberately a **guard**, not an extra positive confirmation. Very strong short-window appreciation can therefore block a candidate instead of being rewarded indefinitely.

Early after graduation, B2's one-minute anchor may include some pre-graduation price movement. B4b treats that ambiguity conservatively: it may trigger anti-chase protection, but it does not create an additional graduation-specific signal beyond the ordinary 1m confirmation below.

### 12.4 Required executability evidence

Missing liquidity -> `LIQUIDITY_UNKNOWN` and prevents `READY`.

Missing exit price impact -> `EXIT_PRICE_IMPACT_UNKNOWN` and prevents `READY`.

Missing values never become zero or optimistic passes.

## 13. Eight Equal-Weight Confirmations

B4b-v1 evaluates exactly eight confirmations in this order:

1. `tx_count_m5 >= min_tx_count_m5`;
2. `volume_velocity_ratio >= min_volume_velocity_ratio`;
3. `buy_fraction_m5 >= min_buy_fraction_m5`;
4. `buy_pressure_acceleration >= min_buy_pressure_acceleration`;
5. `return_1m_pct >= min_return_1m_pct`;
6. `liquidity_change_5m_pct >= min_liquidity_change_5m_pct`;
7. `distance_from_local_high_pct >= min_distance_from_local_high_pct`;
8. `range_position_pct >= min_range_position_pct`.

Every confirmation contributes exactly one point. Equality passes.

Missing confirmation values generate the matching `UNKNOWN` finding and do not pass. Known values below threshold generate the matching threshold finding.

No confirmation receives extra weight for being far beyond threshold.

### Why there is no positive 5-minute-return confirmation

B4b deliberately omits B2 `return_5m_pct` from its positive confirmation set. Immediately after graduation, a 5-minute anchor can substantially represent pre-graduation bonding-curve behavior. Treating that cross-regime move as post-graduation breakout strength would blur the lifecycle transition B4b is meant to measure.

### Why there is no momentum-acceleration confirmation

`momentum_acceleration_1m_vs_5m` inherits the same mixed-regime problem because the 5-minute component may precede migration. B4b-v1 therefore excludes it rather than pretending it is graduation-specific evidence.

Future research may introduce true post-graduation anchors once Shreks has enough lifecycle-aligned observations to calculate them without leakage or regime mixing.

## 14. State Resolution

After all applicable gates and confirmations are evaluated:

```text
if any hard blocker:
    BLOCKED
elif graduation is too recent or executability evidence is missing:
    WATCH
elif confirmations_passed < 8:
    WATCH
else:
    READY
```

If state is `READY`, append exactly one final `ALL_CONFIRMATIONS_PASSED` finding.

A `READY` B4b-v1 assessment therefore proves only that, at the current timestamp:

- B1 safety is `PASS`;
- a verified Pump graduation context exists;
- the transition is Pump.fun bonding curve -> PumpSwap;
- local graduation detection is not from the future;
- the candidate is inside the configured post-graduation window;
- source data is fresh;
- known liquidity and exit impact pass hard executability gates;
- the 1-minute move is not beyond the configured anti-chase ceiling;
- required liquidity and exit-impact evidence is present;
- all eight confirmations pass.

## 15. Missing Data and Fail-Closed Semantics

Missing evidence never passes a condition and never becomes zero.

A missing graduation context is a hard block because this setup specifically requires protocol-verified migration evidence.

Missing market/executability evidence that may arrive later remains `WATCH` unless another hard blocker exists.

B4b does not infer:

- graduation from PumpSwap market presence;
- quote mint from venue;
- pool identity from DEX metadata;
- missing flow or transaction values;
- missing return anchors;
- missing local-high/range structure.

## 16. Safety Precedence and Research Preservation

B1 remains absolute. `SafetyDecision.REJECT` or `SafetyDecision.INCOMPLETE` makes B4b `BLOCKED` regardless of lifecycle strength or confirmation score.

When a candidate is blocked for safety, lifecycle, staleness, liquidity, exit impact, expiry, or anti-chase reasons, B4b still computes any feature-based confirmations that can be computed. This preserves evidence needed to measure opportunity cost and filter value later instead of hiding rejected opportunities from research.

## 17. Determinism and Auditability

Given equal `FeatureVector`, `GraduationContext`, and policy inputs, repeated calls must return equal assessments.

Finding order follows the evaluation sections above and is part of the audit contract.

No wall-clock call is allowed inside the evaluator. `features.as_of_unix_ms` is the sole decision timestamp.

The assessment records policy and feature-schema versions so later outcome analysis can reproduce historical decisions.

## 18. File Boundary

B4b follows the existing setup package:

```text
python/src/shreks_brain/setups/
  __init__.py                 # stable public exports
  models.py                   # shared SetupState + B3 and B4b immutable models
  fresh_launch.py             # unchanged B3 evaluator
  graduation_breakout.py      # B4b evaluator

python/tests/
  test_graduation_breakout_models.py
  test_graduation_breakout_setup.py
  test_graduation_breakout_public_api.py
```

B4b does not modify B2 feature models or Rust lifecycle/storage code.

## 19. Testing Strategy

Development is test-first.

### Model tests

Prove:

- canonical setup name and confirmation count;
- stable reason strings;
- context structural validation and immutability;
- full-width non-negative slot acceptance;
- optional occurred-at validation;
- policy validation and immutability;
- assessment immutability;
- assessment contains no trade intent, side, size, wallet, order, fill, signer, or transaction field.

### Evaluator tests

Use explicit policy fixtures and hand-built `b2-v1` vectors to prove:

- valid verified context plus all eight confirmations -> `READY`, score 100;
- missing graduation -> `BLOCKED`;
- wrong lifecycle event -> `BLOCKED`;
- wrong from/to venue transition -> `BLOCKED`;
- future local detection time -> `BLOCKED`;
- optional block time never advances or backdates decision eligibility;
- safety `REJECT` and `INCOMPLETE` cannot be overridden;
- post-graduation expiry -> `BLOCKED`;
- too-recent graduation -> `WATCH`;
- source staleness -> `BLOCKED`;
- insufficient known liquidity -> `BLOCKED`;
- excessive known exit impact -> `BLOCKED`;
- excessive 1m return -> anti-chase `BLOCKED`;
- missing liquidity or exit impact -> `WATCH`;
- each confirmation below threshold independently -> `WATCH` and score `7 / 8 * 100`;
- equality at every numerical threshold passes;
- each missing confirmation generates its matching `UNKNOWN` reason;
- deterministic multi-finding order;
- repeated evaluation returns equal results;
- blocked candidates still retain feature-based confirmation counts.

### Public API tests

All B4b stable types/constants/functions import from `shreks_brain.setups` without changing B3 imports.

Final verification is full repository CI.

## 20. Calibration Discipline

B4b ships with **no production default policy**.

Later paper/research work must evaluate candidate policies using unseen point-in-time data and realistic costs, including:

- net expectancy after fees/slippage;
- MFE/MAE and drawdown;
- sample size and trade frequency;
- seconds-since-graduation sensitivity;
- liquidity and price-impact sensitivity;
- results by quote mint and PumpSwap pool characteristics;
- stability across market regimes;
- out-of-sample behavior.

The lifecycle event must be aligned using `detected_at_unix_ms` for historical decision eligibility. `occurred_at_unix_ms` may be analyzed as metadata but cannot leak earlier knowledge into a backtest.

## 21. Explicit Non-Goals

B4b does not:

- modify `b2-v1`;
- introduce production thresholds;
- create a generic V0 weighted trade score;
- implement First Pullback or Smart Wallet Cluster;
- create `TradeDecision` or `TradeIntent`;
- size positions;
- paper trade;
- request Jupiter quotes;
- create wallets or signers;
- build, sign, submit, or confirm transactions;
- enable live money.

## 22. Exit Criteria

B4b is complete only when:

1. the unchanged B2 `FeatureVector` and a normalized `GraduationContext` are sufficient to evaluate the setup without storage/provider access;
2. only verified Pump graduation with exact Pump.fun bonding-curve -> PumpSwap transition can satisfy lifecycle eligibility;
3. local B4a detection time is the sole graduation decision clock;
4. all safety, timing, freshness, executability, and anti-chase gates are fail-closed;
5. all eight confirmations are deterministic and missing-safe;
6. blocked candidates preserve confirmation evidence for research;
7. B3 public behavior remains green and unchanged;
8. the B4b public assessment contains no execution authority;
9. full Python/Rust/repository-safety CI passes on the exact final head.
