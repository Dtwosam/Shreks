# G1C V2 fresh-pair sampling priority design

Date: 2026-09-24

## Problem

Production PAPER is correctly bound to the authenticated G1C V2 WSOL runtime manifest. The manifest requires current market evidence no older than 120 seconds and a fresh-launch pair age within 30 minutes.

Production evidence showed a structurally overloaded Observer V2 broad-sampling lane:

- 537 tracked candidates,
- 443 due,
- 395 overdue by at least 120 seconds,
- nominal refresh demand 2.86 candidates/second,
- implementation cap of one broad candidate per sampler cycle.

A concrete old token acquired a new WSOL pair that was still inside the 30-minute fresh-launch window, but its token discovery age placed it on the 300-second broad cadence and backlog made the actual refresh gap much larger. PAPER correctly rejected the stale market evidence.

## Goal

Keep recently created, valid market pairs fresh enough to be observable by downstream PAPER selection even when the broad research queue is overloaded.

## Non-goals

This change does not:

- change PAPER market freshness thresholds;
- change the 30-minute fresh-launch strategy window;
- change candidate-value authority, sizing, or quote identity;
- grant scoring/model-fitting authority;
- grant PAPER promotion authority;
- grant LIVE authority;
- increase the broad sampler's one-candidate-per-cycle budget;
- treat malformed future pair-created timestamps as fresh.

## Design

Add a bounded storage selector for candidate mints with a valid pair creation timestamp inside a recent-pair lookback and without a DexScreener token-pair refresh inside a smaller freshness target.

The selector must:

1. require `pair_created_at_unix_ms <= observed_at_unix_ms <= as_of_unix_ms`;
2. require the pair creation timestamp to be inside the bounded recent-pair lookback;
3. group by canonical candidate id and mint;
4. suppress candidates that already have a current DexScreener snapshot inside the freshness target;
5. order deterministically by newest pair creation time, then candidate id;
6. apply a hard result limit.

Observer V2 will run this fresh-pair priority selector after the existing active-PumpSwap priority lane and before broad due-candidate sampling.

For each selected target, Observer V2 will query DexScreener immediately through the existing paced provider wrapper. Candidates sampled by either priority lane are excluded from duplicate broad work in that cycle.

The priority lane is outcome-neutral. It is driven only by market pair age and market observation freshness.

## Bounds

Initial sealed bounds:

- recent-pair lookback: 30 minutes;
- DexScreener freshness target: 45 seconds;
- priority target limit: 32 per sampler cycle.

The 45-second target is stricter than PAPER's 120-second market-read ceiling and leaves headroom for provider pacing and the 30-second PAPER cycle. The 32-target hard limit preserves bounded public-provider work.

## Failure semantics

Provider failures remain fail-closed and are reported through existing provider health/error handling. An empty DexScreener response is observable and does not invent market data. Priority sampling never mutates PAPER state or strategy authority.

## Acceptance

Tests must prove:

1. an old candidate with a newly created valid pair is selected for priority refresh even though its broad schedule is not due;
2. a fresh DexScreener refresh suppresses duplicate priority work;
3. malformed future pair-created timestamps are ignored;
4. a priority-sampled candidate is not also broad-sampled in the same cycle;
5. existing active-PumpSwap priority and bounded broad-sampling tests continue to pass.

## Authority

This is an observer evidence-freshness correction only. Scoring/model fitting remains not granted, PAPER promotion remains blocked, and LIVE remains disabled.
