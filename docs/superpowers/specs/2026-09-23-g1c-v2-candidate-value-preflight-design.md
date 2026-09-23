# G1C V2 Candidate-Value Compatibility Preflight — Design

**Date:** 2026-09-23  
**Status:** implementation slice; evidence-only compatibility preflight; no candidate-value, authoring, rotation, scoring, promotion, or LIVE authority

## Purpose

Protected production has already produced one authenticated multi-reference WSOL quote review. The current active PAPER runtime remains USDC-denominated, while the frozen FL9 V2 cohort requires WSOL.

The repository already has separate tools for:

- review-backed entry sizing;
- explicit candidate-value decision;
- decision-backed candidate authority;
- exact candidate authoring;
- transition binding;
- rotation readiness and planning.

The remaining review risk is that a human could approve a sizing proposal before proving that the exact proposed candidate economics and explicit new-run identity/time would actually produce a runtime manifest compatible with the frozen V2 cohort and preserved V2 request authority.

This slice adds one read-only preflight between sizing and candidate-value decision.

## Inputs

The preflight requires:

- canonical v1 source runtime manifest;
- authenticated `MULTI_REFERENCE_REVIEW` sizing proposal;
- frozen FL9 V2 cohort;
- preserved authenticated V2 host-request authority;
- explicit future `paper_run_id`;
- explicit future `start_at_unix_ms`;
- new non-existing preflight destination.

No raw quote mint, quote decimals, quote USD value, or entry-input amount may be supplied separately.

Those values come only from the authenticated review-backed sizing proposal.

## Operation

The preflight:

1. stable-reads and authenticates the source runtime manifest;
2. stable-reads and authenticates the sizing proposal;
3. requires `status=PROPOSAL_EVIDENCE_ONLY`;
4. requires `quote_evidence_authority=MULTI_REFERENCE_REVIEW`;
5. requires all candidate/rotation/scoring authority in the proposal to remain ungranted;
6. requires the proposal source SHA/fingerprint/run identity to match the supplied source manifest;
7. derives the exact hypothetical G1C v2 candidate in memory using only:
   - explicit future run id/time;
   - proposal target quote mint/decimals;
   - proposal proposed raw entry amount;
8. canonical-encodes that hypothetical candidate;
9. places those bytes only in a temporary private file;
10. delegates compatibility validation to the existing canonical FL9 V2 candidate assessment against the supplied cohort and preserved request authority;
11. requires terminal candidate compatibility to be exactly `COMPATIBLE`;
12. removes the temporary candidate;
13. rechecks source/proposal stability;
14. writes one canonical mode-`0600` write-once preflight receipt.

The preflight does not persist a runtime-manifest candidate.

## Success artifact

Success emits:

`shreks.g1c_v2_candidate_value_preflight` version 1

with:

```text
status=READY_FOR_EXPLICIT_CANDIDATE_VALUE_DECISION
candidate_compatibility=COMPATIBLE
preflight_authority=EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The receipt commits to:

- exact source manifest SHA/fingerprint/run id;
- exact proposal SHA/fingerprint and review provenance;
- future run id/time used for hypothetical derivation;
- proposal target quote mint/decimals/raw amount;
- exact hypothetical candidate SHA/fingerprint;
- frozen cohort fingerprint and quote mint returned by canonical assessment;
- preserved request fingerprint/release/hydration identity;
- one self-fingerprint over all material fields.

## Fail-closed behavior

No receipt is written when:

- the source or proposal is malformed, tampered, mutable, or symlinked;
- the proposal is not review-backed;
- the proposal already carries downstream authority;
- source/proposal provenance does not match;
- candidate derivation fails;
- cohort/request authentication fails;
- canonical assessment is not exactly `COMPATIBLE`;
- source/proposal bytes change during preflight;
- destination already exists;
- receipt write/readback or self-fingerprint validation fails.

## Authority boundary

This slice does not:

- approve the proposal;
- create a candidate-value decision;
- bind candidate-authoring authority;
- persist or stage a runtime-manifest candidate;
- create a transition binding;
- execute readiness;
- rotate the protected manifest;
- run V2 scoring/model fitting;
- publish a champion;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

A human-reviewed explicit candidate-value decision remains mandatory after successful preflight.
