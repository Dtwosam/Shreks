# Free VPS ARM64 Release Compatibility Design

## Goal

Make the sealed G2 release/deployment integrity path safely support the ARM64 Linux platform required by Oracle Cloud Always Free Ampere A1, while preserving the existing x86_64 release behavior and all sealed trading/PAPER behavior.

This is a non-numbered operational compatibility slice stacked on the sealed Phase-G host-acceptance harness. It is not a strategy, risk, execution, profitability, or live-money phase.

## Problem

The current sealed release builder and release-manifest codec accept only `x86_64-unknown-linux-gnu`. Oracle's useful Always Free compute shape is ARM-based. Copying a separately built ARM binary onto the host would bypass the G2 content-addressed release manifest and is therefore not acceptable.

## Design

### Supported platforms

The release format supports exactly two Linux GNU platforms:

- `x86_64-unknown-linux-gnu`
- `aarch64-unknown-linux-gnu`

No wildcard or arbitrary platform string is allowed.

### Build correctness

`deploy/release/build_release.sh` keeps x86_64 as the backwards-compatible default but accepts `PLATFORM` from the environment. Before compiling, it reads `rustc -vV` and requires the Rust host triple to equal the requested platform. Builds remain native; this slice does not introduce cross-compilation toolchains.

The resulting manifest records the exact requested/native platform.

### Install correctness

`release_manager.py` derives the current Linux host release platform from `os.uname().machine` using an exact map:

- `x86_64` -> `x86_64-unknown-linux-gnu`
- `aarch64` -> `aarch64-unknown-linux-gnu`

A release bundle whose manifest platform does not match the installation host is rejected before its payload is committed as a stored release. Unknown host architectures fail closed.

### CI proof

The normal x86_64 CI remains unchanged for repository safety, Rust tests and Python tests.

A new `ARM64 release build` job runs on GitHub's standard `ubuntu-24.04-arm` hosted runner, installs stable Rust and Python 3.12, and runs the same release builder with `PLATFORM=aarch64-unknown-linux-gnu`. The job verifies the resulting manifest/archive through the existing release-bundle verifier.

Because the repository is public, this standard GitHub-hosted runner is available without adding a paid build service.

### Authority boundary

This slice may modify only release packaging/verification, CI, tests and documentation. It must not modify provider adapters, strategy/setup/scoring, risk thresholds, execution/accounting, registry/promotion, wallet/signing/submission, or live-enable behavior.

`LIVE TRADING: DISABLED`.
