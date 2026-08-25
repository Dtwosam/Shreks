# Phase E7 Shadow Challenger — Design

**Status:** approved by current project direction  
**Base:** sealed E6 head `5933416fa7136ee7594f89baf97da469bedac171`  
**Scope:** Python shadow-decision and evidence layer only

## Goal

Run registered model-backed challengers against current point-in-time Shreks research rows and persist auditable shadow decisions without creating trade intents, executing paper/live fills, mutating champion status, or using future outcomes at decision time.

E7-v1 is deliberately **shadow-first**. The build order requires a challenger to observe current conditions and generate decisions without controlling real money; it does not require E7 itself to simulate fills. Shreks already has a realistic paper execution loop, but wiring a learned challenger into position sizing/exits before the challenger has proven entry value would introduce unnecessary policy assumptions. E8 can later consume E7 shadow evidence together with after-the-fact outcomes/economic evaluation when deciding whether a promotion is justified.

## Source constraints

- learning cannot directly control live money;
- challengers must be evaluated on unseen data and shadow/paper observed before promotion;
- paper/live share the same deterministic safety/risk path;
- future labels must never influence a decision;
- no model self-promotion;
- no production numeric threshold may be invented implicitly;
- live money stays disabled.

## Existing contracts reused

### D6 point-in-time row

The sealed D6 research row already contains the current decision-time market/wallet/regime/safety/setup/score/decision evidence plus future-label columns. E3 inference requires this exact physical row shape but reads only the model's explicit feature transforms.

E7 accepts the exact D6 logical row. Future-label values are treated as irrelevant data: they cannot affect challenger action or its decision-feature fingerprint. This is tested by mutating label columns after the decision-time row is otherwise fixed.

### E3 model artifact

`TrainedLogisticRegressionModel` is the executable challenger artifact. E7 calls the sealed pure-Python `predict_positive_probability` function and does not import or fit scikit-learn.

### E6 registry

`ChampionChallengerRegistry` is the governance/provenance authority. E7 requires the selected candidate to:

- exist;
- currently be `CHALLENGER`;
- be model-backed in E7-v1;
- match the supplied E3 model version, training schema/fingerprint, and exact ordered feature names.

E7 never calls `RegistryStore.record_status` or writes registry state.

## Package

Create `shreks_brain.shadow` with schema version:

`e7-shadow-v1`

Public V1 surface:

1. `SHADOW_CHALLENGER_SCHEMA_VERSION`
2. `ShadowDecisionPolicy`
3. `ShadowReasonCode`
4. `ShadowDecisionRecord`
5. `ShadowEvidenceLedger`
6. `ShadowEvidenceStore`
7. `evaluate_shadow_challenger`

No new dependency, network access, random source, wall-clock read, database server, or live execution component is required.

## Explicit decision policy

`ShadowDecisionPolicy` contains exactly:

- `version: str`
- `enter_min_probability: float`

There is no default production threshold. The caller must provide a finite threshold in `[0, 1]` and version it explicitly.

E7-v1 intentionally uses only one model threshold. When deterministic hard gates permit entry consideration, probability at or above the threshold produces `ENTER`; probability below it produces `WATCH`. A second model-specific rejection threshold would add an unproven degree of freedom with no current evidence that it improves expectancy.

## Decision semantics

E7 reuses `DecisionAction` values `REJECT`, `WATCH`, and `ENTER` for entry-side shadow recommendations.

The incumbent D6 `decision_action` is preserved as `baseline_action` for comparison but is **not** a hard gate; otherwise a challenger could never discover an entry the deterministic score rejected only for being below its final score threshold.

The challenger may replace only the final score/decision threshold. It cannot override deterministic safety/setup/regime state:

1. `safety_decision != PASS` -> `REJECT`;
2. `setup_state == BLOCKED` -> `REJECT`;
3. `market_regime == DEAD` -> `REJECT`;
4. `setup_state == WATCH` -> `WATCH`;
5. `setup_state == READY` and all hard gates above pass:
   - probability >= explicit `enter_min_probability` -> `ENTER`;
   - otherwise -> `WATCH`.

Rows whose baseline action is not an entry-side `REJECT`, `WATCH`, or `ENTER` fail closed because E7-v1 is not an open-position exit challenger.

This means a challenger can differ from V0 on marginal eligible entries while retaining the deterministic fail-closed safety architecture.

## Shadow decision record

`ShadowDecisionRecord` is immutable and content-addressed. It records:

- E7 schema version;
- candidate and strategy versions;
- E6 candidate fingerprint;
- E6 registry fingerprint observed for this decision;
- model version/training fingerprint;
- model target horizon and minimum-return definition;
- shadow policy version and explicit probability threshold;
- candidate mint and decision timestamp;
- D6 dataset schema version;
- deterministic decision-feature fingerprint covering only D6 `RESEARCH_FEATURE_COLUMNS`;
- setup name;
- safety decision;
- setup state;
- market regime;
- baseline action;
- model positive probability;
- challenger action;
- one stable `ShadowReasonCode` describing the controlling decision branch;
- record fingerprint.

The record contains no future label, realized return, MFE/MAE, PnL, fill, position size, wallet secret, or transaction authority.

## Reason codes

Use exactly:

- `SAFETY_NOT_PASS`
- `SETUP_BLOCKED`
- `REGIME_DEAD`
- `SETUP_WATCH`
- `PROBABILITY_BELOW_ENTER_THRESHOLD`
- `PROBABILITY_ENTER_APPROVED`

Reason precedence follows the decision semantics above, so the same input always yields the same controlling reason.

## Point-in-time and leakage firewall

The shadow decision-feature fingerprint hashes only the exact D6 `RESEARCH_FEATURE_COLUMNS` projection, never `RESEARCH_LABEL_COLUMNS`.

The E3 predictor is called only after registry/model/row validation. Because the model's ordered feature names must equal the E6 registered feature columns and E3 training already forbids future-label features, future-label mutation cannot affect probability, action, reason, feature fingerprint, or record fingerprint.

`as_of_unix_ms` must not precede the candidate's E6 registration timestamp. E7 does not backfill fake historical shadow evidence for a challenger before it was registered.

## Deterministic fingerprints

Canonical hashing uses SHA-256 over deterministic JSON-compatible values. Floats are normalized to exact hexadecimal representations before hashing; tuples become ordered lists; dictionary keys are sorted. NaN/infinity are rejected.

Record fingerprint excludes only its own fingerprint.
Ledger fingerprint covers the full canonical ordered record set.

## Durable evidence store

`ShadowEvidenceStore(path)` persists one canonical JSON ledger using the Python standard library.

Properties:

- missing file loads an empty valid ledger;
- parent directories are created as needed;
- writes use sibling temporary file + flush/fsync + `os.replace`;
- every record fingerprint and the ledger fingerprint are recomputed on load;
- invalid/truncated/tampered state fails closed;
- append of an identical decision is idempotent;
- decision identity is `(candidate_version, candidate_mint, as_of_unix_ms, shadow_policy_version)`;
- reuse of that identity with different material content fails closed;
- canonical record order is `(as_of_unix_ms, candidate_version, candidate_mint, shadow_policy_version, record_fingerprint)`;
- no delete or rewrite-history API exists.

The store records evidence only. It does not evaluate profitability or modify E6 status.

## Strategy-only candidates

E6 can register deterministic strategy-only candidates. E7-v1's learned-model engine rejects those explicitly because it has no executable model artifact to call. Supporting arbitrary strategy callbacks in the same API would blur provenance and create a broad plugin surface before it is needed.

The existing deterministic V0/baselines already have E1/E2 replay paths. A later evidence-backed extension can add a separately typed strategy-shadow adapter without changing E7-v1 model semantics.

## E8 boundary

E8 may join E7 shadow records to outcomes or completed paper economics **after the fact** and compare challengers against baselines/champions under explicit promotion rules.

E7 does not:

- label a challenger profitable;
- calculate promotion eligibility;
- promote/demote/retire registry candidates;
- create `TradeIntent` or `RiskAssessment`;
- invoke the paper execution adapter;
- sign, submit, or construct transactions;
- enable live mode.

## Testing

Minimum tests:

- exact public API/schema;
- explicit policy validation/no defaults;
- registered current-CHALLENGER requirement;
- model-backed requirement;
- E6/E3 model version, training fingerprint, training schema, and ordered feature alignment;
- registration timestamp gate;
- exact D6 row requirement;
- safety/setup/regime hard-gate precedence;
- probability threshold ENTER/WATCH behavior;
- incumbent baseline action preserved but not used as the final threshold gate;
- non-entry baseline action fails closed;
- future-label mutation invariance for probability/action/reason/fingerprints;
- deterministic target/provenance recording;
- deterministic record fingerprint;
- store round trip, canonical ordering, idempotency, conflicting identity rejection;
- corrupt/tampered ledger fails closed;
- import/source firewall contains no registry status mutation, `TradeIntent`, signer, transaction submission, paper fill, or live authority;
- importing `shreks_brain.shadow` does not eagerly import scikit-learn or PyArrow.

## Exit criterion

E7-v1 is complete when a registered model-backed challenger can consume current point-in-time D6 rows, generate deterministic safety-preserving shadow entry decisions, and persist tamper-evident evidence across restart—without future-label leakage, status mutation, execution, or live-money authority.
