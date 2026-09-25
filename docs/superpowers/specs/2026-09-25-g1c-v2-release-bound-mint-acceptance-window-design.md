# G1C V2 Release-Bound Mint Acceptance Window Design

**Date:** 2026-09-25  
**Base main SHA:** `3a506d75dc9830763c242a71bd9bba1496ab5e29`  
**Scope:** read-only mint-state physical-verifier window binding only

## Physical evidence

The sealed first-hydration-priority release
`f9ffd83e5c81274706314e35859c1f1d70c30678` was built, released, and deployed
successfully.

The first protected verifier attempt returned:

```text
selected_observations=46
proactive_refreshes=8
missing_selected=4
missing_later_observed=4
missing_unresolved=0
stale_selected=0
invalid_observations=0
max_selected_age_ms=640181
max_missing_followup_delay_ms=372583
provider_failures_last_cycle=0
helius_requests_attempted=3
helius_requests_limit=500
helius_requests_remaining=497
helius_budget_exhausted=false
physical_acceptance=FAILED
```

A protected rerun returned the same failure class:

```text
selected_observations=48
proactive_refreshes=9
missing_selected=4
missing_later_observed=4
missing_unresolved=0
stale_selected=0
invalid_observations=0
max_selected_age_ms=640181
max_missing_followup_delay_ms=372583
provider_failures_last_cycle=0
helius_requests_attempted=4
helius_requests_limit=500
helius_requests_remaining=496
helius_budget_exhausted=false
physical_acceptance=FAILED
```

The verifier request used the normal 30-minute wall-clock window. The repaired
release became active only near the end of that window, so the exact-release
verifier still reconstructed PAPER decisions made by the previous release.

This is a verifier-window attribution defect. It is not evidence that the new
first-hydration ordering failed:

- every miss was later observed;
- no miss remained unresolved;
- no selected mint state was stale;
- no observation was invalid;
- provider failures were zero;
- Helius budget remained healthy.

## Existing trusted release boundary

The already-authenticated PAPER evidence runtime status contains:

```text
release_source_sha
process_started_at_unix_ms
generated_at_unix_ms
completed_cycle_count
cycle_as_of_unix_ms
evidence_cycle_interval_ms
mint_state_max_age_ms
mint_state_refresh_age_ms
...
```

The control already verifies that:

- the status file is private, regular, canonical, and stable while read;
- `release_source_sha` matches the exact active release;
- at least one cycle completed;
- process/cycle/generated timestamps are internally valid and fresh;
- provider failures are zero;
- Helius budget is internally consistent and unexhausted;
- B1 max age and proactive refresh age match the campaign authority.

No new host state or provider request is required.

## Sealed verifier behavior

Keep the requested verifier window unchanged for operator intent and bounded
lookback.

The control first performs its existing analysis so it can validate the
manifest-derived B1/refresh authority against runtime status.

After the release-bound runtime status is validated:

```text
effective_window_start =
    max(request.window_start_unix_ms, runtime_status.process_started_at_unix_ms)
effective_window_end = request.window_end_unix_ms
```

If the effective start is later than the requested start, rerun the read-only
mint-state analyzer using the effective exact-release window and use that
result as the authoritative acceptance analysis.

The release-bound reanalysis must not publish a second provider action or mutate
state. It only re-reads persisted checkpoints/mint evidence.

The final analysis must still report the same:

- `max_critical_data_age_ms`;
- `mint_state_refresh_age_ms`;
- `evidence_cycle_interval_ms`

as the already-validated runtime authority. Any mismatch fails closed.

If the active evidence process started after the requested window ended, the
control must fail closed rather than use pre-process history.

## Why this does not weaken physical acceptance

This change does not shorten the configured operator lookback arbitrarily.

It removes observations that could not have been produced under the release
being verified.

The final sample remains:

- point-in-time;
- checkpoint-reconstructed;
- bounded by the original request end;
- bounded by the active release process start;
- subject to the same PASS / FAILED / HOLD semantics;
- subject to the same B1 900,000 ms ceiling;
- subject to the same proactive-refresh requirement.

A new release with insufficient post-start observations naturally returns
`HOLD_INSUFFICIENT_EVIDENCE`; it does not receive a synthetic PASS.

## RED proof

Before implementation:

1. a trusted request whose 60-second window crosses a runtime process start
   causes only one analysis call at the original pre-release start;
2. the final result is therefore not release-bound;
3. a reanalysis result whose B1/refresh authority conflicts with runtime status
   is not checked because no release-bound reanalysis exists.

## GREEN proof

After implementation:

- the initial analysis remains bounded/read-only;
- runtime status remains release-bound and fail-closed;
- the second analysis occurs only when process start is inside the requested
  window;
- its start equals the exact `process_started_at_unix_ms`;
- its end remains the requested end;
- the second result replaces the pre-release analysis result;
- final B1/refresh/interval authority matches runtime status;
- no filesystem/provider/trading mutation is introduced;
- Python, Rust, repository-safety, and ARM64 gates pass.

## Required physical follow-up

After immutable release and protected deployment, the normal 30-minute
verifier may run immediately.

Its effective mint sample is automatically bounded to the current evidence
process start. Expected outcomes:

- `PASS` if post-release observations are present, clean, and include at least
  one proactive transition;
- `HOLD_INSUFFICIENT_EVIDENCE` if the new release has not yet accumulated
  enough qualifying evidence;
- `FAILED` only for actual post-release missing/stale/invalid observations.

Do not weaken B1, PAPER selection, strategy, scoring, or risk thresholds to
force a PASS.

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
