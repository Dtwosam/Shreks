# Shreks Adaptive Path Observation Amendment

**Status:** Approved continuation of Phase A observation architecture  
**Date:** 2026-08-23  
**Repository:** `Dtwosam/Shreks`

## 1. Purpose

The seven A9 outcome checkpoints (1m, 5m, 15m, 30m, 1h, 4h, 24h) are standardized future labels. They are not sufficient by themselves to describe the path a token took between labels.

Shreks must also collect budget-aware market observations between checkpoints so later research can study sequences such as liquidity growth, flow acceleration, drawdowns, recovery, venue migration, and other path-dependent behavior.

This amendment adds **lifecycle-adaptive path observation** while preserving every Phase A safety and free-source constraint.

## 2. Non-negotiable behavior

1. Official A9 checkpoints remain unchanged and remain the standardized outcome labels.
2. In-between samples are ordinary normalized `market_snapshots`; no second competing market-data format is introduced.
3. Sampling is best-effort and budget-aware. Missing an adaptive sample is preferable to bypassing provider limits.
4. Official due checkpoints have priority over adaptive path samples.
5. A candidate that is due for both an official checkpoint and an adaptive sample receives one market-observation pass, not two.
6. Adaptive sampling must not trigger chain-state/RPC calls solely because a path sample is due.
7. Realtime Pump wake-ups remain durable-inbox-only between full cycles; they must not trigger adaptive market polling.
8. Adaptive schedule state survives restart and is idempotent.
9. Delayed/backlogged samples advance from the actual sample time; Shreks must not burst through missed historical intervals to “catch up.”
10. Adaptive sampling stops after the candidate is 24 hours old in V1.
11. No paid provider or hidden paid fallback may be introduced.
12. No trading, signing, wallet access, or execution capability is introduced by this amendment.

## 3. Lifecycle cadence V0

V0 uses deterministic token age rather than arbitrary profitability/activity thresholds. This gives Shreks a reproducible baseline dataset before it has enough evidence to justify more complex adaptive rules.

Target interval after the last successful adaptive market pass:

| Candidate age | Target interval |
| --- | ---: |
| 0 to <5 minutes | 30 seconds |
| 5 to <15 minutes | 60 seconds |
| 15 to <30 minutes | 120 seconds |
| 30 to <60 minutes | 300 seconds |
| 1 to <4 hours | 900 seconds |
| 4 to <24 hours | 3600 seconds |
| >=24 hours | stopped |

The first adaptive sample is due 30 seconds after durable discovery.

These are scheduling targets, not guarantees. Provider pacing and bounded batches may make an actual sample later than its target.

## 4. Shared market revisit budget

A full observer cycle has a bounded **revisit** budget for already-known candidates. Official checkpoint candidates are selected first. Adaptive-path candidates fill only unused revisit capacity.

V0 revisit candidate limit: **16 distinct candidates per full cycle**.

Examples:

- 16 checkpoint candidates due -> 0 additional adaptive-only candidates.
- 7 checkpoint candidates due -> up to 9 adaptive-only candidates.
- 0 checkpoint candidates due -> up to 16 adaptive-only candidates.

Newly discovered candidates continue through their normal first-observation path and are deduplicated from revisit work by candidate ID.

Existing per-provider request pacing remains authoritative. The shared revisit cap prevents the adaptive layer from multiplying an already bounded outcome workload.

## 5. Durable schedule state

SQLite schema v5 adds one row per candidate describing adaptive sampling state.

Required fields:

- `candidate_id` primary/foreign key,
- `next_due_at_unix_ms`,
- `last_sample_at_unix_ms` nullable,
- `sample_count`,
- `status` (`active` or `completed`),
- `cadence_version` (`lifecycle_v0`).

Schedule creation is idempotent and anchored to the durable candidate discovery time.

When an adaptive market pass completes, schedule advancement uses the actual sample timestamp and the candidate age at that timestamp. When age reaches 24 hours, status becomes `completed` and the candidate leaves the adaptive due set permanently.

## 6. Evidence semantics

Adaptive sampling stores the same provider-neutral `market_snapshots` already used elsewhere in Phase A.

This means path samples can improve existing A9 metrics without schema duplication:

- MFE/MAE can use more observations between baseline and checkpoint,
- liquidity/volume/flow trajectories become available to later feature engineering,
- provider and venue identity remains auditable,
- venue migration can be reconstructed from the snapshot sequence.

Adaptive scheduling metadata must never be mistaken for a market feature. The schedule says when Shreks attempted to observe; `market_snapshots` contain the actual evidence.

## 7. Failure and missing-data behavior

- Provider errors keep the candidate’s adaptive schedule due for a later cycle; they do not fabricate a sample.
- A provider returning no pairs does not prove a rug or dead pool.
- If at least one valid market snapshot is persisted for the candidate during the adaptive pass, the schedule may advance.
- If no valid market snapshot is stored, the schedule remains due rather than pretending the sample occurred.
- Existing provider-health tracking records infrastructure failures normally.

## 8. Restart behavior

After process restart:

- active adaptive schedules remain active,
- overdue schedules are eligible in deterministic due-time order,
- completed schedules remain completed,
- no duplicate schedule row is created,
- no missed-interval catch-up burst is attempted.

## 9. Deferred adaptive intelligence

Do not add arbitrary “hot token” thresholds in V0. After Shreks has collected enough path data, a later phase may evaluate evidence-backed sampling priorities using observed liquidity, volume, flow, wallet behavior, setup state, or market regime.

Any later activity-based sampler must remain deterministic/versioned first and must prove that the additional API cost improves research/trading value before promotion.

## 10. Success criterion

Running Shreks in observe mode should produce a restart-safe sequence of normalized market snapshots between the official outcome checkpoints, with denser coverage early in a token’s life, progressively sparser coverage later, no duplicate work when an official checkpoint is also due, no extra chain calls for path sampling, and no violation of the existing free-provider pacing model.
