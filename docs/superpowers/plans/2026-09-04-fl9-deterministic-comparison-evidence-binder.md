# FL9 Deterministic Comparison Evidence Binder — Implementation Plan

**Date:** 2026-09-04
**Base after prerequisite:** `fb197845d734dcce053e5e1940aa06d9c9b85d29`

1. Preserve the intentional binder RED.
2. Merge sealed shared PAPER risk facts from #182.
3. Add shared deterministic risk-environment model.
4. Derive BUY RiskContext from each candidate's current authoritative PAPER ledger.
5. Add strict comparison evidence row and candidate-authority models.
6. Expand the Rust-authenticated catalog to exactly eight campaign specs.
7. Enforce shared quote/regime/risk-environment population in matrix preflight.
8. Delegate only to the sealed candidate matrix.
9. Run full Python/Rust/ARM64/repository-safety CI.
10. Freeze exact GREEN head, guarded squash merge, then begin real immutable evidence-bundle ingestion.

No superiority decision, promotion, signing, submission, or LIVE authority is added in this slice.
