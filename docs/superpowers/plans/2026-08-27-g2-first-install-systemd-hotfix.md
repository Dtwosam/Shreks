# G2 First-Install systemd Deployment Hotfix — Verification Record

**Date:** 2026-08-27  
**Base production seal:** `502897a9c5f54979da6d2906013dc14d33428e5a`  
**PR:** #56  
**Frozen behavior SHA:** `fbed6835f7d169106cc6080fdf423cf5e90fa0d4`

## Production finding

The verified ARM64 release `shreks-502897a9c5f54979da6d2906013dc14d33428e5a` reached the dedicated VPS through the pinned GitHub-to-host deployment path. Exact tag validation, released-verifier checkout, exact release-asset download, local bundle verification, SSH authentication, strict host-key verification, SCP transfer, host release-manager invocation, release-local virtualenv construction, and Python wheel installation all succeeded.

Activation then failed on the first-ever host install with:

```text
Failed to stop shreks.target: Unit shreks.target not loaded.
```

The rollback path repeated the same stop because there was no previous active Shreks release.

## Root cause

`activate_release()` unconditionally executed:

```text
systemctl stop shreks.target
```

before installing any Shreks systemd units. On an upgrade this is correct because a prior release exists and may be running. On a brand-new VPS, however, `/opt/shreks/current` is absent and `shreks.target` has never been installed or loaded, so systemd correctly returns a non-zero result and the release manager aborts before unit installation.

The production failure therefore came from applying an upgrade-only pre-stop assumption to the first-install path.

## RED

Commit: `21a675ab3a6ffe79719b08f937e7123ab0f8c766`  
CI run: `33069611891`

A targeted regression test modeled the exact first-install condition:

- no current release;
- no pre-existing Shreks systemd target;
- a command runner that fails if `systemctl stop shreks.target` is attempted.

Against the pre-fix release manager, Python CI failed because first-install activation still issued the stop command. Repository safety and unrelated Rust behavior remained clean.

## GREEN

Implementation commit: `8c39b3fb7af6a20541de7f53cbecf2d8d33b868d`  
Final test-alignment head: `9ce0efb38bdb0591b8fcbc05b2784233d5ad868e`  
Merged behavior SHA: `fbed6835f7d169106cc6080fdf423cf5e90fa0d4`  
Final PR CI run: `33070012382`

The release manager now performs the pre-stop only when `_current_release()` returns an existing managed release:

```text
if previous is not None:
    systemctl stop shreks.target
```

The resulting behavior is:

- **First install:** verify release → install unit files → atomically set `current` → `daemon-reload` → start `shreks.target` → require every managed unit healthy.
- **Upgrade:** verify release → stop the existing `shreks.target` → install new unit files → atomically switch `current` → `daemon-reload` → start → require every managed unit healthy.
- **First-install rollback after a later activation failure:** remove the failed active-release claim and stop the newly loaded target, preserving fail-closed behavior.

The earlier first-install test that explicitly expected the obsolete pre-stop was aligned to the corrected contract. No production behavior beyond the single first-install guard changed.

Fresh final PR CI completed successfully:

- Repository safety: GREEN
- Python tests: GREEN — 2,617 tests
- Rust tests: GREEN
- native ARM64 release build: GREEN

## Scope audit

Behavior changes are limited to:

- `deploy/release/release_manager.py`
- release-manager regression/contract tests under `python/tests/`

No strategy, scoring, safety veto, risk sizing, PAPER fill economics, candidate discovery, market data, chain data, accounting, evaluation, wallet, signing, transaction submission, provider credential, runtime secret, or live-capital behavior changed.

The deployment account remains restricted to the exact release-manager sudo command. Strict pinned host-key verification and the dedicated transport-only SSH key remain unchanged.

**LIVE TRADING remains disabled.**

## Seal rule

This verification record is the only permitted post-behavior change. The resulting docs-only seal commit must pass fresh full repository CI before a new native ARM64 release is built or deployed to the VPS.
