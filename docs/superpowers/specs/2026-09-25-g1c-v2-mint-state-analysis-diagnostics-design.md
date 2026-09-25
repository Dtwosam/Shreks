# G1C V2 Mint-State Acceptance Stage Diagnostics Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-state-analysis-diagnostics`  
**Base / deployed release:** `3b47b1709d27fe08ce01200d9d67a3e8ec5707f3`

## Production evidence

The exact sealed runtime-status release installed successfully and the protected
mint-state acceptance bridge became available. The host verifier then reached
historical analysis and failed closed as:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

This proves the journal/runtime-status observation defect is no longer the
blocking stage. The remaining failure is inside the protected read-only
historical analyzer.

The generic code is intentionally secret-safe but is too coarse to distinguish
a checkpoint-integrity failure from a point-in-time replay or mint-row query
failure. Changing strategy or freshness behavior without that distinction would
be guesswork.

## Goal

Add bounded, enumerated analyzer stage codes only.

Do not expose:

- database or manifest paths;
- candidate IDs or mints;
- checkpoint payloads;
- SQL text;
- provider responses;
- arbitrary exception strings.

Do not change acceptance calculations, candidate selection, replay semantics,
B1 thresholds, provider behavior, database permissions, or any trading
authority.

## Error contract

`MintStateAcceptanceError` carries one fixed code chosen by code, not by
external input. Production-relevant codes are:

```text
MANIFEST_VALIDATION_FAILED
DATABASE_OPEN_FAILED
CHECKPOINT_WINDOW_READ_FAILED
CHECKPOINT_WINDOW_TOO_LARGE
CHECKPOINT_DECODE_FAILED
CHECKPOINT_SEQUENCE_INVALID
CHECKPOINT_TIME_INVALID
CYCLE_RECONSTRUCTION_FAILED
CANDIDATE_ATTRIBUTION_INVALID
MINT_STATE_READ_FAILED
MINT_STATE_VALUE_INVALID
```

Input-validation codes may remain internal and are not expected from a trusted
production control request.

The telemetry control maps a classified analyzer failure to:

```text
status=FAILED
error.code=ANALYSIS_<STAGE_CODE>
error.message=mint-state acceptance analysis failed closed
```

Unexpected analyzer exceptions continue to use the existing generic
`ANALYSIS_FAILED` code.

## Safety

The code is diagnostic evidence only. It must preserve:

```text
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
DATABASE_SCHEMA=UNCHANGED
DATABASE_PERMISSION_WIDENING=FORBIDDEN
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

## TDD

RED tests require:

1. a replay-assembly exception maps to
   `ANALYSIS_CYCLE_RECONSTRUCTION_FAILED`;
2. a SQLite mint-state lookup exception maps to
   `ANALYSIS_MINT_STATE_READ_FAILED`;
3. the control result never includes the original exception text;
4. existing PASS/HOLD/FAILED acceptance behavior remains byte-for-byte
   semantically unchanged.
