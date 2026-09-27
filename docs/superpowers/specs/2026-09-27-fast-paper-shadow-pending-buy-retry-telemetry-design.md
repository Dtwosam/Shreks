# Fast PAPER Shadow Pending-BUY Retry Telemetry — Design

**Date:** 2026-09-27  
**Base main SHA:** `963d96339b878190c7a1dfb90fee5c798f43ed2a`

## Purpose

Complete the pending-BUY retry half of FL10.2 execution telemetry.

The existing execution telemetry already authenticates fresh learned decisions,
their immutable execution-source records, exact historical pre-state, and exact
successor commits. Deferred BUYs create a second transaction later, using a
separate immutable pending-BUY retry source record. Without joining that source
to its historical pending checkpoint and successor commit, the operator view
cannot truthfully explain whether a deferred BUY later filled, aborted, failed,
or remained deferred.

This slice extends the existing execution telemetry with retry-specific evidence
and metrics. It does not add new execution authority.

## Historical retry source authentication

Keep the current production retry-source reader strict: it still requires the
exact latest durable pending checkpoint/runtime pair.

Add one read-only historical reader:

```python
read_fast_paper_shadow_pending_buy_retry_source_record_for_checkpoint(
    manifest,
    binding,
    execution_policy,
    paper_checkpoint,
    runtime_state,
    directory,
) -> FastPaperShadowPendingBuyRetrySourceRecord
```

It must:

- authenticate the manifest/binding/execution-policy/checkpoint/runtime pair;
- require a canonical durable pending BUY pair;
- locate the deterministic retry-source filename from the historical runtime
  fingerprint + pending event id;
- canonical-decode and fingerprint-check the persisted source record;
- rebuild and compare the expected record against the supplied historical pair;
- preserve risk-accounting and quote chronology checks;
- perform no writes;
- not require the supplied pair to be latest.

Refactor internals so both latest-only and historical readers share the same
validation core. Production reader latest-state semantics must not weaken.

## Read-only retry reconstruction

Add:

```python
reconstruct_fast_paper_shadow_pending_buy_retry(
    manifest,
    execution_policy,
    binding,
    paper_checkpoint,
    shadow_state,
    retry,
) -> FastPaperShadowExecutionTransition
```

It reuses the same static authority checks and exact existing retry execution
logic as production, but does not require the pair to be latest.

The production `retry_fast_paper_shadow_pending_buy(...)` must still require
the exact latest durable pair before delegating to the pure reconstruction core.

## Execution telemetry integration

Extend:

`shreks-fast-paper-shadow-execution-telemetry summarize`

with:

```text
--pending-buy-retry-source-directory <path>
```

The execution telemetry schema becomes version 2.

The retry window is keyed by
`retry_input.evaluated_at_unix_ms` using the same inclusive/exclusive 24-hour
bounded window as fresh decisions.

## Retry join procedure

For each regular non-symlink retry-source JSON file:

1. probe only the minimal canonical binding fields needed to locate history;
2. load the exact historical pre-retry checkpoint by
   `paper_checkpoint_sequence`;
3. load the exact historical runtime state for that checkpoint;
4. require runtime fingerprint + checkpoint SHA to match the source probe;
5. authenticate the full source through the historical retry-source reader;
6. include the record only when retry evaluation is inside the requested
   window;
7. reconstruct the pending-BUY retry through the read-only retry helper;
8. load exact successor checkpoint/runtime at `pre.sequence + 1`;
9. require successor PAPER/runtime state to equal the reconstructed transition;
10. require the learned decision cursor identity to remain unchanged across the
    retry transaction;
11. only then emit joined retry telemetry.

Missing historical pre-state is a hard integrity failure.

A missing successor is incomplete evidence and increments
`missing_retry_successor_commit_count`.

## Retry metrics

Expose:

- `pending_buy_retry_count`;
- `joined_pending_buy_retry_count`;
- `missing_retry_successor_commit_count`;
- `pending_buy_retry_outcome_counts`;
- `pending_buy_retry_terminal_count`;
- `pending_buy_retry_deferred_count`.

Latency:

```text
retry_to_commit_latency_ms =
    successor_checkpoint.created_at_unix_ms
    - retry_input.evaluated_at_unix_ms
```

For a new terminal ledger entry:

```text
retry_to_booked_entry_latency_ms =
    new_entry.booked_at_unix_ms
    - retry_input.evaluated_at_unix_ms
```

Expose deterministic mean/p50/p95.

## Retry price/cost evidence

A retry is not a new model decision. Do not label the retry quote as a new
decision-selected cost.

For executable BUY retry quotes compute:

```text
retry_quote_price_cost_bps =
    max(0, execution_price_quote / reference_price_quote - 1) * 10_000
```

For filled retry executions expose paired summaries for:

- retry quote price cost bps;
- realized fill signed slippage bps;
- realized minus retry-quote price cost bps;
- realized explicit fee/network cost bps;
- realized total execution burden bps
  = signed slippage + explicit cost bps.

## Outcome attribution

Use the exact existing `FastPaperBuyOutcome` values from the reconstructed
retry. In particular distinguish:

- `DEFERRED`;
- quote unavailable/late;
- price above maximum;
- insufficient capacity;
- risk rejected;
- total cost above maximum;
- execution failed;
- filled;
- ledger rejected.

Expose
`pending_buy_retry_max_entry_price_abort_count` only for
`ABORTED_PRICE_ABOVE_MAXIMUM`.

## Authority firewall

Telemetry may use read-only historical loaders/readers/reconstruction only.

It must not:

- call the service retry transaction;
- call atomic commit/save/write functions;
- create or mutate source records;
- use systemd/subprocess/network clients;
- sign or submit transactions;
- enable LIVE.

Production latest-state gates for source read and retry execution remain intact.

## RED acceptance

Tests prove:

1. production retry source reader still rejects stale pairs;
2. historical retry source reader accepts the same authenticated stale pair;
3. production retry executor still rejects stale pairs;
4. read-only retry reconstruction reproduces the original transition;
5. deferred fresh BUY followed by persisted retry source + fill joins exactly;
6. retry->commit and retry->booked-entry latency are exact;
7. retry quote price cost and realized fill slippage are kept like-for-like;
8. explicit fees and total burden remain separate;
9. retry max-entry-price abort is attributed exactly with no fabricated fill;
10. deferred-again retry is distinct from terminal retry;
11. missing successor is counted incomplete;
12. tampered source/pre-state/successor evidence fails closed;
13. output schema/fingerprint includes retry fields;
14. CLI accepts the retry source directory;
15. no new execution/storage/system/LIVE authority is introduced.

## Following slice

Adapt the operator dashboard to the combined Fast Lane decision, execution,
outcome, latency, cost, and retry telemetry. After that, continue FL10.3 restart
reconstruction and FL10.4 physical resource-headroom evidence.

LIVE remains disabled.
