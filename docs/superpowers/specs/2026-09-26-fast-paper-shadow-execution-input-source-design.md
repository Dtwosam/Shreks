# Fast PAPER Shadow Execution Input Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `cca3c5a630f672636e0e26ccea146d31c06430de`

## Purpose

Add one canonical, write-once, point-in-time source record for the already
defined `FastPaperShadowExecutionInput` contract.

The learned shadow executor already requires explicit BUY sizing authority,
risk context, market regime, and quote/USD evidence. The currently supervised
shadow service has no clean source for all four facts, and importing the legacy
observer PAPER manifest would load the score-gated runtime stack.

This slice therefore creates the authority handoff artifact only. It does not
invent or derive missing execution facts and it does not yet wire the service.

## Record identity

Schema:

`shreks.fast_paper_shadow_execution_input_source` version `1`.

Every record binds:

- exact Fast PAPER runtime manifest fingerprint;
- exact Fast PAPER shadow execution-policy fingerprint;
- exact learned shadow decision-evidence fingerprint;
- source event identity;
- decision evaluation timestamp;
- source observation timestamp, which may not be later than evaluation;
- exact action-compatible `FastPaperShadowExecutionInput`;
- one canonical record fingerprint.

The record filename is the exact decision-evidence fingerprint plus `.json`.
A caller cannot select a different filename.

## Action compatibility

Construction delegates to the existing
`FastPaperShadowExecutionInput` validation.

Therefore:

- BUY requires exact entry authority, risk context, market regime and quote/USD
  evidence;
- SKIP carries none of those authorities;
- HOLD/REDUCE/SELL carry quote/USD evidence only;
- REDUCE remains bound to the target-specific reduction quote later during
  materialization.

## Persistence

The source directory must already exist and must not be a symlink.

Writes are:

- canonical JSON;
- exactly one trailing newline;
- mode 0600;
- write-once;
- temporary-file + fsync + hard-link publication;
- parent-directory fsync after publication.

Reads:

- derive the path only from the supplied decision-evidence fingerprint;
- reject symlinks and non-regular files;
- reject duplicate/unknown/missing JSON fields;
- reject non-canonical JSON;
- recompute the record fingerprint;
- reconstruct exact typed values;
- rerun `FastPaperShadowExecutionInput` invariants;
- require exact current manifest, execution policy and decision evidence.

## Authority boundary

This artifact authenticates the handoff; it does not manufacture the facts in
the handoff.

```text
SCORING_CONTROL_PATH=FORBIDDEN
EXECUTION_INPUT_SOURCE=CANONICAL_WRITE_ONCE
MISSING_EXECUTION_FACTS=FAIL_CLOSED
SHADOW_SERVICE_INTEGRATION=DEFERRED
SHADOW_LEDGER_MUTATION=UNCHANGED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SIGNING_SUBMISSION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```
