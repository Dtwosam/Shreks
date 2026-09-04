# FL9 Deterministic Chronological PAPER Campaign Driver — Design

**Date:** 2026-09-04

## Status

Design after the Python offline deterministic row adapter merged as
`572037aafa790ab8ec78aff180703bfc9e2e400f` (PR #177).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Run one authenticated deterministic lifecycle candidate across one immutable,
chronologically ordered FL8.1 population while making **actual PAPER outcomes**
authoritative for every subsequent FLAT/OPEN strategy decision.

The exact loop is:

`FL8.1 row -> actual PAPER posture -> selected explicit FL6 evidence -> sealed Rust row evaluator -> exact lifecycle decision -> aligned PAPER execution evidence -> sealed prefix replay -> next actual posture`.

This is the first complete deterministic baseline campaign path that can emit the
same sealed `FastPolicyRunEvidence` type already consumed by the FL9 superiority
proof.

## New package

Add:

`python/src/shreks_brain/fast_deterministic_campaign/`

The package owns orchestration only.

It does not implement:

- FL6 strategy rules;
- execution economics;
- quote acquisition;
- risk rules;
- fills;
- ledger accounting;
- E11/E5 evaluation;
- superiority;
- provider/network/database access;
- subprocess launching directly;
- promotion or LIVE execution.

## Campaign row evidence

Add immutable/slotted:

`FastDeterministicCampaignRow`

Fields:

- `record: FastTrainingFeatureRecord`;
- `flat_evidence: FastOfflineRowEvidence`;
- `open_evidence: FastOfflineRowEvidence`;
- `paper_evidence: FastCampaignPaperDecisionEvidence`.

Both posture-specific strategy-evidence objects are supplied up front.

Why both?

The correct posture for a future row is not known from intended actions. It is
known only after replaying the preceding candidate-specific PAPER prefix.

Requiring both variants before execution allows the entire campaign to be
preflighted before the first process launch. The driver then selects exactly one
variant using actual session posture.

### Manifest-family alignment

For every row:

- `flat_evidence.kind` must equal the manifest lifecycle entry family;
- `open_evidence.kind` must equal the manifest lifecycle manager family.

This means:

- missing FL6.4 companion pre-migration evidence prevents that campaign from
  starting rather than being fabricated;
- execution `None`, Wallet evidence `None`, and Longer-Runner continuation
  `None` remain valid when those sealed baseline APIs explicitly support
  missing evidence as fail-closed strategy input.

## Whole-campaign preflight

Before creating/advancing a PAPER session or invoking the offline Rust binary:

1. require exact manifest and row types;
2. require a non-empty tuple of rows;
3. require explicit existing binary path;
4. require every row's FLAT/OPEN evidence families to match the manifest;
5. require every PAPER evidence source-event ID to equal
   `decision_signature:decision_ordinal`;
6. require unique source-event identity;
7. require globally strictly increasing `decision_sequence`;
8. require per-market non-decreasing decision timestamps;
9. require the existing starting PAPER ledger to have no OPEN positions through
   the sealed session constructor;
10. require exact PAPER/risk/evaluation policy types through the sealed session
    constructor.

No partial campaign is allowed after a deterministic structural preflight error.

## Runner API

Add:

`run_fast_deterministic_chronological_campaign(...)`

Inputs:

- explicit offline Rust row binary path;
- exact candidate manifest;
- ordered campaign rows;
- paper run ID;
- assessment version;
- starting PAPER ledger;
- sealed fill policy;
- sealed risk policy;
- sealed position policy;
- sealed trading evaluation policy.

Returns:

`FastDeterministicPaperSession`

The final non-empty session must have `latest_result`.

Therefore the caller receives, without a new PnL/proof model:

- exact ordered lifecycle decisions;
- exact ordered execution evidence;
- final PAPER ledger;
- BUY and position-action outcomes;
- E11 evaluation capture;
- E5 trading evaluation;
- `FastPolicyRunEvidence`.

## Sequential algorithm

For each preflighted row:

1. derive market key exactly as
   `venue:mint:quote_mint`;
2. call `fast_deterministic_paper_session_posture(session, market_key)`;
3. select `flat_evidence` or `open_evidence` from that actual posture;
4. call the sealed
   `evaluate_fast_deterministic_row_offline(...)`;
5. require the authenticated adapter-returned decision;
6. call
   `apply_fast_deterministic_paper_session_step(session, decision, paper_evidence)`;
7. use the returned immutable session for the next row.

The driver never predicts whether a BUY filled or an exit succeeded. Only the
sealed PAPER prefix result changes posture.

## Determinism / complexity

The session layer intentionally replays the whole PAPER prefix after every row,
so the campaign driver is O(n²) in PAPER replay work.

At FL9 this is acceptable and desirable:

- offline/research only;
- deterministic;
- maximally auditable;
- no second incremental ledger implementation.

Optimization belongs after evidence is proven.

## Tests

RED first.

Tests prove:

1. whole-campaign sequence regression fails before the fake binary launches;
2. wrong FLAT/OPEN evidence family fails before launch;
3. PAPER evidence source identity mismatch fails before launch;
4. successful BUY on row 1 makes row 2 use OPEN manager evidence;
5. unavailable BUY on row 1 keeps row 2 FLAT and reuses entry-family evidence;
6. successful BUY then SELL closes the authoritative PAPER position;
7. final session carries sealed `FastPolicyRunEvidence` with every campaign row;
8. returned decision/evidence order equals FL8.1 campaign order;
9. direct strategy/PAPER formulas are absent from the driver;
10. driver contains no subprocess/provider/network/database/promotion/LIVE authority.

Fake binaries prove orchestration only. Rust row semantics remain proven by the
sealed Rust protocol and adapter slices.

## Following slice

Run a **deterministic candidate matrix** over the same immutable FL8.1 population:

- one campaign per required deterministic candidate manifest;
- identical PAPER quote/risk/evaluation policy population where applicable;
- candidate-specific strategy evidence only where the FL6 family requires it;
- collect each final session's sealed `FastPolicyRunEvidence`;
- verify same population fingerprints;
- pass all baseline run evidence to the sealed FL9 superiority evaluator beside
  the learned candidate run.

No profitability claim is allowed until real non-fixture chronological evidence
returns `SUPERIOR`.
