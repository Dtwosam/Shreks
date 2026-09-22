# G1C V2 Review-Backed Entry Sizing — Design

**Date:** 2026-09-22  
**Status:** evidence-only provenance bridge; no production candidate-value authority

## Problem

The sealed multi-reference valuation review produces:

- one canonical median WSOL/USD review statistic;
- one review fingerprint;
- one conservative evidence timestamp;
- `candidate_value_authority=NOT_GRANTED`.

The existing entry-sizing proposal can mechanically accept a value/fingerprint/timestamp, but its current provenance marker is:

`quote_evidence_authority=EXPLICIT_REFERENCE_ONLY`

Using a multi-reference review fingerprint through that path would misstate evidence provenance.

## Design

Add a separate review-backed entry-sizing path.

It authenticates one canonical:

`shreks.g1c_v2_quote_valuation_review`

artifact through the existing decoder.

It then supplies exactly:

- review `quote_mint`;
- review `median_quote_asset_usd_per_token`;
- review `review_fingerprint_sha256`;
- review `quote_evidence_observed_at_unix_ms`

to the existing sizing calculation under a distinct internal provenance:

`MULTI_REFERENCE_REVIEW`

The existing explicit-reference API and CLI remain backward compatible and continue to emit:

`EXPLICIT_REFERENCE_ONLY`.

## Artifact compatibility

The output remains schema:

`shreks.g1c_v2_entry_sizing_proposal`

version 1.

No fields are added.

The existing `quote_evidence_authority` field becomes a strict enum with two valid values:

- `EXPLICIT_REFERENCE_ONLY`;
- `MULTI_REFERENCE_REVIEW`.

The self-fingerprint therefore commits the exact provenance mode.

## Authority boundary

A review-backed proposal remains:

- `status=PROPOSAL_EVIDENCE_ONLY`;
- `candidate_value_authority=NOT_GRANTED`;
- `candidate_authoring_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

The bridge never reads SQLite, selects market rows, approves the median, approves the proposed amount, binds candidate authority, authors a candidate, creates a transition binding, executes readiness, rotates a manifest, scores/fits, promotes, signs, submits, or enables LIVE.

## Production boundary

This implementation itself is not automatically production-executable.

After merge, a separate seal/deploy/presence slice is required before the protected production review artifact may be supplied to the review-backed sizing CLI.

Even after a physical proposal exists, a separate explicit production candidate-value decision must accept, reject, or replace the proposed raw amount before candidate authority may run.
