# FL9 Deterministic Lifecycle PAPER Adapter — Design

**Date:** 2026-09-04

## Status

Design after deterministic candidate manifest merged as `612e96f4efb6f38589f98b7a2bc8a0d057e85046` (PR #173).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Execute canonical deterministic lifecycle decisions through the already-sealed FL7 Fast Campaign PAPER execution/evaluation chain using the real deterministic candidate manifest identity.

Do not create a second PAPER execution path.

## Inputs

The deterministic adapter accepts:

- exact `FastDeterministicCandidateManifest`;
- exact `FastDeterministicLifecycleResults`;
- explicit `paper_run_id`;
- explicit assessment version;
- ordered `FastCampaignPaperDecisionEvidence`;
- starting PAPER ledger;
- sealed fill/risk/position/evaluation policies.

The adapter derives candidate identity directly from the manifest:

- candidate version;
- candidate fingerprint;
- fixed deterministic strategy family;
- strategy version.

Caller does not retype candidate identity.

## Required alignment

Before execution:

1. manifest and lifecycle results must be exact types;
2. lifecycle result policy must equal the manifest lifecycle policy exactly;
3. result rows remain ordered and exact;
4. deterministic FLAT rows normalize current exposure to `0.0` for the shared execution core;
5. OPEN rows must carry explicit current exposure;
6. deterministic assessment translation uses the sealed lifecycle translator and manifest strategy attribution.

## One shared execution core

Refactor `fast_campaign_paper.engine`:

### Learned front-end

Existing public `run_fast_campaign_paper_candidate(...)` keeps its signature and behavior.

It converts each learned result into a private common decision view:

- identity;
- action;
- current/target exposure;
- prebuilt `FastPaperActionAssessment`.

### Deterministic front-end

Add:

`run_fast_deterministic_lifecycle_paper_candidate(...)`

It converts each deterministic lifecycle result into the same private common decision view.

### Shared core

One private execution core owns all:

- population/evidence alignment;
- event-loop application;
- posture tracking;
- BUY risk + fill execution;
- HOLD/REDUCE/SELL position execution;
- exposure tracking;
- E11 extraction;
- evaluated trade normalization;
- trading evaluation;
- Fast Policy run evidence.

There is only one implementation of fill, ledger, risk, position, E11, E5/run-evidence behavior.

## Deterministic semantics

FLAT:
- SKIP -> shared current `0.0`, target `0.0`;
- BUY -> shared current `0.0`, target explicit manifest lifecycle target.

OPEN:
- HOLD -> explicit current == target;
- REDUCE -> explicit current > target > 0;
- SELL -> explicit current > 0, target `0.0`.

The canonical lifecycle wire has already validated these semantics. The shared execution core independently checks them again.

## Evidence rules remain unchanged

SKIP:
- no unused quote/risk/entry/regime evidence.

BUY:
- explicit contemporaneous quote;
- explicit RiskContext;
- explicit entry authority;
- point-in-time MarketRegime.

HOLD/REDUCE/SELL:
- explicit quote;
- no BUY-only risk/entry/regime evidence.

Unavailable quotes never become synthetic fills.

Forecast prices are never PAPER fill prices.

## Result

Return the existing exact `FastCampaignPaperRunResult`.

That preserves existing E11/E5/Fast Policy proof consumers without a new result/evidence format.

## TDD

New deterministic adapter tests prove:

- manifest identity is propagated into E11/run evidence;
- policy mismatch fails before execution;
- skip-only deterministic run is deterministic;
- BUY -> REDUCE -> SELL uses real sealed PAPER fills and closes one evaluated trade;
- REDUCE quantity comes from target/current exposure fraction;
- unavailable BUY quote cannot create a fill;
- learned executor regression tests remain GREEN;
- source contains one shared execution core, not copied execution code.

## Authority boundary

This adapter may invoke the already-sealed PAPER/risk/evaluation authorities because that is its explicit purpose.

It does not:

- fetch providers;
- fabricate quotes;
- infer missing evidence;
- execute LIVE;
- sign transactions;
- promote candidates;
- claim superiority.

## Next slice

Use this adapter to create actual same-population deterministic baseline PAPER run evidence, normalize it through E11/E5, and feed each candidate into the sealed FL9 learned-vs-best-deterministic superiority report.

Infrastructure fixtures still do not prove profitability.
