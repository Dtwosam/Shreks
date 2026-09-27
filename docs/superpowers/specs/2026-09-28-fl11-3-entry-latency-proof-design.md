# Fast Lane FL11.3 Entry Latency Proof — Design

**Date:** 2026-09-28  
**Base main SHA:** `f4e9d960ad0d27724f458f759eb52183660e5673`

## Purpose

Prove whether the learned Fast Lane PAPER-shadow entry path is fast enough for
the horizons on which the model claims BUY edge.

The proof measures each authenticated learned BUY from the original event
timestamp through decision evaluation and, when an entry is booked, through the
actual isolated PAPER ledger booking.

Immediate BUY fills and deferred BUYs that later fill through the authenticated
pending-BUY retry path are both attributed to the original learned BUY.

This slice does not infer LIVE latency, alter execution policy, promote a
champion, or enable LIVE.

## Why the proof is per decision

Existing decision and execution telemetry already expose useful aggregate p50/
p95/p99 values. FL11.3 must not claim an end-to-end percentile by adding
separate percentiles.

For each BUY, this proof joins the exact durable evidence and computes:

```text
event_to_evaluation_ms
decision_compute_ms
decision_to_booked_entry_ms
event_to_booked_entry_ms
event_to_booked_fraction_of_selected_horizon
```

Only after computing those per-observation values are p50/p95/p99/max
aggregates produced.

## Population

The decision population is the exact authenticated FL11.1 window.

The FL11.1 proof must:

- be canonical and fingerprint-valid;
- say `SUFFICIENT_SAMPLE`;
- match release, manifest, champion, action-policy, ledger binding, and window;
- reconcile exactly to the learned decision count selected for the window.

Only learned `BUY` decisions are entry-latency observations.

Every BUY must carry a positive learned `selected_horizon_ms`.

## Immediate BUY path

For each BUY:

1. authenticate its exact execution-source record;
2. load the historical checkpoint/runtime pair referenced by that source;
3. reconstruct the decision;
4. load the durable successor pair;
5. require the successor to equal the reconstruction;
6. inspect the append-only ledger delta.

A `POSITION_OPENED` ledger entry supplies the authoritative booked timestamp.

## Deferred BUY retry path

If the fresh BUY remains durably pending, scan the authenticated retry-source
records bound to that original pending source event.

For each retry in checkpoint order:

1. authenticate its historical checkpoint/runtime pair;
2. reconstruct the retry;
3. require its durable successor to equal reconstruction;
4. inspect the ledger delta.

The first durable `POSITION_OPENED` entry is the actual booked entry for the
original learned BUY.

A retry that terminates the pending BUY without an opening is a terminal
unbooked BUY. Missing source/successor evidence remains an explicit coverage
failure and is never imputed as fast.

## Observation statuses

Each BUY ends in exactly one status such as:

- `BOOKED_IMMEDIATE`;
- `BOOKED_RETRY`;
- `TERMINAL_UNBOOKED`;
- `PENDING_UNRESOLVED`;
- `MISSING_EXECUTION_SOURCE`;
- `MISSING_SUCCESSOR_COMMIT`;
- `MISSING_RETRY_SUCCESSOR_COMMIT`.

Malformed or contradictory evidence fails the entire proof closed.

## Explicit latency policy

There are no hidden latency thresholds.

A versioned operator-reviewed policy supplies:

- minimum BUY decision count;
- minimum booked-entry count;
- minimum distinct selected-horizon count;
- maximum unbooked BUY fraction;
- maximum p95 event-to-booked fraction of selected horizon;
- maximum p99 event-to-booked fraction of selected horizon.

Fractions are positive finite ratios. For example, `0.5` means the specified
percentile must book within half of the selected horizon.

The repository does not choose the policy values.

## Proof decision

The report emits only:

```text
LATENCY_PROVEN
LATENCY_NOT_PROVEN
```

A PASS means the observed entry path meets every explicit policy gate for that
window. It does not grant promotion or LIVE authority.

## Report

The report contains:

- exact runtime/sample identity;
- policy + policy fingerprint;
- BUY count / booked count / unbooked count;
- status counts;
- event-to-evaluation summary;
- decision-compute summary;
- decision-to-booked summary;
- event-to-booked summary;
- event-to-booked / selected-horizon ratio summary;
- within-selected-horizon count/rate;
- per-selected-horizon summaries;
- deterministic per-BUY audit rows;
- gate results;
- canonical report fingerprint.

## Exit timing

FL11.2a already reports closed-position decision-to-booking and holding-vs-
selected-horizon evidence. FL11.3 does not duplicate that accounting.

## Authority firewall

The collector is read-only and contains no:

- PAPER execution/ledger mutation;
- execution-policy mutation;
- champion/registry mutation;
- scoring control path;
- provider/network client;
- systemd mutation;
- signing/submission;
- LIVE mode.

Every report records:

```text
promotion_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Acceptance

Repository tests must prove:

1. exact FL11.1 `SUFFICIENT_SAMPLE` identity/window is mandatory;
2. decision count reconciles with FL11.1;
3. immediate BUY booking is measured from the original event;
4. deferred BUY retry booking is attributed to the original BUY event/horizon;
5. source/checkpoint/runtime/successor contradictions fail closed;
6. missing durable evidence remains explicit unbooked coverage;
7. end-to-end percentiles are computed from joined per-BUY values;
8. per-horizon counts reconcile to overall counts;
9. all thresholds are explicit policy inputs;
10. strict policies can yield `LATENCY_NOT_PROVEN` without mutating evidence;
11. no promotion/PAPER cutover/signing/LIVE authority is added;
12. Python, Rust, repository-safety, and ARM64 release gates stay green.

## Following slice

After real production-shadow evidence passes FL11.3 under an explicitly reviewed
latency policy, proceed to FL11.4 champion/challenger promotion evidence.

LIVE remains disabled.
