# Fast PAPER Shadow BUY Authority Writer Cycle — Design

**Date:** 2026-09-27  
**Base main SHA:** `cc6b56cc151db51684a0eb64cad816e224566c83`

## Purpose

Add the restart-safe write-once cycle that turns the oldest pending learned BUY
decision into the existing authenticated BUY-authority source record.

The exact feature row is now durable inside shadow decision evidence (schema v3),
and the persisted-evidence adapter already derives BUY economics/risk/regime
from sealed read-only sources. This slice composes those pieces and publishes
only the BUY-authority record.

It does not publish an execution-input source and does not execute PAPER.

## Selection

For the current execution bootstrap, scan authenticated shadow decision evidence
and select only the unique oldest decision whose source sequence is greater than
the durable `last_processed_source_sequence`.

The cycle must:

- validate every scanned decision against the active runtime manifest;
- preserve durable processed-event identity checks;
- reject ambiguous duplicate oldest source sequence;
- never leapfrog an older SKIP/HOLD/REDUCE/SELL;
- return `0` when no pending decision exists or the oldest pending decision is
  not BUY;
- require BUY from FLAT posture.

## Exact feature row

Use only:

`decision_evidence.feature_record`

from authenticated schema-v3 decision evidence.

Do not fetch the feature feed again and do not reconstruct a historical feature
row.

## Candidate and quote-read policy

Resolve the per-decision observer candidate id through the exact existing Fast
PAPER service candidate-attribution helper using:

- embedded mint/quote mint;
- active runtime quote provider;
- active shadow service probe/taker/slippage/ENTRY amount;
- decision observed time;
- decision evaluation time;
- active maximum quote age.

Construct `FastPaperShadowQuoteReadPolicy` from that candidate id and the exact
active shadow service policy. BUY is FLAT, so reduction reads remain empty.

No second SQL/query implementation is introduced.

## Quote/USD prerequisite

The existing authenticated quote/USD source remains separate authority.

If the exact quote/USD source record for the oldest BUY is absent, return `0`.
A symlink or non-regular path fails closed.

The writer must not derive quote/USD value.

## Authority production

Call only:

`produce_fast_paper_shadow_buy_authority_from_persisted_evidence(...)`

with:

- active manifest;
- exact isolated ledger binding/execution policy/latest checkpoint/runtime state;
- oldest BUY decision evidence;
- its exact embedded feature row;
- derived exact quote-read policy;
- explicit market/regime/safety/execution-economics policies;
- authenticated quote/USD directory;
- durable operator risk-control path;
- release-local FL3 entry-authority binary;
- explicit risk-day start and health/global-halt facts.

If the adapter returns `None`, return `0`. Do not create a different action
or leapfrog the BUY.

## Write-once publication

Write only through:

`write_fast_paper_shadow_buy_authority_source_record(...)`.

The target directory must already exist and be a regular non-symlink directory.

If a record for the decision already exists, authenticate it against the exact
current manifest/binding/policy/checkpoint/runtime/decision and return `0`.

On a write race (`FileExistsError`), read the record back through the sealed
reader and require exact equality. An unequal collision fails closed.

Return `1` only when this invocation newly publishes the authority record.

## Authority boundary

```text
DECISION_SELECTION=OLDEST_UNEXECUTED_ONLY
FEATURE_ROW=EMBEDDED_AUTHENTICATED_DECISION_ONLY
CANDIDATE_ATTRIBUTION=EXISTING_FAST_PAPER_SERVICE_HELPER
QUOTE_USD=SEPARATE_EXISTING_AUTHORITY
BUY_AUTHORITY_DERIVATION=EXISTING_PERSISTED_EVIDENCE_ADAPTER_ONLY
BUY_AUTHORITY_WRITE=WRITE_ONCE_AUTHENTICATED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
FUTURE_LABELS_COUNTERFACTUALS=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- one public writer-cycle API;
- exact oldest-decision/no-leapfrog behavior;
- exact embedded feature reuse;
- existing candidate-attribution helper reuse;
- exact quote-read policy derived from active service policy;
- quote/USD absence waits without inventing value;
- exact persisted-evidence adapter delegation;
- write-once publication with exact collision read-back;
- no execution-source publication, PAPER execution, network, scoring, signing,
  or LIVE authority.

Current main is expected to fail during Python collection because the writer
module/public API does not exist.

## Following slice

Wire this writer cycle into the supervisor immediately before the existing BUY
source publisher. Its remaining explicit policy/control inputs must be loaded
from authenticated deployment configuration without introducing runtime
defaults. After that wiring, a learned BUY can flow from durable decision
evidence through BUY authority into the existing execution-source publisher and
isolated PAPER executor.
