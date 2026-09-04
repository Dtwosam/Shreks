# FL9 Installed Proof-Tool Cache Compatibility — Plan

**Date:** 2026-09-04

1. Reproduce the physical-host failure as a Python regression using a staged sealed package plus an interpreter-style `__pycache__/__init__.cpython-312.pyc`.
2. Prove RED on the current sealed implementation.
3. Refactor proof-tool directory authentication so the public pristine-package verifier remains exact while the installed materializer has a separate narrow cache-aware path.
4. Accept only a real non-symlink `__pycache__` directory containing regular non-symlink `__init__.*.pyc` files.
5. Preserve exact expected sealed member names, manifest identity, source SHA, platform, sizes, and binary SHA-256 checks.
6. Add rejection coverage for an unexpected cache member.
7. Run focused/full CI including repository safety, Python, Rust, and native ARM64 release build.
8. Inspect the diff for trading/runtime/deployment authority drift.
9. Merge only after GREEN evidence.
10. Seal/release/deploy via the existing immutable release and manual `production-paper` deployment path.
11. Re-run the genuine #206 proof workspace command on the VPS and preserve the exact success/fail-closed evidence.

No threshold change, evidence fabrication, runtime-state reset, or LIVE enablement is permitted.
