# FL9 Learned-vs-Baseline Population Parity — Implementation Plan

**Date:** 2026-09-04
**Base:** `07b8639e6cbff9330aefb3f8480485eba6498068`

1. Commit RED contract tests for exact identity/posture parity.
2. Open draft PR and record missing-module RED.
3. Implement a pure comparator over sealed learned wire + baseline batch types.
4. Add storage exports only.
5. Run repository safety, Python, Rust, ARM64.
6. Guarded squash merge exact GREEN head.

No provider/database/PAPER/risk/promotion/LIVE changes.
