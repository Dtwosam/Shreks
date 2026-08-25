# Phase E8 Promotion Rules Design

## Goal

Build the final Phase E learning gate: a deterministic, auditable promotion evaluator that can decide whether a registered challenger has enough evidence to be **eligible for an explicit recorded promotion operation** without ever promoting itself or enabling live money.

## Source requirements

The build order requires E8 promotion to be an explicit recorded operation based on evaluation gates.

The master source of truth requires a challenger to use valid point-in-time data, pass schema/data-quality checks, be evaluated on unseen data, beat required baselines, remain within drawdown/risk limits, avoid dependence on one tiny period or a few extreme winners, run in paper/shadow mode, and satisfy promotion rules. A challenger never promotes itself automatically.

Exact numeric thresholds must be defined from data rather than invented prematurely.

## Chosen architecture

Add a focused `shreks_brain.promotion` package with three responsibilities:

1. immutable policy/assessment models;
2. a pure evaluator that consumes frozen E6/E5/E7 evidence and caller-supplied thresholds;
3. an append-only canonical assessment store.

E8 does **not** call `RegistryStore.record_status`, build transactions, enable live mode, or control capital. If an assessment is eligible, its fingerprint becomes the explicit `decision_reference` that an external operator/workflow may later use with the already-existing E6 status-event API.

This keeps evaluation and authority separate: E8 can say “eligible under policy X from evidence Y,” but cannot make itself champion.

## Schema and public API

Schema: `e8-promotion-v1`.

Public surface:

- `PROMOTION_SCHEMA_VERSION`
- `PromotionDecision`
- `PromotionGateStatus`
- `PromotionGateCode`
- `PromotionPolicy`
- `PromotionGateResult`
- `PromotionAssessment`
- `PromotionAssessmentStore`
- `evaluate_promotion`

No exported promotion/apply/live/registry mutation method exists.

## Promotion policy

`PromotionPolicy` contains **no defaults**. Every numeric gate is explicit and versioned:

- `version`
- `min_trade_count`
- `min_evaluation_span_ms`
- `min_net_expectancy_pct`
- `min_profit_factor`
- `max_drawdown_pct`
- `max_cost_burden_pct`
- `max_brier_score`
- `max_expected_calibration_error`
- `required_baseline_versions`
- `min_baseline_expectancy_advantage_pct`
- `max_single_winner_share_of_positive_pnl`
- `min_shadow_decision_count`
- `min_shadow_distinct_mint_count`
- `min_shadow_span_ms`

These values are policy inputs, not hard-coded claims of profitability.

## Evidence inputs

`evaluate_promotion` consumes:

- current `ChampionChallengerRegistry`;
- `candidate_version`;
- exact E5 `TradingEvaluationReport` for the challenger;
- exact E5 `EvaluatedTrade` tuple used for concentration/span checks;
- exact E7 `ShadowEvidenceLedger`;
- exact tuple of baseline `TradingEvaluationReport` values;
- explicit `PromotionPolicy`;
- caller-supplied `evaluated_at_unix_ms`.

The evaluator requires the challenger report fingerprint and headline metrics to agree with the E6 registry candidate. It does not trust a second, conflicting evaluation report.

Raw E5 trades must match the challenger identity and reconcile at least the persisted trade count and net PnL used by the E6/E5 evaluation. Their timestamps are used only for evaluation-span evidence, and their positive net-PnL distribution is used only for winner-concentration evidence.

## Gate semantics

Each gate is one of:

- `PASS`
- `FAIL`
- `INSUFFICIENT`

Overall decision precedence:

1. any `FAIL` -> `INELIGIBLE`;
2. otherwise any `INSUFFICIENT` -> `INSUFFICIENT_EVIDENCE`;
3. otherwise -> `ELIGIBLE`.

This distinguishes “bad evidence” from “not enough evidence yet.”

## Gate set

The evaluator records stable gate codes for:

- current registry status is `CHALLENGER`;
- complete model + time-aware validation provenance exists;
- E5 report matches E6 persisted evaluation identity/headline values;
- minimum closed-trade sample size;
- minimum evaluation time span;
- minimum post-cost net expectancy percent;
- minimum profit factor;
- maximum drawdown percent;
- maximum cost burden percent;
- maximum Brier score;
- maximum expected calibration error;
- required baseline reports are present and comparable;
- challenger expectancy beats each required baseline by the configured margin;
- if a current champion exists, its evaluation must be included in the baseline set and beaten by the same margin;
- maximum single-winner share of total positive net PnL;
- minimum E7 shadow decision count;
- minimum E7 distinct-mint coverage;
- minimum E7 observation span;
- E7 records align with the challenger candidate/model fingerprint and do not contain another candidate's evidence.

Missing profit factor/calibration/required baselines or undersized sample/span are `INSUFFICIENT`, not silently converted to zero.

Performance below an explicit economic/risk/concentration threshold is `FAIL`.

## Baseline comparability

Baseline reports are keyed by `candidate_version` and must be unique.

Every required baseline must:

- use the same E5 evaluation policy version as the challenger report;
- have a defined net expectancy percent;
- not be the challenger itself.

If the registry has a current champion, that champion version is automatically required as a baseline even if the policy omitted it. This is the concrete champion/challenger comparison required by the source of truth.

No synthetic baseline score is invented in E8.

## Tiny-period and extreme-winner protection

E8 uses two explicit evidence-quality gates that are directly motivated by the source requirement:

- evaluation span from earliest trade open to latest trade close must meet `min_evaluation_span_ms`;
- largest positive trade divided by total positive net PnL must not exceed `max_single_winner_share_of_positive_pnl`.

The threshold values remain caller-supplied. If there are no positive trades, concentration evidence is insufficient and the expectancy/profitability gates will normally fail independently.

## Shadow evidence

E7 evidence is operational exposure, not PnL.

E8 filters the ledger to the challenger and requires every selected record to match:

- candidate version;
- candidate fingerprint;
- strategy/model version;
- E7 schema.

The policy then gates decision count, distinct mint count, and time span. The evaluator does not treat a large number of shadow `ENTER` decisions as profitability proof and does not optimize for entry frequency.

## Assessment fingerprint

`PromotionAssessment` records:

- schema version;
- policy version;
- candidate version/fingerprint;
- registry fingerprint;
- E5 evaluation fingerprint;
- E7 ledger fingerprint;
- ordered baseline `(version, evaluation_fingerprint)` identities;
- evaluated timestamp;
- canonical gate results;
- overall decision;
- assessment SHA-256 fingerprint.

Floats are normalized with exact `.hex()` representation before hashing, matching existing E5/E7 provenance conventions.

## Durable assessment store

`PromotionAssessmentStore` persists canonical JSON with atomic fsync + replace writes.

Identity is `(candidate_version, policy_version, evaluated_at_unix_ms)`.

- identical append is byte-for-byte idempotent;
- same identity with different content fails closed;
- load independently recomputes every assessment fingerprint;
- unknown fields/schema/enums, malformed JSON, and tampering fail closed;
- no delete/rewrite/status-mutation API exists.

This creates the recorded decision evidence E6 can later reference explicitly.

## Authority boundary

An `ELIGIBLE` assessment is **not** a promotion and is not a live-money gate.

To change E6 status, a separate explicit operation must call the existing registry status API with the assessment fingerprint as `decision_reference`. If another champion currently exists, that separate operation must retire it before promoting the challenger because E6 enforces one current champion.

Phase F/G live-money requirements remain separate. E8 cannot enable live mode.

## Testing strategy

Use TDD and exact-head CI.

Tests lock:

- no defaults for numeric promotion criteria;
- exact model/schema/fingerprint validation;
- PASS/FAIL/INSUFFICIENT precedence;
- E6/E5 evidence mismatch rejection;
- champion auto-baseline requirement;
- baseline margin behavior;
- sample/span/economic/risk/cost/calibration gates;
- extreme-winner concentration gate;
- shadow count/distinct/span and provenance gates;
- deterministic assessment fingerprints;
- canonical append-only persistence and tamper rejection;
- source/API firewalls forbidding registry mutation, live control, signing, or transaction submission.

Final E8 sealing must be docs-only after the last behavior head and must pass Python, Rust/workspace, and repository safety on the exact seal SHA.