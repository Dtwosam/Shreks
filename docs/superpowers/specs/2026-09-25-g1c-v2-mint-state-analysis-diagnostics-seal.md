# G1C V2 PAPER Mint-State Analysis Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `d71d91c3a52faffab410468700f58e1bfe607b05`  
**PR:** #493  
**Merged-main CI:** `36113427140`

## Production failure being diagnosed

The exact sealed PAPER evidence runtime-status release
`3b47b1709d27fe08ce01200d9d67a3e8ec5707f3` was built and installed
successfully on the production PAPER host.

Production deploy verification proved:

- exact release identity matched;
- the protected manifest manager reported `MATCHED_CURRENT_RELEASE`;
- observer, PAPER evidence, and PAPER campaign services were active;
- recent generic runtime failure signatures were absent;
- the protected mint-state acceptance bridge was available.

The verifier then reached protected historical acceptance and failed closed as:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

The generic failure is intentionally secret-safe, but it does not identify
which trusted analyzer stage failed. Changing freshness, selection, thresholds,
or strategy behavior from that signal would be guesswork.

## Sealed diagnostic change

The read-only mint-state analyzer now classifies failures with fixed internal
stage codes:

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

The telemetry control exposes only allow-listed values as:

```text
ANALYSIS_<STAGE_CODE>
```

The public failure message remains exactly:

```text
mint-state acceptance analysis failed closed
```

Unexpected exceptions and input-validation failures remain the generic
`ANALYSIS_FAILED`.

No arbitrary exception text, database path, manifest path, SQL text, candidate
ID, mint, checkpoint payload, provider response, credential, or wallet data is
returned.

## Behavior preserved

This slice does not change:

- historical replay semantics;
- checkpoint decoding semantics;
- candidate selection or ordering;
- point-in-time mint-state lookup rules;
- B1 critical-data age;
- proactive mint-state refresh age;
- provider behavior or budgets;
- protected manifest bytes;
- PAPER execution;
- scoring/model logic;
- promotion or LIVE authority.

It only makes already-failing read-only analysis identify its fixed internal
stage without leaking sensitive details.

## RED / GREEN evidence

RED head:
`aa2a16b5a245ef5ca7cbd387889c6838179ae146`

CI run `36080096194`:

- Python tests: FAIL as intended because
  `MintStateAcceptanceError` had no stage code and the control returned only
  generic `ANALYSIS_FAILED`;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Final GREEN head:
`ee95d516124dc3eb7c424abe5b08309800742902`

CI run `36112991940`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`d71d91c3a52faffab410468700f58e1bfe607b05`

Merged-main CI run `36113427140`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Physical diagnostic acceptance

After immutable release/deployment of this seal:

1. deployed release SHA must equal this seal commit;
2. protected PAPER services must remain healthy and release-local;
3. the mint-state acceptance bridge must run under the existing read-only
   telemetry authority;
4. if historical analysis still fails, the verifier must return one fixed
   `ANALYSIS_<STAGE_CODE>` value;
5. no permission widening is allowed to obtain the stage;
6. the returned stage becomes the only evidence-supported next implementation
   slice.

If the analyzer instead reaches ordinary `PASS`,
`HOLD_INSUFFICIENT_EVIDENCE`, or evidence-level `FAILED` counts, that
result supersedes the prior generic analyzer failure and must be evaluated
without inventing another diagnostic code change.

## Explicit non-authority

```text
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
HISTORICAL_REPLAY=UNCHANGED
DATABASE_SCHEMA=UNCHANGED
DATABASE_PERMISSION_WIDENING=FORBIDDEN
JOURNAL_PERMISSION_WIDENING=FORBIDDEN
SUDO_AUTHORITY_WIDENING=FORBIDDEN
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No scoring, model fitting, threshold relaxation, promotion, signing, wallet,
transaction submission, or LIVE authority is granted by this seal.
