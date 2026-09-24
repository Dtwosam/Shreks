# G1C V2 Discovery Bootstrap Priority Seal

**Date:** 2026-09-24  
**Integration SHA:** `6f0f35172b54288cfc27c2ca06a778779450af7e`  
**PR:** #482  
**Merged-main CI:** `36031921606`

## Proven production defect

Physical PAPER diagnostics on candidate `1359332`
(`6gtKNF38rosqNRGZsEqxPYXd9itc23cbKcjszZofpump`) established:

- candidate discovered at `1790263662740`;
- first market snapshot at `1790264723799`;
- discovery-to-first-market delay: `1,061,059 ms` (17m 41.059s);
- exact WSOL PumpSwap pair created at `1790263098000`;
- pair creation-to-first exact-WSOL snapshot: `1,625,799 ms` (27m 05.799s);
- no market evidence existed before that first exact-WSOL row;
- after bootstrap, exact-pair observations were approximately 45–47 seconds apart.

The existing fresh-pair priority could not prevent the initial delay because its
selector requires a previously persisted DexScreener pair snapshot. Before that
first snapshot, the candidate competed in the bounded broad queue, whose
oldest-due ordering allowed recent discoveries to starve behind backlog.

## Sealed behavior

The observer continues to sample at most one broad due candidate per cycle.

Within that unchanged broad budget:

1. candidates already handled by active PumpSwap priority or fresh-pair priority
   in the same cycle remain excluded;
2. a due candidate with no previous representative sample and discovery time
   within the existing 30-minute fresh-pair lookback is eligible for bootstrap;
3. eligible bootstrap candidates are ordered by newest discovery first, then
   lower candidate ID, then mint;
4. if no bootstrap candidate exists, the pre-existing oldest-due broad ordering
   is preserved;
5. sampling uses the existing `sample_candidate` path, preserving provider
   pacing, persistence, registry scheduling, provider health, and checkpoint
   behavior.

No additional broad provider request is authorized by this change.

## RED / GREEN evidence

RED head: `d4698c03e51fa4f905164f73247b659d00724a04`

CI run `36031502197`:
- ARM64 release build: PASS
- Python tests: PASS
- Repository safety: PASS
- Rust tests: FAIL

The new regression failed because the old implementation sampled
`mint-old-a` while the test market response was intentionally attributed to
`mint-fresh`, proving stale backlog won the broad slot.

GREEN head: `e0a2cd1ba917cd46c8e1b1e5ae2b1f4be00d786c`

CI run `36031556543`:
- Rust tests: PASS
- ARM64 release build: PASS
- Python tests: PASS
- Repository safety: PASS

Merged integration SHA: `6f0f35172b54288cfc27c2ca06a778779450af7e`

Merged-main CI run `36031921606`:
- Rust tests: PASS
- ARM64 release build: PASS
- Python tests: PASS
- Repository safety: PASS

## Physical acceptance required

After immutable release and production deployment:

- deployed release SHA must equal this seal commit;
- observer, PAPER evidence, and PAPER campaign services must remain healthy;
- protected campaign manifest bytes must remain unchanged;
- measure newly discovered candidates' discovery-to-first-market delay;
- verify current discoveries receive bootstrap market evidence promptly under
  normal provider health rather than waiting behind stale broad backlog;
- verify recent pairs continue receiving follow-up exact-pair observations under
  existing priority sampling;
- verify broad work remains bounded and provider failures do not increase
  materially.

Physical acceptance is not complete until VPS evidence is collected.

## Explicit non-authority

```
DISCOVERY_BOOTSTRAP_PRIORITY=SEALED
BROAD_CANDIDATES_PER_CYCLE=UNCHANGED
FRESH_PAIR_FRESHNESS_TARGET=45_SECONDS_UNCHANGED
FEATURE_ANCHOR_WINDOWS=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
PAPER_EVIDENCE_QUOTE_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

## Deferred follow-up

A separate diagnostic established that a roughly 45-second sampling cadence can
straddle the current 60–90 second one-minute anchor band. That interaction is
not changed by this slice and must be evaluated separately after bootstrap
physical acceptance.
