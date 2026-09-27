# Fast Lane FL11.1 Independent Shadow Sample Proof — Design

**Date:** 2026-09-27  
**Base main SHA:** `fbf7461de50a4955212c22f67db9445000e6573c`

## Purpose

Add the first FL11 proof boundary for the current learned Fast Lane PAPER-shadow
runtime.

FL11.1 asks whether enough independent opportunities/trades have accumulated
across varied market conditions to justify later economic analysis. This slice
does **not** decide profitability, superiority, promotion, PAPER cutover, or
LIVE readiness.

The proof consumes only already-persisted immutable shadow evidence:

- learned decision evidence;
- authenticated historical execution-input source records;
- exact market regime carried by BUY execution authority;
- the isolated shadow PAPER ledger checkpoint.

No fill, decision, regime, or trade outcome is fabricated.

## Command

Add one read-only CLI:

```text
shreks-fast-paper-shadow-sample-proof
```

Inputs include:

- exact runtime manifest;
- exact shadow execution policy;
- exact isolated shadow ledger/run id;
- decision-evidence directory;
- execution-source directory;
- explicit release SHA;
- explicit sample window;
- an explicit caller-supplied sample-policy version and thresholds.

There are no repository defaults for “enough evidence”.

## Sample policy

The explicit policy requires positive thresholds for:

- decision count;
- distinct market count;
- distinct mint count;
- observed decision span;
- closed isolated PAPER positions;
- distinct traded mints;
- distinct BUY market regimes;
- distinct selected horizons.

The policy is evidence governance only. It is not a trading policy.

## Evidence integrity

Every selected decision must have:

- exact release identity;
- one stable manifest/champion/action-policy identity;
- unique source sequence;
- unique source event id;
- unique evidence fingerprint;
- point-in-time timestamp inside the requested window.

For every BUY decision, the proof attempts to authenticate its exact persisted
execution-input source against the historical checkpoint/runtime pair referenced
by that source record.

The BUY regime counts only after the canonical source record authenticates.
Missing BUY execution-source evidence is reported as incomplete sample evidence;
a malformed/conflicting source fails closed.

## Closed-position sample

The proof loads the isolated shadow checkpoint at or before the end of the
requested window and counts only positions whose canonical ledger state is
`CLOSED` with `closed_at_unix_ms` inside that window.

This slice records sample breadth only. It does not calculate expectancy,
profit factor, drawdown, winner/loser averages, or any other FL11.2 economic
metric.

## Decision

The report has only:

```text
SUFFICIENT_SAMPLE
INSUFFICIENT_SAMPLE
```

Integrity contradictions raise an error instead of becoming a sample score.

`SUFFICIENT_SAMPLE` means only that every explicit FL11.1 sample threshold
passed. It does not imply positive expectancy or authorize promotion.

## Authority firewall

Every successful report records:

```text
promotion_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The module must contain no:

- champion/registry mutation;
- scoring control path;
- PAPER execution mutation;
- systemd mutation;
- provider/network client;
- signing/submission;
- LIVE mode.

## Acceptance

Repository tests must prove:

1. sample thresholds are explicit and positive;
2. broad independent fixtures pass deterministically;
3. narrow samples remain `INSUFFICIENT_SAMPLE`;
4. missing BUY regime source evidence prevents a sufficient sample;
5. runtime identity drift fails closed;
6. regime evidence cannot be attached to a non-BUY decision;
7. a real learned-shadow BUY fixture authenticates its historical source and
   regime;
8. closed positions are counted only from the isolated shadow ledger;
9. report fingerprints are canonical and deterministic;
10. the CLI is packaged;
11. promotion/PAPER cutover/signing/LIVE authority remains absent;
12. Python, Rust, repository-safety, and ARM64 release gates stay green.

## Following slice

FL11.2 can consume a sample that has passed this independent-sample gate and
build the complete after-cost economics/calibration report.

A fixture passing FL11.1 proves only sample-proof mechanics. Real FL11 progress
still requires real production-shadow evidence.

LIVE remains disabled.
