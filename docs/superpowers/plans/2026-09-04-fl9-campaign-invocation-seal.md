# FL9 Campaign Invocation Seal — Implementation Plan

**Date:** 2026-09-04
**Base:** `397aa8a2273d59313f8c6f3fd40df5733487de95` (#194)

1. RED invocation-seal contract.
2. Capture exact request-file bytes and logical fingerprint.
3. Capture six physical source identities.
4. Include SQLite database + optional WAL; exclude SHM.
5. Run sealed #194 request runner.
6. Re-capture all sources.
7. Fail closed and delete unsealed campaign on any source change.
8. Strictly read back #193 campaign and match returned fingerprint.
9. Build canonical authenticated source snapshot.
10. Build canonical authenticated invocation manifest.
11. Stage three-file seal privately.
12. Strictly read staged seal.
13. Atomically publish seal.
14. Export public API.
15. Update durable docs.
16. Run exact-head four-gate CI.
17. Guarded merge.
18. Next: one-argument console launcher.
19. Then: execute real non-fixture campaign evidence.

FL9 superiority remains EVIDENCE PENDING. LIVE remains disabled.
