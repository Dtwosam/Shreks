# Fast PAPER Shadow Coordinated Supervisor — Design

**Date:** 2026-09-26  
**Base main SHA:** `b66691c30c7d22790b2216895cb9a4e51e8996f3`

## Purpose

Add the long-running supervised entrypoint that continuously composes the
already-sealed learned decision service, isolated execution bootstrap,
decision/execution coordinator, OPEN reduction source, and pending-BUY retry
source.

The existing `shadow_service.py` remains the narrow decision-only service
boundary. The new supervisor owns only orchestration.

## Configuration

Add `FastPaperShadowSupervisorConfig` containing:

- exact `FastPaperShadowServiceConfig`;
- exact `FastPaperShadowServiceExecutionConfig`;
- reduction source directory;
- pending-BUY retry source directory.

Load the existing decision and execution settings unchanged, plus:

- `SHREKS_FAST_PAPER_SHADOW_REDUCTION_SOURCE_DIRECTORY`;
- `SHREKS_FAST_PAPER_SHADOW_PENDING_BUY_RETRY_SOURCE_DIRECTORY`.

Both source directories must be absolute, existing regular non-symlink
directories at bootstrap. The supervisor must require the decision-evidence,
execution-source, reduction-source, and retry-source roots to be distinct and
non-overlapping.

## Preflight

`python -m shreks_brain.fast_paper_runtime.shadow_supervisor --preflight`

must:

1. load both existing config contracts;
2. authenticate the decision service manifest/policy/state;
3. authenticate the isolated execution policy/ledger/checkpoint/runtime state;
4. validate the two additional source directories and source-root separation;
5. emit one READY status document;
6. perform no feature fetch, decision inference, source consumption, retry,
   execution, or persistence.

## Runtime loop

Each loop iteration must:

1. obtain one non-negative wall-clock millisecond value;
2. call `run_fast_paper_shadow_service_coordinated_cycle(...)` with:
   - the current decision bootstrap;
   - exact decision and execution configs;
   - reduction source directory;
   - pending-BUY retry source directory;
   - that clock as commit time;
3. replace only the in-memory decision bootstrap with the returned bootstrap;
4. retain the returned authenticated execution bootstrap for status;
5. accumulate produced-decision and committed-execution counts;
6. emit one RUNNING status document;
7. sleep using the existing decision service cadence;
8. stop cleanly on SIGINT/SIGTERM.

The coordinator remains authoritative for cursor ordering, execution catch-up,
pending-BUY precedence, source authentication, and one-transition bounds.

## systemd boundary

Switch `shreks-fast-paper-shadow.service` to the new supervisor module for
both preflight and ExecStart.

Keep:

- dedicated `/etc/shreks/fast-paper-shadow.env`;
- `PrivateNetwork=true`;
- `ReadWritePaths=/var/lib/shreks/fast-paper-shadow`;
- no legacy PAPER campaign dependency;
- no `PartOf=shreks.target` or `WantedBy=shreks.target`;
- no membership in `shreks.target`.

Package an example env file documenting the complete coordinated settings.
This remains shadow/PAPER packaging only and is not production PAPER cutover.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
SUPERVISOR_AUTHORITY=ORCHESTRATION_ONLY
DECISION_EXECUTION_COORDINATOR=REQUIRED
SOURCE_AUTHORITY=PREPUBLISHED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- new supervisor module/config/bootstrap/run/main API;
- exact reuse of existing config/bootstrap/coordinator APIs;
- preflight with no coordinator side effects;
- one coordinated call per loop iteration;
- source-directory wiring;
- status counts for decisions and isolated executions;
- systemd ExecStart/ExecStartPre switched to supervisor;
- complete env example;
- no scoring, direct executor, source producer/writer, provider/network,
  signing/submission, authoritative PAPER, or LIVE authority.
