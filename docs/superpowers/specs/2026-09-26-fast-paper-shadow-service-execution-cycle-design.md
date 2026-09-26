# Fast PAPER Shadow Service Execution Cycle — Design

**Date:** 2026-09-26  
**Base main SHA:** `7df181e9646c60bcaa409da24735f4377f85fc20`

## Purpose

Add the smallest supervised execution polling cycle on top of the authenticated
execution bootstrap and pre-published source-record consumer.

Decision production and economic execution are intentionally separate. The
decision service may publish learned decision evidence before an upstream has
supplied the external point-in-time execution facts required by the isolated
executor.

The execution cycle must therefore wait for authority rather than invent it.

## Contract

Add:

`run_fast_paper_shadow_service_execution_cycle(...)`

Inputs:

- exact runtime manifest;
- exact `FastPaperShadowServiceExecutionBootstrap`;
- exact decision-evidence directory;
- durable commit timestamp.

For one invocation the cycle must:

1. validate the decision-evidence directory as an existing regular
   non-symlink directory;
2. enumerate canonical `shadow-*.json` decision-evidence artifacts in
   deterministic filename order;
3. ignore evidence whose source sequence is already at/below the durable
   execution runtime state's last processed sequence;
4. select only the oldest unexecuted decision;
5. authenticate that decision evidence and require its manifest/release/champion
   identities to match the runtime manifest;
6. look for the matching source record by the decision evidence fingerprint;
7. if the source record does not yet exist, return zero without executing,
   committing, or skipping ahead;
8. if the expected source path is a symlink or non-regular existing object,
   fail closed;
9. when the exact source record exists, delegate only to
   `consume_fast_paper_shadow_service_execution_source_record(...)`;
10. process at most one decision per invocation and return one on success.

The source consumer remains authoritative for checkpoint/runtime-state
revalidation, source authentication, restart-safe execution, replay refusal,
and atomic commit.

## Why one decision per cycle

Each source record is bound to the exact current isolated checkpoint/runtime
pair. A successful execution commit changes that pair. Therefore a second
pre-published source record cannot truthfully be authorized against the new
state until the first commit is durable.

One-source-per-cycle preserves that state handshake instead of pretending a
batch of independently precomputed authorities remains valid after mutation.

## Missing source semantics

Missing source authority is normal backpressure, not an error. The execution
cycle returns zero and leaves the oldest decision pending.

A later decision with an available source record must never leapfrog an older
decision whose source authority is still absent.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
DECISION_EVIDENCE=READ_ONLY
MISSING_EXECUTION_AUTHORITY=WAIT
EXECUTION_ORDER=OLDEST_PENDING_ONLY
SOURCE_AUTHORITY=PREPUBLISHED_ONLY
SHADOW_EXECUTION=ISOLATED_ONLY
SHADOW_TRANSITION_PERSISTENCE=ATOMIC_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- a public execution-cycle API;
- deterministic oldest-unexecuted evidence selection;
- no leapfrog when the oldest source is missing;
- graceful zero-work return for missing source authority;
- source symlink/non-file refusal;
- manifest-bound decision evidence;
- exactly one consumer call on available authority;
- no producer/writer/scoring/provider/signing/LIVE authority.

Current main is expected to fail during Python collection because the execution
cycle module/API does not exist.
