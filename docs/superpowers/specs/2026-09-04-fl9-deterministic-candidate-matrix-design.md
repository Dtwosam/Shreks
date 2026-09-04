# FL9 Deterministic Same-Population Candidate Matrix — Design

**Date:** 2026-09-04

## Status

Design after deterministic campaign PAPER evidence selector merged as
`f2c2c5f66ae39f5424ac8e7d30fe5056572ad9f7` (PR #179).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Run multiple authenticated deterministic lifecycle candidates across the exact
same immutable FL8.1 decision population and collect each candidate's sealed
`FastPolicyRunEvidence` for the existing FL9 superiority proof.

Candidate actions and PAPER positions may diverge. Comparison population may not.

## Existing sealed population identity

`build_fast_policy_run_evidence` computes
`event_population_fingerprint_sha256` from:

- source_event_id;
- update_fingerprint;
- market_key;
- source_sequence;
- as_of_unix_ms;
- is_material.

The FL7.1 update fingerprint itself covers:

- source_event_id;
- market_key;
- source_sequence;
- as_of_unix_ms;
- state_version;
- materiality/reason.

It does **not** contain the candidate action/assessment.

Therefore two candidates may validly choose different actions while retaining
the same comparable population fingerprint.

## New matrix API

Add:

`FastDeterministicCandidateCampaignSpec`

Fields:

- exact authenticated `FastDeterministicCandidateManifest`;
- candidate-specific ordered tuple of `FastDeterministicCampaignRow`;
- explicit unique `paper_run_id`.

Add:

`FastDeterministicCandidateMatrixResult`

Fields:

- version;
- ordered candidate sessions;
- ordered sealed run evidence;
- shared event population fingerprint.

Add:

`run_fast_deterministic_candidate_matrix(...)`

Common inputs:

- explicit offline Rust row binary path;
- candidate specs;
- assessment version;
- starting PAPER ledger;
- sealed fill/risk/position/evaluation policies.

The common policies and starting ledger are reused as immutable inputs for every
candidate.

## Deterministic ordering

Candidate specs must be supplied in strictly lexical `candidate_version`
order.

Candidate versions and fingerprints must be unique.

The matrix does not reorder silently because caller order is part of evidence
construction and auditability.

## Same-population preflight before any candidate starts

All specs must have:

1. the same non-zero row count;
2. exact `FastTrainingFeatureRecord` equality at every row index;
3. equal raw PAPER:
   - source_event_id;
   - state_version;
   - evaluated_at_unix_ms;
4. equal explicit quote evidence at every row index.

Why quote equality is required:

FL9 comparison must not let one baseline receive a better/worse contemporaneous
execution quote timeline than another. Rich raw evidence is now safe to share
even when one action SKIPs because PR #179 materializes only action-compatible
sealed fields after the decision.

## Candidate-specific fields intentionally allowed to differ

The matrix does **not** require equality of:

- FLAT strategy evidence;
- OPEN strategy evidence;
- RiskContext;
- entry authority;
- candidate manifests;
- actions;
- PAPER positions;
- fills;
- ledger/PnL outcomes.

Risk and entry authority can legitimately depend on candidate-specific PAPER
state and sizing. They remain explicit evidence and are still validated by the
sealed PAPER path.

MarketRegime is observational rather than candidate-state dependent. To avoid
silent comparison drift, if supplied for a row it must be equal across specs.

## Execution

After whole-matrix preflight:

For each spec in lexical order:

1. call sealed `run_fast_deterministic_chronological_campaign(...)`;
2. require final session result;
3. collect exact final `FastPolicyRunEvidence`.

After all candidates:

1. require every run evidence has the same
   `event_population_fingerprint_sha256`;
2. require every trading evaluation uses the exact common
   `TradingEvaluationPolicy`;
3. return immutable matrix result.

No superiority decision is made here.

## Failure semantics

Any deterministic matrix preflight error happens before the first offline Rust
process invocation.

A candidate runtime/evidence failure aborts the matrix and returns no partial
matrix result.

The already-completed candidate's external temporary process work is immutable
and has no LIVE effect; no partial evidence bundle is emitted.

## TDD

RED first.

Tests prove:

1. unequal FL8.1 row at one index fails before fake binary launch;
2. unequal state_version/evaluated clock/quote fails before launch;
3. candidate versions duplicate or non-lexical fail before launch;
4. candidate-specific strategy evidence differences are allowed;
5. candidate-specific risk/entry authority differences are allowed;
6. action divergence (candidate A BUY, candidate B SKIP) still returns equal
   event population fingerprints;
7. matrix result exposes ordered exact `FastPolicyRunEvidence`;
8. evaluation policies match across outputs;
9. matrix contains no superiority/provider/subprocess/direct PAPER authority.

## Following slice

Create/version the required deterministic candidate manifests and campaign
evidence specifications for the FL9 comparison set, run them on real immutable
chronological evidence, and feed the resulting baseline run evidence plus the
learned candidate run into the already-sealed
`evaluate_fast_policy_superiority`.

Fixtures continue to prove plumbing only, never profitability.
