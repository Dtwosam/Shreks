# Phase G2 GitHub-to-VPS Release Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one sealed Shreks source SHA from GitHub to the dedicated Linux VPS as a verified immutable release with atomic activation and rollback, without putting trading-wallet material in GitHub.

**Architecture:** GitHub builds a release tarball from an exact sealed SHA, records it as `shreks-<40-char-sha>`, and deploys only existing release assets over a deployment-only SSH credential. A root-owned standard-library host release manager verifies the bundle, stages `/opt/shreks/releases/<sha>`, atomically switches `/opt/shreks/current`, restarts the existing systemd target, and restores the previous release on activation failure.

**Tech Stack:** GitHub Actions, Bash, Python 3.12 standard library, Cargo/Rust, Python wheel packaging, systemd, SSH/SCP.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-g2-github-vps-release-delivery-design.md`

## Global Constraints

- Base is sealed G1C `517bc81efa6d5cb88c3a471bb7683b5c1cc330ec`.
- Solana V1 only.
- No paid external infrastructure requirement is introduced.
- GitHub is delivery/control plane only; the VPS remains the 24/7 runtime.
- Trading wallet/private signing credentials never enter GitHub, release assets, workflow logs, or deployment transport.
- Deployment must not mutate proof, promotion, strategy, scoring, risk, accounting, checkpoint, or live-enable state.
- `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, `/var/lib/shreks`, E11 evidence, and checkpoints survive deploy/rollback unchanged.
- Existing G1C systemd runtime paths through `/opt/shreks/current` remain authoritative.
- First release platform is `x86_64-unknown-linux-gnu`.
- Release tags are exactly `shreks-<40-character-source-sha>`.
- **LIVE TRADING: DISABLED.**

---

### Task 1: Release manifest, allowlist, and bundle verifier

**Files:**
- Create: `deploy/release/release_bundle.py`
- Create: `python/tests/test_g2_release_bundle.py`

**Interfaces:**
- Produces `RELEASE_MANIFEST_SCHEMA_VERSION = "g2-release-manifest-v1"`.
- Produces `ReleaseBundleError(ValueError)`.
- Produces `ReleaseFile(path: str, size: int, sha256: str)` immutable dataclass.
- Produces `ReleaseManifest(schema_version: str, source_sha: str, platform: str, files: tuple[ReleaseFile, ...])` immutable dataclass.
- Produces `validate_source_sha(value: str) -> str`.
- Produces `release_tag_for_sha(source_sha: str) -> str`.
- Produces `build_release_manifest(staging_dir: Path, source_sha: str, platform: str) -> ReleaseManifest`.
- Produces `encode_release_manifest(manifest: ReleaseManifest) -> bytes` using canonical compact JSON with sorted keys and one trailing newline.
- Produces `decode_release_manifest(payload: bytes) -> ReleaseManifest` with exact-key validation.
- Produces `verify_release_tree(root: Path, manifest: ReleaseManifest) -> None`.
- Produces `write_release_archive(staging_dir: Path, manifest: ReleaseManifest, archive_path: Path) -> str`, returning the archive SHA-256.
- Produces `verify_release_archive(archive_path: Path, checksum_path: Path, manifest_path: Path) -> ReleaseManifest` without extracting unsafe members.

Exact allowlisted release members:

```python
REQUIRED_RELEASE_PATHS = (
    "target/release/shreks-observe",
    "target/release/shreks-paper-evidence",
    "deploy/systemd/shreks-observe.service",
    "deploy/systemd/shreks-paper-evidence.service",
    "deploy/systemd/shreks-paper-campaign.service",
    "deploy/systemd/shreks.target",
    "RELEASE_MANIFEST.json",
)
```

The manifest additionally permits exactly one regular file matching `wheelhouse/shreks_brain-*.whl`. No symlink/device/FIFO/archive member is allowed.

- [ ] **Step 1: Write RED manifest/verification tests**

Tests must prove:

```python
assert validate_source_sha("a" * 40) == "a" * 40
with pytest.raises(ReleaseBundleError):
    validate_source_sha("abc")
assert release_tag_for_sha("a" * 40) == "shreks-" + "a" * 40
```

Build a temporary allowlisted staging tree and assert canonical encode/decode round-trip, sorted file paths, exact sizes/hashes, one-wheel rule, unsupported platform rejection, unknown/missing manifest keys rejection, tampered file rejection, checksum mismatch rejection, archive `../escape` rejection, absolute path rejection, symlink member rejection, and unexpected member rejection.

- [ ] **Step 2: Run RED**

Run:

```sh
python -m pytest python/tests/test_g2_release_bundle.py -q
```

Expected: collection/import failure because `deploy/release/release_bundle.py` does not exist.

- [ ] **Step 3: Implement the minimal standard-library bundle module**

Use `hashlib`, `json`, `tarfile`, `gzip`, `io`, `re`, `dataclasses`, and `pathlib` only. Never shell out from validation code. Validate archive members before extraction and compare the archive member set to the manifest/allowlist exactly.

- [ ] **Step 4: Run targeted GREEN and full CI-equivalent Python tests**

```sh
python -m pytest python/tests/test_g2_release_bundle.py -q
python -m pytest python/tests -q
```

- [ ] **Step 5: Commit Task 1**

Commit message:

```text
feat: add verified G2 release bundle format
```

---

### Task 2: Host release manager with atomic activation and rollback

**Files:**
- Create: `deploy/release/release_manager.py`
- Create: `python/tests/test_g2_release_manager.py`

**Interfaces:**
- Consumes Task 1 manifest/archive verification functions.
- Produces `ReleaseManagerError(RuntimeError)`.
- Produces immutable `ReleasePaths(releases_dir: Path, current_link: Path, systemd_dir: Path)`.
- Produces `stage_release(archive_path: Path, checksum_path: Path, manifest_path: Path, paths: ReleasePaths, *, python_executable: str = "/usr/bin/python3") -> Path`.
- Produces `activate_release(release_dir: Path, paths: ReleasePaths, *, command_runner: Callable[[tuple[str, ...]], None]) -> None`.
- Produces `activate_existing(source_sha: str, paths: ReleasePaths, *, command_runner: Callable[[tuple[str, ...]], None]) -> None`.
- Produces CLI commands `install` and `activate-existing` with production defaults `/opt/shreks/releases`, `/opt/shreks/current`, `/etc/systemd/system`.

Activation uses:

```python
("systemctl", "stop", "shreks.target")
("systemctl", "daemon-reload")
("systemctl", "start", "shreks.target")
("systemctl", "is-active", "--quiet", "shreks.target")
```

The current symlink switch must use a temporary sibling symlink followed by `os.replace`.

- [ ] **Step 1: Write RED manager tests**

Tests must use temporary release/systemd directories and a recording fake command runner. Prove:

- verified archive stages under `<releases>/<source_sha>`;
- a staging failure never changes `current`;
- an existing matching release is reusable;
- an existing mismatched release fails closed;
- activation installs exactly the four allowlisted systemd unit files;
- successful activation points `current` to the new release;
- health-check failure restores the previous symlink and previous systemd units;
- first-deploy health failure leaves no false active release claim;
- `/etc/shreks` and `/var/lib/shreks` are not parameters or mutation targets anywhere in the manager API;
- `activate-existing` re-verifies the stored manifest/tree before switching.

Patch venv construction in unit tests so tests do not perform network/package installation. Production staging must run:

```text
/usr/bin/python3 -m venv <release>/.venv
<release>/.venv/bin/python -m pip install --no-index --no-deps <release>/wheelhouse/shreks_brain-*.whl
```

- [ ] **Step 2: Run RED**

```sh
python -m pytest python/tests/test_g2_release_manager.py -q
```

Expected: import failure because `release_manager.py` is absent.

- [ ] **Step 3: Implement minimal release manager**

The CLI may use `argparse`; production command execution uses `subprocess.run(..., check=True)`. On rollback failure, retain the original deployment exception as context and exit nonzero; never report success after a failed health check.

- [ ] **Step 4: Run targeted GREEN and full Python suite**

```sh
python -m pytest python/tests/test_g2_release_manager.py -q
python -m pytest python/tests -q
```

- [ ] **Step 5: Commit Task 2**

```text
feat: add atomic VPS release activation
```

---

### Task 3: Exact-SHA GitHub Release builder

**Files:**
- Create: `deploy/release/build_release.sh`
- Create: `.github/workflows/release.yml`
- Create: `python/tests/test_g2_delivery_workflows.py`

**Interfaces:**
- Consumes Task 1 `release_bundle.py`.
- Produces release artifacts under `dist/release/`.
- Produces GitHub Release tag `shreks-${SOURCE_SHA}`.

`build_release.sh` must:

```sh
cargo build --release --bin shreks-observe --bin shreks-paper-evidence
python -m pip wheel ./python --no-deps -w dist/release-wheel
```

Then copy only the allowlisted binaries, wheel, and systemd files into a clean staging directory and invoke `release_bundle.py` to write manifest/archive/checksum.

`release.yml` must:

- use `workflow_dispatch.source_sha`;
- require `permissions: contents: write` and no other write permission;
- validate `^[0-9a-f]{40}$`;
- checkout `ref: ${{ inputs.source_sha }}` with `fetch-depth: 0`;
- assert `git rev-parse HEAD` equals the input;
- require `git log -1 --format=%s` to contain `seal` case-insensitively;
- run repository secret-assignment guard;
- run `cargo test --workspace`;
- install `./python[dev]` and run `python -m pytest python/tests -q`;
- build/verify the bundle;
- fail when `shreks-${SOURCE_SHA}` already exists;
- create the GitHub Release with `gh release create` only after verification.

- [ ] **Step 1: Write RED static workflow/build-script tests**

Parse workflow text as plain text rather than adding PyYAML. Assert exact required commands/permissions and assert forbidden strings are absent:

```python
FORBIDDEN = (
    "WALLET",
    "SEED_PHRASE",
    "SIGNING_KEY",
    "HELIUS_API_KEY",
    "JUPITER_API_KEY",
    "LIVE_TRADING=ENABLED",
)
```

Also assert `build_release.sh` has `set -euo pipefail`, builds both Rust binaries, builds the wheel with `--no-deps`, starts from a clean staging directory, and delegates manifest/archive creation to the verified Task 1 module.

- [ ] **Step 2: Run RED**

```sh
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: missing workflow/build-script assertions fail.

- [ ] **Step 3: Implement build script and release workflow**

Do not add third-party release actions. Use `actions/checkout@v7`, `actions/setup-python@v7`, `dtolnay/rust-toolchain@stable`, and the preinstalled GitHub CLI.

- [ ] **Step 4: Run targeted GREEN and full suites**

```sh
python -m pytest python/tests/test_g2_delivery_workflows.py -q
python -m pytest python/tests -q
cargo test --workspace
```

- [ ] **Step 5: Commit Task 3**

```text
feat: build exact-SHA GitHub releases
```

---

### Task 4: GitHub-to-VPS deployment transport and bootstrap runbook

**Files:**
- Create: `.github/workflows/deploy.yml`
- Create: `deploy/release/README.md`
- Modify: `python/tests/test_g2_delivery_workflows.py`
- Modify: `crates/shreks-observer/tests/systemd_units.rs` only if needed to lock unchanged `/opt/shreks/current` execution paths.

**Interfaces:**
- Consumes an existing GitHub Release `shreks-<40-char-sha>`.
- Consumes only deployment transport secrets `SHREKS_DEPLOY_HOST`, `SHREKS_DEPLOY_PORT`, `SHREKS_DEPLOY_USER`, `SHREKS_DEPLOY_SSH_KEY`, `SHREKS_DEPLOY_KNOWN_HOSTS`.
- Invokes root-owned `/usr/local/sbin/shreks-release-manager install ...` on the host.

- [ ] **Step 1: Extend RED tests for deployment boundary**

Assert `.github/workflows/deploy.yml`:

- is `workflow_dispatch` only;
- accepts required `release_tag`;
- uses `environment: production-paper`;
- has `permissions: contents: read`;
- validates tag `^shreks-[0-9a-f]{40}$`;
- downloads exactly tarball/checksum/manifest from the existing GitHub Release;
- runs local bundle verification before SSH;
- writes the private SSH key to an ephemeral `0600` file;
- writes `SHREKS_DEPLOY_KNOWN_HOSTS` to an ephemeral known-hosts file;
- passes `StrictHostKeyChecking=yes` and the explicit known-hosts file;
- never invokes `ssh-keyscan`;
- copies only release artifacts;
- invokes only the root-owned release manager through `sudo`;
- contains none of the forbidden wallet/provider/live-mode secret strings.

Assert the runbook includes one-time installation of the manager as root-owned mode `0755`, a dedicated deploy account, a narrow sudoers command, release provenance checks (`readlink -f /opt/shreks/current` and `cat /opt/shreks/current/RELEASE_MANIFEST.json`), and rollback by selecting an earlier GitHub Release tag.

- [ ] **Step 2: Run RED**

```sh
python -m pytest python/tests/test_g2_delivery_workflows.py -q
```

Expected: deployment/runbook assertions fail because files are absent.

- [ ] **Step 3: Implement deploy workflow and runbook**

The workflow must not create or alter host runtime secrets. Document that GitHub Environment secret population is account configuration, not repository content, and that the deploy SSH key is intentionally separate from any trading key.

- [ ] **Step 4: Run full verification**

```sh
python -m pytest python/tests -q
cargo test --workspace
```

Repository-safety CI must also remain GREEN.

- [ ] **Step 5: Commit Task 4**

```text
feat: add verified GitHub-to-VPS deployment
```

---

### Task 5: Freeze, audit, verification record, and seal

**Files:**
- Modify only after behavior freeze: `docs/superpowers/plans/2026-08-25-phase-g2-github-vps-release-delivery.md`

- [ ] **Step 1: Freeze behavior SHA**

Wait for full CI GREEN on the exact final behavior commit. Record Python pass count, Rust/workspace result, repository-safety result, and workflow run ID.

- [ ] **Step 2: Audit sealed G1C -> G2 behavior**

Compare:

```text
517bc81efa6d5cb88c3a471bb7683b5c1cc330ec -> <G2_BEHAVIOR_SHA>
```

Inspect every changed file. Verify the diff contains only G2 design/plan, release bundle/manager/build/deploy tooling, workflow files, runbook, and tests.

Explicitly verify absent:

- strategy/setup/scoring changes;
- risk-engine changes;
- provider behavior changes;
- storage schema/migration changes;
- paper/live execution logic changes;
- ledger/accounting/checkpoint/evaluation changes;
- registry/promotion mutation;
- transaction construction/signing/submission;
- wallet/private key material;
- live-mode enablement;
- mutation/deletion of `/etc/shreks` protected runtime config or `/var/lib/shreks` durable state.

- [ ] **Step 3: Replace this plan with final verification record**

Record every RED/GREEN commit/CI anchor, final behavior SHA/CI, exact changed-file audit, secret/authority boundary, and release/deploy/rollback invariants.

- [ ] **Step 4: Commit the one-document seal**

```text
docs: seal G2 GitHub VPS release delivery
```

- [ ] **Step 5: Prove seal geometry**

Compare behavior SHA -> seal SHA and require:

```text
ahead_by = 1
behind_by = 0
changed_files = [docs/superpowers/plans/2026-08-25-phase-g2-github-vps-release-delivery.md]
```

- [ ] **Step 6: Run/check fresh exact-seal CI**

Require Python, Rust/workspace, and repository safety all GREEN on the exact seal SHA.

- [ ] **Step 7: Update stacked draft PR**

Record base sealed G1C SHA, behavior SHA, seal SHA, CI IDs, audit result, rollback mechanics, secret boundary, and:

`LIVE TRADING: DISABLED.`

## Deferred after G2 seal

After G2 is sealed, configure the real VPS and GitHub `production-paper` environment/transport secrets when the host exists, then use the release/deploy path to support G3 real-host supervision/restart verification. G4+ monitoring/dashboard/alerts/backup work remains separate. Live money remains disabled until all proof and pre-F7 operational gates pass.
