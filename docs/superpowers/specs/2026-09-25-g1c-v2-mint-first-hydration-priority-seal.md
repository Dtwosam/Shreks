# G1C V2 Mint First-Hydration Priority Seal

**Date:** 2026-09-25  
**Integration SHA:** `c75217244a2d5adb41d5cee2dcfb15d8ba6990d6`  
**PR:** #514  
**RED CI:** `36172947144`  
**Feature-head GREEN CI:** `36173147857`  
**Merged-main CI:** `36173455818`

## Production evidence

The exact missing-mint follow-up diagnostics release
`31253a81f0ffef70f48aac0fb8ed9e29f67a78e1` deployed successfully.

Its protected physical verifier returned:

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
g1c_v2_paper_evidence_completed_cycles=3
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=3
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=497
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=FAILED
```

All four point-in-time mint misses received exact Helius mint-state evidence
later inside the bounded acceptance window. No miss remained unresolved.
The maximum observed first-hydration delay was 98,923 ms.

This rules out persistent provider coverage failure, Helius budget exhaustion,
and B1 pre-expiry freshness regression for the sampled window.

## Proven ordering gap

The separately supervised PAPER evidence selector already allowed too-young
fresh-pair prewarming, but its ordering was:

1. PAPER entry-window candidates;
2. too-young prewarm candidates;
3. apply the bounded evidence candidate limit.

With the active bounded candidate budget, a fresh exact-quote candidate could
therefore lose every evidence slot while too young, cross into PAPER
eligibility without a Helius mint row, be evaluated fail-closed by PAPER, then
receive first mint-state hydration on a later evidence cycle.

## Sealed repair

Inside the existing exact-quote fresh-launch evidence population, candidates
with no Helius mint-state row at or before the evidence-cycle timestamp now
receive first-hydration priority before candidates that already have mint-state
evidence.

After that one-bit first-hydration priority, the existing ordering remains:

1. entry-window age class before too-young prewarm;
2. newest canonical market observation;
3. candidate ID tie-break.

Once a candidate has any exact Helius mint-state row, it loses the temporary
first-hydration priority and returns to the normal evidence ordering.

The total candidate cap is unchanged. The evidence cadence is unchanged.
No extra provider request class or second selector is introduced.

## RED / GREEN evidence

RED head:

`b601a5eacf5d47e8155910c0ca4ba277255e41b6`

RED CI `36172947144`:

- Rust: expected FAIL;
- repository safety: PASS;
- Python: unaffected;
- ARM64 release build: unaffected.

The intended regression
`fresh_launch_candidates_prioritize_missing_mint_first_hydration_before_limit`
proved the old selector chose already-hydrated mature candidate ID 1 while the
missing-mint prewarm candidate was ID 3.

GREEN head:

`5b45813150ae0e7bf116cc70081b00459eab52fb`

Feature-head CI `36173147857`:

- Rust: PASS;
- Python: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`c75217244a2d5adb41d5cee2dcfb15d8ba6990d6`

Merged-main CI `36173455818`:

- Rust: PASS;
- Python: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This changes PAPER evidence collection ordering only.

It does **not** change:

- PAPER candidate selection or ordering;
- evidence candidate cap;
- evidence cycle interval;
- pair-age thresholds;
- B1 max critical-data age;
- proactive refresh age;
- holder refresh semantics;
- Jupiter quote semantics;
- strategy/setup/regime/scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution/accounting;
- protected campaign-manifest bytes;
- model/champion authority;
- PAPER promotion;
- LIVE authority.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
mint-state physical verifier.

The target evidence is:

- `selected_missing_mint_count = 0`;
- `selected_missing_mint_later_observed_count = 0`;
- `selected_missing_mint_unresolved_count = 0`;
- `selected_stale_mint_count = 0`;
- `invalid_observation_count = 0`;
- at least one proactive pre-expiry refresh transition;
- provider failures remain zero or fail closed;
- Helius budget remains unexhausted.

If the bounded window still contains point-in-time misses, use only the new
physical counters to justify the next slice. Do not change PAPER candidate
semantics, B1, or strategy/risk thresholds to force acceptance.

## Explicit non-authority

```text
PAPER_EVIDENCE_FIRST_HYDRATION_PRIORITY=SEALED
PAPER_EVIDENCE_MAX_CANDIDATES=UNCHANGED
PAPER_EVIDENCE_INTERVAL=UNCHANGED
PAPER_CANDIDATE_SELECTION=UNCHANGED
PAPER_MIN_PAIR_AGE=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_UNCHANGED
HOLDER_REFRESH_SEMANTICS=UNCHANGED
QUOTE_SEMANTICS=UNCHANGED
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
