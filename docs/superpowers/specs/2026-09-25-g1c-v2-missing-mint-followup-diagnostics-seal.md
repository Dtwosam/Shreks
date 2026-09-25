# G1C V2 Missing Mint Follow-up Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `cb02ccb088afe48a6e2987eaad95771dd442a984`  
**PR:** #512  
**Initial RED CI:** `36169764396`  
**Bounded-lookup RED CI:** `36170087616`  
**Feature-head GREEN CI:** `36170181385`  
**Merged-main CI:** `36170458120`

## Production evidence that required this slice

The exact sealed mint-acceptance FAILED-contract release was re-verified after
the normal 30-minute acceptance window had moved fully beyond deployment
startup.

That protected verifier returned:

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

This narrowed the outstanding physical gate materially:

- the selected stale count fell to zero;
- 12 qualifying proactive refresh transitions were observed;
- maximum selected mint-state age was 608,527 ms, below the unchanged
  900,000 ms B1 critical-data ceiling;
- the Helius process budget remained healthy;
- exactly one selected observation still had no point-in-time Helius mint row.

The existing protected result could not distinguish a first-hydration/order
race from a candidate that remained unhydrated through the bounded acceptance
window.

## Sealed diagnostic refinement

For a selected PAPER observation with no Helius mint-state row at or before its
decision timestamp, the read-only analyzer may now inspect only the first exact
Helius mint-state row:

- strictly after the PAPER decision timestamp; and
- no later than the already-authorized acceptance window end.

That future row is diagnostic evidence only. It never satisfies historical B1,
changes the reconstructed decision, or becomes point-in-time input.

The analyzer adds three aggregate fields:

```text
selected_missing_mint_later_observed_count
selected_missing_mint_unresolved_count
max_selected_missing_mint_followup_delay_ms
```

The first two counters partition `selected_missing_mint_count`.

The protected verifier validates that partition and emits only:

```text
g1c_v2_mint_state_missing_later_observed=<count>
g1c_v2_mint_state_missing_unresolved=<count>
g1c_v2_mint_state_max_missing_followup_delay_ms=<milliseconds-or-none>
```

No candidate ID, mint address, individual timestamp, SQL, raw database value,
provider payload, checkpoint payload, manifest content, filesystem path, or raw
exception detail is exposed.

## Acceptance semantics remain unchanged

A selected observation that lacked mint state at its historical PAPER decision
still contributes to `selected_missing_mint_count` and still makes the
physical acceptance result `FAILED`.

A later row only tells us which implementation slice is justified next.

## RED / GREEN evidence

RED head:

`cec5a340a2f2bba9dd3a22a621b36098bf5f2999`

RED CI `36169764396`:

- Python: expected FAIL;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

The Python failures were exactly the missing behavior:

1. `MintStateAcceptanceSample` could not represent a bounded later Helius row;
2. the evaluator did not expose later-observed/unresolved aggregate counters;
3. the protected verifier did not validate or print those counters.

The RED run otherwise passed 3,756 Python tests.

Bounded-lookup RED head:

`f0de95ffb2d2612e75544d906c60e234b38386cb`

Bounded-lookup RED CI `36170087616`:

- Python: expected FAIL;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

That RED added the exact missing boundary proof: `_mint_state_times` did not yet
accept a bounded `followup_through_unix_ms`, so post-decision evidence could not
be explicitly constrained to the authorized acceptance window. The run failed
on that new lookup contract plus the still-unimplemented aggregate diagnostics,
while the other canonical gates remained green.

Final feature head:

`deff1b1ca8f05272594edd66a7239850a5a2fdb8`

Feature-head CI `36170181385`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`cb02ccb088afe48a6e2987eaad95771dd442a984`

Merged-main CI `36170458120`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
production verifier.

Interpret the bounded result as follows:

1. `missing_selected=0` with clean freshness and at least one proactive
   transition may close the mint-state physical-acceptance gate under the
   existing PASS contract.
2. `missing_selected>0`,
   `missing_later_observed>0`, and matching bounded follow-up delay proves a
   first-hydration/order race. The next slice must address only that ordering
   boundary.
3. `missing_selected>0` and `missing_unresolved>0` proves the candidate
   remained without exact Helius mint state through the bounded window. The next
   slice must diagnose collection coverage/selection/provider behavior only.
4. Any stale/invalid/provider-budget failure remains its existing fail-closed
   condition.

Do not relax B1, strategy, selector, score, risk, or PAPER thresholds to force a
PASS.

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
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
