# G1C V2 Mint First-Hydration Priority Design

**Date:** 2026-09-25  
**Base main SHA:** `31253a81f0ffef70f48aac0fb8ed9e29f67a78e1`

## Physical evidence

Exact-release production verification returned:

```text
selected_observations=48
proactive_refreshes=12
missing_selected=4
missing_later_observed=4
missing_unresolved=0
stale_selected=0
invalid_observations=0
max_selected_age_ms=719757
max_missing_followup_delay_ms=98923
provider_failures_last_cycle=0
helius_requests_attempted=3
helius_requests_limit=500
helius_requests_remaining=497
helius_budget_exhausted=false
```

Every point-in-time mint miss was eventually hydrated inside the bounded window.
No miss remained unresolved. The maximum observed follow-up delay was 98,923 ms.

This proves a first-hydration/order race rather than provider coverage failure,
budget exhaustion, or B1 pre-expiry freshness regression.

## Proven ordering gap

The PAPER evidence selector intentionally supports too-young prewarming, but its
current ordering ranks every already-entry-window candidate ahead of every
too-young candidate before applying the bounded `max_candidates` cap.

With a small candidate budget, a candidate can therefore:

1. be visible as a fresh exact-quote pair while still too young for PAPER;
2. lose the evidence slots to already-mature candidates;
3. cross the PAPER minimum-age boundary without a Helius mint row;
4. be selected/evaluated by PAPER;
5. receive first mint-state hydration only on a later evidence cycle.

## Repair

Within the existing exact-quote fresh-launch evidence population, prioritize
candidates with **no Helius mint-state row at or before the evidence cycle
timestamp** before candidates that already have mint-state evidence.

After that first-hydration priority, preserve the existing ordering:

1. PAPER entry-window age class before too-young prewarm;
2. newest canonical market observation;
3. candidate ID tie-break.

The total evidence candidate limit is unchanged. Provider budgets, collection
cadence, holder/quote semantics, and PAPER selection are unchanged.

Once a candidate has any Helius mint row, it loses the first-hydration priority
and returns to normal evidence ordering.

## RED proof

Add a focused selector test where:

- two entry-window candidates already have Helius mint state;
- one exact-quote too-young candidate has no mint state;
- `max_candidates=2`.

The current implementation selects the two mature candidates. The required
behavior selects the missing-mint candidate within the bounded evidence budget,
proving prewarming can happen before PAPER eligibility.

## Non-authority

```text
PAPER_EVIDENCE_MAX_CANDIDATES=UNCHANGED
PAPER_EVIDENCE_INTERVAL=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
PAPER_MIN_PAIR_AGE=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_UNCHANGED
HOLDER_REFRESH_SEMANTICS=UNCHANGED
QUOTE_SEMANTICS=UNCHANGED
SAFETY_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
