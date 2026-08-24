# Phase E6 Champion / Challenger Registry — Design

**Status:** approved by current project direction  
**Base:** sealed A10 head `d36ec5fd3d650f0c8d55c56fd461f371e910d8f3`  
**Scope:** Python registry/audit layer only

## Goal

Create a durable, deterministic registry for strategy/model candidates so Shreks can identify exactly what was trained, how it was validated, what E5 measured, and which version is currently designated challenger/champion/retired.

E6 is an audit and state-management layer. It does **not** decide whether a candidate deserves promotion. E8 owns promotion rules; E7 owns shadow/paper challenger operation. No E6 API may infer a status transition from performance metrics.

## Source constraints

The build order requires E6 to persist:

- model/strategy version;
- training window;
- feature schema;
- evaluation results;
- promotion status.

The master source of truth additionally requires challengers to remain separated from live control and forbids self-promotion. Therefore the registry must make promotion explicit, attributable, deterministic, and auditable without creating a profitability gate of its own.

## Existing evidence reused

E6 references the sealed predecessor contracts rather than recomputing them.

### E3 model evidence

`TrainedLogisticRegressionModel` already carries:

- `model_version`;
- model/training schema and policy versions;
- exact feature transforms;
- selected target;
- training row counts;
- minimum/maximum training decision timestamps;
- `training_fingerprint_sha256`.

### E4 validation evidence

`TimeAwareValidationRun` already carries:

- validation schema/policy version;
- exact training request;
- chronological fold definitions/results;
- `validation_run_fingerprint_sha256`.

### E5 evaluation evidence

`TradingEvaluationReport` already carries:

- evaluation schema/policy version;
- `candidate_version`;
- after-cost trading metrics;
- calibration when available;
- setup/regime slices;
- `evaluation_fingerprint_sha256`.

E6 stores enough normalized summary fields for registry inspection plus the sealed predecessor fingerprints that identify the authoritative full evidence.

## Package

Create `shreks_brain.registry` with schema version:

`e6-registry-v1`

Public V1 surface:

1. `CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION`
2. `RegistryStatus`
3. `RegistryEvaluationEvidence`
4. `RegistryCandidate`
5. `RegistryStatusEvent`
6. `ChampionChallengerRegistry`
7. `RegistryStore`
8. `build_registry_candidate`

No network, database server, random source, or wall-clock read is required.

## Registry statuses

Use exactly three state labels:

- `CHALLENGER`
- `CHAMPION`
- `RETIRED`

Registration always begins as `CHALLENGER`. E6 never automatically produces `CHAMPION` based on metrics.

A later status transition requires an explicit caller-supplied audit event containing:

- candidate version;
- prior status;
- requested new status;
- explicit decision/reference identifier;
- explicit decision timestamp;
- non-empty reason.

The registry enforces structural integrity only:

- candidate must already exist;
- event's prior status must match current state;
- no no-op transition;
- at most one current champion;
- event timestamps are non-negative and cannot precede candidate registration;
- duplicate event fingerprints are idempotent;
- conflicting duplicate identities fail closed.

It deliberately does not enforce economic thresholds. E8 will decide when a structurally valid `CHAMPION` transition should be recorded.

`RETIRED` is not terminal in E6 because E8 may later define an explicit rollback/reactivation policy. Any such change still requires a new audit event.

## Candidate identity and provenance

A `RegistryCandidate` is immutable and content-addressed. It contains:

- registry schema version;
- candidate version;
- strategy version;
- optional model version;
- optional E3 model-training fingerprint;
- feature schema version;
- canonical ordered feature columns;
- optional training start/end decision timestamps;
- optional E4 validation schema/policy/fingerprint;
- E5 evaluation evidence;
- explicit registration timestamp;
- candidate fingerprint.

### ML candidate validation

When constructed from an E3 trained model + E4 validation run + E5 report:

- model version must equal the E4 training request's model version;
- model feature names must exactly equal E4 requested feature columns;
- every E4 fold model must have the same model version and feature names;
- E5 `candidate_version` must equal the registry candidate version;
- training bounds come from the registered E3 artifact;
- sealed schema versions and all SHA-256 references are preserved.

### Strategy-only candidate support

The registry data model permits `model_version=None` with no training/validation fingerprint. This is required so deterministic strategies/baselines can be represented without inventing a fake ML artifact. Strategy-only candidates still require a real E5 evaluation report when registered through the V1 builder.

The V1 builder has two explicit modes rather than guessing:

- model-backed registration: caller supplies exact E3 model and E4 validation run;
- strategy-only registration: caller explicitly passes both as `None`.

Mixed partial provenance fails closed.

## Evaluation evidence

`RegistryEvaluationEvidence` snapshots headline E5 results needed for registry inspection while retaining the authoritative E5 fingerprint:

- evaluation schema/policy version;
- evaluation fingerprint;
- trade count;
- net PnL;
- net expectancy USD and percent;
- profit factor;
- maximum drawdown USD and percent;
- win rate;
- turnover USD;
- total cost USD;
- Brier score / expected calibration error when calibration exists.

Setup/regime details remain authoritative in the E5 report identified by the fingerprint rather than being duplicated into the registry.

No metric is converted into a pass/fail or promotion recommendation in E6.

## Deterministic fingerprints

Canonical JSON uses:

- UTF-8;
- sorted object keys;
- compact separators;
- explicit enum strings;
- list representation for ordered tuples;
- no NaN/infinity;
- caller-supplied timestamps only.

Candidate fingerprint excludes no material candidate field other than the fingerprint itself.
Status-event fingerprint excludes only its own fingerprint.
Registry fingerprint covers the canonical ordered candidate set plus complete canonical event history.

Candidate order is lexical by `candidate_version`. Event order is `(decided_at_unix_ms, candidate_version, event_fingerprint)`.

## Durable store

`RegistryStore(path)` persists one canonical JSON document using only the Python standard library.

Properties:

- parent directory is created when needed;
- writes use a deterministic sibling temporary path then `os.replace` for atomic replacement;
- load validates schema, canonical structure, every candidate/event fingerprint, current-status reconstruction, and registry fingerprint;
- missing file loads as an empty valid registry;
- corrupt/truncated/tampered data fails closed;
- APIs never silently repair invalid state;
- no deletion API in V1; retirement remains auditable history.

The store rewrites the complete small registry document atomically. It is logically append-only because public mutations only add immutable candidates/events and history cannot be removed through the API.

## Champion semantics

An empty registry is valid and has no champion.
Registering a candidate does not create a champion.
`current_champion()` returns zero or one candidate based solely on explicit status history.

This avoids fabricating an incumbent before Shreks has evidence and an explicit promotion decision.

## E7 / E8 boundary

E7 may query registered challengers and run them in shadow/paper mode, but E7 does not mutate champion status automatically.

E8 will consume validation/evaluation/shadow evidence, apply explicit promotion rules, and—only when those rules pass—submit a caller-visible `RegistryStatusEvent` to E6. E6 records that decision; it does not make it.

## Safety / profitability boundary

E6 provides provenance and governance that are prerequisites for profitable iteration, but registry status is not proof of positive expectancy. Live-money authority remains disabled.

The registry contains no execution, signing, quote, wallet-secret, trade-intent, or runtime-live code.

## Testing

Minimum tests:

- exact public API/schema;
- model-backed candidate provenance alignment;
- strategy-only candidate registration;
- partial/mismatched provenance rejection;
- deterministic candidate/evaluation fingerprints;
- registration always starts challenger;
- no metric-driven auto-promotion API;
- explicit status-event validation;
- at-most-one champion invariant;
- duplicate event idempotency and conflicting duplicate rejection;
- canonical ordering independent of insertion order;
- store round trip;
- missing file -> empty registry;
- corrupt/tampered/truncated file fails closed;
- atomic write leaves canonical document;
- no deletion/live/trading authority surface.

## Exit criterion

E6-v1 is complete when Shreks can durably register evaluated strategy/model candidates, reconstruct their exact provenance and current status after restart, identify at most one explicit champion, preserve complete status history, and fail closed on corruption—without deciding promotion eligibility or enabling live trading.
