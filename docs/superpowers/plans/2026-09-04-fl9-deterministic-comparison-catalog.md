# FL9 Deterministic Comparison Catalog — Implementation Plan

**Date:** 2026-09-04
**Base:** `d57eb0f22b84bff88b03f185d48fc7adbf208499`

1. Add Rust and Python RED tests for catalog API/decoder/binary.
2. Open draft PR and capture exact RED.
3. Implement Rust catalog schema, explicit reference policies, 8-candidate builder,
   canonical encoder/decoder, and fingerprint.
4. Export Rust API from shreks-storage.
5. Add no-argument catalog stdout binary.
6. Generate one shared canonical golden fixture.
7. Add Python immutable catalog model + strict decoder using existing manifest decoder.
8. Run full four-gate CI.
9. Freeze exact GREEN head and guarded squash merge.

No tuning, profitability selection, provider I/O, PAPER execution, superiority,
promotion, signing, submission, or LIVE authority.
