# FL4 Covered Event Population — Implementation Plan

**Date:** 2026-09-05
**Base:** `4d1e90603a654374d5f87c13cbe923d81c59109f`
**Spec:** `docs/superpowers/specs/2026-09-05-fl4-covered-event-population-design.md`

## Task 1 — Population preflight contract

- [ ] Add focused RED tests.
- [ ] Resolve exact coverage session.
- [ ] Reject missing and latest/mutable sessions.
- [ ] Require explicit decision bounds fully inside the selected session.
- [ ] Count canonical FastEvents before writes.
- [ ] Reject zero rows and rows above the explicit maximum.
- [ ] Run focused Rust tests.

## Task 2 — Efficient canonical event selection

- [ ] Add a bounded canonical event-window query or equivalent storage helper.
- [ ] Preserve exact FastEvent provenance/identity.
- [ ] Keep conflict quarantine authoritative.
- [ ] Load each affected market replay once.
- [ ] Prove deterministic ordering.
- [ ] Run focused Rust tests.

## Task 3 — Atomic FL4 labeling

- [ ] Build one `FuturePathDecision` per canonical event.
- [ ] Leave decision total quote absent.
- [ ] Use the sealed default FL4 horizons exactly.
- [ ] Use only the selected immutable coverage-session watermark.
- [ ] Leave route/capacity/net-exit annotations unknown.
- [ ] Persist through the existing exact/idempotent FL4 writer.
- [ ] Wrap the invocation in one SQLite savepoint and roll back on any failure.
- [ ] Prove rerun idempotency.
- [ ] Prove partial coverage creates incomplete long horizons rather than false complete labels.
- [ ] Run focused and full Rust tests.

## Task 4 — Host subcommand/report

- [x] Add machine-readable report model and canonical JSON encoding.
- [x] Add `shreks-observe populate-future-path-labels` before normal runtime-config loading.
- [x] Require all five explicit named inputs.
- [x] Print one JSON report on success.
- [x] Add host-subcommand regression tests proving it works with provider/PAPER environment cleared.
- [x] Preserve the existing release binary/proof-tool allowlists.
- [x] Audit the subcommand for no network/provider/trading/PAPER/signing/submission/LIVE authority.

## Task 5 — Exact-head proof

- [ ] Repository safety GREEN.
- [ ] Rust workspace GREEN.
- [ ] Python suite GREEN.
- [ ] native ARM64 release build GREEN.
- [ ] Review exact diff.
- [ ] Merge only reviewed exact head.
- [ ] Require fresh merged-main GREEN/seal before host deployment.

## Task 6 — Physical host evidence

- [ ] Deploy sealed release through protected `production-paper`.
- [ ] Verify exact release SHA and core services.
- [ ] Produce/identify an immutable historical coverage session.
- [ ] Choose a bounded explicit covered decision window.
- [ ] Run the population CLI.
- [ ] Read exact report and FL4 counts.
- [ ] Preserve any fail-closed result; never widen the window merely to force success.

## Following slice

Add source-backed execution/capacity annotation required for realistic cost-adjusted FL9 targets.
Do not infer historical economics from current constants.

FL9 remains EVIDENCE PENDING. LIVE remains disabled.
