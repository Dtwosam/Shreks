# Fast PAPER Shadow Pending BUY Retry Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `1df07f21d8c5a5f61e8057e839397fe22008a371`

## Purpose

Add a canonical write-once source record for the fresh point-in-time facts used
to retry one already-durable deferred learned BUY.

The retry executor and service transaction are already sealed. The coordinator
can accept an explicit in-process retry resolver, but an unattended supervised
service still needs a durable handoff that survives process restart and is
cryptographically bound to the exact isolated pending-BUY state.

This slice adds only that source boundary. It does not execute the retry and
does not wire the coordinator to the new source directory.

## Record contract

Add schema:

`shreks.fast_paper_shadow_pending_buy_retry_source` version `1`.

Add public:

- `FastPaperShadowPendingBuyRetrySourceRecord`;
- `build_fast_paper_shadow_pending_buy_retry_source_record(...)`;
- `write_fast_paper_shadow_pending_buy_retry_source_record(...)`;
- `read_fast_paper_shadow_pending_buy_retry_source_record(...)`.

Each record binds:

- runtime manifest fingerprint;
- isolated ledger-binding fingerprint;
- execution-policy fingerprint;
- exact PAPER checkpoint sequence and payload SHA-256;
- exact learned runtime-state fingerprint;
- pending source-event id;
- pending market key;
- pending mint;
- persisted learned target exposure fraction;
- explicit risk-day start;
- source-observation timestamp;
- exact `FastPaperShadowPendingBuyRetryInput`;
- deterministic record fingerprint.

## Build validation

Building a source record must:

1. require the exact latest checkpoint/runtime pair;
2. require that pair to contain both the canonical pending BUY approval and the
   learned pending target;
3. require their event/market/mint identities to match;
4. require the runtime state's execution-policy fingerprint to match the
   supplied execution policy;
5. require retry evaluation to be at/after the durable pending checkpoint;
6. reuse the sealed pending-BUY quote attribution/chronology validator;
7. require explicit `risk_day_started_at_unix_ms` at/before retry evaluation;
8. recompute isolated-ledger risk accounting for that risk day and require the
   supplied retry `RiskContext` to match the durable ledger exactly for
   trading capital, open positions/risk, realized PnL, drawdown, consecutive
   losses and last-loss timestamp;
9. reject external active-intent claims;
10. require source observation at/after the retry quote and quote/USD evidence
    observations and at/before retry evaluation.

The source may carry externally supplied liquidity, price-impact and health
facts already present in the exact retry `RiskContext`; it must not invent
them.

## Persistence

The record is canonical JSON with exactly one trailing newline and mode 0600.

Publication is write-once into an existing private regular non-symlink
directory. The filename is deterministic from the exact runtime-state
fingerprint plus pending source-event identity.

The reader rebuilds the expected record against the current exact latest pair.
Any state advance, policy drift, pending identity drift, malformed payload,
unknown field, symlink, or fingerprint mismatch fails closed.

A retry that remains deferred commits a new checkpoint/runtime state, producing
a new runtime-state fingerprint and therefore a new source namespace for the
next fresh retry facts.

## Authority boundary

```text
PENDING_BUY_RETRY_SOURCE=WRITE_ONCE_AUTHENTICATED
RETRY_MARKET_FACTS=EXPLICIT_ONLY
LEDGER_RISK_ACCOUNTING=RECOMPUTED
RETRY_EXECUTION=NOT_GRANTED
COORDINATOR_INTEGRATION=DEFERRED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- stable public schema/model/build/read/write API;
- exact pending checkpoint/runtime binding;
- canonical pending identity binding;
- sealed quote chronology validation;
- ledger-backed risk-accounting validation;
- strict source chronology;
- private write-once canonical round trip;
- stale-state/tamper refusal;
- no execution, scoring, provider/network, signing/submission, or LIVE
  authority.

Current main is expected to fail during Python collection because the retry
source public API does not exist.
