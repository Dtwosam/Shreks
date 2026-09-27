# Fast PAPER Shadow First Learned BUY End-to-End Proof — Design

**Date:** 2026-09-27  
**Base main SHA:** `9eeecf40395fbf067dcff704aaa526b19fda34ca`

## Purpose

Prove the first learned BUY can traverse the fully supervised, provisioned
isolated Fast PAPER shadow path using persisted point-in-time observer evidence
and authenticated quote/USD authority.

This is a proof/integration slice. It grants no new trading authority.

## Path under proof

```text
provision isolated shadow ledger
-> authenticated learned BUY decision evidence
-> persisted observer ENTRY/EXIT + market/regime/safety evidence
-> authenticated quote/USD source
-> supervised BUY-authority writer
-> supervised BUY execution-source publisher
-> existing coordinator
-> existing isolated Fast PAPER executor
-> atomic shadow ledger/runtime commit
-> restart/reload verification
```

The integration test must use the real SQLite read adapters, policy codecs,
BUY-authority writer, BUY source publisher, risk engine, fill/accounting engine,
coordinator, commit path, and isolated ledger persistence.

External release-local binaries may be deterministic local test executables.
No provider/network call is permitted.

## Required proof

A single supervised cycle beginning with one durable unexecuted learned BUY must
prove:

- BUY authority is newly written from persisted evidence;
- the BUY execution-input source is newly written;
- exactly one execution is committed;
- the execution cursor advances to the learned decision sequence;
- the isolated checkpoint advances exactly once;
- one OPEN isolated PAPER position exists for the learned market;
- no pending BUY remains;
- cash/processed-intent accounting reflects one real PAPER fill;
- a fresh execution bootstrap reloads the exact committed checkpoint/runtime
  state;
- a second read of the durable ledger cannot reinterpret the position;
- the authoritative PAPER evidence path is byte-for-byte unchanged;
- no LIVE/signing/submission/provider-network authority is introduced.

## Fixture economics

The persisted observer evidence uses exact point-in-time quantities:

- 5 quote tokens ENTRY input;
- 5 base tokens quoted/available;
- executable price = 1 quote/base;
- quote/USD = 100;
- exact learned BUY notional = USD 500;
- liquidity well above preserved risk minimum;
- explicit price impact 0.2%;
- price-impact evidence notional = USD 500.

The isolated execution policy keeps all production risk/accounting logic but
uses zero assumed test latency so the persisted post-decision quote is
legitimately fill-eligible.

## Authority boundary

```text
PROOF_ENVIRONMENT=ISOLATED_PAPER_ONLY
OBSERVER_EVIDENCE=PERSISTED_READ_ONLY
QUOTE_USD=AUTHENTICATED_SOURCE
BUY_AUTHORITY=EXISTING_WRITER_ONLY
BUY_EXECUTION_SOURCE=EXISTING_PUBLISHER_ONLY
RISK=EXISTING_FAST_ENTRY_RISK
FILL_ACCOUNTING=EXISTING_PAPER_ENGINE
LEDGER=ISOLATED_SHADOW_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

## Acceptance

If current code passes this integration contract unchanged, this slice is a
proof-only merge. If it exposes a real integration defect, the paired GREEN
must repair only that defect and preserve all existing authority boundaries.

A passing proof does not authorize production PAPER cutover. It only proves the
first learned BUY path in the isolated shadow environment.
