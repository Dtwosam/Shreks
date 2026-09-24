# G1C V2 Discovery Bootstrap Priority Design

**Date:** 2026-09-24  
**Branch:** `fix/g1c-v2-discovery-bootstrap-priority`  
**Base:** `6140e820fbdc6bcd8e7cc498c7a60affff590ffb`

## Problem

Physical PAPER diagnostics proved that candidate `1359332` was discovered at
`1790263662740` but did not receive its first market snapshot until
`1790264723799`, a delay of 1,061,059 ms (17m 41.059s).

The relevant WSOL pair already existed before candidate discovery. The first exact
WSOL snapshot arrived 1,625,799 ms (27m 05.799s) after pair creation, leaving less
than three minutes before the sealed Fresh Launch 30-minute maximum age.

The deployed fresh-pair priority cannot prevent this initial delay because its
database selector requires an existing DexScreener market snapshot in order to
know that a recent pair exists. Once the first snapshot exists, the current
45-second fresh-pair priority behaves as designed.

The broad sampler is bounded to one due candidate per cycle and orders due work by
oldest due/discovery first. Under backlog, a newly discovered never-sampled token
can therefore wait many minutes before receiving the first request that would
bootstrap fresh-pair priority.

## Goal

Promptly bootstrap current discoveries into market sampling without increasing
the broad-sampler provider budget or changing PAPER trading behavior.

## Design

Add a deterministic registry query for **recent unsampled due candidates**.

A bootstrap candidate must:

- have `last_sample_at_unix_ms == None`;
- already be due at the current observer timestamp;
- have been discovered no more than the existing fresh-pair 30-minute lookback
  ago;
- not have been sampled by active PumpSwap priority or fresh-pair priority in the
  same cycle.

Bootstrap ordering is:

1. newest discovery timestamp first;
2. lower candidate ID first for identical discovery timestamps;
3. mint lexicographically for final deterministic tie-breaking.

In each observer cycle, after active PumpSwap priority and existing fresh-pair
priority:

1. choose at most one eligible recent unsampled bootstrap candidate;
2. if none exists, fall back to the existing oldest-due broad ordering;
3. call the existing `sample_candidate` path.

The existing `BROAD_CANDIDATES_PER_CYCLE = 1` budget remains unchanged. The
change affects ordering only, not the number of broad candidates sampled per
cycle.

A successful bootstrap market response is persisted through the existing market
snapshot path and updates the sampling registry through the existing
`sample_candidate` behavior. If the returned pair is recent, the existing
fresh-pair priority can then maintain its 45-second freshness target.

## Non-goals

This slice does **not** change:

- the 45-second fresh-pair freshness target;
- the 60–90 second 1m feature-anchor band;
- the 300–360 second 5m feature-anchor band;
- the 15m anchor band;
- PAPER Fresh Launch thresholds or confirmation count;
- safety thresholds;
- candidate quote identity or WSOL authority;
- Jupiter quote economics;
- scoring;
- model fitting;
- PAPER promotion;
- protected campaign manifest bytes;
- wallet/signing behavior;
- LIVE state.

The narrower anchor-band/cadence interaction remains a separate follow-up after
bootstrap acceptance evidence.

## Tests

RED coverage must prove:

1. with an older due backlog and a newly discovered never-sampled token, the
   newest recent unsampled token receives the single broad slot first;
2. the broad sampler still performs only one broad candidate sample in the cycle;
3. after that bootstrap succeeds, the next cycle can return to another due
   candidate while provider work remains bounded;
4. candidates outside the recent bootstrap horizon do not override existing
   broad ordering.

Existing fresh-pair-priority and broad-bounding tests must remain green.

## Physical acceptance

After immutable release/deploy:

- release SHA matches the sealed implementation;
- observer service remains healthy;
- protected V2 manifest SHA is unchanged;
- for newly discovered candidates entering the Fresh Launch horizon, measure
  `discovery_to_first_any_market_ms` and
  `discovery_to_first_exact_wsol_ms`;
- prove the prior multi-minute backlog pattern is removed under normal provider
  health;
- prove follow-up exact-pair observations continue under existing bounded
  priority sampling;
- no threshold, scoring, promotion, or LIVE authority is changed.
