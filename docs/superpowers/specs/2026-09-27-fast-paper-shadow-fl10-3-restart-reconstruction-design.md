# Fast Lane PAPER Shadow FL10.3 Restart Reconstruction — Design

**Date:** 2026-09-27  
**Base main SHA:** `748f0b80546da2fcb760502cbde1575e7f93de85`

## Purpose

Close FL10.3 with one deterministic supervised integration proof that the
already-durable Fast Lane PAPER-shadow authorities reconstruct coherently after
process restart without duplicating an economic action.

This is a proof/hardening slice. It does not add a second persistence format,
change the coordinator, widen systemd authority, mutate authoritative legacy
PAPER state, fetch providers, sign or submit transactions, or enable LIVE.

## Durable restart authority

A fresh supervisor bootstrap must reconstruct only from the existing sealed
durable sources:

- authenticated Fast PAPER learned decision runtime state/cursor;
- isolated shadow PaperLedger checkpoint;
- authenticated learned runtime companion state;
- unresolved pending BUY identity and learned target exposure;
- exact OPEN market-position mapping and raw inventory;
- learned execution cursor and last decision-evidence identity;
- PaperLedger processed-intent/idempotency state.

The decision checkpoint and isolated execution checkpoint remain separate
durable authorities. Restart does not synthesize one from the other.

## Proof sequence

The integration proof drives one learned BUY through the real supervised
orchestration while using the existing deterministic fixture authorities.

1. Provision a fresh isolated PAPER-shadow run.
2. Use an execution fill policy with positive assumed latency.
3. Produce exactly one learned BUY decision.
4. Commit that decision while it is still latency-ineligible so the BUY becomes
   durable `DEFERRED`.
5. Assert the learned decision cursor and execution cursor both equal source
   sequence 1, the isolated checkpoint advanced exactly once, the pending BUY is
   durable, no OPEN mapping exists, and no processed economic intent exists.
6. Construct a completely fresh supervisor bootstrap.
7. Require exact reconstruction of both decision state and the isolated
   checkpoint/runtime-state pair.
8. Run another supervised cycle with no pending-BUY retry source. It must apply
   backpressure: zero new decisions, zero commits, and no durable-state change.
9. Publish one exact write-once pending-BUY retry source bound to that durable
   checkpoint/runtime fingerprint.
10. Construct another fresh supervisor bootstrap and consume the retry.
11. Require one and only one economic commit: checkpoint sequence advances by
    one, execution cursor remains at learned decision sequence 1, pending BUY
    clears, one OPEN learned market mapping exists, one BUY fill exists, and
    exactly one processed intent/idempotency key exists.
12. Construct another fresh supervisor bootstrap with the OPEN position.
13. Run an idle supervised cycle with no next learned feature.
14. Require zero decisions and zero commits and byte/logical equality of the
    isolated ledger/checkpoint/runtime state. The BUY fill and processed-intent
    counts must remain exactly one.

The authoritative legacy PAPER evidence file must remain byte-for-byte
unchanged for the entire proof.

## Why this proves the missing FL10.3 boundary

Lower-level executor coverage already proves a deferred BUY can be reloaded and
that exact learned-decision replay becomes an idempotent no-op. Existing
supervised lifecycle coverage proves an OPEN learned position survives a fresh
supervisor bootstrap before a later SELL. Physical commissioning separately
proves controlled host restart identities and monotonic durable state.

This slice joins those guarantees at the production shadow supervisor boundary:
a pending BUY is reconstructed after restart, blocks new learning while retry
authority is absent, is later filled exactly once from an authenticated retry
source after another restart, and the resulting OPEN position/idempotency state
survives another fresh bootstrap without a duplicate economic action.

## Fail-closed expectations

The existing implementation remains authoritative:

- torn checkpoint/runtime pairs fail bootstrap;
- stale or mismatched retry-source records fail authentication;
- a pending BUY blocks another learned decision;
- retry does not advance the learned execution cursor;
- normal execution refuses replayed transitions;
- atomic transition commit remains the only supervised economic persistence
  path;
- uncertain outcomes are recovered by reopening the durable pair, not blind
  reinsertion.

No new recovery shortcut is introduced by this slice.

## Acceptance

The new integration test must prove all of the following in one run:

- decision learned state/cursor reconstructs exactly;
- durable pending BUY reconstructs exactly;
- missing retry authority is backpressure with no state advance;
- retry after restart commits exactly one BUY fill;
- execution cursor reconstructs and does not double-advance during retry;
- OPEN learned position mapping/raw inventory reconstructs exactly;
- PaperLedger processed-intent idempotency remains exactly-once;
- a later fresh bootstrap plus idle cycle cannot duplicate the BUY;
- authoritative legacy PAPER state remains unchanged;
- runtime mode remains PAPER.

## Authority boundary

```text
FAST_LANE_MODE=PAPER_SHADOW_ONLY
RESTART_RECONSTRUCTION=DURABLE_STATE_ONLY
PENDING_BUY_RETRY=PREPUBLISHED_EXACT_SOURCE_ONLY
ECONOMIC_COMMIT=ATOMIC_SHADOW_PAIR_ONLY
DUPLICATE_BUY=FORBIDDEN
AUTHORITATIVE_LEGACY_PAPER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_AUTHORITY=UNCHANGED
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

## Following slice

After this deterministic FL10.3 proof is green, proceed to FL10.4 physical
resource-headroom evidence under real event bursts. Optimize only measured
bottlenecks. LIVE remains disabled.
