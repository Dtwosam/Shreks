# FL9 FL6 Baseline Replay Dispatcher — Design

**Date:** 2026-09-04

## Status

Design for the next FL9 evidence slice after the learned-candidate PAPER executor was SEALED.

Base: merged-main `870477e71c98339856788896b26a3b7107cf56ea`.

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Provide one deterministic, posture-aware replay seam over the six already-SEALED FL6 baseline evaluators so later evidence campaigns can apply those baselines to the exact same point-in-time market population without inventing a monolithic strategy.

This slice is deliberately narrower than the later PAPER comparison. It answers:

> At this point-in-time state and current posture, is this FL6 baseline applicable, and if so, what exact sealed FL6 assessment does it produce?

The dispatcher does not create fills, positions, PnL, or superiority evidence.

## Architectural constraint

FL6 is intentionally split by posture:

- FL6.1 Impulse Scalp — flat-position `BUY/SKIP`;
- FL6.2 Micro Pullback / Reclaim — flat-position `BUY/SKIP`;
- FL6.3 Pre-Graduation Acceleration — flat-position `BUY/SKIP`;
- FL6.4 Graduation / Migration Flow — flat-position `BUY/SKIP`;
- FL6.5 Wallet/Cohort Ride/Fade — open-position `HOLD/REDUCE/SELL`;
- FL6.6 Longer Runner — open-position `HOLD/REDUCE/SELL`.

The replay layer must not blur those contracts.

If a baseline is asked to evaluate the wrong posture, the result is explicit `NotApplicable`. It is **not** converted to a fake `SKIP`, `HOLD`, or weaker substitute baseline.

## Package boundary

Add:

`crates/shreks-core/src/fast_lane/baseline_replay.rs`

The module remains pure `shreks-core` strategy/research logic.

No provider calls, network, SQLite, filesystem, PAPER, risk-authority, registry, promotion, signer, submission, deployment, secret, or LIVE authority belongs here.

## Public contract

### Version

`FAST_BASELINE_REPLAY_VERSION = 1`

### Baseline identity

`FastBaselineKind`:

- `ImpulseScalp`
- `MicroPullback`
- `PreGraduation`
- `GraduationFlow`
- `WalletCohort`
- `LongerRunner`

Each value exposes the sealed underlying FL6 baseline version.

### Posture

`FastBaselinePosture`:

- `Flat`
- `Open`

Posture is supplied explicitly by the caller. The dispatcher does not infer authoritative portfolio state from market features.

### Replay input

`FastBaselineReplayInput<'a>` is an enum. Each variant carries exactly the arguments already required by its sealed evaluator.

Examples:

- Impulse Scalp: snapshot + optional explicit execution economics + policy;
- Graduation Flow: pre/post snapshots + optional boost context + optional explicit execution economics + policy;
- Wallet Cohort: snapshot + optional point-in-time wallet evidence + authoritative position input + policy;
- Longer Runner: snapshot + protective state + optional point-in-time continuation evidence + policy.

No baseline-specific evidence is synthesized by the dispatcher.

### Replay output

`FastBaselineReplayAssessment` is an enum with:

- `NotApplicable(FastBaselineNotApplicable)`, or
- one typed variant containing the exact sealed assessment:
  - `ImpulseScalp(ImpulseScalpAssessment)`
  - `MicroPullback(MicroPullbackAssessment)`
  - `PreGraduation(PreGraduationAssessment)`
  - `GraduationFlow(GraduationFlowAssessment)`
  - `WalletCohort(WalletCohortAssessment)`
  - `LongerRunner(LongerRunnerAssessment)`

The wrapper provides read-only helpers for:

- replay version,
- baseline kind,
- baseline version,
- action (`Option<FastLaneAction>`; none only for not-applicable),
- market identity,
- as-of timestamp.

The underlying typed assessment is preserved so no FL6 reason/economic/audit fields are lost.

### Not-applicable evidence

`FastBaselineNotApplicable` records:

- replay version;
- baseline kind;
- baseline version;
- actual posture;
- required posture;
- market;
- as-of timestamp.

This becomes explicit later campaign evidence instead of a silently weakened strategy decision.

### Errors

`FastBaselineReplayError` wraps each existing FL6 evaluator error without rewriting it.

Malformed/contradictory applicable evidence therefore keeps the original fail-closed behavior.

## Evaluation semantics

1. determine baseline identity and required posture;
2. capture the point-in-time market/timestamp from the baseline's canonical snapshot:
   - FL6.4 uses the post-migration snapshot as the decision identity;
   - all others use their single current snapshot;
3. if current posture is incompatible, return `NotApplicable` without fabricating an action;
4. otherwise invoke exactly one sealed FL6 evaluator with the supplied arguments;
5. wrap the exact typed assessment or exact typed evaluator error.

No arbitration across baselines occurs.

## Point-in-time / campaign boundary

This core dispatcher consumes canonical `FastMarketSnapshot` values and explicit baseline-specific evidence.

A following evidence-hydration slice will reconstruct those snapshots from the same immutable FL8.1 feature rows used for learned-policy campaign requests and will supply execution/wallet/continuation evidence explicitly.

That later layer must fail closed when a required context class is unavailable. It must not use future labels, forecast prices as PAPER fills, or synthetic wallet evidence.

## Why no baseline aggregator

Combining an FL6.1-6.4 entry rule with FL6.5/6.6 position management would create a new strategy that has never been specified or sealed.

That may eventually be useful, but it must be a separately named, explicitly tested candidate.

This dispatcher only preserves the six existing baseline contracts.

## TDD requirements

RED tests must prove the intended contract before production code exists:

1. flat Impulse Scalp delegates exactly and preserves BUY/typed assessment;
2. open posture for an entry-only baseline is explicit not-applicable;
3. flat posture for an open-position baseline is explicit not-applicable;
4. open Longer Runner delegates exactly, including missing-continuation fail-closed REDUCE behavior;
5. repeated identical input is deterministic;
6. baseline kind/version helpers are stable;
7. source authority firewall forbids provider/network/storage/PAPER/LIVE dependencies.

## Economic boundary

This slice does **not** prove any deterministic baseline profitable.

It also does not yet satisfy FL9's economic exit.

The later campaign layer must:

- hydrate the exact same point-in-time event population;
- build posture-valid baseline decision streams without inventing an unsealed aggregate strategy;
- execute comparable decisions through the already-SEALED PAPER executor using identical contemporaneous quote evidence;
- evaluate through E11/E5;
- pass all required baseline run evidence to the SEALED FL9 superiority proof.

Until real evidence returns `SUPERIOR`, FL9 remains **EVIDENCE PENDING** and LIVE remains disabled.
