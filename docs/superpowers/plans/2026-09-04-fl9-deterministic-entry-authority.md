# FL9 Deterministic Entry Authority — Implementation Plan

**Date:** 2026-09-04
**Base:** `5d0edec562c7699ab9abfc742eab16d0a9401136` (#185)

1. RED Rust + Python contracts.
2. Add strict request/result wire models.
3. Call sealed Rust `ExecutionEconomics::assess`; do not reimplement FL3.
4. Add fingerprinted offline CLI.
5. Add Python subprocess adapter with pre-launch FL8.1 price provenance checks.
6. Cross-check result market/quantity/cost attribution.
7. Represent FL3 max-below-decision as absent BUY authority.
8. Permit absent candidate BUY authority in comparison/bundle transport.
9. Prove actual binary integration.
10. Update durable docs.
11. Run exact-head repository safety, Python, Rust, and ARM64 gates.
12. Guarded merge, then begin real evidence hydration.

FL9 superiority remains EVIDENCE PENDING. LIVE remains disabled.
