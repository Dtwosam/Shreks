# Phase G2 GitHub-to-VPS Release Delivery — Design

**Base:** sealed G1C `517bc81efa6d5cb88c3a471bb7683b5c1cc330ec`

## Goal

Establish a traceable GitHub-controlled delivery path from one sealed Shreks source SHA to one immutable Linux release on the dedicated VPS, with verifiable artifacts, atomic activation, explicit rollback points, and no trading-wallet material in GitHub.

G2 is delivery mechanics only. It does not enable live trading, create wallet/signing authority, alter proof/promotion rules, change strategy/scoring/risk behavior, add provider credentials, or replace the G1C systemd runtime model.

**LIVE TRADING: DISABLED.**

## Canonical requirements

G2 implements the Build Order flow:

`code change -> GitHub PR -> tests GREEN -> approved/sealed release -> deploy to VPS -> VPS runs 24/7`

The deployment path must preserve all of these properties:

- deployed versions are traceable to exact source/release versions;
- release history and rollback points remain available;
- GitHub can trigger deployment without holding the trading wallet key;
- deployment cannot bypass proof, mode, risk, or live-enable gates.

The Master Source of Truth continues to make GitHub the source/test/release/deployment control plane, while the VPS remains the continuously running host.

## Approaches considered

### A. Build source on the VPS

Rejected. Copying source to the VPS and compiling/installing there makes the deployed result depend on mutable host toolchains and network state, weakens release provenance, and expands the production host's build surface.

### B. Introduce Docker images and a registry

Rejected for G2. Containers could provide a strong artifact boundary, but G1C already standardized the first host on systemd and release-coupled filesystem paths. Adding a registry/container runtime now is extra infrastructure without a current proof-driven need.

### C. GitHub-built immutable release bundle + atomic host activation

Chosen. GitHub builds and records one release bundle for one sealed source SHA. The host verifies the bundle, stages it under `/opt/shreks/releases/<source-sha>`, and atomically repoints `/opt/shreks/current`. Existing systemd units continue to execute through `/opt/shreks/current`.

This gives exact provenance and rollback while preserving the G1C runtime architecture.

## Release identity and history

Every production-shaped release is identified by the full 40-character Git commit SHA.

GitHub Release tag format:

`shreks-<40-character-source-sha>`

A release contains:

- `shreks-release-<source-sha>.tar.gz`;
- `shreks-release-<source-sha>.tar.gz.sha256`;
- `RELEASE_MANIFEST.json`.

The manifest schema is `g2-release-manifest-v1` and contains exactly:

- `schema_version`;
- `source_sha`;
- `platform` (`x86_64-unknown-linux-gnu` for the first host);
- sorted `files`, each with repository-relative release path, byte size, and SHA-256 digest.

The manifest contains no timestamp, host name, secret, wallet, provider credential, strategy override, risk override, or mode override. Release identity comes from source SHA and artifact hashes.

The release workflow refuses malformed/non-full SHAs and verifies that checkout `HEAD` exactly equals the requested source SHA. It also reruns repository safety, Rust tests, Python tests, and release-bundle verification on that exact checkout before recording the GitHub Release.

A release source must be an explicit seal commit: the release workflow verifies that the source commit subject contains `seal`. This is a mechanical guard against accidentally releasing an intermediate RED/GREEN checkpoint; it does not replace code review or proof gates.

## Bundle contents

The release bundle carries only runtime code/artifacts and deployment metadata needed by G1/G1B/G1C:

- `target/release/shreks-observe`;
- `target/release/shreks-paper-evidence`;
- one built `shreks_brain` wheel under `wheelhouse/`;
- `deploy/systemd/shreks-observe.service`;
- `deploy/systemd/shreks-paper-evidence.service`;
- `deploy/systemd/shreks-paper-campaign.service`;
- `deploy/systemd/shreks.target`;
- `RELEASE_MANIFEST.json`.

The Python project currently declares no mandatory runtime dependencies, so the host installs the local Shreks wheel with `--no-index --no-deps`. Research/learning extras are not production runtime dependencies for G1C and are not silently pulled from the network.

The release packager uses only the Python standard library. It sorts manifest entries, rejects unexpected paths, computes every file hash from bytes, and writes the archive with deterministic metadata ordering. Artifact hashes, not a claim of cross-toolchain byte-for-byte rebuild reproducibility, are the authoritative deployed-binary identity.

## GitHub release workflow

Add `.github/workflows/release.yml`.

Triggers:

- `workflow_dispatch` with required `source_sha`;
- optional tag-push compatibility for `shreks-*` only after the workflow exists on the relevant release lineage.

The manual path is authoritative for the first deployment.

Permissions are minimized:

- `contents: write` only because the workflow must create a GitHub Release/tag and upload assets;
- no environment/provider/wallet secrets are consumed.

The workflow:

1. validates the full SHA syntax;
2. checks out that exact SHA;
3. proves `git rev-parse HEAD` equals the input;
4. verifies the commit subject contains `seal`;
5. runs the same repository secret-assignment guard as CI;
6. runs `cargo test --workspace`;
7. installs `./python[dev]` and runs the complete Python suite;
8. builds `shreks-observe` and `shreks-paper-evidence` in release mode;
9. builds a local Shreks Python wheel;
10. stages the allowlisted bundle contents;
11. creates and verifies `RELEASE_MANIFEST.json` and the tarball checksum;
12. creates GitHub Release `shreks-<source_sha>` only after all prior steps succeed.

Existing tags/releases are immutable from this workflow: if the tag already exists, the job fails instead of overwriting assets.

## Deploy workflow and secret boundary

Add `.github/workflows/deploy.yml`.

Trigger:

- `workflow_dispatch` with required `release_tag` matching `shreks-<40-char-sha>`.

Permissions:

- `contents: read` only.

The deployment job uses GitHub Environment `production-paper` so repository/environment policy can later add reviewers or branch restrictions without changing the deployment protocol.

Allowed GitHub deployment secrets are transport-only:

- `SHREKS_DEPLOY_HOST`;
- `SHREKS_DEPLOY_PORT`;
- `SHREKS_DEPLOY_USER`;
- `SHREKS_DEPLOY_SSH_KEY`;
- `SHREKS_DEPLOY_KNOWN_HOSTS`.

No secret name or workflow step may reference wallet, seed phrase, signing key, live private key, provider API key, or trading credential.

`SHREKS_DEPLOY_KNOWN_HOSTS` is required. The workflow does not use unauthenticated `ssh-keyscan` as the trust root.

The deploy workflow downloads the exact three assets from the named GitHub Release, verifies the checksum and manifest locally, copies them to a unique remote staging directory, and invokes one preinstalled root-owned host release manager through narrowly scoped `sudo`.

GitHub never uploads `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, wallet material, provider credentials, SQLite state, E11 evidence, or checkpoints.

## One-time host bootstrap

G2 adds a root-owned host release manager and a bootstrap runbook.

One time, an operator installs `deploy/release/shreks-release-manager` as:

`/usr/local/sbin/shreks-release-manager`

with root ownership and non-writable permissions for the deploy account.

The dedicated deploy account may receive a narrowly scoped sudo rule permitting only that root-owned command. The deployment SSH key is therefore a delivery credential, not a trading credential.

The bootstrap also establishes:

- `/opt/shreks/releases` owned/protected for releases;
- existing `/var/lib/shreks` durable state;
- existing `/etc/shreks` protected runtime configuration;
- systemd unit destination `/etc/systemd/system`.

The bootstrap does not create or populate wallet/private signing credentials.

## Host release-manager contract

The release manager is a Python 3.12+ standard-library CLI with production paths fixed by default and importable pure functions for tests.

### Verification

Before any activation it:

- verifies the tarball SHA-256 sidecar;
- parses the exact manifest schema;
- requires full source SHA and supported platform;
- rejects absolute paths, `..` traversal, symlinks, device files, and unmanifested archive members;
- verifies every extracted file size and SHA-256;
- requires the exact G2 allowlist of runtime files;
- refuses a release directory that already exists with different content.

### Staging

It extracts into a temporary directory under `/opt/shreks/releases`, never over the active release.

Before activation it:

- creates `<release>/.venv` with system Python;
- installs the bundled Shreks wheel with `pip --no-index --no-deps`;
- makes Rust runtime binaries executable;
- leaves `/etc/shreks` and `/var/lib/shreks` untouched;
- preserves the manifest inside the release root for later provenance checks.

### Atomic activation

Activation sequence:

1. record the current `/opt/shreks/current` target if present;
2. stop `shreks.target`;
3. install the release's systemd units to `/etc/systemd/system`;
4. atomically replace `/opt/shreks/current` using a temporary symlink + `os.replace`;
5. run `systemctl daemon-reload`;
6. start `shreks.target`;
7. require `systemctl is-active --quiet shreks.target` to succeed.

If any post-switch step fails and a prior release existed, the manager restores the previous symlink, restores that release's systemd units, reloads systemd, restarts `shreks.target`, and exits nonzero. If no prior release exists, it leaves the target stopped and exits nonzero.

A failed deployment therefore cannot silently claim success or delete durable state.

## Rollback

Rollback uses the same verified release path.

Any prior GitHub Release remains a durable rollback point. Re-running the deploy workflow with an earlier `shreks-<sha>` tag re-verifies and activates that release.

The host also retains staged verified release directories under `/opt/shreks/releases/<sha>`. The release manager exposes an explicit `activate-existing <sha>` operation for emergency host-local rollback, subject to the same manifest verification and systemd health check.

Rollback never replaces `/var/lib/shreks`, `/etc/shreks/shreks.env`, `/etc/shreks/paper-campaign.json`, E11 evidence, or checkpoints.

## Gate preservation

G2 has deployment authority only.

It must not:

- write `LIVE TRADING: ENABLED` or any live-mode value;
- modify registry promotion state;
- modify strategy/scoring/risk parameters;
- construct, sign, or submit transactions;
- copy wallet/private keys;
- overwrite protected runtime configuration or durable trading/evidence state.

The deployed application still enforces the existing proof/mode/risk/live-enable gates. Deployment merely changes the version of code reached through `/opt/shreks/current` and restarts supervised services.

## Observability and provenance

The active host exposes provenance without secrets:

- `/opt/shreks/current/RELEASE_MANIFEST.json` identifies exact source SHA and file hashes;
- `readlink -f /opt/shreks/current` identifies the active release directory;
- GitHub Release history identifies the corresponding immutable release assets;
- systemd remains the process supervisor.

A later monitoring phase may surface the active source SHA in the dashboard, but G2 does not build dashboard/telemetry infrastructure.

## Tests

G2 uses TDD and adds no third-party test dependency.

Python tests cover:

- exact release manifest schema and canonical encoding;
- SHA/size verification;
- full-SHA/tag validation;
- archive path traversal/symlink rejection;
- missing/unexpected member rejection;
- atomic current-symlink replacement;
- successful activation with a fake systemctl runner;
- failed activation restores previous release;
- durable `/etc/shreks` and `/var/lib/shreks` paths are never deletion/replacement targets;
- existing release mismatch fails closed.

Static workflow/deployment tests cover:

- release workflow uses exact SHA checkout and reruns full tests;
- release workflow alone has `contents: write`;
- deploy workflow has `contents: read` and `production-paper` environment;
- deploy workflow requires pinned known-hosts input and does not use `ssh-keyscan`;
- only deploy-transport secret names are present;
- no wallet/provider/live-mode secret or value is embedded;
- deploy workflow downloads an existing GitHub Release and invokes the root-owned manager;
- systemd runtime paths remain `/opt/shreks/current`.

## Seal discipline

After implementation:

1. freeze a behavior SHA with full CI GREEN;
2. compare sealed G1C -> G2 and inspect every changed file;
3. verify no strategy/scoring/risk/execution/accounting/checkpoint/evaluation drift and no wallet/live authority;
4. replace the G2 implementation plan with the final verification record as the only post-behavior change;
5. prove behavior -> seal is exactly one commit, zero behind, one file;
6. run fresh exact-seal CI;
7. update the stacked draft PR with behavior SHA, seal SHA, CI IDs, audit result, and `LIVE TRADING: DISABLED`.

## Deferred after G2

- actual provisioning/purchase of the VPS if not already available;
- production-paper GitHub Environment policy configuration and deployment secret population on the GitHub account;
- G3 24/7 supervision/restart verification on the real host;
- G4 telemetry;
- G5 dashboard;
- G6 alerts;
- G7 emergency operator controls;
- G8 backup/restore proof;
- live-money enablement.
