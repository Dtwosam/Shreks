# G2 Linux Virtualenv Deployment Hotfix — Verification Record

**Date:** 2026-08-27  
**Base production seal:** `fee696abbc169354ec5bffa430f18286d8f29328`  
**PR:** #55  
**Frozen behavior SHA:** `8537b78f9fd874d5b29ab2968822e8bb165d00b9`

## Production finding

The verified ARM64 release `shreks-fee696abbc169354ec5bffa430f18286d8f29328` reached the dedicated VPS through the pinned GitHub-to-host deployment path. SSH authentication, strict host-key verification, SCP transfer, release-manager invocation, release archive verification, release-local Python virtualenv construction, and wheel installation all succeeded.

The host release manager then exited with status 1 immediately after pip reported `Successfully installed shreks-brain-0.1.0`, before release activation completed.

## Root cause

G2 constructs the release-local virtualenv with:

```text
python3 -m venv --copies <release>/.venv
```

On Ubuntu Linux, `venv --copies` still creates the standard internal compatibility symlink:

```text
.venv/lib64 -> lib
```

The G2 stored-release verifier rejected every symlink anywhere inside `.venv`. Therefore a normal Linux virtualenv created by the release manager violated the verifier's own post-install invariant.

The failure was reproduced independently on Ubuntu before changing production code.

## RED

Commit: `99a8049368539e1ca1fbb26c145fae5df4e0c244`  
CI run: `33067954690`

A regression test created the standard copied-venv layout with `.venv/lib64 -> lib` and required the runtime virtualenv verifier to accept it. A separate test required an unrelated symlink escaping to `/tmp` to remain rejected.

Python CI failed exactly on the missing behavior:

```text
FAILED test_runtime_venv_accepts_standard_linux_lib64_to_lib_symlink
1 failed, 2615 passed
```

The failure was the existing `ReleaseManagerError: symlinks are not allowed inside stored release virtualenv`.

## GREEN

Implementation commit on the PR branch: `f7f8c11c6ef9cbbb89878897f0e2045b9e1cb0f7`  
Merged behavior SHA: `8537b78f9fd874d5b29ab2968822e8bb165d00b9`  
CI run: `33068110990`

The verifier now permits exactly one Linux virtualenv compatibility link:

```text
.venv/lib64 -> lib
```

and only when `.venv/lib` exists as a real directory and is not itself a symlink. Every other symlink inside the stored release virtualenv remains fail-closed, including the explicit unsafe-symlink regression.

Full PR CI completed successfully:

- Repository safety: GREEN
- Python tests: GREEN
- Rust tests: GREEN
- native ARM64 release build: GREEN

## Scope audit

Behavior changes are limited to:

- `deploy/release/release_manager.py`
- `python/tests/test_g2_release_manager_linux_venv.py`

No strategy, scoring, safety, risk, paper-fill economics, candidate discovery, market data, chain data, accounting, evaluation, wallet, signing, transaction submission, provider credentials, runtime secrets, or live-capital behavior changed.

The deploy account remains unprivileged except for the exact release-manager sudo command shape. Strict pinned host-key checking and the dedicated transport-only SSH key remain unchanged.

**LIVE TRADING remains disabled.**

## Seal rule

This verification record is the only permitted post-behavior change. The resulting seal commit must pass fresh full repository CI before a new native ARM64 release is built and deployed to the VPS.