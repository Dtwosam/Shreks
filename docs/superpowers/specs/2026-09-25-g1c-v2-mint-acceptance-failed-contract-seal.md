# G1C V2 Mint-State Acceptance FAILED Contract Seal

**Date:** 2026-09-25  
**Integration SHA:** `b3436050f62f18efcd776174d4e6019b1ca6f549`  
**PR:** #511  
**RED CI:** `36161171139`  
**Feature-head GREEN CI:** `36161509654`  
**Merged-main CI:** `36161864564`

## Production evidence

The exact sealed selection-only mint acceptance release
`a583e3617af266fb6e09d6d8b33dc1a80826a443` deployed successfully.

The prior full-cycle reconstruction timeout was eliminated: the protected
mint-state acceptance control returned quickly. The verifier then failed with:

```text
mint acceptance failure shape is invalid
```

Inspection showed a verifier-contract mismatch.

The control surface has two legitimate top-level `status="FAILED"` shapes:

1. operational/control failure:
   `error={code,message}`;
2. completed behavioral mint-state acceptance failure:
   `analysis` plus validated `runtime_status`.

The production verifier incorrectly assumed every `FAILED` was case (1), so
it rejected behavioral physical-acceptance evidence before printing the bounded
analysis counters.

## Sealed refinement

The embedded verifier validator now uses the internal-only sentinel:

```text
CONTROL_FAILED
```

for operational error-object failures.

Operational failures remain sanitized and terminal. The external log still
reports:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=<bounded code>
g1c_v2_mint_state_acceptance_failure_message=<sanitized message>
```

A completed behavioral `FAILED` analysis is now validated through the same
analysis/runtime-status contract as PASS/HOLD. The verifier prints only the
existing bounded counters and then reports:

```text
g1c_v2_mint_state_physical_acceptance=FAILED
```

before exiting terminally.

No candidate IDs, mints, raw database values, SQL, filesystem paths, provider
payloads, or exception details are exposed.

## RED / GREEN evidence

RED head:

`b122a546bb01bdb89cf8d6d0110a60b4234a55b0`

RED CI `36161171139`:

- Python: expected FAIL, exactly the new failure-contract workflow assertion;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

GREEN head:

`3955d4ff571d284e236033a4331c7d745538cc1e`

Feature-head CI `36161509654`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`b3436050f62f18efcd776174d4e6019b1ca6f549`

Merged-main CI `36161864564`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This release changes verifier interpretation only.

It does **not** change:

- mint-state acceptance analysis calculations;
- candidate selection;
- historical point-in-time replay;
- Helius collection/refresh behavior;
- safety policy or thresholds;
- setup/regime/scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution/accounting;
- active protected campaign-manifest bytes;
- champion/model authority;
- PAPER promotion;
- LIVE authority.

The deterministic commissioning campaign remains baseline/commissioning logic
and is not the target learned market-intelligence authority.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
production verifier.

For a behavioral `FAILED` result, the bounded counters now become the only
justified next evidence:

- selected observations;
- proactive refresh count;
- selected missing mint count;
- selected stale mint count;
- invalid observation count;
- reconstructed checkpoint count;
- maximum selected mint age;
- runtime provider failures;
- Helius request budget state.

If the result is PASS, close the mint-state pre-expiry physical acceptance
gate. If it is HOLD, retain the gate without changing strategy. If it is
behavioral FAILED, diagnose only the failed acceptance condition; do not weaken
B1 or strategy thresholds.

## Explicit non-authority

```text
MINT_ACCEPTANCE_ANALYSIS=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_REPLAY=UNCHANGED
SAFETY_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
