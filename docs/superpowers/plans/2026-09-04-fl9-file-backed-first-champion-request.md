# FL9 File-Backed First Champion Request — Implementation Plan

**Date:** 2026-09-04
**Base:** `e6d6bdfc94a1bb6df5206d752eb878ce1ef585b4` (#204)

1. Add an intentional RED contract for the absent file-backed request API.
2. Define canonical request schema v1 with exact source, policy, selection, and evidence-floor fields.
3. Preserve integer numeric scalars and encode Python floats with `float.hex()` tags.
4. Recompute the request fingerprint on construction and decode.
5. Reject non-canonical JSON, duplicate keys, raw JSON floats, unknown/missing fields, and non-TEST evaluation policy.
6. Resolve relative paths only against the request-file directory.
7. Refuse any pre-existing result destination.
8. Capture stable SHA-256 for feature JSONL, database, optional WAL, and context corpus.
9. Exclude volatile SQLite SHM from durable content identity.
10. Decode context bytes only when their SHA equals the captured context-file SHA.
11. Build the exact #201 logical FL8.1 bundle from JSONL + read-only SQLite.
12. Require the runtime bundle's feature source SHA to equal the captured JSONL SHA.
13. Invoke #203 with the exact #204 contexts and request policies.
14. Require every TEST report to carry the exact context-corpus logical fingerprint.
15. Rehash every mutable source after the complete champion build.
16. Require request bytes to remain identical.
17. Stage request, context corpus, champion, five TEST reports, and manifest in a private temporary directory.
18. Bind source hashes, bundle/champion/context fingerprints, validation/report fingerprints, counts, and file hashes into the manifest.
19. Strict-read the staged artifact before publication.
20. Atomically rename only after strict reopen succeeds.
21. Delete staging on every failure and never overwrite a destination.
22. Strict reader must reject unknown/missing files, file tampering, cross-chain report substitution, or manifest tampering.
23. Keep provider/network, PAPER execution, automatic selection, signing/submission, and LIVE authority absent.
24. Run exact-head Python/Rust/repository-safety/ARM64 CI.
25. Guarded squash merge only on exact 4/4 GREEN.
26. Run merged-main four-gate CI and seal.
27. Next: host-side PAPER evidence orchestration under the existing `shreks` service identity.

TDD RED: `5418c1f2c1da5b58c050a4d0a423179fff31d7e3`.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
