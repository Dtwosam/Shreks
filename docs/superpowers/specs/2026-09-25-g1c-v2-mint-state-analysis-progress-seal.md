# G1C V2 PAPER Mint-State Analysis Progress Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `5cf7c24bdf68e18b18e2c27b6ea1d77dfc13056e`  
**PR:** #497  
**Merged-main CI:** `36121266358`

## Purpose

The physical mint-state acceptance verifier had reached a terminal timeout on
the exact deployed `28bb36d...` release while:

- the request marker remained present;
- the result exchange existed;
- no `result.json` existed;
- `shreks-telemetry.timer` remained active/running; and
- `shreks-telemetry.service` remained in `activating / start-pre` with no main
  process start timestamp.

Because telemetry processes mint-state acceptance controls during its
`--preflight` execution, the failure was narrowed to protected control
processing but not to a specific analyzer stage.

This seal adds bounded, read-only progress evidence only. It does not alter the
acceptance calculation, replay semantics, thresholds, timer cadence, verifier
timeout, final-result semantics, or trading authority.

## Sealed progress contract

The protected telemetry control may publish:

```text
/dev/shm/shreks-g1c-v2-mint-state-acceptance.<request_id>.result.d/
  progress.json
  result.json
```

`progress.json` is diagnostic-only canonical JSON containing exactly:

- schema name/version;
- trusted request ID;
- exact expected release SHA;
- one allow-listed progress stage;
- generation timestamp.

Allow-listed stages are:

```text
REQUEST_ACCEPTED
RUNTIME_AUTHORITY_RESOLVED
MANIFEST_VALIDATION
DATABASE_OPEN
CHECKPOINT_WINDOW_READ
CHECKPOINT_DECODE
CYCLE_RECONSTRUCTION
MINT_STATE_READ
ANALYSIS_COMPLETE
RUNTIME_STATUS_VALIDATION
RESULT_READY
```

It does not contain candidate IDs, token mints, database paths, SQL, checkpoint
payloads, provider responses, wallet data, credentials, secrets, or exception
text.

## Trust boundary

Progress transport reuses the existing mint-acceptance result exchange.

The progress receipt is:

- written only by the `shreks` telemetry identity;
- release-bound to the exact accepted request;
- canonical JSON;
- bounded in size;
- published mode 0644;
- atomically replaced as progress advances;
- validated by the deploy verifier for file type, ownership, mode, size,
  canonical form, schema/version, request ID, release SHA, stage enum, and
  timestamp before any field is printed.

Progress publication is best-effort diagnostic evidence. Failure to publish a
progress receipt does not change acceptance calculations and does not create a
PASS/HOLD/FAILED result.

`result.json` remains the only acceptance result and keeps its existing
write-once/fail-closed semantics.

## Analyzer instrumentation

`analyze_mint_state_acceptance` now accepts an optional progress callback.

The callback is invoked only around existing analyzer stages:

- manifest validation;
- read-only database open;
- bounded checkpoint-window read;
- checkpoint decode;
- historical candidate reconstruction;
- point-in-time Helius mint-state read;
- analysis completion.

No analyzer query, point-in-time rule, checkpoint authentication rule, safety
threshold, or status computation changed.

## Verifier behavior

The existing 180-second acceptance deadline is unchanged.

On terminal timeout, the verifier may read and validate `progress.json` and
print only:

```text
g1c_v2_mint_state_acceptance_progress_stage=<ALLOW_LISTED_STAGE>
g1c_v2_mint_state_acceptance_progress_generated_at_unix_ms=<INTEGER>
```

Missing or invalid progress remains diagnostic-only and does not change the
terminal timeout outcome.

## RED / GREEN evidence

RED head:
`0638593f590a5210df9e6f443a436cd4ad32c817`

CI run `36120159109` failed as intended because the progress contract had not
yet been implemented.

Final GREEN head:
`e94ea677cddc1b1e53d4b49a4309ac14e590d88f`

CI run `36120985476` passed.

Merged integration SHA:
`5cf7c24bdf68e18b18e2c27b6ea1d77dfc13056e`

Merged-main CI run `36121266358` passed.

The merged implementation diff is confined to:

- production verification workflow;
- progress design documentation;
- mint-state acceptance analyzer/control progress plumbing;
- progress and integration tests.

## Required physical follow-up

After immutable release and deployment of this seal, rerun the exact-release
production verifier.

If the acceptance result still times out, use only the sanitized progress stage
to identify the next implementation slice.

Do not increase the timeout or alter replay/strategy/safety behavior merely to
make the verifier complete.

If a final result is produced:

- `PASS` requires the already-sealed physical acceptance conditions;
- `HOLD_INSUFFICIENT_EVIDENCE` remains non-promotional;
- `FAILED` remains fail-closed and should drive the next evidence-backed slice.

## Explicit non-authority

```text
VERIFIER_TIMEOUT_SECONDS=180_UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
HISTORICAL_REPLAY=UNCHANGED
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No scoring, model fitting, threshold relaxation, manifest rotation, PAPER
promotion, signing, wallet, transaction submission, or LIVE authority is
granted by this seal.
