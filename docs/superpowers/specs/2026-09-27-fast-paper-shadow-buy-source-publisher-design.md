# Fast PAPER Shadow BUY Source Publisher — Design

**Date:** 2026-09-27  
**Base main SHA:** `7617108f9c83de14139c67ad717893ecd406b8da`

## Purpose

Add the smallest bounded publisher that turns one already-authenticated learned
BUY authority record plus the already-authenticated quote/USD record for the
same decision into the existing state-bound execution-input source record.

This slice does not derive sizing, risk, regime, USD conversion, or market
facts. It does not execute a trade.

## Inputs

The publisher consumes:

- the exact current Fast PAPER runtime manifest;
- the exact current service execution bootstrap;
- the decision-evidence directory;
- the initial BUY authority source directory;
- the quote/USD source directory.

The existing execution-source directory remains owned by the service bootstrap.

## Ordering

The publisher considers only the oldest unexecuted learned decision after the
durable runtime cursor.

- If none exists, return without publication.
- If the oldest decision is not `BUY`, return without publication.
- Never leapfrog an older SKIP/HOLD/REDUCE/SELL decision.
- The BUY must be FLAT.

## Required authority

For the exact BUY decision fingerprint, both source files must already exist:

1. `FastPaperShadowBuyAuthoritySourceRecord`;
2. `FastPaperShadowQuoteUsdSourceRecord`.

Missing either record is backpressure, not an error and not permission to
invent defaults.

Both records are read through their existing strict readers. The BUY authority
reader rebinds to the exact latest checkpoint/runtime state.

## Publication

Construct exactly one `FastPaperShadowExecutionInput` from:

- exact decision evidence;
- BUY record entry authority;
- BUY record risk context;
- BUY record market regime;
- quote/USD record evidence.

Then delegate to
`produce_fast_paper_shadow_execution_input_source_record(...)`.

Use:

- `risk_day_started_at_unix_ms` from the authenticated BUY authority record;
- `source_observed_at_unix_ms` equal to the later of the BUY authority source
  observation and the quote/USD evidence observation.

The latest input observation must still be at/before the sealed decision
evaluation time under the existing source contracts.

Persist only with the existing canonical execution-source writer. An exact
write collision is restart-safe only when strict read-back equals the record
that would have been written.

## Authority boundary

```text
BUY_AUTHORITY_DERIVATION=FORBIDDEN
BUY_RISK_DERIVATION=FORBIDDEN
MARKET_REGIME_DERIVATION=FORBIDDEN
QUOTE_USD_DERIVATION=FORBIDDEN
EXECUTION_SOURCE_PUBLICATION=BOUNDED
PAPER_EXECUTION=NOT_GRANTED
LEDGER_MUTATION=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- one public publisher-cycle API;
- oldest-decision ordering with no leapfrog;
- exact authenticated BUY + quote/USD composition;
- missing-source backpressure;
- exact risk-day/source-observation forwarding;
- restart-safe exact collision handling;
- no authority derivation, execution, provider/network, scoring, signing, or
  LIVE path.

Current main is expected to fail during Python collection because the publisher
API does not exist.

## Following slice

Wire the BUY authority/source directories and BUY publisher into the supervised
shadow service/provisioner with strict root separation. Upstream production of
the explicit BUY authority facts remains a separate authority surface.
