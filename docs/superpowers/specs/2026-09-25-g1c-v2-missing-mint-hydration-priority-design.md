# G1C V2 Missing Mint First-Hydration Priority Design

**Date:** 2026-09-25  
**Base main SHA:** `31253a81f0ffef70f48aac0fb8ed9e29f67a78e1`  
**Scope:** bounded PAPER-evidence collection ordering only

## Production evidence

The exact sealed missing-mint follow-up diagnostics release was deployed and
verified through protected production run `36172088078`.

The read-only verifier returned:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_selected_observations=48
g1c_v2_mint_state_proactive_refreshes=12
g1c_v2_mint_state_missing_selected=4
g1c_v2_mint_state_missing_later_observed=4
g1c_v2_mint_state_missing_unresolved=0
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_reconstructed_checkpoints=24
g1c_v2_mint_state_max_selected_age_ms=719757
g1c_v2_mint_state_max_missing_followup_delay_ms=98923
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=3
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=497
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

All four point-in-time missing mint observations were later hydrated inside the
bounded acceptance window. None remained unresolved. No selected mint state was
stale and provider/budget health was clean.

This isolates an ordering/readiness problem rather than a Helius availability,
budget, B1 freshness, or unresolved collection problem.

## Existing ordering boundary

The PAPER evidence selector already admits too-young fresh pairs for prewarming,
but it currently sorts by pair-age class before applying its bounded
`max_candidates` cap:

1. entry-window candidates;
2. too-young prewarm candidates;
3. newest canonical market observation;
4. candidate id.

Therefore an already-hydrated entry-window population can consume the entire
bounded evidence budget while a newly observed candidate with no Helius mint
state remains only in the prewarm tail.

The PAPER selector itself is not changed by this slice.

## Sealed behavior to implement

Within the existing PAPER-evidence candidate universe, add one operational
readiness priority before the current age/market ordering:

1. candidates with **no exact Helius mint-state row at or before the evidence
   cycle timestamp**;
2. candidates that already have exact Helius mint-state evidence;
3. within each readiness class, preserve the existing pair-age priority;
4. then preserve newest canonical market observation;
5. then preserve candidate-id ordering;
6. apply the existing `max_candidates` cap only after this ordering.

This means a missing-mint too-young candidate may prewarm ahead of an
already-hydrated entry-window candidate.

This is evidence-collection scheduling only. It does not make the too-young
candidate PAPER-entry eligible and does not alter PAPER candidate selection.

## Bounds preserved

This slice must not change:

- evidence candidate cap;
- evidence cycle interval;
- Helius per-process request limit;
- provider pacing;
- exact WSOL quote identity;
- market-source priority;
- pair-age bounds;
- holder refresh behavior;
- Jupiter quote semantics;
- proactive 540,000 ms mint refresh boundary;
- B1 900,000 ms critical-data age;
- PAPER selector/strategy/scoring/risk behavior.

Provider failure remains fail-closed. A missing-mint candidate that cannot be
hydrated still remains unknown evidence rather than a fabricated fact.

## Schema boundary

`fresh_launch_candidates` may validate/read the existing
`token_mint_states(candidate_id, provider, observed_at_unix_ms)` table because
mint readiness now participates in operational evidence scheduling.

Legacy `recent_candidates` behavior and its minimal schema boundary remain
unchanged.

## Required RED proof

Before implementation, tests must prove that:

1. with a bounded limit, already-hydrated entry-window candidates currently
   starve a missing-mint too-young prewarm candidate;
2. the desired order requires the missing-mint candidate to be selected before
   already-hydrated candidates;
3. the selected missing-mint candidate receives the existing single bounded
   Helius first-hydration request through the normal evidence cycle.

## Required GREEN proof

After implementation:

- missing-mint readiness is evaluated point-in-time at the evidence cycle
  timestamp;
- future mint rows never count as readiness;
- missing-mint priority is applied before the cap;
- existing age/market/id order is preserved inside each readiness class;
- provider budget and failure semantics remain unchanged;
- Rust, Python, repository-safety, and ARM64 release gates pass.

## Physical acceptance

After immutable release and protected deployment, rerun the exact mint-state
physical verifier.

The desired result is:

- `selected_missing_mint_count = 0`;
- `selected_stale_mint_count = 0`;
- `invalid_observation_count = 0`;
- `proactive_refresh_count >= 1`;
- Helius budget unexhausted;
- no recent provider-failure escalation.

If point-in-time misses persist, the next slice must be driven by the new
physical evidence; do not weaken PAPER selection, B1, strategy, score, or risk
thresholds.

## Explicit non-authority

```text
PAPER_EVIDENCE_FIRST_HYDRATION_PRIORITY=BOUNDED_OPERATIONAL
PAPER_EVIDENCE_MAX_CANDIDATES=UNCHANGED
PAPER_EVIDENCE_INTERVAL=UNCHANGED
PAPER_CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_POINT_IN_TIME_REPLAY=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
HOLDER_REFRESH_SEMANTICS=UNCHANGED
JUPITER_QUOTE_SEMANTICS=UNCHANGED
SETUP_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
