# G1C V2 Candidate Value Decision — Design

**Date:** 2026-09-22  
**Status:** explicit candidate-value decision only; no candidate authoring or runtime mutation

## Problem

The canonical multi-reference valuation review can now produce an authenticated review-backed entry-sizing proposal with:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

That proposal is intentionally evidence only:

`candidate_value_authority=NOT_GRANTED`

The repository repeatedly states that a later reviewed production-value decision may accept, reject, or replace the proposed raw entry amount before candidate authority may proceed.

No canonical artifact currently represents that decision.

## Decision contract

Add one offline command:

`shreks-g1c-v2-candidate-value-decision`

It accepts:

- one explicit canonical entry-sizing proposal path;
- one explicit decision;
- one non-empty decision reason;
- an explicit replacement raw amount only when replacement is selected;
- one new non-existent destination path.

Supported decisions:

- `ACCEPT_PROPOSAL`;
- `REJECT_PROPOSAL`;
- `REPLACE_PROPOSAL`.

The command authenticates the proposal through the existing sizing-proposal decoder.

For this production path it requires:

`quote_evidence_authority=MULTI_REFERENCE_REVIEW`

An `EXPLICIT_REFERENCE_ONLY` proposal is insufficient for this decision contract.

## Authority semantics

For `ACCEPT_PROPOSAL`:

- selected raw amount equals the proposal's `proposed_entry_input_amount`;
- replacement input is forbidden;
- `candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND`.

For `REPLACE_PROPOSAL`:

- one explicit positive u64 replacement raw amount is required;
- replacement must differ from the proposal amount;
- selected raw amount equals that explicit replacement;
- `candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND`.

For `REJECT_PROPOSAL`:

- replacement input is forbidden;
- selected raw amount is null;
- `candidate_value_authority=NOT_GRANTED`.

All decisions preserve the proposal fingerprint, proposal file SHA-256, target quote identity, quote-evidence fingerprint, quote-evidence timestamp, and quote-evidence authority.

## Output

One canonical write-once mode-0600 JSON artifact:

`shreks.g1c_v2_candidate_value_decision`

version 1.

The self-fingerprint commits the exact decision, reason, proposal provenance, and selected amount.

## Authority boundary

Even an accepted or replaced decision grants candidate-value authority only.

Always:

- `candidate_authoring_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

The command never reads SQLite, discovers market rows, executes the review, executes sizing, calls the candidate-authority binder, authors a candidate, creates a transition binding, executes readiness, rotates a manifest, scores/fits, promotes, signs, submits, or enables LIVE.

## Next boundary

The existing candidate-authority binder accepts raw explicit values and does not authenticate this decision artifact.

Do not copy a selected amount from this artifact into that binder as an unbound raw value.

A later separate bridge must authenticate one approved candidate-value decision and supply its exact selected quote mint, decimals, and raw amount into the existing candidate-authority derivation together with separately explicit new-run identity/time inputs.

That later bridge may grant candidate-authoring authority. This slice does not.
