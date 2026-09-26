# Fast PAPER Shadow Incremental Executor — Design

**Date:** 2026-09-26  
**Base main SHA:** `dc57d322ef00b608695df697f5b9a4b7755231c1`

## Purpose

Add the first ledger-mutating component of the learned Fast PAPER shadow path.

This slice consumes only already-authenticated learned decision evidence,
execution-input authority, the isolated Fast PAPER checkpoint, and its learned
posture companion state. It delegates fills, risk, accounting, event recording,
and position actions to the existing sealed Fast PAPER components.

It does not wire the service, mutate authoritative PAPER state, or enable LIVE.

## Fresh decision transition

For one new learned decision:

1. require the supplied paper checkpoint and learned posture state to describe
   the same checkpoint sequence/payload;
2. reject new learned decisions while a deferred BUY is unresolved;
3. convert the sealed learned result with
   `fast_campaign_result_to_paper_assessment(...)`;
4. record the material event through `run_fast_paper_event(...)`;
5. exact event replay returns a no-op and never calls economic execution again;
6. materialize the already-authenticated execution input;
7. dispatch only through:
   - `execute_fast_paper_buy(...)`;
   - `apply_fast_paper_position_action(...)`;
8. return one immutable checkpoint-ready transition.

The transition contains no new fill or PnL arithmetic.

## Deferred BUY restart authority

`FastPaperRuntimeState.pending_buy` preserves the exact FL7.2 approval, but
the learned target exposure is not part of that approval. Without separately
persisting the target, a BUY that fills after restart cannot reconstruct the
truthful learned OPEN posture.

Therefore the learned posture companion state advances to schema version 2 and
adds one optional exact `FastPaperShadowPendingBuy` value containing:

- market key;
- mint;
- source event id;
- selected target exposure fraction in `(0,1]`.

It must exist iff the canonical Fast PAPER checkpoint has
`pending_buy != None`, and its market/mint/event identity must match that
approval exactly.

A deferred BUY transition stores both the canonical pending approval and this
learned target. A terminal non-fill clears both. A filled retry opens the
canonical PAPER position, creates the sealed FL7.4 position-action state, and
moves the persisted learned target into the OPEN market mapping.

## Pending BUY retry

A pending BUY blocks consumption of another learned decision until it resolves.

Retry takes only fresh point-in-time execution facts:

- evaluation timestamp;
- exact ENTRY quote evidence;
- exact quote/USD evidence;
- exact fresh `RiskContext`.

The original approval, decision timestamp, size/economic boundary, market, and
learned target come only from the persisted checkpoint/companion state.

The retry never creates a new Fast PAPER event or a new learned decision.

## OPEN-position execution

For HOLD/REDUCE/SELL the executor requires the exact persisted learned market
mapping and exact canonical OPEN PAPER position/action state.

Fresh REDUCE base exit quantity is derived using the already-sealed campaign
rule:

`position_quantity * (1 - target_exposure/current_exposure)`.

Pending FL7.4 exit precedence remains owned by
`apply_fast_paper_position_action(...)`.

After an actually applied reduction, learned exposure is updated from the
authoritative before/after PAPER position quantity ratio. This is important for
capacity-limited partial exits and avoids pretending that the selected target
was fully reached.

SELL removes the learned mapping only when the canonical position actually
closes.

## Replay and restart rules

- exact already-processed learned decision fingerprint => no-op transition;
- conflicting replay => fail closed;
- new decision while `pending_buy` exists => fail closed until retry resolves;
- checkpoint/posture mismatch => fail closed;
- persisted FL7.4 pending exit is passed back into the sealed position executor;
- processed intent keys remain owned by `PaperLedger`;
- no duplicate BUY/REDUCE/SELL may be created by exact replay.

The existing companion-state torn-write detector remains authoritative. This
slice returns checkpoint-ready state but does not add service-level atomic
multi-row persistence; a later orchestration slice may make the two durable
writes one transaction.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
SHADOW_LEDGER_EXECUTION=ISOLATED_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
SHADOW_SERVICE_INTEGRATION=DEFERRED
SYSTEMD_CUTOVER=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```
