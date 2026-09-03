# FL9 PAPER/Shadow Superiority Proof — Design

**Date:** 2026-09-03

## Status

Design for the evidence/proof work required to close the FL9 exit criterion after the continuous-action policy implementation was SEALED.

Base: FL9 policy implementation merged-main commit `1731ce4f9cb5943b7b9971b2150db03ae5a9a6c4` with push-triggered CI `33811322808` four-gate GREEN.

LIVE remains disabled.

## Source-of-truth requirement

The build order requires:

> The approved champion produces stable, auditable continuous action decisions and beats the best deterministic baseline in PAPER/shadow evaluation.

The repository currently contains no committed real PAPER database, parquet bundle, CSV, JSONL, or other empirical trading-evidence dataset for the learned FL9 policy. Therefore this phase can build and seal the **measurement/proof pipeline**, but fixture tests must never be described as economic edge, profitability, or satisfaction of the FL9 exit criterion.

Actual FL9 exit remains contingent on real PAPER/shadow evidence passing the sealed proof pipeline.

## Existing authorities to reuse

This work must not invent a second simulator or a second PnL model.

Reuse unchanged:

- FL7 Fast PAPER event loop for event-resolution decisions;
- C1/C3 PAPER execution and ledger accounting for fills, costs, quantities, realized PnL, partial fills, and reductions;
- E11 `paper_evaluation` evidence models and `build_evaluated_trades` for normalized closed-trade economics;
- E5 `evaluation` for deterministic after-cost metrics;
- E12/E8 governance concepts for sample sufficiency, drawdown/cost controls, and baseline expectancy advantage.

Do not invoke E8 promotion, E12 registry promotion proof, registry mutation, signer/submission, or LIVE authority.

## Problem 1 — E11 extraction is legacy-cycle-specific

The existing `extract_paper_evaluation_evidence(...)` consumes a legacy `PaperCycleResult`. FL7 Fast PAPER produces:

- `FastPaperActionAssessment`;
- C1 `PaperExecutionResult`;
- C3 `PaperLedgerUpdate`;
- immutable Fast PAPER loop state.

The economic evidence is already sufficient, but there is no adapter that converts those Fast PAPER authorities into the sealed E11 evidence models.

### Decision: add a pure Fast PAPER → E11 adapter

Add:

`python/src/shreks_brain/paper_evaluation/fast.py`

The adapter is measurement-only. It consumes already-produced execution/ledger evidence and never generates a fill. It is an additive module API under `shreks_brain.paper_evaluation.fast`; the sealed E11 package-level `shreks_brain.paper_evaluation` public surface remains unchanged.

### Public version and sentinel

```python
FAST_PAPER_EVALUATION_ADAPTER_VERSION = "fl9-fast-paper-evaluation-v1"
FAST_PAPER_SCORE_POLICY_SENTINEL = "not-applicable:fast-lane-score"
```

The sentinel is explicit because Fast Lane does not use the legacy score-policy layer. It is not a fabricated score version.

### `FastPaperEvaluationIdentity`

Immutable, slotted:

- `version`
- `paper_run_id`
- `candidate_version`
- `candidate_fingerprint_sha256`
- `strategy_version` — candidate/run-level attribution used by sealed E11 evidence
- `allowed_assessment_strategy_versions` — canonical tuple of actual Fast PAPER assessment/journal strategy versions that may contribute to this candidate run, including an explicitly approved protective-exit component when applicable

Rules:

- exact adapter version;
- all identifiers non-empty;
- candidate fingerprint lowercase SHA-256;
- allowed assessment strategy versions non-empty, unique, lexical.

This explicitly separates candidate-level evaluation attribution from component action/protective policy versions.

### `FastPaperEntryEvaluationContext`

Immutable, slotted:

- `source_event_id`
- `market_regime: MarketRegime`

One context is required for every opening BUY assessment that becomes an applied position-opening fill. The setup name comes from `assessment.strategy_family`; the Fast Lane decision-policy version comes from `assessment.strategy_version`; the legacy score-policy field receives the explicit not-applicable sentinel.

No regime is inferred from later data.

### `FastPaperExecutionEvidenceInput`

Immutable, slotted:

- `assessment: FastPaperActionAssessment` — the assessment that authorized this exact execution;
- `execution: PaperExecutionResult`;
- `ledger_update: PaperLedgerUpdate`.

The input is intentionally generic across BUY/REDUCE/SELL. Callers may construct it from FL7 BUY and position-action results, but the adapter validates the authoritative journal/execution/assessment relationship itself.

Validation includes:

- ledger update is APPLIED;
- execution is terminal (FAILED/PARTIAL/FILLED), never DEFERRED;
- final journal entry matches execution identity, mint, side, state, reason, paper policy, costs, fill quantity/notional;
- journal strategy version equals the authorizing assessment strategy version;
- assessment strategy version is explicitly allowed by the run identity;
- BUY execution requires BUY assessment;
- SELL execution requires REDUCE or SELL assessment;
- opening BUY requires exactly one point-in-time entry context;
- no duplicate ledger sequences or duplicate opening provenance;
- candidate-level E11 attribution is the explicit run identity, while actual component strategy versions remain verified at the adapter boundary.

The adapter produces the existing exact E11 types:

`PaperEvaluationCapture(entry_provenance, executions, closures, orphan_costs)`

and can therefore flow unchanged through `build_evaluated_trades` and E5 evaluation.

### Failure and orphan costs

Applied failed executions with a position ID remain execution evidence.

Applied failed executions without a position ID but with positive explicit cost become E11 orphan-cost evidence. Existing `build_evaluated_trades` then blocks normalization rather than silently dropping cost.

This preserves sealed E11 fail-closed semantics.

## Problem 2 — no FL9-specific, promotion-free superiority report

E8 already knows how to compare expectancy against required baselines, but it is coupled to the legacy registry and promotion workflow. FL9 needs a measurement/proof report that cannot promote anything.

### Decision: add `shreks_brain.fast_policy_proof`

Package:

```text
python/src/shreks_brain/fast_policy_proof/
  __init__.py
  models.py
  engine.py
  codec.py
```

It has no provider, network, SQLite, registry mutation, promotion, execution, signer, or LIVE authority.

## Run evidence

### `FastPolicyRunEvidence`

Immutable, slotted:

- schema/version fields;
- `paper_run_id`;
- `candidate_version`;
- `candidate_fingerprint_sha256`;
- `strategy_version`;
- exact `TradingEvaluationEvidence`;
- `event_population_fingerprint_sha256`;
- `action_journal_fingerprint_sha256`;
- `material_update_count`;
- `decision_count`;
- `distinct_market_count`;
- `observed_from_unix_ms`;
- `observed_through_unix_ms`;
- `run_evidence_fingerprint_sha256`.

### `build_fast_policy_run_evidence(...)`

Inputs:

- explicit paper-run/candidate identity;
- one sealed `FastPaperLoopState`;
- one exact E5 `TradingEvaluationEvidence`.

The builder computes two separate fingerprints:

1. **event population fingerprint** from point-in-time update identity only (event ID, update fingerprint, market key, sequence, timestamp, material flag), excluding decisions;
2. **action journal fingerprint** from the recorded assessment material.

This allows learned-policy and deterministic-baseline runs to prove they evaluated the same event population while still producing different decisions.

For every material accepted record, an assessment must exist. Thus:

`decision_count == material_update_count`.

No material decision may occur after the run/evaluation evidence window. Closed E5 trades must lie within the observed run window.

The builder does not read wall-clock time.

## Superiority policy

### `FastPolicySuperiorityPolicy`

Caller-supplied; no production defaults:

- `version`
- `required_baseline_versions` — unique lexical tuple
- `min_material_decision_count`
- `min_distinct_market_count`
- `min_evaluation_span_ms`
- `min_trade_count`
- `min_distinct_traded_mint_count`
- `min_net_expectancy_pct`
- `min_profit_factor`
- `max_drawdown_pct`
- `max_cost_burden_pct`
- `max_single_winner_share_of_positive_pnl`
- `min_baseline_expectancy_advantage_pct`

Thresholds are evidence policy, not trading policy.

## Comparable baseline rule

A baseline is comparable only if:

- its candidate version is declared in `required_baseline_versions`;
- its run evidence uses the exact same event-population fingerprint as the learned candidate;
- its E5 `TradingEvaluationPolicy` object equals the candidate policy exactly;
- its run evidence is internally valid;
- it has enough trade evidence to define net expectancy.

All declared baselines must be present exactly once.

The **best deterministic baseline** is the comparable required baseline with the highest after-cost `net_expectancy_pct`. Ties are broken lexically by candidate version.

The candidate must beat that best baseline by at least:

`min_baseline_expectancy_advantage_pct`.

This is equivalent to beating every required baseline by the same margin, but the report records the best baseline explicitly because that is the FL9 exit wording.

## Proof decision

Enums:

```python
FastPolicyProofDecision:
    SUPERIOR
    INSUFFICIENT_EVIDENCE
    FAILED

FastPolicyProofGateStatus:
    PASS
    FAIL
    INSUFFICIENT
```

Gate families:

- candidate/evaluation provenance;
- event-population comparability;
- evaluation-policy comparability;
- required baseline coverage;
- minimum material decisions;
- minimum distinct markets;
- minimum evaluation span;
- minimum closed trades;
- minimum distinct traded mints;
- minimum after-cost expectancy;
- minimum profit factor;
- maximum drawdown;
- maximum cost burden;
- maximum single-winner concentration;
- best-baseline expectancy advantage.

Integrity contradictions are FAIL.

Missing sample/undefined metrics are INSUFFICIENT.

Economic threshold misses are FAIL.

Decision precedence:

- any FAIL → FAILED;
- else any INSUFFICIENT → INSUFFICIENT_EVIDENCE;
- otherwise → SUPERIOR.

`SUPERIOR` is an evidence conclusion only. It performs no promotion and enables no runtime mode.

## Canonical report

`FastPolicySuperiorityReport` records:

- candidate/run/evaluation identities;
- exact baseline evaluation identities;
- best baseline identity and expectancy;
- candidate expectancy;
- expectancy advantage;
- population fingerprint;
- ordered gate results;
- decision;
- canonical SHA-256 fingerprint.

`codec.py` provides pure canonical JSON encode/decode. It does not write files or mutate stores.

## Empirical evidence boundary

Passing unit/integration fixtures proves only:

- the Fast PAPER accounting bridge is correct;
- the comparator is deterministic and fail-closed;
- candidate/baseline populations cannot silently differ;
- costs and E5 metrics are preserved;
- superiority cannot be declared with missing baseline/sample evidence.

Fixtures do **not** prove:

- positive expectancy in real markets;
- superiority over FL6 on real data;
- profitability;
- readiness for FL10/FL11/FL12;
- LIVE readiness.

Actual FL9 exit requires feeding real PAPER/shadow evidence through this sealed pipeline and obtaining a `SUPERIOR` report under an explicit approved evidence policy.

## Scope firewall

Forbidden from this phase:

- training/retraining;
- model/champion selection;
- registry promotion;
- self-promotion;
- provider/network calls;
- transaction construction/signing/submission;
- production runtime wiring;
- LIVE enablement;
- fabricated fills;
- synthetic profitability claims.

LIVE remains disabled.
