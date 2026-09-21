# G1C V2 Multi-Reference Quote-Valuation Review — Design

**Date:** 2026-09-21  
**Status:** evidence-only review; no production candidate-value authority

## Problem

The protected production inspection produced multiple fresh exact WSOL valuation identities across PumpSwap, Pump.fun bonding-curve, and other Solana venues.

The repository provides no production venue-ranking rule for this evidence step.

Selecting one row merely because it is freshest would invent policy and could silently turn venue choice into candidate economics authority.

The production-presence design explicitly allows a trusted administrator to capture **one or more** exact reference artifacts.

This slice adds an offline review layer over those already-canonical reference artifacts.

## Inputs

The review accepts only paths to canonical:

`shreks.g1c_v2_quote_valuation_reference`

artifacts.

It never reads SQLite and never fetches external prices.

Every input must decode and self-authenticate through the existing quote-reference decoder.

The review requires:

- at least three references;
- unique market-row ids;
- unique reference fingerprints;
- one common `as_of_unix_ms`;
- one common quote mint;
- one common source;
- evidence-only/non-authority fields on every reference.

Venues, base mints, candidate ids, pair addresses, and observation timestamps may differ and are retained in the review evidence.

## Review policy

The deterministic review policy is:

`median_exact_reference_values`

Using exact `Decimal` arithmetic, the artifact records:

- reference count;
- exact sorted reference identities;
- min quote USD-per-token;
- median quote USD-per-token;
- max quote USD-per-token;
- median absolute deviation in USD;
- full range spread as basis points of the median;
- oldest and newest included observation timestamps.

The review's conservative `quote_evidence_observed_at_unix_ms` is the **oldest included reference timestamp**, because the aggregate depends on all included references.

Input order cannot affect the artifact or fingerprint.

## Artifact

The result is canonical JSON, write-once, mode `0600`, with one self-fingerprint over all material fields.

Each reference entry retains:

- market row id;
- candidate id;
- observed timestamp;
- venue;
- pair address;
- base mint;
- quote USD-per-token;
- original reference fingerprint.

## Authority boundary

Always:

- `status=REVIEW_EVIDENCE_ONLY`;
- `candidate_value_authority=NOT_GRANTED`;
- `candidate_authoring_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

The median is a review statistic, not an approved production price.

The tool does not run the entry-sizing proposal automatically.

It does not bind candidate authority, author a candidate, create a transition binding, execute readiness, rotate a manifest, score/fit, promote, sign, submit, or enable LIVE.

## Next boundary

After this implementation is merged, the twelve physical production reference artifacts may be reviewed through this tool only after a separate seal/deploy/presence step if the review is executed on the protected host.

The resulting review artifact may then be inspected as evidence for a later sizing proposal and candidate-value decision.

Neither the review artifact nor a sizing proposal grants candidate-value authority.
