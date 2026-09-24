# G1C V2 PAPER Mint-State Pre-Expiry Headroom Design

**Date:** 2026-09-24  
**Branch:** `fix/g1c-v2-mint-state-preexpiry-headroom`  
**Base:** `e80af3bf5c7db5ed93c45b5e5f0675658491e3cb`

## Physical residual defect

The sealed mint-state freshness repair proved that stale existing Helius mint-state
rows can be refreshed without changing B1 safety semantics. Physical acceptance
also proved a residual scheduler race: PAPER can consume a mint-state row after
it crosses the authenticated B1 freshness boundary but before the next
`shreks-paper-evidence` refresh cycle.

Deployed runtime facts:

- PAPER evidence interval: 60 seconds;
- PAPER evidence max candidates: 2;
- B1 max critical-data age: 900,000 ms;
- Helius process request budget: 500;
- provider failures: zero;
- budget exhaustion: zero.

Three post-deploy stale PAPER evaluations were observed. Their mint-state ages at
decision were 921,299 ms, 1,041,462 ms, and 915,016 ms. Each received a
successful Helius refresh roughly 50.8--54.9 seconds after the PAPER decision.

Point-in-time selector reconstruction proved that all three candidates had already
been selected by the evidence daemon while their mint state was still valid.
The last useful selected-cycle remaining lifetimes were:

- candidate 1381030: 57,318 ms;
- candidate 1381414: 313,233 ms;
- candidate 1381335: 311,999 ms.

Therefore the residual issue is not provider failure, budget exhaustion, or
missing selector coverage in these observed cases. Refresh begins only after
evidence is already stale; selected candidates need bounded pre-expiry headroom.

## Goal

Refresh mint-state evidence early enough to survive normal two-slot evidence
selector rotation, while preserving the authenticated 900,000 ms B1 validity
threshold and keeping Helius usage bounded.

## Derived headroom

No new manifest field or host policy is introduced.

The PAPER evidence runtime derives mint-state refresh headroom from two existing
runtime authorities:

- authenticated B1 `mint_state_max_age_ms`;
- configured PAPER evidence `cycle_interval`.

Define:

```
scheduler_headroom_ms = 6 * cycle_interval_ms
bounded_headroom_ms = min(
    scheduler_headroom_ms,
    mint_state_max_age_ms / 2,
)
refresh_age_ms = mint_state_max_age_ms - bounded_headroom_ms
```

For the deployed campaign:

- cycle interval = 60,000 ms;
- six-cycle scheduler headroom = 360,000 ms;
- half B1 max age = 450,000 ms;
- bounded headroom = 360,000 ms;
- proactive refresh age = 540,000 ms.

This exceeds the largest observed required pre-expiry headroom (313,233 ms) by
46,767 ms.

The half-age cap guarantees that, for positive B1 max ages, proactive scheduling
never consumes more than half of the authenticated evidence lifetime as
headroom. A continuously selected candidate therefore cannot be refreshed merely
because of this guard more frequently than once per remaining half-lifetime.

If B1 max age is zero, refresh age is zero, preserving the existing exact
fail-closed semantics rather than inventing a positive freshness allowance.

## Runtime behavior

For each candidate already selected by the existing PAPER evidence selector:

1. compute the derived proactive refresh age;
2. search for an exact Helius mint-state row inside
   `[as_of - refresh_age_ms, as_of]`;
3. if found, suppress the Helius mint-state request;
4. if absent, make one refresh attempt through the existing bounded Helius
   provider;
5. persist correctly attributed evidence using the existing path;
6. provider failures remain fail-closed.

This does not widen the evidence candidate set or change its ordering.

## Non-goals / authority firewall

No changes to:

- B1 `max_critical_data_age_ms = 900000`;
- B1 pass/reject semantics;
- evidence candidate limit or ordering;
- holder refresh semantics;
- Jupiter quote semantics;
- Fresh Launch thresholds;
- B2 feature schema or anchor bands;
- quote mint, sizing, slippage, or execution semantics;
- protected campaign manifest bytes;
- scoring/model fitting;
- PAPER promotion;
- signing/wallet;
- LIVE.

## Tests

RED/GREEN coverage must prove:

1. at the old behavior, a row aged 586,767 ms suppresses mint refresh even though
   the deployed 60s cadence needs proactive headroom;
2. with a 900,000 ms B1 max age and 60s evidence interval, the derived refresh
   age is exactly 540,000 ms;
3. a row exactly 540,000 ms old remains within the proactive freshness window;
4. a row 540,001 ms old triggers one bounded mint refresh;
5. the six-cycle headroom is capped at half the B1 max age;
6. zero B1 max age remains representable and yields zero refresh age;
7. existing stale-row, exact-B1-boundary, holder, quote, launcher, provider
   failure, repository-safety, Python, Rust, and ARM64 tests remain green.

## Physical acceptance

After seal/release/deploy:

- release and protected manifest identity pass;
- services remain healthy;
- runtime B1 max-age authority remains 900,000 ms;
- no selected PAPER evaluation is blocked solely by mint-state
  `CRITICAL_DATA_STALE`;
- mint refreshes occur before B1 expiry when a selected row crosses the derived
  540,000 ms proactive age;
- provider failures remain zero/acceptable;
- Helius budget is not exhausted;
- historical replay remains unchanged.

No successful physical acceptance grants PAPER promotion or LIVE authority.
