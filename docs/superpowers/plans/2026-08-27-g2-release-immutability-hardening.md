# G2 production release immutability hardening seal

Date: 2026-08-27

## Purpose

This docs-only seal exists so the next production PAPER release is created only after GitHub repository release immutability is enabled.

## Verified behavior being preserved

- PR #57 merged the aggregate regime auxiliary-evidence fix as `d90b17b9916d3af283dea8a261bb2a1af2998da0`.
- The fix was proven RED on the exact VPS failure and GREEN with the full suite.
- The prior production seal was `b1bbb7d75fa29555a8f092307d40efdff3cbf4a2`.
- Seal CI for that source passed repository safety, Python, Rust, and native ARM64 release-build gates.
- ARM64 release workflow run `33078675974` successfully built and verified `b1bbb7d75fa29555a8f092307d40efdff3cbf4a2` on `aarch64-unknown-linux-gnu` and published release `377859938`.

## Supply-chain finding

GitHub's release API reported release `377859938` with `immutable: false` after publication.

The Shreks bundle verifier still validates the archive checksum, canonical manifest, exact payload set, embedded/external manifest agreement, payload sizes, and payload SHA-256 digests. However, those checks are not a substitute for repository-level release immutability because a mutable release writer could theoretically replace the archive, checksum sidecar, and manifest together.

Therefore release `377859938` / tag `shreks-b1bbb7d75fa29555a8f092307d40efdff3cbf4a2` is not approved for production deployment.

## Required production release condition

Before creating the release from this seal:

1. Enable GitHub repository release immutability.
2. Create a fresh ARM64 release from this exact seal SHA.
3. Verify the new GitHub release object reports `immutable: true`.
4. Verify the release target is this exact seal SHA and exactly the expected three verified release assets are present.
5. Only then dispatch the production PAPER deployment workflow for that new release tag.

## Scope

This commit is documentation only. It changes no trading logic, strategy thresholds, risk policy, observer behavior, PAPER economics, runtime secrets, systemd behavior, or LIVE authority.

LIVE remains disabled.
