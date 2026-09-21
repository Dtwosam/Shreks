# G1C V2 Entry Sizing Proposal — Design

**Date:** 2026-09-21  
**Status:** evidence-only proposal; no production candidate value authority

## Problem

Production now has:

- a sealed/deployed candidate-input authority binder;
- a fresh exact-release helper installation proof;
- frozen V2 cohort quote mint = WSOL;
- repository-sealed protocol knowledge that SOL/WSOL quote decimals are 9.

The remaining economic gap is the raw WSOL `entry_input_amount`.

The repository contains no reviewed production sizing rule for that value. Test constants are not authority.

## Proposed policy

Add an offline, evidence-only calculator implementing one conservative proposal policy:

`preserve_source_quote_notional_floor`

The tool reads one authenticated canonical v1 source runtime manifest and calculates its source quote notional:

`source raw input / 10^source decimals * source quote USD-per-token`

It then accepts an explicit target quote USD-per-token reference and target decimals and proposes:

`floor(source_notional_usd / target_quote_usd_per_token * 10^target_decimals)`

The floor rule guarantees the proposed target notional never exceeds the source quote notional because of raw-unit rounding.

This is a proposal, not a production sizing decision.

## Inputs

- canonical v1 source runtime manifest path;
- target quote mint;
- target quote decimals;
- explicit positive decimal target quote USD-per-token reference;
- SHA-256 fingerprint identifying the external quote-evidence item reviewed by the caller;
- quote-evidence observation timestamp;
- new destination path.

The tool does not fetch prices, read SQLite, or discover host evidence.

## Output

One canonical write-once mode-0600 JSON proposal containing:

- source manifest raw SHA-256 and runtime-manifest fingerprint;
- source quote mint, decimals, USD rate, raw input amount, and exact source quote notional;
- target quote mint/decimals;
- explicit target quote USD reference;
- evidence fingerprint/timestamp;
- proposed raw target input amount;
- proposed target token amount;
- proposed USD notional;
- notional shortfall from floor rounding;
- self-fingerprint;
- explicit non-authority fields.

All decimal quantities are canonical decimal strings to avoid float ambiguity.

## Authority boundary

Always:

- `status=PROPOSAL_EVIDENCE_ONLY`;
- `candidate_value_authority=NOT_GRANTED`;
- `candidate_authoring_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

The tool does not call the candidate binder/author, transition binder, readiness proof, manifest manager, scoring, fitting, promotion, signing, submission, or LIVE code.

## Follow-up

A separate reviewed production-value decision may accept, reject, or replace the proposal. Only that later decision may supply an `entry_input_amount` to the candidate-input authority binder.
