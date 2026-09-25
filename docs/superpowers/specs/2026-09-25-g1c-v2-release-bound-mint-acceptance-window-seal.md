# G1C V2 Release-Bound Mint Acceptance Window Seal

**Date:** 2026-09-25  
**Integration SHA:** `97f4c01a42b59f58318bccdfcd0db11dab9324ed`  
**PR:** #518  
**RED CI:** `36176202302`  
**Feature-head GREEN CI:** `36176502734`  
**Merged-main CI:** `36176821412`

## Production evidence

The sealed first-hydration-priority release
`f9ffd83e5c81274706314e35859c1f1d70c30678` passed:

- merged-main CI;
- release-side Rust/Python tests;
- release bundle verification;
- immutable GitHub release creation;
- exact-release deployment.

The protected physical verifier then failed because its normal 30-minute
wall-clock sample crossed the release boundary.

Initial protected verifier result:

```text
g1c_v2_mint_state_selected_observations=46
g1c_v2_mint_state_proactive_refreshes=8
g1c_v2_mint_state_missing_selected=4
g1c_v2_mint_state_missing_later_observed=4
g1c_v2_mint_state_missing_unresolved=0
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_max_selected_age_ms=640181
g1c_v2_mint_state_max_missing_followup_delay_ms=372583
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=3
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=497
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

A protected rerun moved the wall-clock window forward but remained in the same
failure class:

```text
g1c_v2_mint_state_selected_observations=48
g1c_v2_mint_state_proactive_refreshes=9
g1c_v2_mint_state_missing_selected=4
g1c_v2_mint_state_missing_later_observed=4
g1c_v2_mint_state_missing_unresolved=0
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_max_selected_age_ms=640181
g1c_v2_mint_state_max_missing_followup_delay_ms=372583
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=4
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=496
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

The repaired release became active only near the end of those 30-minute
samples. Both verifier attempts therefore reconstructed PAPER decisions made
before the release being verified.

No sampled miss remained unresolved. No selected mint state was stale. No
observation was invalid. Provider failures were zero and Helius budget was
healthy.

This isolated a verifier-window attribution defect rather than a new collection
or B1 failure.

## Sealed repair

The control keeps the original requested verifier lookback unchanged.

It first performs the existing bounded read-only analysis so the
manifest-derived:

- B1 max critical-data age;
- proactive refresh age;
- evidence cycle interval

can be validated against the authenticated active PAPER-evidence runtime status.

That runtime status is already exact-release bound and already validates:

- release source SHA;
- process start timestamp;
- completed cycle state;
- current cycle/generation timestamps;
- provider failure state;
- Helius request budget;
- B1 max age;
- proactive refresh age.

After runtime-status validation, the control computes:

```text
effective_window_start =
    max(request.window_start_unix_ms, runtime_status.process_started_at_unix_ms)
```

If that effective start is later than the requested start, the mint-state
acceptance analyzer is rerun read-only on:

```text
[effective_window_start, request.window_end_unix_ms]
```

and that release-bound result replaces the pre-release analysis result.

The final analysis must still match the authenticated runtime status for:

```text
max_critical_data_age_ms
mint_state_refresh_age_ms
evidence_cycle_interval_ms
```

Any mismatch fails closed with a sanitized
`ANALYSIS_RUNTIME_AUTHORITY_MISMATCH` result.

If the active evidence process began after the requested window ended, the
control fails closed with `RELEASE_WINDOW_EMPTY` instead of using pre-process
history.

## Acceptance semantics remain unchanged

This does not grant a new PASS path.

For the release-bound final sample:

- missing/stale/invalid selected evidence still returns `FAILED`;
- a nonempty clean sample with qualifying proactive refresh evidence may return
  `PASS`;
- insufficient clean post-release evidence returns
  `HOLD_INSUFFICIENT_EVIDENCE`.

B1 remains 900,000 ms. The derived proactive refresh boundary remains 540,000
ms. The operator-requested lookback remains unchanged.

## RED / GREEN evidence

RED head:

`d13d84cf057809fbce78e435a1affb36a32932d7`

RED CI `36176202302`:

- Python: expected FAIL;
- repository safety: PASS;
- ARM64 release build: PASS;
- Rust: unaffected.

The Python suite passed 3,760 tests and failed exactly the two new release-bound
contracts:

1. only one analysis call occurred instead of a second process-start-clamped
   analysis;
2. final release-bound runtime authority could not be checked because no
   release-bound reanalysis existed.

Feature implementation head:

`3e9d1b76a051ba8566c2b75b41a0a0a659fb4d41`

Feature-head CI `36176502734`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`97f4c01a42b59f58318bccdfcd0db11dab9324ed`

Merged-main CI `36176821412`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Required physical follow-up

After immutable release and protected deployment, run the normal production
verifier with its unchanged 30-minute requested lookback.

Because the final mint analysis is now exact-release bounded, an immediate
post-deploy verifier must classify only evidence at or after the active
PAPER-evidence process start.

Interpret the result normally:

- `PASS`: post-release mint evidence is clean and proactive refresh evidence
  is physically observed;
- `HOLD_INSUFFICIENT_EVIDENCE`: release-bound history is clean but not yet
  sufficient for PASS;
- `FAILED`: an actual post-release missing/stale/invalid observation remains.

Do not weaken B1, PAPER selection, strategy, score, risk, or collection budgets
to force a PASS.

## Behavioral boundary

This slice changes read-only verifier attribution only.

It does **not** change:

- PAPER evidence collection ordering;
- evidence candidate limits;
- evidence cadence or provider pacing;
- PAPER candidate selection;
- holder/Jupiter evidence semantics;
- B1 or proactive-refresh thresholds;
- market/setup/regime/scoring/decision policy;
- risk assessment or sizing;
- PAPER execution/accounting;
- protected campaign-manifest bytes;
- model/champion authority;
- PAPER promotion;
- LIVE authority.

## Explicit non-authority

```text
VERIFIER_REQUEST_LOOKBACK=UNCHANGED
VERIFIER_EFFECTIVE_WINDOW=BOUND_TO_ACTIVE_EVIDENCE_PROCESS
MINT_ACCEPTANCE_STATUS_SEMANTICS=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_UNCHANGED
PAPER_EVIDENCE_COLLECTION=UNCHANGED
PAPER_CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_POINT_IN_TIME_REPLAY=UNCHANGED
SAFETY_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
