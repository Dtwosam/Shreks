# Fast PAPER Shadow Supervisor OPEN Sources — Design

**Date:** 2026-09-26  
**Base main SHA:** `d74b006d37f80f52e930e46e61451983f4b37046`

## Purpose

Wire the already-sealed OPEN execution-source publisher into the coordinated
shadow supervisor without granting new quote/USD derivation authority.

This slice adds one dedicated quote/USD source directory to supervisor config
and provisioning, then invokes the OPEN publisher before the coordinator.

## Configuration

Extend `FastPaperShadowSupervisorConfig` with:

- `quote_usd_source_directory: Path`.

Load it from:

- `SHREKS_FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_DIRECTORY`.

The directory must be absolute and, at bootstrap, an existing regular
non-symlink directory.

It must be distinct and non-overlapping with:

- decision evidence directory;
- execution source directory;
- reduction source directory;
- pending-BUY retry source directory.

## Provisioning

The explicit one-time shadow provisioner must create the quote/USD source
directory as another private mode-0700 leaf beneath an existing host-owned
parent.

It must participate in the same source-root separation checks.

The packaged env example must include the new setting.

## Supervisor ordering

For each supervisor cycle:

1. run the SKIP source publisher;
2. run the OPEN source publisher with:
   - exact current manifest;
   - exact current execution bootstrap;
   - decision evidence directory;
   - quote/USD source directory;
3. run the existing coordinator.

The publishers are both bounded and oldest-decision-aware:

- oldest SKIP => SKIP publisher may publish; OPEN publisher no-ops;
- oldest HOLD/REDUCE/SELL => SKIP publisher no-ops; OPEN publisher may publish;
- oldest BUY => both no-op and coordinator remains backpressured until separate
  BUY authority exists.

The supervisor must not read or derive quote/USD evidence itself.

## Authority boundary

```text
QUOTE_USD_SOURCE_ROOT=DEDICATED_PREPUBLISHED_AUTHORITY
OPEN_SOURCE_PUBLISHER=ENABLED
QUOTE_USD_DERIVATION=FORBIDDEN
BUY_SOURCE_PUBLICATION=NOT_GRANTED
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- quote/USD source directory in supervisor config and env loader;
- source-root separation including quote/USD;
- private provisioner creation of the quote/USD source root;
- env example entry;
- OPEN publisher invocation between SKIP publication and coordinator;
- exact decision/execution bootstrap forwarding;
- no quote/USD derivation, observer/provider access, BUY publication,
  signing/submission, authoritative PAPER, or LIVE authority.
