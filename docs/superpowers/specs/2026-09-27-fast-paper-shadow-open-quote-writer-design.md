# Fast PAPER Shadow Persisted OPEN Quote Writer — Design

**Date:** 2026-09-27  
**Base main SHA:** `600279f0f4457ca80440916f73a410135c943680`

## Purpose

Add the restart-safe read-only observer adapter that publishes the existing
Fast PAPER shadow OPEN quote-source v2 record before an OPEN learned decision is
evaluated.

Durable runtime state now seals exact current raw base inventory. OPEN quote
source v2 seals that same inventory and exact full-exit raw input. The remaining
gap is target-specific reduction raw input authority.

This writer must choose those raw inputs only from persisted observer EXIT quote
requests. It must never reconstruct token raw quantities from PAPER ledger
floats or learned exposure floats.

This slice does not wire the writer into the supervisor and does not execute
PAPER.

## Public API

Add:

`run_fast_paper_shadow_open_quote_writer_cycle(...)`

Inputs:

- exact `FastPaperShadowServiceBootstrap`;
- exact `FastPaperShadowServiceExecutionBootstrap`;
- existing OPEN/reduction source directory;
- optional explicit clock.

Return exactly:

- `1` when one new v2 OPEN quote-source record is published;
- `0` when no publication is required or required target quote requests have
  not yet appeared.

## Next-feature preview

The writer must call:

`fetch_fast_paper_runtime_feature_batch(..., maximum_decisions=1)`

against the current decision bootstrap state.

This is preview-only. The writer must not save or advance the feature cursor.

If there is no next row, return `0`.

Build the next market key only from the exact feature row:

`<venue>:<mint>:<quote_mint>`.

Resolve posture only from the exact durable learned runtime state. FLAT posture
returns `0`.

## Candidate attribution and chronology

For OPEN posture:

1. use the same service quote identity and the same existing
   `_resolve_candidate_id(...)` attribution path as the supervised decision
   service;
2. use one evaluation timestamp from the supplied clock;
3. require that timestamp at/after the feature decision timestamp;
4. use the same freshness lower bound:
   `max(feature.decision_observed_at_unix_ms,
         evaluated_at_unix_ms - service_policy.max_quote_age_ms)`.

The observer database is opened read-only/query-only only.

## Persisted EXIT raw-input discovery

Read only matching `paper_quote_snapshots` rows with exact:

- candidate id;
- purpose `exit`;
- runtime quote provider;
- service probe-policy version;
- base input mint;
- runtime quote output mint;
- service taker;
- service slippage;
- exact chronology/freshness window.

Only canonical positive decimal-u64 `input_amount` values are eligible.

### Full EXIT

The exact durable
`FastPaperShadowMarketPosition.current_base_quantity_raw` must already appear
as one matching persisted EXIT quote request input.

The writer does not derive this value. It comes from durable state.

If the exact full-exit request has not appeared yet, return `0`.

### Reduction targets

Eligible targets remain exactly the action-policy reduction targets strictly
below current durable exposure.

For each target, inspect the persisted raw input candidates. A candidate matches
the target only by checking the **remaining fraction implied by that explicit
raw row**:

`(current_raw - candidate_input_raw) / current_raw`

against:

`target_exposure / current_exposure`.

The comparison tolerance may cover at most half one raw base-token unit at the
current exposure, plus ordinary floating-point arithmetic tolerance.

The writer must never compute, round, truncate, cast, or otherwise construct a
raw input amount from an exposure float.

Require exactly one distinct persisted raw input amount for every eligible
target:

- no matching row yet -> return `0`;
- multiple matching raw amounts -> fail closed.

## Canonical resolver replay

After selecting persisted raw inputs, construct one
`FastPaperShadowQuoteReadPolicy` with:

- existing static ENTRY amount;
- exact durable full EXIT raw amount;
- complete ordered reduction reads from persisted rows.

Then call existing
`resolve_fast_paper_shadow_cycle_input(...)` for the previewed feature and
OPEN posture.

This replay must authenticate the same candidate, token decimals, raw quote
rows, freshness, ambiguity rules, and quote evidence used by the supervised
decision path.

Require replayed full EXIT raw input and every reduction raw input to match the
selected authority exactly.

## Publication and restart

Delegate record construction only to:

`build_fast_paper_shadow_reduction_source_record(...)`.

Delegate persistence only to:

`write_fast_paper_shadow_reduction_source_record(...)`.

Publication remains deterministic, canonical, private `0600`, state-bound,
and write-once.

If the deterministic source already exists, authenticate it through
`read_fast_paper_shadow_reduction_source_record(...)` and return `0`.

On a write collision, exact read-back equality is required.

## Authority boundary

```text
NEXT_FEATURE=READ_ONLY_PREVIEW
OBSERVER_DATABASE=READ_ONLY_QUERY_ONLY
CANDIDATE_ATTRIBUTION=EXISTING_SERVICE_RULE
FULL_EXIT_RAW=EXACT_DURABLE_INVENTORY
REDUCTION_RAW=SELECT_EXISTING_PERSISTED_ROWS_ONLY
FLOAT_TO_RAW_DERIVATION=FORBIDDEN
OPEN_QUOTE_SOURCE_V2_WRITE=GRANTED
DECISION_CURSOR_MUTATION=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
LEDGER_MUTATION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- one public writer-cycle API;
- exact one-row feature preview without cursor mutation;
- exact OPEN durable raw-inventory binding;
- exact full-exit raw request must be persisted;
- complete reduction target raw inputs selected only from persisted EXIT rows;
- missing target row waits without publication;
- ambiguous persisted target authority fails closed;
- canonical quote resolver replay before source publication;
- restart/collision read-back is exact;
- source code contains no float-to-raw conversion and no execution, scoring,
  network-provider, signing/submission, authoritative PAPER, or LIVE authority.

Current main is expected to fail during Python collection because the writer
module/public API does not exist.

## Following slice

Wire this writer into the supervisor before the coordinated OPEN decision cycle,
then make the supervised service consume the v2 source's dynamic
`exit_input_amount_raw` instead of the deployment-static full-exit amount.
