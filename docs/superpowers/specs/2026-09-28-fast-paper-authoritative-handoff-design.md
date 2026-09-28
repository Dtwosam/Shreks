# Fast Lane Authoritative PAPER Handoff State — Design

**Date:** 2026-09-28
**Base main SHA:** `f87859f138d393f62025eb586a7d2c28cb585184`
**Migration phase:** PR 4 durable Fast Lane PAPER runner foundation

## Purpose

Introduce the authoritative Fast Lane PAPER state boundary required before a
production learned runner can replace the legacy score-gated PAPER service.

The learned shadow runtime already proves decision/execution/restart behavior,
but its durable ledger binding intentionally rejects the authoritative observer
SQLite path. Production PAPER cannot reuse that isolation rule.

This slice adds a separate authoritative binding/checkpoint contract that:

- uses the existing authoritative observer SQLite database;
- preserves the exact legacy `PaperLedger` value at a flat reconciled handoff;
- starts a new Fast PAPER checkpoint namespace with fresh learned event state;
- pins the exact release, manifest, champion, action policy and execution policy;
- commits the binding and initial Fast checkpoint atomically;
- is idempotent only for the exact same handoff;
- does not start, stop, enable, or switch any service.

It is storage/runtime preparation only. Production service authority is still
not granted.

## Source of accounting truth

The handoff source is one exact latest legacy `PaperCheckpointRecord` already
persisted in the same SQLite database.

The handoff must require:

```text
legacy_checkpoint=EXACT_LATEST
legacy_accounting=RECONCILED
legacy_open_positions=0
legacy_pending_entry=NONE
legacy_pending_exits=0
```

The handoff does not force-close or rewrite anything.

The new Fast state reuses the source checkpoint's exact `PaperLedger` object.
No starting cash, cash balance, realized PnL, costs, journal entries,
processed-intent keys, positions, marks, or timestamps may be synthesized or
recomputed into a replacement ledger.

## Fast initial runtime state

Create one `FastPaperRuntimeState` with:

- `version=FAST_PAPER_RUNTIME_STATE_VERSION`;
- `as_of_unix_ms=legacy_checkpoint.state.last_cycle_at_unix_ms`;
- fresh empty `create_fast_paper_loop_state()`;
- exact source `PaperLedger`;
- Fast execution-policy `fill_policy`;
- Fast execution-policy `position_action_policy`;
- `pending_buy=None`;
- `position_action_states=()`.

Because the handoff is allowed only when the source ledger is flat, an empty
Fast position-action set is exact.

Both legacy and Fast accounting reports must be `RECONCILED`, and because they
validate the same ledger they must be equal.

## Authoritative binding

Add
`python/src/shreks_brain/fast_paper_runtime/authoritative_handoff.py`.

Binding schema:

`shreks.fast_paper_authoritative_binding` version `1`.

The binding records:

- new Fast run ID;
- source legacy run ID;
- source legacy checkpoint sequence;
- source legacy checkpoint payload SHA-256;
- legacy runtime-manifest fingerprint supplied by the caller;
- release source SHA;
- Fast runtime-manifest fingerprint;
- champion version/fingerprint;
- action-policy version;
- execution-policy fingerprint;
- risk-policy version;
- fill-policy version;
- position-action-policy version;
- authoritative SQLite database path;
- binding fingerprint.

The new Fast run ID must differ from the legacy run ID so the legacy
`c6-paper-state-v1` namespace and Fast
`fl7.5-fast-paper-state-v1` namespace can never collide.

## Database path

The target database must be the exact existing regular non-symlink file named
by `FastPaperRuntimeManifest.observer_database_path`.

Unlike the shadow ledger module, this contract deliberately requires the
authoritative observer database and must reject any isolated substitute path.

It must not create or chmod the authoritative database file.

## Atomic persistence

Use one SQLite `BEGIN IMMEDIATE` transaction to:

1. require the existing `paper_loop_checkpoints` table;
2. re-read the exact latest legacy checkpoint identity from the database;
3. create/verify `fast_paper_authoritative_bindings`;
4. verify the new Fast run namespace is unused or exactly idempotent;
5. insert the binding;
6. insert Fast checkpoint sequence `0`.

The initial checkpoint is encoded with the existing canonical
`encode_fast_paper_checkpoint(...)` codec.

After commit, reload both binding and checkpoint and require exact equality.

## Idempotency and collisions

Repeating the exact same handoff returns the same binding/checkpoint and creates
no new row.

Fail closed when:

- source legacy checkpoint is stale;
- source accounting is not reconciled;
- any legacy OPEN position exists;
- legacy pending entry exists;
- any managed legacy position carries a pending exit;
- database path differs from the manifest's authoritative observer DB;
- Fast run ID equals legacy run ID;
- Fast target run already contains a different checkpoint/schema/state;
- existing authoritative binding differs;
- binding or checkpoint readback is tampered.

## Authority boundary

This module may:

- authenticate manifests/policies;
- read the latest legacy PAPER checkpoint;
- validate accounting;
- write one new binding row and one initial Fast checkpoint row in the same
  authoritative SQLite database.

It must not:

- modify/delete any legacy checkpoint;
- mutate the source `PaperLedger`;
- execute BUY/SKIP/HOLD/REDUCE/SELL;
- import legacy scoring/decision authority;
- write decision/evaluation evidence;
- control systemd;
- change target membership;
- sign or submit transactions;
- enable LIVE.

This slice records no service cutover receipt and grants no production runtime
authority.

## Acceptance tests

1. flat reconciled exact-latest legacy checkpoint seeds Fast sequence 0;
2. new Fast checkpoint contains the exact legacy `PaperLedger`;
3. legacy and Fast accounting reports are equal and reconciled;
4. event-loop/pending/action state starts empty;
5. execution policy versions/fingerprint are pinned in the binding;
6. exact repeat is idempotent;
7. stale source checkpoint is rejected;
8. OPEN legacy position is rejected;
9. pending legacy entry is rejected;
10. pending legacy exit is rejected;
11. invalid legacy accounting is rejected;
12. non-authoritative database path is rejected;
13. legacy and Fast run IDs cannot be equal;
14. target checkpoint namespace collision is rejected;
15. binding tamper is rejected before checkpoint load;
16. checkpoint readback is restart-equivalent;
17. module has no scoring, execution-action, service-control, signing, or LIVE
    authority imports/references.

## Following slice

Build the production Fast Lane PAPER runner on this binding/checkpoint contract,
reusing the proven score-free learned decision and PAPER execution semantics.
Only after that runner exists should the protected cutover ceremony stop the
legacy service, freshly revalidate the flat handoff, seed this state, switch
service authority, and perform physical verification.

LIVE remains disabled.
