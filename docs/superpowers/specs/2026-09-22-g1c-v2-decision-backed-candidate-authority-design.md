# G1C V2 Decision-Backed Candidate Authority — Design

**Date:** 2026-09-22  
**Status:** candidate-authoring authority proof only; no candidate file/runtime mutation

## Purpose

An approved candidate-value decision now binds reviewed production economics, but candidate authoring remains blocked.

The existing candidate-authority binder authenticates source/cohort/request authority and derives one exact canonical candidate, but accepts quote mint/decimals/raw amount as unbound explicit CLI inputs.

Do not copy values out of the approved decision into that raw-input CLI.

This slice adds one bridge that authenticates the approved decision and supplies its exact bound values into the existing candidate-authority derivation.

## Inputs

The bridge accepts only:

- canonical v1 source runtime-manifest path;
- frozen V2 cohort path;
- authenticated V2 host request-authority path;
- approved candidate-value decision path;
- explicit new `paper_run_id`;
- explicit new `start_at_unix_ms`;
- new non-existent destination.

There are no CLI inputs for quote mint, quote decimals, or entry amount.

## Decision requirements

The decision must authenticate as:

`shreks.g1c_v2_candidate_value_decision`

and require:

- `status=CANDIDATE_VALUE_APPROVED`;
- decision is `ACCEPT_PROPOSAL` or `REPLACE_PROPOSAL`;
- `candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND`;
- `quote_evidence_authority=MULTI_REFERENCE_REVIEW`;
- positive-u64 selected entry amount.

The supplied source manifest bytes/fingerprint must equal the source authority recorded by the decision.

## Derivation

The bridge invokes the existing candidate-authority binder using only:

- decision target quote mint;
- decision target quote decimals;
- decision selected raw entry amount;
- separately explicit new-run id/time.

The existing binder remains responsible for source/cohort/request authentication and exact canonical-candidate derivation.

The bridge records the resulting candidate-authority fingerprint plus the exact candidate/cohort/request identities in its own self-fingerprinted artifact.

## Output

One canonical write-once mode-0600 artifact:

`shreks.g1c_v2_decision_backed_candidate_authority`

version 1.

It records:

- exact candidate-value decision file SHA/fingerprint/decision/reason;
- decision quote-evidence provenance;
- source authority identity;
- derived candidate identity;
- frozen cohort/request authority;
- derived legacy candidate-authority fingerprint;
- `candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND`;
- `candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND`.

Always:

- `installation_authority=NOT_GRANTED`;
- `activation_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

## Authority boundary

This artifact authorizes later exact candidate authoring only.

The bridge does not persist a candidate runtime-manifest file, create a transition binding, execute readiness, install/activate/rotate a manifest, score/model-fit, promote PAPER, sign, submit, or enable LIVE.

A later separate authoring step must reproduce the exact candidate identity committed by this authority before transition binding can proceed.
