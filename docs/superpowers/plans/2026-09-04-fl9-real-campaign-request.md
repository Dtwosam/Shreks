# FL9 Canonical Real Campaign Request — Implementation Plan

**Date:** 2026-09-04
**Base:** `d2150420440c642fded88e51de4a228ea91e73dc` (#193)

1. RED canonical request codec + file runner.
2. Define request dataclass and fingerprint.
3. Use fixed tagged dataclass/enum registry.
4. Encode finite floats as exact hex tags.
5. Reject raw floats/arrays, unknown tags, noncanonical JSON, and tampering.
6. Lock one starting capital across PAPER, risk context, and evaluation.
7. Resolve paths relative to request file.
8. Read sealed FL8.1 Parquet + comparison catalog.
9. Build fresh common PAPER ledger.
10. Delegate exactly to #193 artifact writer.
11. Lock no-network/no-superiority/no-LIVE boundary.
12. Update durable docs.
13. Run exact-head four-gate CI.
14. Guarded merge.
15. Next: one-argument console launcher, then real non-fixture run.

FL9 superiority remains EVIDENCE PENDING. LIVE remains disabled.
