# Remove FL9 V2 Scoring-Authority Drift — Corrective Design

**Date:** 2026-09-25  
**Base main SHA:** `966c6523f03120e0e50f5f3bdd6cca48f8d8e6dd`  
**Status:** corrective architecture slice

## Source-of-truth correction

The active Fast Lane architecture does not use score approval as its decision control path.

Canonical decision flow:

```text
EVENT -> UPDATE STATE -> FORECAST FUTURE PATHS -> PRICE EXECUTION -> ESTIMATE NET EV -> CHOOSE ACTION -> RISK CHECK -> EXECUTE/WAIT -> RECORD -> LEARN
```

FL9 is the learned continuous action policy. It compares `BUY`, `SKIP`, `HOLD`,
`REDUCE`, and `SELL` using forecasts and expected net value subject to hard risk
constraints.

Legacy deterministic scoring remains only where already preserved as a baseline,
research signal, or compatibility test. It must not be promoted into a new FL9
authority/execution control plane.

## Drift introduced

PRs #524 and #526 introduced a new active abstraction:

- `shreks-fl9-v2-scoring-authority-decide`;
- `shreks_brain.fl9_v2_scoring_authority`;
- a scoring-authority schema and write-once authority artifact;
- protected verifier production-presence checks for that CLI/module;
- a trusted-admin scoring-authority runbook ceremony.

That control path is inconsistent with the active Fast Lane source of truth.

## Corrective scope

Remove only the newly introduced scoring-authority path:

- scoring-authority module;
- scoring-authority CLI registration;
- scoring-authority tests;
- scoring-authority production-presence verifier block;
- scoring-authority trusted-admin runbook ceremony;
- both scoring-authority design documents.

Do not remove or rewrite unrelated legacy deterministic scoring baselines, historical
compatibility code, existing request-preparation artifacts, Fast Lane forecasting,
net-EV evaluation, risk, PAPER, champion/challenger, deployment, or LIVE guards.

## Required regression

A focused test must prove:

- no FL9 V2 scoring-authority CLI registration exists;
- no FL9 V2 scoring-authority module exists;
- production verifier does not require or advertise the scoring-authority tool;
- release runbook does not contain a scoring-authority ceremony;
- the two drift design documents are absent;
- the source of truth still defines the active event/forecast/net-EV/action path;
- FL9 still defines direct `BUY/SKIP/HOLD/REDUCE/SELL` action comparison.

## Authority boundary

This corrective slice grants no new execution, promotion, PAPER, risk, wallet,
transaction, or LIVE authority.

```text
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
