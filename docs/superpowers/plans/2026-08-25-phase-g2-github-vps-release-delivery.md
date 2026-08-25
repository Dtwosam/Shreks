# Phase G2 GitHub-to-VPS Release Delivery Verification Record

**Phase:** G2 — GitHub deployment path

**Base sealed G1C SHA:** `517bc81efa6d5cb88c3a471bb7683b5c1cc330ec`

**Frozen G2 behavior SHA:** `2aa640196266109119a7c21dde27727fc33d9beb`

**Frozen-behavior CI:** `32904668639`

**Frozen-behavior result:** Python `2308 passed in 10.23s`; Rust/workspace GREEN; repository safety GREEN.

**Status at record commit:** behavior frozen and audited; this record is the one-file seal commit. Exact-seal CI is recorded in PR #43 metadata after this commit runs through CI.

**LIVE TRADING: DISABLED.**

## 1. Goal and authority boundary

G2 establishes a traceable GitHub-controlled delivery path from one sealed Shreks source SHA to one immutable Linux release on the dedicated VPS. GitHub is the release/deployment control plane; it is not the 24/7 trading runtime.

G2 adds release packaging, verification, atomic host activation/rollback, exact-SHA GitHub Release construction, deployment-only SSH transport, and a VPS bootstrap/runbook. It does not add or modify strategy, scoring, risk, paper/live execution logic, promotion, transaction signing/submission, or live-enable authority.

Trading-wallet/private signing credentials are not release assets and are not GitHub deployment credentials. The deployment SSH key is a separate transport-only credential. Protected runtime configuration and durable state remain host-side.

## 2. Final implemented architecture

The verified path is:

```text
sealed source SHA
  -> exact-SHA GitHub release workflow
  -> Rust/Python/repository-safety retest
  -> allowlisted deterministic release bundle
  -> canonical manifest + SHA-256 sidecar
  -> immutable GitHub Release shreks-<40-char-sha>
  -> manual existing-release deploy workflow
  -> local bundle verification before host contact
  -> pinned-host-key SSH/SCP using deploy-only credential
  -> root-owned host release manager
  -> /opt/shreks/releases/<sha>
  -> release-local copied Python venv at final SHA path
  -> systemd unit install
  -> atomic /opt/shreks/current switch
  -> shreks.target health check
  -> automatic previous-release restoration on activation failure
```

Protected runtime/state paths are outside the release manager API and outside deployment transport:

- `/etc/shreks/shreks.env`
- `/etc/shreks/paper-campaign.json`
- `/var/lib/shreks`

## 3. Task 1 — immutable release manifest, archive, and verifier

### RED

Commit: `56ec6187cfcbde6c6655fc27ce081296e66a40ec`

CI: `32901438939`

Result: Rust and repository safety GREEN; Python failed at collection only because `deploy/release/release_bundle.py` did not exist.

The RED contract covered exact source SHA identity, canonical manifest encoding, strict payload allowlist, exactly one Shreks wheel, checksums, external/embedded manifest equality, archive traversal/absolute-path rejection, and rejection of symlinks/non-regular members.

### First implementation and fixture correction

Implementation commit: `fcb9a452cbd0e97cf201dff2112db610480d3352`

CI: `32901680524`

Result: `1 failed, 2287 passed`. The only failure was a test helper creating `second/staging` without creating its parent; the release verifier was not the failing behavior.

Fixture-only correction commit: `327112b800b955c33fc162acfb902cc35c14b70e`

Final Task 1 CI: `32901814288`

Result: Python `2288 passed in 10.17s`; Rust/workspace GREEN; repository safety GREEN.

### Frozen Task 1 behavior

- schema: `g2-release-manifest-v1`
- source SHA: exactly 40 lowercase hexadecimal characters
- platform: `x86_64-unknown-linux-gnu`
- static payload allowlist:
  - `target/release/shreks-observe`
  - `target/release/shreks-paper-evidence`
  - `deploy/systemd/shreks-observe.service`
  - `deploy/systemd/shreks-paper-evidence.service`
  - `deploy/systemd/shreks-paper-campaign.service`
  - `deploy/systemd/shreks.target`
- exactly one `wheelhouse/shreks_brain-*.whl`
- `RELEASE_MANIFEST.json` is an archive control member but is intentionally not recursively listed inside its own `files` array
- external and embedded manifest bytes must be identical
- canonical compact sorted JSON with one trailing newline
- deterministic tar metadata
- SHA-256 archive sidecar
- archive validation occurs before extraction and rejects unsafe/non-regular members

## 4. Task 2 — root-owned host release manager, atomic activation, and rollback

### RED

Commit: `a98362f3591f5c35743b24c91cd5baac0705018b`

CI: `32902059563`

Result: Python failed at collection only because `deploy/release/release_manager.py` did not exist; repository safety remained GREEN.

### Iteration and hardening history

First manager implementation: `b4376ab20505b1db3a425904bfd4f2c4a3ca8e5d`

CI: `32902196376`

Result: `1 failed, 2297 passed`. The failure was a test expectation that assumed venv construction at the final path while the first implementation used a temporary staging path.

Test correction/hardening: `a7a4a7e2e00873cd4a2003f37ef9645533ec6ff9`

CI: `32902333754`

Result: `1 failed, 2298 passed`. The new failing case exposed that a normal Python venv can contain interpreter symlinks.

The design was then tightened rather than weakening release verification. A Python venv built under a temporary path and renamed can contain absolute-path assumptions, and the temporary directory mode also prevented safe traversal by the non-root Shreks runtime.

Corrected RED contract commit: `c95a6a8ba16e61f535a8bbc2df7fa865965d3997`

CI: `32902586039`

Result: `2 failed, 2298 passed`. The two intended failures were:

1. final release directory mode remained `0700` rather than `0755`;
2. a rejected venv state left an incomplete SHA-addressed release directory.

### Final GREEN

Commit: `4aae09207b594dbd6e7e91e0407998391080b4a6`

CI: `32902756839`

Result: Python `2300 passed in 10.04s`; Rust/workspace GREEN; repository safety GREEN.

### Frozen Task 2 behavior

- `ReleasePaths` exposes only release directory, `current` symlink, and systemd unit directory.
- No `/etc/shreks` or `/var/lib/shreks` mutation parameter exists.
- incoming archive is verified before staging.
- signed payload is extracted into hidden staging and reverified.
- verified payload moves to immutable final `/opt/shreks/releases/<sha>`.
- final release directory is traversable by the non-root services (`0755`).
- runtime binaries are executable.
- Python venv is created only at the final SHA path using `python3 -m venv --copies`.
- Shreks wheel installation is offline and dependency-closed at install time: `pip install --no-index --no-deps`.
- incomplete releases are removed on install/final-verification failure.
- `/opt/shreks/current` is untouched until activation.
- stored payloads are reverified before any activation.
- activation installs exactly the four sealed systemd unit files.
- `current` switches through a temporary sibling symlink followed by `os.replace`.
- activation requires `shreks.target` to become active.
- failed upgrade restores the previous verified release and its previous systemd units, then health-checks the restored target.
- failed first deployment leaves no false active-release claim.

## 5. Task 3 — exact-SHA GitHub Release construction

### RED

Commit: `ff99227dc271848f154f9f9a720bd3c9f1cd909b`

CI: `32902924638`

Result: Rust/workspace and repository safety GREEN; Python failed only on the newly introduced release workflow/build-script/CLI contract because those G2 files/features were not yet present.

### GREEN

Commit: `055be3658b60d116d7a19e4132a6921669621624`

CI: `32904304095`

Result: Python `2304 passed in 12.44s`; Rust/workspace GREEN; repository safety GREEN.

### Frozen Task 3 behavior

`deploy/release/build_release.sh`:

- `set -euo pipefail`
- exact 40-lowercase-hex source SHA validation
- `git rev-parse HEAD` must equal requested source SHA
- builds only `shreks-observe` and `shreks-paper-evidence`
- builds exactly one Shreks wheel with `--no-deps`
- stages only the allowlisted binaries, existing sealed systemd files, and Shreks wheel
- delegates bundle construction and verification to `release_bundle.py`

`.github/workflows/release.yml`:

- manual `workflow_dispatch` only
- required exact `source_sha`
- `permissions: contents: write` only
- no `secrets.*` consumption
- no SSH or deployment environment
- checkout exact input SHA with full history
- assert checkout SHA equality
- require commit subject to contain `seal` case-insensitively
- rerun committed-secret guard
- rerun Rust workspace tests
- rerun Python tests
- build and locally verify release bundle
- reject duplicate `shreks-<sha>` release tag
- create the GitHub Release only after all gates pass
- release target is the exact source SHA

## 6. Task 4 — deployment-only GitHub-to-VPS transport and runbook

### RED

Commit: `83e01d8733f70c05ecc156f26e8f47b507ae2ce9`

CI: `32904495302`

Result: Python `4 failed, 2304 passed in 9.59s`. All four failures were exactly the new Task 4 boundary: three tests required missing `.github/workflows/deploy.yml`, and one required missing `deploy/release/README.md`. Repository safety remained GREEN.

### GREEN / frozen behavior

Commit: `2aa640196266109119a7c21dde27727fc33d9beb`

CI: `32904668639`

Result: Python `2308 passed in 10.23s`; Rust/workspace GREEN; repository safety GREEN.

### Frozen Task 4 behavior

`.github/workflows/deploy.yml`:

- manual `workflow_dispatch` only
- accepts an existing `shreks-<40-char-sha>` release tag only
- `environment: production-paper`
- `permissions: contents: read`
- cannot build or create a release
- checks out the verifier at the release tag
- downloads exactly tarball, checksum, and manifest
- verifies the release locally before any host contact
- consumes exactly five deployment-transport environment secrets:
  - `SHREKS_DEPLOY_HOST`
  - `SHREKS_DEPLOY_PORT`
  - `SHREKS_DEPLOY_USER`
  - `SHREKS_DEPLOY_SSH_KEY`
  - `SHREKS_DEPLOY_KNOWN_HOSTS`
- deploy key and pinned known-hosts material are written only to trapped temporary files with restrictive permissions
- `StrictHostKeyChecking=yes`, explicit known-hosts file, and `BatchMode=yes`
- no `ssh-keyscan`
- exactly three `scp` transfers: tarball, checksum, manifest
- no protected runtime/state path appears in the workflow
- no direct `systemctl`
- only remote privileged command is the root-owned Shreks release manager `install` command

`deploy/release/README.md`:

- creates dedicated unprivileged `shreks-deploy` account
- installs verifier and release manager root-owned mode `0755`
- documents narrow sudoers entry for the manager install command
- documents the exact five `production-paper` transport secrets
- explicitly separates the deploy SSH key from any trading/signing key
- keeps runtime/provider/trading credentials host-only
- includes active-release provenance and systemd health checks
- rollback selects an earlier immutable GitHub Release and reuses the exact same verified deployment path
- explicitly states `LIVE TRADING: DISABLED`

## 7. Frozen G1C -> G2 behavior audit

Compare range:

```text
517bc81efa6d5cb88c3a471bb7683b5c1cc330ec
  ->
2aa640196266109119a7c21dde27727fc33d9beb
```

Compare result:

- status: ahead
- commits: `13`
- changed files: `11`
- every changed file is an addition; no pre-existing file was modified

Exact changed files:

1. `.github/workflows/deploy.yml`
2. `.github/workflows/release.yml`
3. `deploy/release/README.md`
4. `deploy/release/build_release.sh`
5. `deploy/release/release_bundle.py`
6. `deploy/release/release_manager.py`
7. `docs/superpowers/plans/2026-08-25-phase-g2-github-vps-release-delivery.md`
8. `docs/superpowers/specs/2026-08-25-phase-g2-github-vps-release-delivery-design.md`
9. `python/tests/test_g2_delivery_workflows.py`
10. `python/tests/test_g2_release_bundle.py`
11. `python/tests/test_g2_release_manager.py`

The audit therefore found no modifications to any sealed production file implementing:

- strategy/setup/scoring logic;
- risk engine;
- provider behavior;
- observer/storage schema or migrations;
- paper/live execution logic;
- ledger/accounting/checkpoint/evaluation logic;
- registry/promotion authority;
- transaction construction/signing/submission;
- live-mode enablement.

The G2 Python release modules use standard-library release/deployment mechanics and do not import Shreks strategy, promotion, live, signing, or execution authority. The workflows/scripts invoke build/test/package/release/SSH/release-manager operations only. Existing G1C systemd unit source files are release inputs; G2 did not modify them.

No wallet/private signing key material was committed. The only private-key-shaped authority introduced by G2 is a reference to a deployment SSH secret stored in the GitHub `production-paper` environment; it is explicitly transport-only and distinct from any trading/signing credential.

Protected `/etc/shreks` and `/var/lib/shreks` paths are referenced only in the runbook/tests as protected state that deployment must preserve, not as workflow mutation targets.

## 8. Complete G2 commit chronology

The 13 commits from sealed G1C through frozen G2 behavior are:

1. `dc805fea70f8364f9b595b138c1ab4c2d1808237` — G2 design and implementation plan.
2. `56ec6187cfcbde6c6655fc27ce081296e66a40ec` — Task 1 RED.
3. `fcb9a452cbd0e97cf201dff2112db610480d3352` — Task 1 first implementation.
4. `327112b800b955c33fc162acfb902cc35c14b70e` — Task 1 fixture correction / final GREEN.
5. `a98362f3591f5c35743b24c91cd5baac0705018b` — Task 2 RED.
6. `b4376ab20505b1db3a425904bfd4f2c4a3ca8e5d` — Task 2 first implementation.
7. `a7a4a7e2e00873cd4a2003f37ef9645533ec6ff9` — Task 2 test correction/hardening RED.
8. `c95a6a8ba16e61f535a8bbc2df7fa865965d3997` — Task 2 corrected final-path/permissions/cleanup RED contract.
9. `4aae09207b594dbd6e7e91e0407998391080b4a6` — Task 2 final GREEN.
10. `ff99227dc271848f154f9f9a720bd3c9f1cd909b` — Task 3 RED.
11. `055be3658b60d116d7a19e4132a6921669621624` — Task 3 GREEN.
12. `83e01d8733f70c05ecc156f26e8f47b507ae2ce9` — Task 4 RED.
13. `2aa640196266109119a7c21dde27727fc33d9beb` — Task 4 GREEN / frozen G2 behavior.

## 9. What G2 proves — and what it does not

G2 proves in repository tests/CI that Shreks has a fail-closed software/control path for:

- exact sealed source provenance;
- immutable release identity;
- allowlisted reproducible packaging;
- cryptographic bundle verification;
- root-owned release installation;
- atomic release activation;
- health-gated rollback;
- deployment-only SSH transport with pinned host keys;
- preservation of protected runtime configuration and durable state by the deployment path.

G2 does **not** claim that an actual production VPS was bootstrapped or reached by this conversation. Real-host bootstrap and deployment require the dedicated VPS plus correctly configured `production-paper` environment/host transport credentials. That operational execution remains external to this repository-only proof.

G2 also does not prove profitability, positive expectancy, production market-data quality, live-capital readiness, wallet-signing safety, or recovery/monitoring/emergency-control completeness. Those remain governed by later proof and Phase G gates.

## 10. Seal rule

This verification record is the only permitted file change after frozen behavior SHA `2aa640196266109119a7c21dde27727fc33d9beb`.

The seal is valid only if all of the following hold after this commit:

1. behavior -> seal compare is exactly one commit;
2. the only changed file is this verification record;
3. exact-seal CI is GREEN for Python, Rust/workspace, and repository safety;
4. Python remains at the frozen behavior test count (`2308`);
5. PR #43 remains draft and unmerged;
6. live trading remains disabled.

The exact seal SHA and exact-seal CI run are recorded in PR #43 after CI completes, because those identifiers do not exist until this one-file seal commit itself has been created and tested.
