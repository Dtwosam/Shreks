# G2 Sealed-Main Automatic Release — Design

**Base:** `f55b4e97b9d17eb6a8f611ca47e9f7f13833831b`

## Goal

Remove the manual GitHub Release dispatch bottleneck after the first proven G2 production deployment, while preserving the existing immutable-release and production-deployment trust boundaries.

A successful CI run for a sealed commit on `main` may automatically build and create the immutable GitHub Release for that exact SHA. Deployment to the `production-paper` VPS remains manual and continues to require the existing `Deploy verified Shreks release` workflow and protected environment.

**LIVE TRADING: DISABLED. FL2 remains blocked pending real-host FL1.5 acceptance.**

## Why this is allowed

The sealed G2 design states that the manual release path is authoritative for the first deployment and leaves later release-trigger compatibility open. The first production-paper release/deploy path has already been proven successfully on the real control plane. The security boundary is therefore the exact sealed SHA, successful CI, immutable bundle verification, and immutable release tag—not the human click itself.

This slice automates release creation only. It does not automate production deployment.

## Trigger contract

`release.yml` keeps the existing `workflow_dispatch` interface and adds a `workflow_run` trigger for:

- workflow name exactly `CI`;
- completed runs only;
- branch exactly `main`.

The automatic job runs only when the upstream CI conclusion is `success`.

For automatic runs:

- `SOURCE_SHA` is `github.event.workflow_run.head_sha`;
- `PLATFORM` is fixed to `aarch64-unknown-linux-gnu` for the current production host;
- the job uses the native ARM64 runner;
- the exact SHA is checked out with full history;
- the commit subject must still contain `seal`;
- all repository safety, Rust, Python, bundle-build, bundle-verify, and duplicate-tag checks remain unchanged.

For manual runs, the existing `source_sha` and `platform` inputs remain authoritative.

## Security properties

The automatic path must not:

- consume repository/environment secrets;
- reference the `production-paper` environment;
- use SSH/SCP;
- invoke the deploy workflow;
- create or mutate VPS state;
- bypass the seal-subject check;
- bypass exact-SHA checkout;
- bypass any existing tests or release-bundle verification;
- overwrite an existing release tag;
- add wallet, signing, provider, strategy, risk, transaction-submission, PAPER-authority, or LIVE authority.

The release workflow retains only `contents: write`, solely for immutable GitHub Release/tag creation.

## Duplicate/race behavior

A manual release and an automatic release may race for the same sealed SHA. The existing duplicate-tag guard remains fail-closed: one release may succeed and the other must fail rather than overwrite or mutate the immutable release.

## Deployment boundary

`.github/workflows/deploy.yml` remains manual `workflow_dispatch` only, uses the `production-paper` environment, and consumes only the existing transport secrets. No automatic release event may trigger deployment.

## Acceptance

Repository tests must prove:

1. automatic release is sourced only from successful `CI` on `main`;
2. automatic source identity comes from `workflow_run.head_sha`;
3. automatic platform is native ARM64;
4. manual release inputs remain supported;
5. exact-SHA/seal/full-test/bundle/duplicate guards remain present;
6. release workflow still consumes no secrets or deployment environment;
7. deploy workflow remains manual-only and unchanged in authority.

After exact-head CI is GREEN, merge as a `seal:` commit. The resulting successful `main` CI should itself trigger the automatic immutable release for that new seal. Production deployment still requires the existing manual deploy workflow.
