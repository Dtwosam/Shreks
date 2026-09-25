# G1C V2 Mint-Acceptance Timeout Diagnostics Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-acceptance-timeout-diagnostics`  
**Base / deployed release:** `5620c21a7082ef79ed7e450e971ef1427c3cf00c`

## Physical failure

The exact diagnostic release installed successfully, but the protected
mint-state acceptance request produced no result inside the verifier's existing
180 second deadline:

```text
g1c_v2_mint_state_acceptance_bridge=available
g1c_v2_mint_state_acceptance_status=TIMEOUT
```

The prior sealed release reached the analyzer and returned a fail-closed result,
so the `/dev/shm` control bridge is known to work in principle. The new timeout
does not prove whether:

- the telemetry timer failed to trigger;
- the telemetry oneshot was already active;
- telemetry preflight/control processing failed;
- protected historical analysis was still running;
- the marker was not visible to the telemetry process; or
- the result exchange was never populated.

Changing replay, thresholds, selector behavior, or provider behavior without
distinguishing those states would be guesswork.

## Goal

Add bounded timeout diagnostics to the existing production verifier only.

On mint-acceptance timeout, report:

- telemetry timer `ActiveState`, `SubState`, `LastTriggerUSec`, and
  `NextElapseUSecRealtime`;
- telemetry service `ActiveState`, `SubState`, `Result`,
  `ExecMainCode`, `ExecMainStatus`, start timestamp, and exit timestamp;
- `/dev/shm` lstat/resolved target metadata;
- whether the exact acceptance request marker is still present, plus only its
  path/mode/owner/size/mtime metadata;
- whether the exact result exchange directory exists, plus only its
  path/mode/owner metadata;
- whether the exact result file exists, plus only its
  path/mode/owner/size/mtime metadata;
- best-effort recent telemetry service journal output, subject to the existing
  deploy-user visibility boundary.

No protected database, manifest, runtime-status sidecar, checkpoint payload,
provider response, candidate mint, or secret is read or printed by the deploy
identity.

## Safety

This is verifier diagnostics only.

```text
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
HISTORICAL_ANALYZER=UNCHANGED
TELEMETRY_TIMER=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

The timeout remains terminal. Diagnostics do not convert TIMEOUT to HOLD or
PASS and do not increase the deadline.

## TDD

RED requires the production verifier's mint timeout branch to contain the same
bounded service/timer/marker/result metadata diagnostics already used for FL9
discovery timeouts.

GREEN adds only that diagnostic block and keeps all existing acceptance
semantics unchanged.
