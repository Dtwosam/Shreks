# G1C V2 Mint-State Acceptance Progress Diagnostics Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-analysis-progress`  
**Base / deployed release:** `28bb36ded2ce293daeff90318666e8e66be3204f`

## Production evidence

The exact timeout-diagnostics release installed successfully. At the terminal
mint-acceptance timeout, the verifier observed:

```text
shreks-telemetry.timer:
  ActiveState=active
  SubState=running
  LastTriggerUSec=Fri 2026-09-25 09:28:48 UTC

shreks-telemetry.service:
  ActiveState=activating
  SubState=start-pre
  ExecMainStartTimestamp=
  ExecMainStatus=0

mint_acceptance_marker_present=yes
mint_acceptance_result_exchange=present
mint_acceptance_result_file=absent
```

The request marker was valid and still present. The exchange existed with the
expected deploy ownership/mode. No result had been published. The telemetry
oneshot was still in its `ExecStartPre` command, which runs
`python -m shreks_brain.telemetry.runtime --preflight`.

The telemetry runtime processes mint-state acceptance controls before ordinary
telemetry preflight, so this evidence narrows the timeout to protected control
processing, but it does not identify the exact long-running analyzer stage.

Increasing the verifier timeout or changing replay behavior without that stage
evidence would be guesswork.

## Goal

Expose a tiny, non-authoritative progress receipt in the already-established
mint-acceptance result exchange while protected analysis is running.

The progress receipt is diagnostic only. The final `result.json` remains the
only acceptance result.

## Progress schema

Exact canonical JSON:

```text
schema_name = shreks.g1c_v2_mint_state_acceptance_progress
schema_version = 1
request_id = exact trusted request id
expected_release_sha = exact active sealed release
stage = one allow-listed enum
generated_at_unix_ms = non-negative integer
```

Allow-listed stages:

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

No candidate ID, mint, path, SQL, checkpoint content, provider response, wallet
data, secret, or exception text is included.

## Transport

Reuse the existing result exchange:

```text
/dev/shm/shreks-g1c-v2-mint-state-acceptance.<request_id>.result.d/
  progress.json
  result.json
```

The exchange remains deploy-owned mode 0733.

`progress.json` is:

- written only by the `shreks` telemetry process;
- canonical JSON;
- mode 0644;
- bounded to 4096 bytes;
- atomically replaced as the stage advances;
- authenticated by exact request ID and exact release SHA.

Progress publication is best-effort diagnostic evidence. A progress-write
failure must not alter acceptance calculations or convert a valid final result
into PASS/HOLD/FAILED. Final-result publication remains independently
fail-closed.

## Analyzer integration

`analyze_mint_state_acceptance` accepts an optional stage callback.

The callback is invoked immediately before each potentially material read or
replay stage. Repeated checkpoint/candidate work may repeat a stage; the
progress receipt stores only the latest stage.

The analyzer result, error codes, thresholds, point-in-time semantics, and
read-only database behavior remain unchanged.

## Verifier behavior

The existing 180-second timeout remains terminal.

On timeout, the verifier additionally reads `progress.json` if present and
prints only:

```text
g1c_v2_mint_state_acceptance_progress_stage=<ENUM>
g1c_v2_mint_state_acceptance_progress_generated_at_unix_ms=<INTEGER>
```

The verifier validates regular-file type, `shreks` ownership, mode 0644,
bounded size, canonical JSON, schema/version, request ID, release SHA, enum
stage, and timestamp before printing those two fields.

Missing or invalid progress remains diagnostic only and does not change the
terminal TIMEOUT outcome.

## Safety

```text
VERIFIER_TIMEOUT_SECONDS=180_UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
HISTORICAL_REPLAY=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

## TDD

RED must require:

1. the analyzer emits allow-listed stage callbacks around historical work;
2. the progress publisher writes canonical, bounded, release-bound
   `progress.json` and safely replaces it as stages advance;
3. an unsupported stage is rejected;
4. production timeout diagnostics validate and print only the sanitized progress
   stage/timestamp;
5. final result semantics and write-once behavior remain unchanged.
