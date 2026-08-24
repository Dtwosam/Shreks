# Phase E4 Time-Aware Validation Verification Record

## Scope

Phase E4 adds deterministic, leakage-safe chronological challenger validation on top of frozen E3. It does not evaluate profitability, select a champion, change trading policies, or enable live money.

Frozen E3 base:

```text
1328efce85464f3f1b1636d837bcefb1193c2eac
```

E4 public schema:

```text
e4-time-validation-v1
```

## Design and planning

Design commit:

```text
66ac00b7ae0e35649e617f66d8258af2c4ada743
```

Implementation-plan correction commit:

```text
d9facc5b214239b2260f4dfe57455bcfe6f910bc
```

The plan correction removed a false Task-1 requirement to export an engine function before that function existed. Task 1 therefore exposed only real contract symbols; Task 2 expanded the public API after its own RED test.

A later docs-only clarification aligned the design's leakage wording with its walk-forward semantics:

```text
a6811b0ffd9754df15a6a2a27468c0ab6b20065c
```

The clarified invariant is: target/future-label changes for rows in one fold's validation interval cannot change that same fold's model, predictions, validation membership, or fingerprint. Those rows may affect a later fold only after the selected target has matured by that later fold's validation start.

## TDD cycle 1 — public contracts

### RED

Contract tests defined:

- `TIME_AWARE_VALIDATION_SCHEMA_VERSION`;
- frozen/slotted fold, policy, fold-result, and run contracts;
- half-open chronological boundaries;
- unique fold names;
- non-overlapping validation intervals;
- count/model/prediction reconciliation;
- canonical result ordering;
- explicit five-symbol Task-1 public API.

The content-equivalent RED branch head used for CI was:

```text
028193a33df7ef838263f05f14ed7eac5746f8f5
```

CI:

```text
32771102635
```

Expected Python RED was observed: collection failed only because `shreks_brain.validation` did not exist. No E4 production code existed yet.

### GREEN

Contract implementation commit:

```text
2c30bf7cc4069c6f56bad90457e5707f3cd5e66c
```

The detached GREEN diff was audited before attachment and contained only:

```text
python/src/shreks_brain/validation/models.py
python/src/shreks_brain/validation/__init__.py
```

CI:

```text
32771300203
```

Evidence:

```text
Python: 1773 passed in 3.86s
Rust tests/workspace metadata: success
Repository safety: success
```

## TDD cycle 2 — chronological validation engine

### RED

Engine behavior RED commit:

```text
01643938e2b6751599bc34a96acfc0a3214c304a
```

The detached diff was audited before attachment and contained only:

```text
python/tests/test_time_validation_engine.py
python/tests/test_time_validation_public_api.py
```

CI:

```text
32771746375
```

Expected Python RED was observed: exactly one collection error because `run_time_aware_validation` was not exported or implemented. There was no fixture, contract, dependency, or predecessor failure.

The RED tests separately proved requirements for:

- canonical row and fold order;
- half-open train/validation membership;
- exclusion of selected targets that mature after validation starts;
- inclusion when completion occurs exactly at the split;
- pending-target exclusion;
- same-fold validation-label isolation;
- non-target future-label isolation;
- sequential walk-forward reuse only after label maturity;
- fresh fold-local E3 artifacts;
- exact D6 row/schema/identity validation;
- fold-context errors for invalid chronology and insufficient training populations;
- empty-validation rejection;
- metric firewall;
- lazy sklearn/import purity;
- no storage/network/filesystem/wall-clock/random dependency in the E4 engine.

### GREEN

Engine implementation commit:

```text
a9d33cf4e05097ec690d2763ca9e77c0f8515dbc
```

The detached GREEN diff was audited before attachment and contained only:

```text
python/src/shreks_brain/validation/engine.py
python/src/shreks_brain/validation/__init__.py
```

CI:

```text
32772043039
```

Evidence:

```text
Python: 1785 passed in 5.49s
Rust tests/workspace metadata: success
Repository safety: success
```

The real CI environment installed and exercised the existing E3 scikit-learn training path through multiple E4 folds.

## Leakage contract verified

E4 enforces two independent gates for every fold.

A row first belongs to the training-window population only when:

```text
training_started_at <= as_of_unix_ms < training_ended_at
```

It can train only when its selected target is structurally valid and its completion timestamp satisfies:

```text
completed_at_unix_ms <= validation_started_at_unix_ms
```

A historical decision with a later-maturing outcome is therefore withheld from that fold and counted as target-unavailable-at-split rather than being backfilled into training.

Validation membership is independent of label state:

```text
validation_started_at <= as_of_unix_ms < validation_ended_at
```

Every row in that interval is predicted. The current fold does not read validation labels to choose membership or predictions. An earlier validation row may join a later fold's training population only after its selected outcome is legitimately knowable by the later split.

## Determinism and provenance

Equivalent logical inputs produce canonical results regardless of caller row/fold order. E4 sorts rows by `(as_of_unix_ms, candidate_mint)` and folds by validation boundary/name, delegates deterministic preprocessing/training to sealed E3, and stores exact fold-local E3 training fingerprints.

The E4 run fingerprint includes only validation policy/fold boundaries, exact E3 training-request provenance, fold artifact training fingerprints, and prediction identity/probability provenance. It includes no validation target value and no performance metric.

## Metric firewall

E4 outputs no field for:

- accuracy;
- AUC;
- calibration;
- expectancy;
- PnL;
- profit factor;
- drawdown;
- win rate;
- turnover;
- costs;
- promotion status.

E4 answers only what historical evidence was knowable at each split, what E3 model was trained from it, and what that model predicted on the next unseen interval. E5 owns predictive/trading-economic evaluation.

## Purity boundary

E4 adds no dependency. Importing `shreks_brain.validation` does not eagerly import sklearn; sklearn is reached only through sealed E3 when fitting is actually requested.

Production E4 code performs no SQLite, PyArrow, filesystem, network, wall-clock, or random-number access.

## Frozen-E3 to E4 behavior diff audit

The cumulative diff from frozen E3 `1328efce85464f3f1b1636d837bcefb1193c2eac` through the docs-clarified E4 behavior head `a6811b0ffd9754df15a6a2a27468c0ab6b20065c` was audited.

Exactly these paths were present:

```text
docs/superpowers/plans/2026-08-24-phase-e4-time-validation.md
docs/superpowers/specs/2026-08-24-phase-e4-time-validation-design.md
python/src/shreks_brain/validation/__init__.py
python/src/shreks_brain/validation/engine.py
python/src/shreks_brain/validation/models.py
python/tests/test_time_validation_engine.py
python/tests/test_time_validation_models.py
python/tests/test_time_validation_public_api.py
```

No E3 learning production file, D6 research/export file, E2 baseline file, B7/B8/B9 production file, paper/exit production file, Python dependency declaration, Rust source, or migration changed.

A temporary placeholder file was accidentally created while opening the stacked PR and immediately removed in the next commit. It does not exist in the cumulative frozen-E3 to E4 diff and carries no runtime or repository-content effect.

## Pre-seal verification

The docs-clarified E4 head `a6811b0ffd9754df15a6a2a27468c0ab6b20065c` also completed full CI successfully:

```text
CI 32772363378: success
```

## Phase boundary

E4 proves reproducible chronological mechanics and target-maturity leakage protection only.

It does **not** prove the challenger beats E2 baselines, improves expectancy, survives realistic costs, or makes money. No production feature set, target, training policy, fold schedule, economic threshold, or champion is selected here.

Live-money authority remains disabled. Phase E5 must evaluate the exact E4 unseen populations with realistic trading/economic metrics before any performance claim exists.
