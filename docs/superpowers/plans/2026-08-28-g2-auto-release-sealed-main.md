# G2 Sealed-Main Automatic Release — Implementation Plan

**Base:** `f55b4e97b9d17eb6a8f611ca47e9f7f13833831b`

## Task 1 — Pin the workflow authority contract (RED)

Add a new Python workflow-contract test requiring:

- `release.yml` retains `workflow_dispatch`;
- `release.yml` also uses `workflow_run` for `CI`, completed, `main`;
- auto path requires upstream conclusion `success`;
- auto path derives source SHA from `github.event.workflow_run.head_sha`;
- auto path fixes platform to `aarch64-unknown-linux-gnu` and selects the ARM64 runner;
- existing exact SHA, seal, full test, bundle verification, duplicate-tag, and `contents: write` guards remain;
- release workflow consumes no secrets/SSH/production environment;
- deploy workflow remains manual-only and does not accept `workflow_run`, `workflow_call`, `release`, or `push` triggers.

Commit and verify RED in CI before production workflow edits.

## Task 2 — Implement automatic sealed-main release (GREEN)

Update `.github/workflows/release.yml` only as needed to support both trigger modes.

Requirements:

- preserve the existing manual inputs;
- add `workflow_run` trigger scoped to successful completed `CI` on `main`;
- resolve `SOURCE_SHA`, `PLATFORM`, and runner deterministically from the event type;
- checkout the resolved exact SHA, not the workflow definition commit;
- keep all existing tests and release-bundle verification;
- preserve immutable duplicate-tag rejection;
- do not reference deployment secrets/environment or invoke deploy.

Run full CI and fix only contract/implementation defects.

## Task 3 — Update release operations documentation

Update `deploy/release/README.md` to distinguish:

- automatic immutable release creation after successful sealed-main CI;
- retained manual release dispatch for explicit platform/rollback-compatible operations;
- manual-only production deployment.

Add a static documentation test if needed to prevent authority drift.

## Task 4 — Final audit and seal

Before merge:

- full CI GREEN: repository safety, Rust, Python, ARM64 bundle;
- compare base -> head and verify changes are limited to release workflow/tests/docs;
- verify no deploy workflow authority widening;
- verify no provider/strategy/risk/PAPER/wallet/signing/submission/LIVE changes.

Merge with a `seal:` squash commit. Then verify:

1. exact merged-main CI succeeds;
2. that CI automatically creates `shreks-<merged-sha>`;
3. the release contains exactly the verified historical VPS-compatible payload set.

Do not automatically deploy. FL2 remains blocked until the new release is manually deployed and the physical-host FL1.5 acceptance evidence passes.

**LIVE TRADING: DISABLED.**
