# Phase G1B Paper Campaign Coordinator — Design

**Date:** 2026-08-25  
**Base:** sealed G1 `945c66d3ea725a0aebd8ba86bb71ad8c4f3e0463`  
**Purpose:** complete the missing multi-token paper-orchestration primitive needed to turn continuous observer/evidence collection into one restart-safe real paper campaign.

## Boundary

G1B is paper-only orchestration. It does not add provider credentials, registry mutation, promotion, live execution, transaction construction, signing, submission, or wallet authority. It reuses sealed E15/C5/C6/E11 behavior rather than creating a parallel paper engine.

`RegistryCandidate` continues to mean the approved strategy/model attribution for one paper run. It is **not** a token opportunity. One G1B coordinator owns one `RegistryCandidate`, one `paper_run_id`, one shared `PaperLoopState`, one E11 evidence ledger, and one checkpoint chain while evaluating multiple observer token candidates.

## Why sequential E15 runners are not sufficient

E15 `ObserverPaperCampaignRunner` assembles exactly one observer candidate per call and advances the shared paper checkpoint. Calling multiple single-candidate runners at one timestamp is incorrect: the first completed call advances `last_cycle_at_unix_ms`, and later calls at the same timestamp become idempotent replays. Advancing synthetic timestamps per token would distort point-in-time evidence and would under-monitor open positions.

C5 already supports multiple `PaperEntryCandidate` values and multiple independent open-position exit observations in one `PaperCycleInput`, while permitting at most one new BUY attempt per cycle. G1B therefore assembles one aggregate cycle and invokes C5 once per campaign timestamp.

## Candidate selection

A new read-only coordinator selection policy contains only explicit operational bounds:

- `recent_lookback_ms`
- `max_entry_candidates`

No default is supplied. Candidate discovery is point-in-time and uses the authoritative observer SQLite database in read-only mode.

Every cycle includes three classes of mint, deduplicated by mint:

1. every mint with an OPEN managed paper position, regardless of recent-entry selection bounds, so exits remain monitored;
2. the pending-entry mint, if any, regardless of the recent-entry bounds, so deferred C1 execution can resolve;
3. a bounded set of recently active observer candidates whose latest market snapshot is at or before the cycle timestamp and within the explicit lookback.

Ambiguous mint-to-observer-candidate identity fails closed. Missing/invalid schema or malformed rows fail closed. Selection never creates or migrates the database.

## Per-candidate assembly

The coordinator receives one exact `ObserverFreshLaunchPolicyBundle` template. For each selected observer candidate it derives only the candidate-specific ENTRY quote identity (`candidate_id` and output mint); all strategy, safety, regime, score, decision, risk, exit, quote-asset, amount, taker, slippage, freshness, and policy-version values remain the caller-supplied sealed bundle values.

Each candidate is assembled with the sealed E15 `assemble_observer_paper_cycle` against the **same restored `PaperLoopState` and same `as_of_unix_ms`**. This preserves point-in-time comparability and prevents cross-candidate state mutation during evidence reconstruction.

## Entry ordering

C5 intentionally ships no strategy-ordering default, and C5 consumes entry candidates in tuple order. G1B therefore makes ordering explicit and deterministic without inventing a new threshold:

- compute each Fresh Launch setup assessment using the sealed setup engine;
- compute B7 score using the candidate's sealed score policy;
- sort regular entry opportunities by descending sealed total score;
- break ties by observer `candidate_id`, then mint.

Managed-position and pending-entry candidates may be assembled first for evidence completeness, but they do not gain priority for a new BUY: OPEN mints are rejected by C5's same-mint anti-pyramiding rule and a pending entry already occupies C5's single entry slot.

The coordinator never bypasses B8 decision or B9 risk. Ranking only determines which already-sealed candidate evaluation C5 sees first when more than one candidate could consume the one BUY slot.

## Aggregate cycle

The coordinator merges component assemblies into exactly one `PaperCycleInput`:

- unique entry candidate per mint;
- all exit observations for positions open at cycle start;
- at most one purpose-correct quote per mint, consistent with E15 pending-entry/open-position quote semantics;
- one shared timestamp.

Contradictory duplicate mint, quote, or position evidence fails closed. The aggregate audit records the selected observer candidate identities, ranked entry order, and component E15 audit fingerprints.

## Restart/evidence semantics

G1B reuses the E15 runner's existing C6/E11 commit sequence:

1. load E11 evidence and latest checkpoint;
2. validate accounting and attribution;
3. assemble one point-in-time aggregate cycle;
4. run sealed C5 once;
5. validate resulting accounting;
6. record E11 evidence before checkpoint;
7. save the next checkpoint sequence;
8. reload and prove restart equivalence.

To avoid duplicating this transaction logic, E15 runner internals may be refactored into a private helper used by both the existing single-candidate runner and the new coordinator. The public E15 single-candidate behavior and `__all__` contract must remain unchanged unless G1B explicitly adds the coordinator to the package surface after an authority-firewall RED test.

## Fail-closed behavior

A campaign cycle fails instead of guessing when:

- selection schema/data is invalid;
- a required managed/pending mint cannot be resolved unambiguously;
- any selected candidate cannot be assembled safely;
- candidate-specific bundle derivation contradicts quote identity;
- aggregate duplicates conflict;
- C5 execution raises;
- accounting becomes invalid;
- E11 attribution/evidence is contradictory;
- checkpoint persistence/reload/restart equivalence fails.

Provider no-route/degradation semantics remain those already sealed by G1/E15. No synthetic quote/fill is introduced.

## Runtime/deployment boundary

This slice builds the reusable Python multi-token coordinator and its authority-limited public API. A later G1 runtime-bootstrap slice will bind it to an immutable campaign configuration artifact and systemd process. That bootstrap must not hard-code strategy thresholds or make registry/promotion decisions.

## Proof standard

Synthetic/static fixtures prove mechanics only. G1B does not claim profitability. After runtime bootstrap/deployment, a real independent paper campaign must accumulate point-in-time trades and be evaluated through E10/E11/E12 for expectancy after costs, drawdown, independent sample/mint/time coverage, cost burden/winner concentration, and reproducibility.

**LIVE TRADING REMAINS DISABLED.**
