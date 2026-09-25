# G1C V2 Missing Mint Follow-up Diagnostics Design

**Date:** 2026-09-25  
**Base main SHA:** `d7d347a427bc628bd6a5299b33cf55cf59027dec`  
**Scope:** read-only physical-acceptance diagnostics only

## Production evidence

The exact sealed mint-acceptance FAILED-contract release was re-verified after
the 30-minute acceptance window had moved fully past deployment startup.

The bounded production result was:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_selected_observations=48
g1c_v2_mint_state_proactive_refreshes=12
g1c_v2_mint_state_missing_selected=1
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_reconstructed_checkpoints=24
g1c_v2_mint_state_max_selected_age_ms=608527
g1c_v2_paper_evidence_completed_cycles=56
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=63
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=437
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

This proves the pre-expiry freshness repair is operating for the sampled
post-deploy window: no selected observation was stale, proactive refreshes were
observed, and the maximum selected mint-state age remained below the unchanged
900,000 ms B1 ceiling.

One selected observation still had no Helius mint-state row at its exact PAPER
decision timestamp. The existing protected result does not distinguish whether:

1. the candidate received its first Helius mint-state row shortly after that
   PAPER decision, indicating a first-hydration/order race; or
2. no Helius mint-state row appeared for that candidate through the bounded
   acceptance window, indicating an unresolved collection/coverage failure.

Changing collection order or strategy behavior before distinguishing those
cases would be speculative.

## Diagnostic extension

Extend each read-only acceptance sample with the first exact Helius mint-state
observation, if any, strictly after the PAPER decision timestamp and no later
than the acceptance window end.

The acceptance summary adds only bounded aggregate evidence:

- `selected_missing_mint_later_observed_count`;
- `selected_missing_mint_unresolved_count`;
- `max_selected_missing_mint_followup_delay_ms`.

For a selected observation that already has point-in-time mint state, these
diagnostics do not alter evaluation.

For a selected observation missing point-in-time mint state:

- a later Helius row inside the bounded window increments
  `selected_missing_mint_later_observed_count`;
- no later Helius row by window end increments
  `selected_missing_mint_unresolved_count`;
- when a later row exists, its non-negative delay from the PAPER decision may
  contribute to `max_selected_missing_mint_followup_delay_ms`.

The existing `selected_missing_mint_count` remains authoritative and the
overall acceptance status remains `FAILED` whenever any selected observation
was missing at decision time.

## Historical boundary

The first post-decision mint row is diagnostic evidence only.

It must never satisfy historical B1 safety, change the reconstructed PAPER
decision, or be treated as information available at the earlier decision
timestamp.

The lookup is bounded by the already-authorized acceptance window end so the
verifier does not silently inspect arbitrary future history.

## Protected-output boundary

The protected verifier may print the three new aggregate values only.

It must not expose:

- candidate IDs;
- mint addresses;
- raw timestamps for an individual candidate;
- SQLite values/SQL;
- filesystem paths;
- provider payloads;
- exception text;
- checkpoint payloads;
- manifest contents.

## Required RED proof

Tests must fail before implementation because:

1. a missing-at-decision sample cannot yet represent a bounded later mint
   observation;
2. the evaluator does not yet separate later-observed from unresolved misses;
3. the production verifier does not yet validate/print the bounded follow-up
   diagnostics.

## Required GREEN proof

After implementation:

- missing-at-decision remains `FAILED`;
- later-observed and unresolved counters partition the missing count;
- future evidence never satisfies the historical decision;
- follow-up lookup stops at the acceptance window end;
- analyzer remains read-only;
- protected output remains aggregate/sanitized;
- Python, Rust, repository-safety, and ARM64 release gates remain green.

## Explicit non-authority

```text
MINT_ACCEPTANCE_STATUS_SEMANTICS=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_POINT_IN_TIME_REPLAY=UNCHANGED
PAPER_EVIDENCE_COLLECTION_ORDER=UNCHANGED
SAFETY_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
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
