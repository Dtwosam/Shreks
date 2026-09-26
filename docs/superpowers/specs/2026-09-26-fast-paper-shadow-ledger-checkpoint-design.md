# Fast PAPER Shadow Ledger Checkpoint — Design

**Date:** 2026-09-26  
**Base main SHA:** `326b33bc7d23d7df7694470933c786cfa6be3849`  
**Parent plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Introduce the first durable isolated shadow-ledger state boundary required before the learned shadow service can move beyond FLAT-only posture.

This slice does not execute BUY/REDUCE/SELL actions yet. It reuses the existing canonical `FastPaperRuntimeState`, `PaperLedger`, and Fast PAPER checkpoint codec/storage and adds only a manifest-bound shadow namespace around them.

## Reuse, do not fork

The implementation must directly reuse:

- `FastPaperRuntimeState`;
- `create_paper_ledger(...)`;
- `create_fast_paper_loop_state(...)`;
- `save_fast_paper_checkpoint(...)`;
- `load_latest_fast_paper_checkpoint(...)`;
- `validate_fast_paper_restart_equivalence(...)`.

No second ledger model, second accounting codec, or alternate checkpoint format is permitted.

## Shadow binding

Add one canonical binding:

`shreks.fast_paper_shadow_ledger_binding` version `1`.

It binds one isolated shadow checkpoint database and run namespace to:

- exact runtime-manifest fingerprint;
- release source SHA;
- champion fingerprint;
- action-policy version;
- runtime state-version identity;
- risk-policy version;
- fill-policy version;
- position-action-policy version;
- exact absolute shadow checkpoint database path;
- exact run id;
- deterministic binding fingerprint.

The database path must differ from and not alias:

- the manifest observer database;
- authoritative PAPER evidence path;
- the learned decision cursor checkpoint path.

## Initial state

The initializer must build one empty Fast PAPER runtime state with:

- caller-supplied positive starting cash;
- empty canonical Fast PAPER event loop;
- empty canonical `PaperLedger`;
- no pending BUY;
- no position-action states;
- exact manifest-bound fill-policy version;
- exact manifest-bound position-action-policy version.

It must not synthesize a position or exposure.

## Durable storage

The shadow database contains:

- the existing `paper_loop_checkpoints` table expected by the canonical Fast PAPER checkpoint functions;
- one private binding table storing the exact canonical binding document/fingerprint for the run.

Database creation is allowed only at the explicit shadow path. The file must be private (`0600`) and its parent directory private (`0700`) when created by this boundary.

Reopening an existing database must authenticate the exact binding before checkpoint load/save. Binding conflicts fail closed.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
AUTHORITATIVE_PAPER_EXECUTION=NOT_GRANTED
SHADOW_LEDGER_STATE=ISOLATED_DURABLE
SHADOW_LEDGER_EXECUTION=NOT_GRANTED
SHADOW_SERVICE_INTEGRATION=DEFERRED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

Tests require:

- a new `shadow_ledger` module and public API;
- exact manifest/path binding with deterministic fingerprint;
- authoritative path rejection;
- reuse of the existing Fast PAPER state/checkpoint APIs;
- initial empty accounting state;
- private isolated SQLite storage;
- exact restart round-trip;
- tampered/conflicting binding rejection;
- no scoring, provider-network, execution, transaction, signing, submission, or LIVE authority.

Current main is expected to fail because the shadow-ledger checkpoint module does not exist.
