# FL9 V2 Telemetry Discovery Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the existing protected production verifier request and receive authenticated FL9 V2 runtime-manifest discovery through the already-installed `shreks` telemetry identity, without widening deploy-account permissions or requiring an interactive administrator shell.

**Architecture:** GitHub's existing verifier writes a canonical ephemeral request under `/dev/shm`. The already-installed 60-second telemetry service processes bounded requests during its existing `--preflight` invocation, authenticates preserved V2 request authority and protected runtime manifests, stores an idempotence receipt under the telemetry tree, and emits one sanitized canonical JSON result to journald. No new systemd unit, sudoers rule, release-manager capability, or trading authority is added.

**Tech Stack:** Python 3.12, existing canonical Shreks codecs/readers, systemd telemetry timer, GitHub Actions/Bash/SSH, pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-fl9-v2-telemetry-discovery-bridge-design.md`

## Global Constraints

- Keep `shreks-deploy` unable to read `/etc/shreks` or `/var/lib/shreks` directly.
- Do not modify sudoers, the root release-manager command surface, or systemd unit files.
- Use only the existing `shreks-telemetry.service` execution identity for protected discovery.
- The GitHub request may contain only request identity/time and expected release SHA; no arbitrary protected paths or commands.
- Historical authority search is bounded and only targets the known `v2-first-champion-request.json` filename.
- Existing runtime-manifest and V2 request/hydration codecs remain the authority; do not synthesize or rewrite quote/runtime policy.
- Discovery-control failure must not break normal telemetry preflight/snapshot operation.
- Trusted HOLD outcomes are successful discovery completion, not CI failures.
- `V2_SCORING_RETRY=NOT_YET_AUTHORIZED`.
- `PAPER_PROMOTION=BLOCKED`.
- `LIVE=DISABLED`.

---

### Task 1: Extract reusable authenticated V2 request authority

**Files:**
- Modify: `python/src/shreks_brain/fl9_v2_runtime_manifest_discovery.py`
- Modify: `python/tests/test_fl9_v2_runtime_manifest_discovery.py`

**Interfaces:**
- Consumes: `read_fl9_v2_cohort_acceptance`, `decode_fast_first_champion_v2_host_request`, `decode_fast_forecast_context_hydration_policy`.
- Produces: `AuthenticatedV2DiscoveryRequestAuthority` and `authenticate_fl9_v2_discovery_request_authority(...)` for both existing discovery and the bridge scanner.

- [ ] **Step 1: Write failing authentication-helper tests**

Add tests requiring an authenticated result to expose canonical request path/fingerprint/release SHA, cohort fingerprint, canonical hydration-policy path/fingerprint, and exactly the five non-manifest assumptions. Add fail-closed tests for cohort mismatch and request-bound hydration-policy fingerprint mismatch.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest python/tests/test_fl9_v2_runtime_manifest_discovery.py -q
```

Expected: FAIL because `authenticate_fl9_v2_discovery_request_authority` and its result type do not yet exist.

- [ ] **Step 3: Implement the minimal reusable authority helper**

Create an immutable dataclass with these fields:

```python
@dataclass(frozen=True, slots=True)
class AuthenticatedV2DiscoveryRequestAuthority:
    request_path: Path
    request_fingerprint_sha256: str
    request_release_source_sha: str
    cohort_artifact_fingerprint_sha256: str
    hydration_policy_path: Path
    hydration_policy_fingerprint_sha256: str
    hydration_policy_version: str
    strategy_families: tuple[str, ...]
    max_exit_quote_age_ms: int
    execution_cost_policy_version: str
    expected_round_trip_cost_bps: float | int | None
```

Move the existing request/cohort/policy authentication steps into:

```python
def authenticate_fl9_v2_discovery_request_authority(
    *,
    cohort_path: str | Path,
    v2_host_request_authority_path: str | Path,
) -> AuthenticatedV2DiscoveryRequestAuthority:
    ...
```

Refactor `discover_fl9_v2_runtime_manifests_from_v2_request_authority(...)` to call the helper and preserve its current report schema/provenance.

- [ ] **Step 4: Re-run focused tests**

Run the same pytest command. Expected: PASS with all prior discovery tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add python/src/shreks_brain/fl9_v2_runtime_manifest_discovery.py python/tests/test_fl9_v2_runtime_manifest_discovery.py
git commit -m "refactor: expose authenticated FL9 V2 discovery authority"
```

---

### Task 2: Build the bounded telemetry discovery-control processor

**Files:**
- Create: `python/src/shreks_brain/telemetry/fl9_v2_discovery_control.py`
- Create: `python/tests/test_fl9_v2_discovery_control.py`

**Interfaces:**
- Consumes: Task 1 authentication helper and `discover_fl9_v2_runtime_manifests_from_v2_request_authority(...)`.
- Produces: `process_pending_fl9_v2_discovery_requests(...) -> tuple[dict[str, object], ...]` and canonical result JSON lines.

- [ ] **Step 1: Write RED request-validation and bounded-enumeration tests**

Cover:

```python
# valid canonical 0644 deploy-owned request succeeds
# symlink, wrong owner, wrong mode, non-canonical JSON, oversize, stale/future request fail closed
# expected release SHA must equal current release link + manifest identity
# enumeration checks root + bounded fl9-v2-* descendants only
# source must not use Path.rglob or os.walk for /var/lib/shreks
```

Use injectable paths, expected owner UID, clock, and discovery function so tests never touch production paths.

- [ ] **Step 2: Run the new test file and verify RED**

```bash
python -m pytest python/tests/test_fl9_v2_discovery_control.py -q
```

Expected: import failure because the control module does not exist.

- [ ] **Step 3: Implement strict control-request parsing and release binding**

Define request schema `shreks.fl9_v2_discovery_control_request` v1 with exact keys `schema_name`, `schema_version`, `request_id`, `expected_release_sha`, `created_at_unix_ms`. Require canonical compact JSON plus trailing newline, request ID regex `[A-Za-z0-9._-]{1,96}`, 40-char lowercase source SHA, mode `0644`, stable inode/size/mtime, configured deploy-owner UID, and a bounded age/future-skew window.

Verify `/opt/shreks/current` resolves to `/opt/shreks/releases/<expected_sha>` and its `RELEASE_MANIFEST.json` reports the same source SHA.

- [ ] **Step 4: Add RED authority-resolution tests**

Cover zero valid requests -> `HOLD_NO_REQUEST_AUTHORITY`; one valid request -> discovery delegation; two requests with identical five-value authority -> one group; two distinct authority tuples -> `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`; invalid historical candidates are rejected and never selected.

- [ ] **Step 5: Implement bounded authority resolution and delegation**

Search only for `v2-first-champion-request.json` at the configured root and below bounded real `fl9-v2-*` directories. Authenticate candidates with Task 1. Group valid candidates by SHA-256 of canonical JSON containing cohort fingerprint plus the five non-manifest inputs. Select the lexicographically first request path only when exactly one group exists, then delegate to the existing sealed discovery function.

- [ ] **Step 6: Add RED receipt/idempotence tests**

Require first processing to write a `0600` canonical receipt atomically below the configured receipt root, and a repeated marker with the same request ID to re-emit the stored result without invoking historical scan/discovery again.

- [ ] **Step 7: Implement receipt and batch processing**

Expose:

```python
def process_pending_fl9_v2_discovery_requests(
    *,
    marker_directory: Path = Path("/dev/shm"),
    receipt_root: Path = Path("/var/lib/shreks/telemetry/fl9-v2-discovery-control"),
    request_search_root: Path = Path("/var/lib/shreks"),
    cohort_path: Path = Path("/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2"),
    active_runtime_manifest_path: Path = Path("/etc/shreks/paper-campaign.json"),
    backup_root: Path = Path("/var/lib/shreks/backups"),
    current_release_link: Path = Path("/opt/shreks/current"),
    expected_owner_uid: int | None = None,
    now_unix_ms: int | None = None,
    max_requests: int = 8,
) -> tuple[dict[str, object], ...]:
    ...
```

Production default owner resolution uses `pwd.getpwnam("shreks-deploy").pw_uid`. Every trusted marker yields a `shreks.fl9_v2_discovery_control_result` v1 object and one canonical stdout line through a small `emit...` helper used by Task 3.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest python/tests/test_fl9_v2_discovery_control.py python/tests/test_fl9_v2_runtime_manifest_discovery.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add python/src/shreks_brain/telemetry/fl9_v2_discovery_control.py python/tests/test_fl9_v2_discovery_control.py
git commit -m "feat: add read-only FL9 V2 discovery control processor"
```

---

### Task 3: Integrate the bridge into the existing telemetry preflight safely

**Files:**
- Modify: `python/src/shreks_brain/telemetry/runtime.py`
- Modify: `python/tests/test_g4_telemetry_runtime.py`

**Interfaces:**
- Consumes: `process_pending_fl9_v2_discovery_requests(...)` from Task 2.
- Produces: automatic processing once per telemetry timer activation via the existing `--preflight` command.

- [ ] **Step 1: Write RED telemetry-integration tests**

Monkeypatch the control processor and require:

```python
# main(["--preflight"]) invokes the control processor before telemetry config loading
# every returned result is emitted as one canonical JSON line
# control-processor exception is converted to a sanitized bridge failure line
# a control failure does not prevent normal telemetry preflight from running
# main([]) does not process discovery controls a second time
```

- [ ] **Step 2: Run focused telemetry tests and verify RED**

```bash
python -m pytest python/tests/test_g4_telemetry_runtime.py -q
```

- [ ] **Step 3: Implement isolated preflight integration**

At the start of the existing `--preflight` path, call the bridge processor in its own exception boundary and print canonical result lines. Do not add new telemetry environment keys and do not change `run_telemetry_once(...)`.

- [ ] **Step 4: Re-run telemetry + bridge tests**

```bash
python -m pytest python/tests/test_g4_telemetry_runtime.py python/tests/test_fl9_v2_discovery_control.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/src/shreks_brain/telemetry/runtime.py python/tests/test_g4_telemetry_runtime.py
git commit -m "feat: process FL9 discovery controls in telemetry preflight"
```

---

### Task 4: Make production verification request and surface protected discovery

**Files:**
- Modify: `.github/workflows/verify-production-paper.yml`
- Modify: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes: existing production SSH secrets and the Task 2/3 telemetry journal result.
- Produces: one automatic read-only FL9 discovery attempt as part of the existing protected production verification workflow whenever the deployed release contains the bridge module.

- [ ] **Step 1: Write RED workflow-contract assertions**

Require the workflow to contain all of:

```text
/dev/shm/shreks-fl9-v2-discovery.
shreks.fl9_v2_discovery_control_request
shreks_brain.telemetry.fl9_v2_discovery_control
systemctl is-active --quiet shreks-telemetry.timer
journalctl -u shreks-telemetry.service -o cat
HOLD_NO_REQUEST_AUTHORITY
HOLD_AMBIGUOUS_REQUEST_AUTHORITY
HOLD_NO_COMPATIBLE
FOUND_COMPATIBLE
rm -f "$DISCOVERY_MARKER"
```

Also assert that no new secret name, `sudo`, protected-path write, `chmod/chown/setfacl` on protected state, systemctl mutation, scoring command, or LIVE command is introduced.

- [ ] **Step 2: Run the workflow-contract test and verify RED**

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py::test_production_verifier_is_manual_read_only_and_uses_existing_transport_boundary -q
```

Expected: FAIL on missing bridge workflow strings.

- [ ] **Step 3: Implement the verifier bridge request**

After current production checks, remotely:

1. test importability of `shreks_brain.telemetry.fl9_v2_discovery_control`; if absent, print `fl9_v2_discovery_bridge=unavailable` and preserve legacy behavior;
2. require `shreks-telemetry.timer` active;
3. create request ID `gha-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}` supplied as an SSH argument;
4. use remote Python as `shreks-deploy` to atomically create canonical `0644` marker under `/dev/shm` with the expected release SHA and current epoch milliseconds;
5. poll the telemetry journal with `-o cat` for up to 180 seconds;
6. require exactly parseable schema/request ID/release binding;
7. remove only that workflow's marker on terminal paths;
8. return success for the four trusted FOUND/HOLD statuses and failure for `FAILED`/timeout/malformed output.

- [ ] **Step 4: Run workflow and related delivery tests**

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/verify-production-paper.yml python/tests/test_g2_delivery_workflows.py
git commit -m "feat: bridge production FL9 discovery through telemetry"
```

---

### Task 5: Document the no-admin-shell production continuation

**Files:**
- Modify: `deploy/release/README.md`
- Modify: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes: Task 4 verifier behavior.
- Produces: operator documentation stating that protected FL9 read-only discovery now rides through telemetry and does not require deploy-account access to protected state.

- [ ] **Step 1: Add RED runbook assertions**

Require documentation of `/dev/shm/shreks-fl9-v2-discovery`, `shreks-telemetry.timer`, journal result retrieval, deploy-account permission boundary, and the fact that FOUND/HOLD is evidence only and LIVE remains disabled.

- [ ] **Step 2: Update the runbook narrowly**

Document the bridge after the existing production verification section. Explicitly state that operators must not add sudoers entries or relax `/etc/shreks`/`/var/lib/shreks` permissions to make discovery work.

- [ ] **Step 3: Run delivery tests**

```bash
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add deploy/release/README.md python/tests/test_g2_delivery_workflows.py
git commit -m "docs: document telemetry FL9 discovery bridge"
```

---

### Task 6: Full verification, authority review, PR, and seal handoff

**Files:**
- Review all files changed by Tasks 1-5.

**Interfaces:**
- Consumes: complete feature branch.
- Produces: PR-ready implementation with no authority creep.

- [ ] **Step 1: Run focused regression suite**

```bash
python -m pytest \
  python/tests/test_fl9_v2_runtime_manifest_discovery.py \
  python/tests/test_fl9_v2_discovery_control.py \
  python/tests/test_g4_telemetry_runtime.py \
  python/tests/test_g2_delivery_workflows.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full Python suite**

```bash
python -m pytest python/tests -q
```

Expected: PASS.

- [ ] **Step 3: Run Rust/workspace tests**

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 4: Review authority diff**

Confirm the diff contains no changes to:

```text
/etc/sudoers.d/shreks-release-manager contract
deploy/release/release_manager.py
deploy/systemd/*.service or *.timer
wallet/signing/submission paths
PAPER promotion authority
LIVE authority
```

- [ ] **Step 5: Push PR and require all canonical CI gates**

Require Repository safety, Python tests, Rust tests, and ARM64 release build green on exact PR head.

- [ ] **Step 6: Merge only after exact-head green CI and clean base**

After merge, require exact merged-main green CI before writing a documentation-only `seal:` commit for immutable release/deploy authorization.

- [ ] **Step 7: Seal boundary**

The future seal may authorize only immutable release -> protected deploy -> production verification with the telemetry discovery bridge. It must continue to state:

```text
V2_SCORING_RETRY=NOT_YET_AUTHORIZED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
