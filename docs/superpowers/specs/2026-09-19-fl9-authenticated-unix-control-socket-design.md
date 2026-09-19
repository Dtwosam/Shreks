# FL9 Authenticated Unix Control Socket — Design

**Date:** 2026-09-19  
**Base:** sealed main `531253d1e5af2cdb391c140a76415b4efef6cf15`  
**Status:** approved by ongoing anti-stall directive for implementation

## Problem

The automatic sealed release and PAPER deploy chain is working, but the FL9 protected discovery verifier has timed out repeatedly despite:

- exact release activation succeeding;
- all PAPER services remaining healthy;
- the telemetry timer firing during the request window;
- the telemetry oneshot exiting successfully;
- both preflight and normal telemetry runtime containing discovery-control processing.

The current control path depends on two indirect channels: a request marker under `/dev/shm` and a response recovered from journald. Production evidence does not establish which channel is failing, and repeated patches to those channels risk recreating the same operational dead end.

## Goal

Replace the critical request/response transport with one bounded, local, mutually authenticated Unix-domain socket exchange while retaining the existing marker/journal bridge as a backward-compatible fallback.

No administrator shell, sudoers change, systemd change, protected-state permission change, or persistent daemon is introduced.

## Transport

The telemetry runtime exposes an abstract AF_UNIX stream socket only while the existing telemetry oneshot is running.

Protocol address:

`\0shreks.fl9_v2_discovery_control.v1`

The socket is abstract (not filesystem-backed), so it is independent of `/dev/shm`, `/tmp`, `/var/tmp`, filesystem mount namespaces, file ownership, ACLs, and journal visibility.

Each telemetry invocation listens for at most 0.5 seconds. The production verifier retries connections every 0.1 seconds for at most 180 seconds, so one ordinary timer invocation is sufficient.

## Mutual kernel authentication

The server obtains Linux `SO_PEERCRED` from each accepted connection and accepts requests only when the peer UID exactly equals the host `shreks-deploy` UID.

The verifier client obtains `SO_PEERCRED` from the connected server and accepts responses only when the server UID exactly equals the host `shreks` UID.

No application secret or reusable credential is introduced. A different local user can at most cause denial of service by squatting the abstract socket; it cannot produce trusted evidence because the verifier rejects the wrong server UID.

## Request schema

The socket request reuses the existing canonical control request fields exactly:

- `schema_name = shreks.fl9_v2_discovery_control_request`;
- `schema_version = 1`;
- `request_id`;
- `expected_release_sha`;
- `created_at_unix_ms`.

The encoded request must be canonical UTF-8 JSON plus one newline and must not exceed 4096 bytes.

The server validates request ID, source SHA, timestamp age/skew, and exact release binding exactly as the marker path does.

## Shared processing and idempotence

Marker and socket requests must converge on one internal authenticated-request processor.

That processor retains:

- exact active release binding;
- existing receipt lookup/write-once semantics;
- bounded historical V2 request-authority enumeration;
- exact authority grouping;
- runtime-manifest discovery;
- fail-closed HOLD/FAILED behavior.

A request that was already processed through either transport returns the existing authenticated receipt.

## Response schema

The server returns the existing canonical `shreks.fl9_v2_discovery_control_result` document plus one newline on the same connected stream.

The response is sanitized evidence already intended for the production verifier. The client imposes a hard 1 MiB response bound.

The client requires:

- exact schema name/version;
- exact request ID;
- exact expected release SHA;
- exact observed release SHA;
- terminal status in:
  - `HOLD_NO_REQUEST_AUTHORITY`;
  - `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
  - `HOLD_NO_COMPATIBLE`;
  - `FOUND_COMPATIBLE`.

`FAILED`, malformed data, peer-credential mismatch, timeout, truncation, or release mismatch fails verification.

## Telemetry behavior

Both normal telemetry runtime and `--preflight` call one control-processing helper.

That helper:

1. services at most one authenticated socket request during the bounded accept window;
2. processes any legacy marker requests;
3. emits results to stdout for observational compatibility;
4. isolates any control-transport/control-processing exception from telemetry snapshot generation.

Normal telemetry authority remains observational only.

## Production verifier

For releases containing the socket client module, `Verify production PAPER runtime` uses the socket client as the primary discovery transport.

For older releases without the socket client module, the existing `/dev/shm` marker + journal polling path remains available as fallback.

The verifier does not start/restart telemetry and does not mutate protected state.

## Authority boundary

This design does not change:

- `deploy/release/release_manager.py`;
- sudoers;
- systemd units/timers;
- `/etc/shreks` or `/var/lib/shreks` ownership/modes/ACLs;
- wallet/signing/submission code;
- PAPER promotion authority;
- LIVE authority.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
