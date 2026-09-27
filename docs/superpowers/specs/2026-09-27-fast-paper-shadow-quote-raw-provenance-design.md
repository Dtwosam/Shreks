# Fast PAPER Shadow Quote Raw-Provenance — Design

**Date:** 2026-09-27  
**Base main SHA:** `16b06730599e2570fb910071967b925d5499cbc0`

## Purpose

Preserve the exact raw token amounts already present in persisted observer PAPER
quotes inside learned shadow decision evidence.

The first learned BUY is now proven end to end, but the post-fill learned runtime
only retains normalized float quantity/exposure. That is insufficient for safe
unattended reduction/exit sizing because the existing reduction-source contract
correctly forbids reconstructing raw token amounts from floats.

This slice is evidence plumbing only. It does not derive reduction sizes, mutate
the ledger, or change action selection.

## Schema

Advance:

`shreks.fast_paper_shadow_decision` from version `3` to version `4`.

Extend every `FastPaperShadowQuoteEvidence` with:

- `input_amount_raw: int`
- `output_amount_raw: int | None`
- `minimum_output_amount_raw: int | None`

Rules:

- `input_amount_raw` is always an explicit positive u64 because the quote
  request size exists even when the route is unavailable;
- executable quotes require positive u64 `output_amount_raw` and
  `minimum_output_amount_raw`;
- executable minimum output must not exceed output;
- unavailable quotes require both output fields to be `None`;
- no normalized quantity is converted back into raw units.

## Persisted observer adapter

`resolve_fast_paper_shadow_cycle_input(...)` already validates canonical raw
SQLite text before converting to normalized quantities.

It must forward those exact validated raw values into quote evidence:

- ENTRY:
  - raw input = quote-asset input;
  - raw output = base output;
  - raw minimum output = minimum base output;
- EXIT / REDUCE:
  - raw input = base input;
  - raw output = quote output;
  - raw minimum output = minimum quote output;
- unavailable quote:
  - preserve exact raw input request;
  - output/minimum remain `None`.

The adapter must not recompute raw amounts from floats.

## Canonical evidence

The raw values participate in:

- decision evidence fingerprinting;
- canonical JSON persistence;
- strict read-back;
- tamper detection.

Old v3 payloads are not silently accepted as v4.

## Authority boundary

```text
RAW_QUOTE_PROVENANCE=PERSISTED_OBSERVER_EXACT_ONLY
FLOAT_TO_RAW_DERIVATION=FORBIDDEN
ACTION_SELECTION=UNCHANGED
RISK=UNCHANGED
PAPER_EXECUTION=UNCHANGED
LEDGER_ACCOUNTING=UNCHANGED
REDUCTION_SIZE_DERIVATION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- decision schema version `4`;
- executable quote evidence requires exact raw input/output/minimum-output;
- unavailable quote preserves raw input and carries no synthetic outputs;
- persisted ENTRY/EXIT/reduction resolver forwards exact SQLite raw amounts;
- canonical decision round-trip preserves raw values;
- raw-field tamper changes/rejects the evidence fingerprint;
- no float-to-raw conversion helper is added to the shadow decision module.

## Following slice

Use this sealed raw quote provenance to evolve learned OPEN-position durable
state with exact current raw inventory authority, then build supervised
reduction/exit source publication without reverse-converting ledger floats.
