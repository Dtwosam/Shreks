# Fast PAPER Shadow Execution Source Producer — Design

**Date:** 2026-09-26  
**Base main SHA:** `0dd390f9ede7f518b9efa2b1da339503051f31f2`

## Purpose

Close the state-authentication gap between an already valid
`FastPaperShadowExecutionInput` and the write-once execution-input source record.

The existing source-record builder deliberately accepts durable-state identity
as explicit scalar inputs. That is appropriate for the storage contract, but it
does not prove that those identifiers belong to the exact latest isolated
checkpoint/posture pair or that BUY portfolio accounting inside `RiskContext`
was derived from that ledger.

This slice adds the narrow producer that owns those checks.

## Producer contract

Add:

`produce_fast_paper_shadow_execution_input_source_record(...)`

Inputs:

- exact authenticated Fast PAPER runtime manifest;
- exact isolated shadow-ledger binding;
- exact shadow execution policy;
- exact current Fast PAPER checkpoint;
- exact current learned shadow runtime state;
- one already action-compatible `FastPaperShadowExecutionInput`;
- source observation timestamp;
- for BUY only, the explicit risk-accounting day-start timestamp.

The producer must:

1. require the supplied checkpoint and learned runtime state to be the exact
   latest durable pair;
2. require their checkpoint sequence/payload identities to agree;
3. require the learned runtime state's execution-policy fingerprint to equal
   the supplied execution policy;
4. reconstruct the current learned market posture and require it to equal the
   posture sealed into the decision evidence;
5. reject a new decision whose source clock predates the durable PAPER state;
6. for BUY, require no unresolved canonical/learned pending BUY;
7. for BUY, recompute canonical ledger accounting using
   `derive_paper_risk_accounting_facts(...)` and require exact equality with
   the supplied `RiskContext` for:
   - open position count;
   - aggregate open risk;
   - daily realized PnL;
   - rolling drawdown;
   - consecutive losses;
   - last loss timestamp;
8. for BUY, require trading capital to equal the isolated ledger's starting
   cash and require no separately claimed active entry intents;
9. require a BUY day-start at or before evaluation; non-BUY actions may not
   carry a day-start;
10. derive checkpoint sequence, checkpoint payload SHA-256, and learned runtime
    state fingerprint from the exact supplied objects and delegate record
    construction to the existing source-record builder.

The producer does not derive external market facts. Entry authority, market
regime, liquidity/health/impact facts, and quote/USD evidence remain explicit
authenticated inputs to the already-sealed execution-input contract.

## Why this boundary matters

A stale BUY `RiskContext` must not be relabeled with fresh checkpoint hashes.
The source record already rejects a stale persisted record when consumed
against a newer checkpoint. This producer additionally prevents creating the
record with truthful current hashes but stale portfolio-accounting facts.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
LATEST_SHADOW_PAIR=REQUIRED
BUY_LEDGER_ACCOUNTING=RECOMPUTED
EXTERNAL_MARKET_FACTS=EXPLICIT_ONLY
EXECUTION_INPUT_RECORD=PRODUCED_ONLY
SHADOW_LEDGER_MUTATION=NOT_GRANTED
SHADOW_SERVICE_INTEGRATION=DEFERRED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

The producer must not invoke BUY/position execution, provider/network clients,
observer SQLite, scoring/legacy decision authority, signing/submission, future
labels, counterfactuals, or LIVE mode.

## Following slice

Once this producer is merged, the supervised shadow service may be extended to
load its exact isolated checkpoint/posture pair, consume a separately supplied
point-in-time execution input, produce/read the state-bound source record,
dispatch through the restart-safe executor, and persist via the atomic
transition commit. Missing source authority must fail closed.
