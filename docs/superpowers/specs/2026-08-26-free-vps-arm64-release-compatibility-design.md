# Free VPS ARM64 Release Compatibility Design

## Goal

Make the sealed G2 release/deployment integrity path safely support the ARM64 Linux platform required by Oracle Cloud Always Free Ampere A1, while preserving the existing x86_64 release behavior and all sealed trading/PAPER behavior.

This is a non-numbered operational compatibility slice stacked on the sealed Phase-G host-acceptance harness. It is not a strategy, risk, execution, profitability, or live-money phase.

## Problem

The current sealed release builder and release-manifest codec accept only `x86_64-unknown-linux-gnu`. Oracle's useful Always Free compute shape is ARM-based. Copying a separately built ARM binary onto the host would bypass the G2 content-addressed release manifest and is therefore not acceptable.

The existing manual sealed-release workflow also runs only on an x86_64 GitHub runner. Merely teaching the bundle codec about ARM would therefore prove compatibility without giving the operator a sealed path to create the ARM release that the Oracle host actually needs.

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

A release bundle whose manifest platform does not match the installation host is rejected before its payload is committed as a stored release. Stored releases are also rechecked against the host before reuse or activation. Unknown host architectures fail closed.

### CI proof

The normal x86_64 CI remains unchanged for repository safety, Rust tests and Python tests.

A new `ARM64 release build` job runs on GitHub's standard `ubuntu-24.04-arm` hosted runner, installs stable Rust and Python 3.12, and runs the same release builder with `PLATFORM=aarch64-unknown-linux-gnu`. The job verifies the resulting manifest/archive through the existing release-bundle verifier and checks that the manifest records the ARM64 platform.

Because the repository is public, this standard GitHub-hosted runner is available without adding a paid build service.

### Sealed release production

The existing manual sealed-release workflow gains an exact `platform` choice limited to the same two supported triples. x86_64 remains the default. The workflow selects an ARM GitHub runner only for the ARM64 choice, exports the selected `PLATFORM` into the unchanged release builder, reruns the full sealed test suite on that native runner, and then creates the same immutable content-addressed GitHub Release.

This preserves the existing release-tag and deployment contract while making it possible to create the one native ARM64 sealed release needed by the Oracle host. A single source SHA still maps to one immutable release tag; the operator therefore chooses the target platform when producing that release rather than publishing multiple architectures under the same tag.

### Test portability

Historical G2 release-manager tests intentionally use x86_64 fixture manifests. A narrowly scoped pytest fixture pins only that legacy test module to its declared fixture platform so the full suite can run on both x86_64 and ARM64 runners. The new compatibility tests independently exercise real host mapping, unsupported architectures and cross-platform rejection.

### Authority boundary

This slice may modify only release packaging/verification, release/CI workflows, tests and documentation. It must not modify provider adapters, strategy/setup/scoring, risk thresholds, execution/accounting, registry/promotion, wallet/signing/submission, or live-enable behavior.

`LIVE TRADING: DISABLED`.
