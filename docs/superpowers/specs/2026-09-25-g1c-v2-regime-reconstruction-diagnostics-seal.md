# G1C V2 Regime Reconstruction Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `18588458b61bcbcb92a23732457e0c77044bf510`  
**PR:** #503  
**Merged-main CI:** `36132050310`

## Production evidence

The exact deployed reconstruction-diagnostics release
`285daecd353203d9e3326047c8244828c2cef9b9` returned:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

The failure is therefore inside aggregate regime reconstruction for a selected
historical PAPER component. Transport, exact-release binding, protected
checkpoint access, and the fail-closed control boundary were already proven.

## Sealed refinement

This slice refines only known stable regime-reader failure families into fixed
non-sensitive analyzer codes:

```text
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_WINDOW_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_MARKET_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_SAFETY_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED
```

The existing generic regime code remains the fallback for unrelated regime
messages.

The classifier recognizes:

- aggregate regime evidence outside the requested replay window;
- nested aggregate regime replay failures attributable to market/snapshot
  evidence;
- nested aggregate regime replay failures attributable to safety evidence;
- nested aggregate regime replay failures that do not match the known market or
  safety families.

Only fixed enum values cross the protected control boundary. Candidate IDs,
mints, paths, SQL, provider details, checkpoint content, and raw exception text
remain private.

## RED / GREEN evidence

RED head:
`030ddede1232d32b8eed269992315c588bcba4e3`

CI run `36131427065`:

- Python: failed exactly the five new regime-family assertions;
- 3,733 existing Python tests passed;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Final GREEN head:
`af5ade4faafd117c1c562419d690392d94680334`

CI run `36131750422`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`18588458b61bcbcb92a23732457e0c77044bf510`

Merged-main CI run `36132050310`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Required physical follow-up

After immutable release and deployment of this seal, rerun the exact-release
production verifier.

The next implementation slice must be driven by the returned sanitized regime
subfamily. Do not change replay, regime policy, safety policy, candidate
selection, or thresholds before that evidence exists.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
REGIME_POLICY=UNCHANGED
SAFETY_POLICY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
