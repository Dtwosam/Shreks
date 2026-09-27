# Fast Lane FL11.2b Missed-Opportunity + Cost Sensitivity — Design

**Date:** 2026-09-28  
**Base main SHA:** `269553024f8c0c8665630f0ef8d9074ad1601ce0`

## Purpose

Close the remaining FL11.2 economics gap left by FL11.2a without creating a
second counterfactual pricing model.

FL11.2a already reports actual learned-shadow closed-trade economics and the
observed fee/slippage burden. FL11.2b adds:

- authenticated missed-entry opportunity evidence for learned `SKIP`
  decisions;
- explicit fee/slippage sensitivity over those same counterfactual
  opportunities.

The slice reuses the existing sealed training-economics overlay,
`build_entry_counterfactual_context_from_training_economics(...)`, and
`label_entry_counterfactuals(...)`.

It does not reprice actual fills, mutate PAPER state, promote a champion, or
enable LIVE.

## Why SKIP is the missed-opportunity population

A learned BUY that executes is already measured by FL11.2a. A learned SKIP has
zero executed PnL by construction, so its missed-opportunity question is:

> What would the same canonical decision have produced if an executable entry
> had been taken and exited at an authenticated future-path horizon?

FL11.2b answers only that question.

Open-position HOLD/REDUCE/SELL counterfactuals are not fabricated from entry
overlay evidence.

## Inputs

The CLI requires:

- exact runtime manifest;
- exact isolated shadow ledger/run binding;
- exact FL11.1 `SUFFICIENT_SAMPLE` proof;
- learned decision-evidence directory;
- exact training-economics overlay directory;
- one or more explicit counterfactual horizons;
- one baseline execution-cost policy;
- zero or more sensitivity execution-cost policies;
- exact release SHA and FL11.1 window.

No default horizon or cost policy is embedded in the repository.

## Evidence binding

For every learned SKIP inside the requested window, the proof binds the
decision to overlay rows using the exact:

- decision signature;
- decision ordinal;
- decision sequence;
- decision timestamp;
- mint;
- quote mint;
- venue;
- future-path label version;
- requested horizon.

A missing row is reported as missing counterfactual coverage.

A row whose identity conflicts with the learned decision fails closed.

The overlay itself must pass its existing manifest/rows fingerprint checks.

## Counterfactual economics

For each row and cost policy:

1. build the existing authenticated entry counterfactual context;
2. run the existing counterfactual labeler;
3. select the exact `BUY_NOW` outcome;
4. compare it with the actual learned `SKIP` outcome of zero executed PnL.

For executable BUY_NOW outcomes:

- positive counterfactual net PnL = missed profitable opportunity;
- negative counterfactual net PnL = avoided loss;
- zero = flat counterfactual.

The report preserves the signed counterfactual value rather than clipping
losses away.

Unavailable overlay rows remain unavailable; they are never filled in by
inference.

## Sensitivity boundary

The baseline and sensitivity policies are exact
`FastTrainingExecutionCostPolicy` values.

FL11.2b may vary:

- additional entry slippage;
- additional exit slippage;
- entry/exit network fee;
- entry/exit priority fee;
- entry/exit expected failure cost.

The following must remain exactly equal to the baseline:

- entry latency bps;
- exit latency bps.

Latency sensitivity belongs to FL11.3 and must not be smuggled into FL11.2b.

Every policy is fingerprinted. Policy versions must be unique.

## Report

For each policy, overall and per-horizon metrics include:

- SKIP decision/horizon observation count;
- executable counterfactual count;
- unavailable/missing coverage counts;
- profitable missed-opportunity count;
- avoided-loss count;
- flat count;
- total positive missed-opportunity quote value;
- total avoided-loss quote value;
- signed net opportunity quote value;
- mean / p50 / p95 executable return bps.

Sensitivity policies additionally report deltas versus baseline:

- signed net opportunity quote delta;
- positive missed-opportunity quote delta;
- avoided-loss quote delta;
- profitable-opportunity count delta;
- avoided-loss count delta;
- sign-flip count across comparable executable observations.

This is descriptive evidence, not an automatic promotion score.

## FL11.1 prerequisite

The FL11.1 proof must:

- be canonical and fingerprint-valid;
- say `SUFFICIENT_SAMPLE`;
- match the exact release;
- match the exact manifest/champion/action-policy identity;
- match the exact isolated shadow ledger binding;
- match the exact requested window;
- retain no promotion/PAPER cutover/signing/LIVE authority.

## Authority firewall

Every successful report records:

```text
promotion_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The module contains no:

- PAPER execution or checkpoint mutation;
- champion/registry mutation;
- scoring control path;
- provider/network client;
- systemd mutation;
- signing/submission;
- LIVE mode.

## Acceptance

Repository tests must prove:

1. exact FL11.1 `SUFFICIENT_SAMPLE` identity/window is mandatory;
2. learned SKIPs bind to exact overlay rows by canonical feature identity;
3. the existing sealed training-economics builder and counterfactual labeler are
   used;
4. profitable missed opportunities and avoided losses remain signed and
   distinguishable;
5. unavailable/missing rows are not inferred;
6. sensitivity policies may change fee/slippage assumptions only;
7. latency-policy changes fail closed;
8. sensitivity deltas reconcile observation by observation to baseline;
9. per-horizon counts reconcile to overall counts;
10. report fingerprints are canonical and deterministic;
11. no promotion/PAPER cutover/signing/LIVE authority is added;
12. Python, Rust, repository-safety, and ARM64 release gates stay green.

## FL11.2 completion boundary

FL11.2a + FL11.2b together provide the required actual-trade economics,
capacity/cost burden, expected-vs-realized calibration, entry/exit efficiency,
regime/horizon performance, missed-opportunity evidence, and explicit
fee/slippage sensitivity.

FL11.3 latency proof remains separate. LIVE remains disabled.
