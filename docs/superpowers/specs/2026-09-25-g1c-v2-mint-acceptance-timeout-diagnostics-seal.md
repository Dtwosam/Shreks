# G1C V2 Mint-Acceptance Timeout Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `e84cd1669bd8398a689af401fd186bdf0f17952b`  
**PR:** #495  
**Merged-main CI:** `36116805429`

## Production trigger

The prior exact sealed release
`5620c21a7082ef79ed7e450e971ef1427c3cf00c` installed successfully, but the
protected mint-state acceptance request did not return a result inside the
existing 180 second verifier deadline:

```text
g1c_v2_mint_state_acceptance_bridge=available
g1c_v2_mint_state_acceptance_status=TIMEOUT
```

That run did not expose enough bounded service-state evidence to distinguish a
busy/failed telemetry oneshot from an unobserved marker or missing result
publication.

## Sealed change

The production verifier now emits bounded diagnostics only when the
mint-acceptance result remains absent at the unchanged deadline:

- telemetry timer ActiveState/SubState and last/next trigger timestamps;
- telemetry service ActiveState/SubState/Result, main status/code, and
  start/exit timestamps;
- /dev/shm directory metadata;
- exact request-marker presence and metadata;
- exact result-exchange presence and metadata;
- exact result-file presence and metadata;
- best-effort recent telemetry service journal output through the existing
  deploy-user visibility boundary.

The timeout remains terminal.

The diagnostic path does not read:

- the protected operational SQLite database;
- the protected PAPER campaign manifest;
- the private PAPER evidence runtime-status sidecar;
- checkpoint payloads;
- provider payloads;
- candidate identities;
- credentials or wallet material.

No new sudo, ACL, group, database, journal, or filesystem authority is granted.

## RED / GREEN evidence

RED head:
`bb53e59ce0de5809321dd6e73812a5fba88b25e0`

CI `36116228739`:

- Python: FAIL exactly on the missing timeout-diagnostics contract;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

GREEN head:
`5add84cd35d1a7f783e27ccb4fa88e42f06c3c7b`

CI `36116525493`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`e84cd1669bd8398a689af401fd186bdf0f17952b`

Merged-main CI `36116805429`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Required physical evidence

After deployment of this seal, a mint-acceptance timeout must identify enough
bounded state to distinguish at least:

1. telemetry timer is not active / not triggering;
2. telemetry service is active and still running;
3. telemetry service completed or failed without publishing a result;
4. request marker remains present;
5. request marker was consumed/removed unexpectedly;
6. result exchange exists but result file is absent;
7. result file exists but the verifier could not consume it.

That evidence determines the next implementation slice. Do not change the
historical analyzer, acceptance thresholds, or trading behavior merely to avoid
a timeout.

## Explicit non-authority

```text
MINT_ACCEPTANCE_TIMEOUT_SECONDS=180_UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_UNCHANGED
HISTORICAL_ANALYZER=UNCHANGED
TELEMETRY_TIMER=UNCHANGED
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
