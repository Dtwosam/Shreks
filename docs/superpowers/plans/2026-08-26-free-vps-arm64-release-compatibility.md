# Free VPS ARM64 Release Compatibility Implementation Plan

**Goal:** Extend the sealed G2 release integrity path to build, verify, publish, and install exact ARM64 Linux releases for Oracle Always Free Ampere A1 without changing trading behavior.

**Base:** sealed Phase-G host acceptance `fed57c3a5d8d13ccd08306c41d4d915498b39b42`.

## Task 1 — RED platform contract

Add tests proving:
- release manifests accept exactly x86_64 and aarch64 Linux GNU triples;
- arbitrary platforms remain rejected;
- release manager rejects a manifest whose platform does not match the host;
- unknown host architectures fail closed;
- build script requires requested platform to equal the native Rust host triple;
- CI contains a standard `ubuntu-24.04-arm` ARM release-build job;
- the manual sealed-release workflow can select the exact native target platform and ARM runner.

Keep historical G2 release-manager fixtures architecture-independent so the full Python suite can execute on both x86_64 and ARM64 runners.

Run CI and record intended failures only.

## Task 2 — GREEN dual-platform release path

Implement:
- exact two-platform release-manifest allowlist;
- backwards-compatible x86 default plus explicit `PLATFORM` build input;
- native Rust host/platform equality gate;
- exact host architecture mapping and install-time manifest platform gate;
- stored-release host-platform revalidation before reuse/activation;
- ARM64 release-build CI on GitHub's standard ARM runner;
- manual sealed-release platform choice with native x86_64/ARM64 runner selection, preserving the immutable release tag and existing deployment contract.

Run full CI including the ARM release build.

## Task 3 — audit and seal

Audit the compatibility diff against the host-acceptance seal. No trading/runtime authority drift is permitted. Freeze all-green behavior, replace this plan with a verification record in one docs-only seal commit, prove 1-commit/1-file seal geometry, rerun exact-seal CI including ARM64 release build, and keep the stacked PR draft/open/unmerged.

**LIVE TRADING: DISABLED.**
