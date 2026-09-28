# Fast Lane Authoritative PAPER Source Production — Design

**Date:** 2026-09-28  
**Base main SHA:** `f7784d5b3f86a2ba6de914f3fbb23c6a18ceca79`

## Purpose

Complete the production-facing evidence pipeline for the authoritative Fast
PAPER runtime without granting physical service cutover authority.

PR #652 added file-backed authoritative execution authority, but those files
still had to be supplied externally. This slice makes the already-sealed
authoritative runtime continuously derive and publish them from persisted,
point-in-time observer evidence plus the exact authoritative PAPER
checkpoint/runtime pair.

The runtime path becomes:

```text
persisted observer evidence
-> learned decision evidence
-> authoritative source writers
-> authenticated file-backed authority
-> authoritative coordinator
-> authoritative PAPER runner
-> atomic checkpoint/runtime commit
```

No network/provider client is introduced into this layer.

## Reused authority

The source writer deliberately reuses the proven shadow-era evidence machinery
only where it is ledger-independent:

- canonical learned decision evidence;
- persisted quote readers;
- read-only observer market/campaign stores;
- exact market quote/USD ratio evidence;
- BUY execution-economics policy;
- offline entry-authority binary;
- regime and safety readers;
- operator risk-control state;
- deterministic source fingerprints;
- raw-inventory reduction selection.

It must not load or mutate the isolated shadow ledger/runtime pair.

All risk accounting and position authority are derived from:

```text
FastPaperAuthoritativeServiceExecutionBootstrap
-> authoritative checkpoint
-> authoritative PaperLedger
-> authoritative runtime-state market mappings
```

## Runtime policy binding

The authoritative runtime now requires the existing reviewed BUY-writer policy:

```text
SHREKS_FAST_PAPER_AUTHORITATIVE_BUY_WRITER_POLICY_PATH=
  /etc/shreks/fast-paper-shadow-buy-writer-policy.json
```

The historical filename remains for compatibility. The policy itself is
ledger-independent and already seals:

- observer market-read identity;
- regime-read identity;
- safety probe identity;
- execution economics for every learned horizon;
- operator risk-control path;
- release-local entry-authority binary and SHA;
- risk-day start;
- health/halt inputs.

Runtime bootstrap reads the policy and re-verifies it against the exact
production manifest and learned service policy.

There are no production defaults.

## Quote/USD writer

For the oldest unexecuted non-SKIP decision, derive quote/USD authority only
from the existing read-only observer-market SQLite path:

```text
ObserverMarketStore.load_window(...)
ObserverMarketStore.quote_asset_usd_evidence(...)
quote_asset_usd_per_token = base_price_usd / base_price_quote
```

The exact market row is pinned with:

- candidate ID;
- source;
- venue;
- base mint;
- quote mint;
- market row ID;
- freshness boundary.

Publish with the existing canonical decision-bound quote/USD codec.

The source fingerprint binds the complete persisted market evidence.

No HTTP/provider lookup is permitted.

## BUY authority writer

For the oldest unexecuted learned BUY:

1. require matching decision-bound quote/USD authority;
2. reconstruct exact persisted ENTRY/EXIT quote evidence at decision time;
3. require those quotes to equal the sealed learned-decision evidence;
4. select the exact horizon economics policy;
5. build champion execution evidence;
6. derive entry authority using the release-local sealed binary;
7. read point-in-time market/regime/safety/operator-control evidence;
8. build risk context from the **authoritative PaperLedger**;
9. publish an authoritative BUY authority record bound to the exact latest
   checkpoint/runtime pair.

If persisted execution authority is not yet available, publish nothing.

## OPEN reduction/exit writer

Before learned OPEN-position decision production, inspect at most one canonical
feature row.

For the exact authoritative market mapping:

- use current raw inventory from authoritative runtime state;
- require a matching durable OPEN position;
- require persisted EXIT probes for full raw inventory;
- derive the complete eligible REDUCE target/input set with the existing
  deterministic raw-inventory selector;
- publish an authoritative reduction source keyed by current runtime-state
  fingerprint and market key.

After any position-state change the old file cannot authenticate because its
runtime-state fingerprint is stale.

## Pending BUY retry writer

A durable pending BUY takes precedence over new learned decisions.

The writer:

1. locates the exact original decision by the authoritative durable processed
   decision fingerprint;
2. reads a fresh persisted ENTRY quote at the current cycle time;
3. if no executable quote exists, returns no authority and leaves the pending
   BUY deferred;
4. derives current quote/USD from exact persisted market evidence;
5. builds risk context from the authoritative ledger;
6. publishes a retry record bound to the exact pending checkpoint/runtime pair.

Missing fresh execution evidence is backpressure, not daemon failure.

Once the pending BUY resolves, the runtime-state fingerprint changes and the
old retry file no longer authenticates.

## Cycle ordering

Each authoritative runtime cycle uses one exact `now` and runs:

```text
1. prepare OPEN reduction authority for current posture
2. publish quote/USD for oldest unexecuted decision
3. publish BUY authority when oldest decision is BUY
4. publish pending-BUY retry authority when a pending BUY exists
5. run authoritative coordinator
```

This ordering preserves the one-step learned decision/execution cursor rule.

When cursors are equal, source production sees no new decision and the
coordinator may produce exactly one. On the next cycle the writers materialize
the required authority before that decision can commit.

SKIP still requires no external economic source.

## Write/restart semantics

All source files retain canonical write-once behavior.

For a write collision:

- read back through the strict canonical reader;
- require exact equality;
- treat exact equality as restart replay;
- reject any mismatch.

Writers never delete or rewrite an existing authority file.

## Authority firewall

This slice may:

- read persisted observer SQLite evidence;
- read learned decision evidence;
- read authoritative checkpoint/runtime state;
- read operator risk-control state;
- run the sealed offline entry-authority binary;
- write file-backed PAPER authority evidence.

It must not:

- load or mutate the isolated shadow ledger/runtime state;
- bypass the authoritative coordinator;
- execute or commit PAPER directly;
- fetch provider/network data;
- invoke systemd/service control;
- sign or submit transactions;
- score with legacy strategy authority;
- enable LIVE.

Authority remains:

```text
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

## Acceptance proof

Tests must prove:

1. writer cycle order is OPEN -> quote/USD -> BUY -> pending retry;
2. quote/USD is derived from one exact persisted market row and exact replay is
   idempotent;
3. BUY authority uses the authoritative ledger/runtime pair;
4. OPEN authority uses authoritative raw inventory and state fingerprint;
5. pending BUY with no fresh executable quote safely backpressures;
6. pending retry survives restart through the authoritative pair;
7. runtime source production precedes coordinator execution;
8. source code imports no shadow-ledger persistence, provider network,
   service-control, signing/submission, scoring, or LIVE authority;
9. the authoritative runtime config pins the reviewed BUY-writer policy path;
10. Python, Rust, ARM64, and repository-safety CI remain green.

## Following slice

After this source-production topology is proven, protected host preparation can
create and permission the authoritative source roots, install the exact sealed
environment, and validate the cutover-baseline receipt plus source-writer
policy on the target host.

The physical systemd replacement of legacy PAPER authority remains a separate
explicit cutover ceremony.

LIVE remains disabled.
