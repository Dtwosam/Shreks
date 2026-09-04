# FL9 Learned Chronological PAPER Campaign — Design

**Date:** 2026-09-04

## Status

Implementation slice after the installable deterministic campaign launcher merged as
`ae4885747180debc5adc305375c7f0cd4259c38d` (#196).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Produce the missing learned-candidate `FastPolicyRunEvidence` on chronological, point-in-time-safe FL8.1 evidence using the approved FL8.5 forecast champion and FL9 continuous-action policy.

The learned candidate must operate on actual PAPER position state after prior execution outcomes. It may not evaluate later rows using an assumed fill or a statically precomputed posture.

The output remains PAPER evidence only. No superiority or promotion decision is made by this driver.

## Execution topology

For each ordered FL8.1 row:

1. reconstruct the actual learned candidate PAPER posture from the prior sealed PAPER prefix;
2. select explicit FLAT or OPEN action constraints for that posture;
3. extract the sealed 169-feature forecast vector from the FL8.1 row;
4. append the exact learned request to the prefix;
5. run the existing Rust `shreks-fast-campaign-decision` binary over the complete request prefix;
6. strict-decode the Rust-authored result and verify request/result population identity;
7. require all prior Rust decisions to exactly equal the previous prefix;
8. require champion provenance to equal the authenticated FL8.5 champion file;
9. materialize action-compatible contemporaneous PAPER evidence;
10. re-run the existing learned PAPER executor on the full decision/evidence prefix;
11. use the resulting actual PAPER ledger/fills to determine the next posture.

The final PAPER result contains the sealed learned `FastPolicyRunEvidence`.

## Why full-prefix Rust evaluation is required

Rust result documents carry the canonical batch fingerprint.

The Python driver therefore does not synthesize or mutate a Rust decision result for one row.

Instead, every new state-aware request is appended and the complete prefix is evaluated again by Rust.

Before the new row may be applied to PAPER, all earlier decisions must exactly match their previously authenticated values.

This simultaneously preserves a genuine Rust-authored batch fingerprint and detects any champion/inference/policy drift during one chronological campaign.

## Offline Rust adapter

New package:

`shreks_brain.fast_campaign_offline`

Public API:

`evaluate_fast_campaign_decision_batch_offline(...)`

Inputs:

- explicit Rust decision-binary path;
- explicit FL8.5 champion path;
- exact `FastCampaignDecisionBatch`.

The adapter:

- emits the existing canonical Python request codec;
- writes one private temporary request file;
- invokes the binary with `shell=False`;
- captures stdout/stderr;
- strict-decodes the existing Rust result codec;
- verifies result length and exact source-event/market/sequence/time identity;
- verifies result policy version equals the request policy;
- removes the temporary request file.

It has no provider, SQLite, PAPER execution, superiority, promotion, signing, submission, or LIVE authority.

## Learned row contract

`FastLearnedCampaignRow` carries:

- exact `FastTrainingFeatureRecord`;
- explicit FLAT `FastCampaignActionConstraints`;
- explicit OPEN `FastCampaignActionConstraints`;
- the same raw point-in-time PAPER evidence envelope already used by deterministic baselines.

The constraints are explicit evidence. The driver does not invent execution economics.

Actual current exposure is never taken from the row. It is reconstructed from prior PAPER outcomes.

## Shared PAPER evidence

The deterministic-only action materializer is refactored into a shared action-aware primitive:

`materialize_fast_campaign_paper_evidence(...)`

The existing deterministic wrapper delegates to it unchanged.

Semantics remain:

- `SKIP`: no execution fields materialized;
- `BUY`: explicit ENTRY quote + RiskContext + entry authority + MarketRegime required;
- `HOLD`/`REDUCE`/`SELL`: explicit EXIT/action quote required.

Thus learned and deterministic candidates can consume the same contemporaneous PAPER evidence while making different decisions.

## Learned candidate provenance

A superiority candidate fingerprint must not be arbitrary caller text.

Schema:

`shreks.fast_learned_campaign_candidate` v1.

The candidate fingerprint binds:

- candidate version;
- exact FL8.5 champion version;
- exact FL8.5 champion fingerprint;
- exact continuous-action policy;
- strategy family;
- strategy version;
- assessment version.

Floating-point policy values are fingerprinted through exact hexadecimal float representation.

The PAPER run id is intentionally excluded because it identifies an evaluation run, not the candidate semantics.

Public helpers:

- `fast_learned_campaign_candidate_fingerprint_sha256(...)`
- `build_fast_learned_campaign_identity(...)`

The chronological driver recomputes this fingerprint from the authenticated champion and policy and rejects a mismatching identity before Rust executes.

## Champion and chronology gates

The Python driver independently reads the champion through the sealed FL8.5 codec.

Every Rust result must return the same:

- champion version;
- champion fingerprint.

Every FL8.1 row must also satisfy:

- feature schema version equals the champion feature schema version;
- champion selection time is not later than the decision time;
- the maximum training decision time across the exact active members used by the policy is strictly earlier than the decision time.

The active member set mirrors Rust exactly for every configured horizon:

- endpoint cost-adjusted return;
- endpoint return;
- MAE;
- reversal occurrence;
- route-unavailability occurrence.

Unrelated champion horizons/targets do not unnecessarily discard otherwise valid unseen evaluation rows.

This prevents pre-selection/training leakage from entering learned PAPER proof.

## Actual PAPER posture reconstruction

For each market, posture is reconstructed from the authoritative prefix PAPER result.

A filled BUY creates OPEN posture using the exact selected target exposure.

Failed/unfilled BUY leaves the market FLAT.

SELL removes the reconstructed OPEN market.

REDUCE replaces current exposure with the exact selected target exposure.

The reconstructed position id must correspond to an authoritative OPEN position in the final PAPER ledger.

Any missing, extra, contradictory, or misordered BUY/position result fails closed.

## Failure behavior

The learned campaign fails before the next economic step on:

- invalid/missing binary or champion;
- malformed champion;
- candidate fingerprint mismatch;
- feature-schema mismatch;
- pre-selection/training row;
- duplicate or non-chronological rows;
- Rust request/result population mismatch;
- Rust policy mismatch;
- Rust champion mismatch;
- historical Rust prefix drift;
- PAPER posture/result contradiction;
- action-incompatible quote/risk/entry evidence.

There is no partial immutable proof artifact in this slice.

## Authority boundary

This slice does not:

- access providers/network;
- choose or promote a champion;
- evaluate FL9 superiority;
- sign or submit transactions;
- enable LIVE;
- change runtime service topology.

It is offline/PAPER evidence plumbing.

## TDD provenance

Intentional RED commits:

- `d8599cbc3bc3f81d83ec3bca973a08c02cb5ebe2` — offline learned Rust prefix adapter absent;
- `b15f8cda35415eefc87301720965573651fee05f` — learned chronological driver absent.

Tests cover:

- canonical Rust request execution;
- request/result population mismatch rejection;
- actual filled PAPER posture feeding the next Rust request;
- historical Rust decision drift rejection before the next PAPER apply;
- learned candidate fingerprint binding;
- pre-selection evidence rejection;
- authority firewalls.

## Following slice

Bind the learned run to the immutable #193/#195 deterministic campaign invocation so one authenticated comparison artifact contains:

- the exact baseline campaign invocation;
- the exact learned candidate identity;
- the learned `FastPolicyRunEvidence`;
- population parity proof;
- then, only after parity passes, the already-sealed FL9 superiority report.

Real non-fixture evidence is still required before any profitability claim.
