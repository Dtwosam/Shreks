# G1C V2 Preflight-Bound Decision-Backed Candidate Authority — Design

**Date:** 2026-09-23  
**Status:** candidate-authoring authority hardening only; no candidate file/runtime mutation

## Purpose

The existing decision-backed candidate-authority binder predates the candidate-value compatibility preflight.

It already authenticates an approved review-backed candidate-value decision and derives one exact canonical candidate identity against the frozen V2 cohort and preserved request authority.

However, the binder currently accepts `paper_run_id` and `start_at_unix_ms` separately and does not require proof that the exact derived candidate was the one previously assessed as `COMPATIBLE`.

That leaves an avoidable drift path between:

1. evidence-only compatibility preflight;
2. explicit candidate-value decision;
3. candidate-authoring authority.

No production candidate-authority artifact exists yet, so harden this boundary before first use.

## New authority contract

The decision-backed candidate-authority binder must additionally require one authenticated:

`shreks.g1c_v2_candidate_value_preflight`

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

The binder takes future `paper_run_id` and `start_at_unix_ms` only from that authenticated preflight receipt.

The CLI must no longer accept those two values separately.

## Exact provenance equality

Before deriving authority, require the approved candidate-value decision and preflight receipt to agree exactly on:

- source runtime-manifest SHA/fingerprint/run id;
- source proposal SHA/fingerprint;
- quote-evidence fingerprint/authority/timestamp;
- target quote mint;
- target quote decimals;
- proposed raw entry amount.

Because the current preflight proves the proposal-derived raw amount, this hardened authority path accepts only:

`decision=ACCEPT_PROPOSAL`

A `REPLACE_PROPOSAL` decision is not preflight-backed and must fail closed. A replacement requires a separately designed compatibility proof before it may become candidate-authoring authority.

## Canonical candidate equality

The binder still delegates ordinary candidate derivation to the existing canonical G1C V2 runtime-manifest candidate-authority path.

It supplies:

- candidate run id from the preflight;
- candidate start time from the preflight;
- quote mint/decimals and selected raw amount from the approved decision.

After derivation it requires the resulting candidate to equal the exact preflighted hypothetical candidate on:

- candidate manifest SHA-256;
- runtime-manifest fingerprint;
- run id;
- start timestamp;
- quote mint;
- quote decimals;
- raw entry amount;
- frozen cohort fingerprint/quote mint;
- request fingerprint;
- request release SHA;
- request hydration-policy fingerprint.

Any mismatch fails closed and writes no authority.

## Authority artifact

Bump the decision-backed candidate-authority schema to version 2.

The artifact additionally commits to:

- candidate-value preflight SHA-256;
- candidate-value preflight fingerprint;
- preflight status;
- preflight compatibility;
- preflight authority;
- preflight source proposal SHA/fingerprint.

Existing downstream authority remains bounded:

```text
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## CLI

The production CLI becomes:

```text
shreks-g1c-v2-decision-backed-candidate-authority-bind
  --source-runtime-manifest <path>
  --cohort <path>
  --v2-host-request-authority <path>
  --candidate-value-preflight <path>
  --candidate-value-decision <path>
  --destination <new-path>
```

It must not expose:

- `--paper-run-id`;
- `--start-at-unix-ms`;
- raw quote mint;
- raw quote decimals;
- raw entry amount.

## Authority boundary

This hardening does not:

- execute the preflight;
- make the candidate-value decision;
- persist or stage the candidate runtime manifest;
- create a transition binding;
- execute readiness;
- rotate the protected PAPER manifest;
- execute scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

A separate production-presence and seal/deploy slice is required after this code change.
