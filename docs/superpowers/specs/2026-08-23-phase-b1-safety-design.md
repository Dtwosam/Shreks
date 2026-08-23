# Phase B1 Deterministic Safety Assessment Design

**Status:** Approved in-chat design, pending written-spec review  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`

## 1. Purpose

Phase B1 begins the `UNDERSTAND` stage by adding a deterministic, point-in-time safety assessment to the Python brain. The safety layer runs before strategy scoring and has veto power over any later momentum/setup score.

B1 does not create trade ideas, size positions, simulate fills, submit transactions, or enable live trading. It only converts already-observed candidate facts plus a versioned safety policy into an auditable safety result.

## 2. Source-of-Truth Requirements

This design implements the approved master-design requirements that:

- safety runs before strategy scoring;
- a high score cannot override a hard safety rejection;
- hard rejection examples include critical authority risk, inadequate executable liquidity, excessive concentration, inability to obtain a reliable exit quote, stale/contradictory critical data, explicitly detected execution traps, and a global risk halt;
- threshold values are configuration rather than magic constants buried in code;
- softer risks reduce confidence/score later rather than becoming automatic hard rejects;
- the safety engine returns structured reasons so later research can measure whether rules are useful or overly conservative;
- all point-in-time inputs are timestamped/versionable so future outcome data cannot leak into a current decision.

## 3. Scope

### In scope

B1 introduces a dependency-free Python package under `shreks_brain.safety` containing:

1. typed input facts supplied by later adapters;
2. a versioned/configurable `SafetyPolicy`;
3. deterministic hard-rule and soft-risk evaluation;
4. structured findings/reason codes;
5. an overall `PASS`, `REJECT`, or `INCOMPLETE` result;
6. deterministic tests for every rule and precedence behavior.

### Out of scope

B1 intentionally does not:

- read SQLite directly;
- call Solana, Helius, DEX Screener, Jupiter, or any external API;
- calculate strategy/setup scores;
- calculate position size;
- create `TradeIntent` objects;
- make paper or live execution decisions;
- infer holder concentration, creator identity, or exitability from raw provider payloads;
- use future outcome checkpoints as safety inputs;
- introduce machine learning or self-modifying policies.

Adapters that translate operational storage/provider state into `SafetyInputs` are a later integration slice.

## 4. Package Boundary

The new package is:

```text
python/src/shreks_brain/safety/
  __init__.py
  models.py
  evaluator.py
python/tests/
  test_safety_models.py
  test_safety_evaluator.py
```

`models.py` owns immutable enums/dataclasses and policy validation. `evaluator.py` owns the pure evaluation function. The evaluator imports only the Python standard library and `models.py`.

The public package surface exports the types and `assess_safety` function from `shreks_brain.safety` so later feature/strategy code does not depend on module internals.

## 5. Public Domain Types

### `SafetyDecision`

A string enum with exactly:

- `PASS`
- `REJECT`
- `INCOMPLETE`

Semantics:

- `REJECT`: one or more proven hard blockers are present.
- `INCOMPLETE`: there is no proven hard blocker, but a policy-required critical fact is unknown/stale/contradictory, so downstream entry scoring must fail closed.
- `PASS`: no hard blocker exists and all policy-required critical facts are usable.

Precedence is always `REJECT > INCOMPLETE > PASS`.

### `SafetySeverity`

A string enum with exactly:

- `HARD`
- `SOFT`
- `DATA_QUALITY`

`HARD` findings can force `REJECT`. `DATA_QUALITY` findings can force `INCOMPLETE`. `SOFT` findings never change the overall decision away from `PASS` by themselves.

### `SafetyReasonCode`

A stable string enum used for audit/research. B1 defines these codes:

Hard blockers:

- `GLOBAL_RISK_HALT`
- `MINT_AUTHORITY_ACTIVE`
- `FREEZE_AUTHORITY_ACTIVE`
- `LIQUIDITY_BELOW_MINIMUM`
- `HOLDER_CONCENTRATION_ABOVE_MAXIMUM`
- `EXIT_QUOTE_UNAVAILABLE`
- `EXECUTION_TRAP_DETECTED`

Critical-data blockers:

- `MINT_AUTHORITY_UNKNOWN`
- `FREEZE_AUTHORITY_UNKNOWN`
- `LIQUIDITY_UNKNOWN`
- `HOLDER_CONCENTRATION_UNKNOWN`
- `EXIT_QUOTE_UNKNOWN`
- `CRITICAL_DATA_STALE`
- `CRITICAL_DATA_CONTRADICTORY`

Soft risks:

- `CREATOR_CONCENTRATION_ELEVATED`
- `LIQUIDITY_WEAK`
- `HOLDER_CONCENTRATION_ELEVATED`
- `EXIT_PRICE_IMPACT_ELEVATED`

Reason-code strings are part of the audit contract and must be deterministic.

### `SafetyFinding`

Immutable dataclass fields:

- `code: SafetyReasonCode`
- `severity: SafetySeverity`
- `message: str`
- `observed_value: float | bool | None = None`
- `threshold_value: float | None = None`

Messages are human-readable explanations; consumers must use `code` for logic.

### `SafetyInputs`

Immutable point-in-time facts:

- `as_of_unix_ms: int`
- `mint_authority_active: bool | None`
- `freeze_authority_active: bool | None`
- `liquidity_usd: float | None`
- `top_holder_concentration_pct: float | None`
- `creator_concentration_pct: float | None`
- `exit_quote_available: bool | None`
- `exit_price_impact_pct: float | None`
- `execution_trap_detected: bool`
- `critical_data_observed_at_unix_ms: int | None`
- `critical_data_contradictory: bool`
- `global_risk_halt: bool`

`None` means unknown, not false. Percent values use percentage points (for example `12.5` means 12.5%).

B1 does not include outcome-checkpoint fields, realized returns, future MFE/MAE, or any later-observed value.

### `SafetyPolicy`

Immutable configuration with an explicit version string:

- `version: str`
- `min_liquidity_usd: float`
- `soft_min_liquidity_usd: float`
- `max_top_holder_concentration_pct: float`
- `soft_max_top_holder_concentration_pct: float`
- `soft_max_creator_concentration_pct: float`
- `soft_max_exit_price_impact_pct: float`
- `max_critical_data_age_ms: int`
- `require_known_authorities: bool = True`
- `require_liquidity: bool = True`
- `require_holder_concentration: bool = True`
- `require_exit_quote: bool = True`

Validation rules:

- version must be non-empty;
- numeric thresholds must be finite and non-negative;
- `soft_min_liquidity_usd >= min_liquidity_usd`;
- `soft_max_top_holder_concentration_pct <= max_top_holder_concentration_pct`;
- concentration and price-impact percentages must lie within policy-appropriate non-negative bounds;
- `max_critical_data_age_ms >= 0`.

Invalid policy construction raises `ValueError` before evaluation.

### `SafetyAssessment`

Immutable result fields:

- `decision: SafetyDecision`
- `policy_version: str`
- `as_of_unix_ms: int`
- `findings: tuple[SafetyFinding, ...]`

Convenience properties may expose hard, data-quality, and soft findings, but the tuple remains the canonical ordered audit record.

## 6. Deterministic Evaluation Rules

Public API:

```python
def assess_safety(inputs: SafetyInputs, policy: SafetyPolicy) -> SafetyAssessment:
    ...
```

The function is pure: identical inputs and policy produce an equal assessment and finding order.

### 6.1 Hard rules

Append hard findings in this fixed order:

1. global risk halt;
2. active mint authority;
3. active freeze authority;
4. liquidity below `min_liquidity_usd`;
5. top-holder concentration above `max_top_holder_concentration_pct`;
6. explicit unavailable exit quote (`False`);
7. execution-trap detector positive.

A hard finding always produces overall `REJECT`, even when critical data is also missing or stale.

### 6.2 Critical-data rules

If no fact can prove a hard blocker, unknown critical fields generate `DATA_QUALITY` findings only when the corresponding `require_*` policy flag is true.

Freshness is evaluated as:

```text
age_ms = as_of_unix_ms - critical_data_observed_at_unix_ms
```

If the observation timestamp is missing, required critical data is treated as stale/unknown through `CRITICAL_DATA_STALE`. If the timestamp is in the future, the input is contradictory and produces `CRITICAL_DATA_CONTRADICTORY` rather than accepting look-ahead data.

If `age_ms > max_critical_data_age_ms`, append `CRITICAL_DATA_STALE`.

`critical_data_contradictory=True` appends `CRITICAL_DATA_CONTRADICTORY`.

One or more data-quality findings with no hard findings produce `INCOMPLETE`.

### 6.3 Soft rules

Soft findings are still evaluated for auditability, even if the overall decision is already `REJECT` or `INCOMPLETE`.

Append soft findings in this fixed order when the value is known:

1. liquidity is at least the hard minimum but below `soft_min_liquidity_usd`;
2. top-holder concentration is above `soft_max_top_holder_concentration_pct` but at/below the hard maximum;
3. creator concentration is above `soft_max_creator_concentration_pct`;
4. exit price impact is above `soft_max_exit_price_impact_pct`.

Soft findings never cancel or override hard/data-quality findings and never independently cause `REJECT` or `INCOMPLETE`.

## 7. Input Validation and Fail-Closed Semantics

`SafetyInputs` validates local invariants before evaluation:

- timestamps are non-negative integers;
- known monetary/percentage values are finite and non-negative;
- concentration percentages are within `[0, 100]`;
- a negative or NaN value raises `ValueError` rather than being interpreted optimistically.

The evaluator does not guess missing values. Unknown required critical data produces `INCOMPLETE`; downstream entry logic must later treat both `REJECT` and `INCOMPLETE` as non-enterable.

B1 itself does not know about `ENTER`, `WATCH`, or strategy scores, so it cannot accidentally turn incomplete data into a trade decision.

## 8. Auditability

Finding order is deterministic and reason codes are stable. Every finding includes the observed value and relevant configured threshold when applicable. Assessments include the policy version and point-in-time timestamp.

No provider-specific names or payload fields appear in these types. Provider adapters remain responsible for proving facts such as authority state, concentration, and quote availability before constructing `SafetyInputs`.

## 9. Look-Ahead Prevention

B1 accepts only a single `as_of_unix_ms` and facts intended to be known at or before that timestamp. It has no API for candidate outcome checkpoints, future returns, future liquidity, future MFE/MAE, or later trade results.

A `critical_data_observed_at_unix_ms` greater than `as_of_unix_ms` is rejected as contradictory data through the assessment rather than treated as fresh evidence.

Tests must explicitly prove that the public input model has no future-outcome fields and that future critical-data timestamps do not produce `PASS`.

## 10. Testing Strategy

Development is test-first.

`test_safety_models.py` proves:

- enum values are stable;
- valid policies construct;
- invalid/non-finite/negative/internally inconsistent policies fail;
- invalid inputs fail;
- immutable dataclasses cannot be mutated.

`test_safety_evaluator.py` uses table-driven deterministic cases to prove:

- clean facts produce `PASS`;
- every hard rule independently produces `REJECT` with its exact reason code;
- hard rejection wins over missing/stale data;
- every required unknown critical fact produces `INCOMPLETE`;
- optional unknown facts do not force `INCOMPLETE`;
- stale and future-dated/contradictory critical data fail closed;
- soft conditions create ordered `SOFT` findings without becoming hard rejects;
- threshold boundary behavior is exact;
- repeated evaluation produces equal assessments and identical finding order;
- future outcome fields are absent from `SafetyInputs`.

The full repository CI remains the final gate: Rust workspace tests, Python tests, workspace metadata validation, and repository secret-safety must all pass.

## 11. Integration Contract for Later Phases

Later storage/provider integration may add a separate assembler that reads point-in-time operational evidence and constructs `SafetyInputs`. Strategy code consumes `SafetyAssessment` but must never reinterpret hard safety findings as soft score penalties.

A later scoring layer may use soft findings as features/subscores, but it must accept `PASS` as the only safety state eligible for entry consideration unless the approved architecture is explicitly revised.

## 12. Non-Trading Guarantee

B1 adds no wallet secret configuration, signer, transaction builder, swap execution call, paper fill adapter, or position management code. Runtime mode behavior is unchanged and live-money execution remains disabled.
