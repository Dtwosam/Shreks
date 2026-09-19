# FL9 Authenticated Unix Control Socket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragile FL9 marker/journal critical path with a mutually peer-authenticated abstract Unix-domain socket while retaining the old bridge as fallback.

**Architecture:** Extract one shared authenticated-request processor from the existing marker implementation. Add a bounded AF_UNIX stream server to telemetry runtime and a release-local client used by the production verifier. Both ends verify Linux `SO_PEERCRED`; request/result schemas and receipt idempotence remain unchanged.

**Tech Stack:** Python 3.12, Linux AF_UNIX/`SO_PEERCRED`, GitHub Actions YAML, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-fl9-authenticated-unix-control-socket-design.md`

## Global Constraints

- Abstract socket address is `\0shreks.fl9_v2_discovery_control.v1`.
- Server accept window is at most 0.5 seconds per telemetry invocation.
- Verifier retries at 0.1-second cadence for at most 180 seconds.
- Request bound is 4096 bytes; response bound is 1 MiB.
- Server accepts only peer UID `shreks-deploy`.
- Client accepts only server UID `shreks`.
- Marker/journal transport remains fallback for older releases.
- No release-manager, sudoers, systemd, protected-permission, signing, promotion, or LIVE changes.
- `V2_SCORING_RETRY=NOT_YET_AUTHORIZED`.
- `PAPER_PROMOTION=BLOCKED`.
- `LIVE=DISABLED`.

## Review Focus

- Wrong local UID connects first: reject and continue accepting until deadline.
- Socket-name squatting: client rejects non-`shreks` server and fails closed; never accepts spoofed evidence.
- Partial/oversized request or response: fail without parsing trailing bytes.
- Duplicate request across socket/marker paths: return the existing receipt, never run discovery twice.
- Telemetry control exception: emit sanitized failure where possible and continue ordinary telemetry snapshot work.

---

### Task 1: Extract shared authenticated request processing

**Files:**
- Modify: `python/src/shreks_brain/telemetry/fl9_v2_discovery_control.py`
- Modify: `python/tests/test_fl9_v2_discovery_control.py`

**Interfaces:**
- Produces: `decode_fl9_v2_discovery_control_request(payload: bytes) -> dict[str, object]`
- Produces: `process_authenticated_fl9_v2_discovery_request(request: dict[str, object], ...) -> dict[str, object]`
- Existing marker processor delegates to both.

- [ ] **Step 1: Add RED tests for canonical in-memory request decode and marker/socket-equivalent processing.**
- [ ] **Step 2: Run focused discovery-control tests; expect missing APIs.**
- [ ] **Step 3: Extract canonical decoder from `_read_control_request` without weakening marker owner/mode/stable-read checks.**
- [ ] **Step 4: Extract the post-decode release/receipt/age/authority/discovery path into the shared processor.**
- [ ] **Step 5: Run focused tests GREEN and commit `refactor: share FL9 discovery request processing`.**

### Task 2: Add mutually authenticated abstract Unix socket protocol

**Files:**
- Create: `python/src/shreks_brain/telemetry/fl9_v2_discovery_socket.py`
- Create: `python/tests/test_fl9_v2_discovery_socket.py`

**Interfaces:**
- Produces: `serve_fl9_v2_discovery_socket_once(*, accept_timeout_seconds=0.5, ...) -> tuple[dict[str, object], ...]`
- Produces: `request_fl9_v2_discovery_over_socket(..., timeout_seconds=180.0) -> dict[str, object]`
- Module CLI: `python -m shreks_brain.telemetry.fl9_v2_discovery_socket --client --request-id ... --expected-release-sha ... --timeout-seconds 180`.

- [ ] **Step 1: Write RED Linux socket tests using real AF_UNIX abstract sockets and current UID injected as expected client/server UID.**
- [ ] **Step 2: Cover wrong peer UID, malformed canonical request, oversized request, oversized response, timeout, and server-UID mismatch.**
- [ ] **Step 3: Implement fixed abstract socket address, bounded framing, `SO_PEERCRED`, and one-request server.**
- [ ] **Step 4: Implement retrying client with server peer verification and exact result validation.**
- [ ] **Step 5: Run focused tests GREEN and commit `feat: add authenticated FL9 Unix control socket`.**

### Task 3: Service socket requests from telemetry runtime

**Files:**
- Modify: `python/src/shreks_brain/telemetry/runtime.py`
- Modify: `python/tests/test_g4_telemetry_runtime.py`

**Interfaces:**
- Runtime control helper calls socket server first, then legacy marker processor, and emits every returned result.

- [ ] **Step 1: Add RED ordering/isolation tests for socket server before marker processing and config loading on normal and preflight invocations.**
- [ ] **Step 2: Implement bounded socket servicing inside the existing exception-isolated control helper.**
- [ ] **Step 3: Ensure a socket error cannot prevent marker fallback or telemetry snapshot generation.**
- [ ] **Step 4: Run runtime tests GREEN and commit `feat: serve FL9 socket controls in telemetry`.**

### Task 4: Switch production verifier to socket primary with legacy fallback

**Files:**
- Modify: `.github/workflows/verify-production-paper.yml`
- Modify: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- New release: invoke release-local socket client and validate its canonical terminal result.
- Old release: retain current marker/journal path unchanged.

- [ ] **Step 1: Add RED delivery tests requiring socket-client capability detection, primary socket invocation, exact 180-second bound, and legacy marker fallback.**
- [ ] **Step 2: Require the socket path to contain no sudo/systemctl mutation/protected-state write.**
- [ ] **Step 3: Implement capability probe using import of `shreks_brain.telemetry.fl9_v2_discovery_socket`.**
- [ ] **Step 4: Invoke the client with exact request ID/release SHA and capture one canonical result line.**
- [ ] **Step 5: Reuse the existing strict result validator for schema/request/release/status.**
- [ ] **Step 6: Run delivery tests GREEN and commit `fix: use authenticated FL9 socket transport`.**

### Task 5: Document transport and run full gates

**Files:**
- Modify: `deploy/release/README.md`
- Modify: relevant static delivery/systemd tests only if required by documented invariant.

- [ ] **Step 1: Document socket primary, marker/journal fallback, mutual UID authentication, and fail-closed semantics.**
- [ ] **Step 2: Run focused Python tests for discovery control, socket, telemetry runtime, and delivery workflows.**
- [ ] **Step 3: Run canonical Repository safety, Python, Rust, and ARM64 CI on exact feature head.**
- [ ] **Step 4: Review diff: confirm no release-manager, sudoers, systemd, protected-permission, wallet/signing, promotion, or LIVE changes.**
- [ ] **Step 5: Open PR and require independent PR CI before merge.**
- [ ] **Step 6: After exact merged-main CI, create a docs-only `seal:` PR and require its full PR CI.**
- [ ] **Step 7: Follow automatic sealed release -> deploy -> verifier and preserve the exact terminal FL9 discovery evidence.**
