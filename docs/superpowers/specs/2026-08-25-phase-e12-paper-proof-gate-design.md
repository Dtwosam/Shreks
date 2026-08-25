# Phase E12 Paper Proof Gate Design

## Purpose

Phase E12 closes the remaining proof-path gap between sealed E8 historical/shadow promotion eligibility and sealed E11 restart-safe paper-trade evidence.

The master source of truth requires a challenger to run in paper/shadow mode and forbids live money until Shreks demonstrates sufficient independent paper-trade sample size, positive expectancy after realistic costs, acceptable drawdown, stable/reproducible evidence, and no unresolved accounting/execution defects.

E8 already evaluates point-in-time historical E5 evidence, baselines, calibration, winner concentration, registry identity, and E7 shadow coverage. E11 now provides trustworthy paper-run `EvaluatedTrade` evidence after realistic C1/C3/C5 execution/accounting. What is still missing is a deterministic gate that proves the paper-run evidence is genuinely derived from E11, reconciles to a sealed E10 evaluation bundle, and meets explicit paper-specific sample/economic/risk thresholds.

E12 adds that gate. It does not alter E8, E10, E11, the registry, paper execution, or any live path.

Base exactly on sealed E11 head `1b19a6dc5828be33e4c9553a06b3f7379396ddfc`.

## Chosen architecture

Create a focused `shreks_brain.proof` package with four responsibilities:

1. immutable E12 policy/gate/assessment models;
2. a pure evaluator that composes sealed E6/E8/E10/E11 evidence;
3. canonical assessment fingerprinting and append-only persistence;
4. an explicit public API with an authority firewall.

E12 consumes, but does not mutate:

- current E6 `ChampionChallengerRegistry`;
- a sealed E8 `PromotionAssessment`;
- one explicit `paper_run_id`;
- the sealed E11 `PaperEvaluationLedger` containing that run;
- one sealed E10 `TradingEvaluationEvidence` built from the E11-derived trades;
- caller-supplied `PaperProofPolicy` thresholds;
- caller-supplied evaluation timestamp.

The core composition is:

```text
E8 historical/shadow assessment
  + current E6 candidate identity
  + E11 paper ledger/run
  -> rebuild exact paper EvaluatedTrade tuple
  -> require equality with E10 paper source evidence
  -> evaluate explicit paper sample/economic/risk gates
  -> CandidateProofAssessment
```

A `SUFFICIENT` E12 result is still only evidence. It is not a registry status change and is not live authorization.

## Schema and public API

Schema version:

```text
e12-paper-proof-v1
```

Public exports exactly:

- `PAPER_PROOF_SCHEMA_VERSION`
- `PaperProofDecision`
- `PaperProofGateStatus`
- `PaperProofGateCode`
- `PaperProofPolicy`
- `PaperProofGateResult`
- `CandidateProofAssessment`
- `CandidateProofAssessmentStore`
- `evaluate_candidate_proof`

No public method or symbol may mutate the registry, create/execute trade intents, sign/submit transactions, change operating mode, or enable live money.

## Policy

`PaperProofPolicy` has no defaults. Every threshold is explicit and versioned:

- `version: str`
- `min_trade_count: int`
- `min_distinct_mint_count: int`
- `min_evaluation_span_ms: int`
- `min_net_expectancy_pct: float`
- `min_profit_factor: float`
- `max_drawdown_pct: float`
- `max_cost_burden_pct: float`
- `max_single_winner_share_of_positive_pnl: float`

Numeric thresholds are caller inputs. E12 does not invent “profitable” thresholds.

## Gate semantics

`PaperProofGateStatus` values:

- `PASS`
- `FAIL`
- `INSUFFICIENT`

`PaperProofDecision` precedence:

1. any `FAIL` -> `FAILED`;
2. otherwise any `INSUFFICIENT` -> `INSUFFICIENT_EVIDENCE`;
3. otherwise -> `SUFFICIENT`.

`SUFFICIENT` means only that the supplied evidence satisfies the explicit E12 paper-proof policy and the referenced E8 assessment was already eligible.

## Gate set

Stable gate codes, in lexical order:

- `E8_ASSESSMENT_ELIGIBLE`
- `E8_REGISTRY_PROVENANCE`
- `PAPER_EVIDENCE_PROVENANCE`
- `MIN_PAPER_TRADE_COUNT`
- `MIN_PAPER_DISTINCT_MINT_COUNT`
- `MIN_PAPER_EVALUATION_SPAN`
- `MIN_PAPER_NET_EXPECTANCY_PCT`
- `MIN_PAPER_PROFIT_FACTOR`
- `MAX_PAPER_DRAWDOWN_PCT`
- `MAX_PAPER_COST_BURDEN_PCT`
- `MAX_PAPER_SINGLE_WINNER_SHARE`

### E8 assessment eligibility

The referenced `PromotionAssessment` must belong to the same candidate.

- E8 `ELIGIBLE` -> PASS.
- E8 `INSUFFICIENT_EVIDENCE` -> INSUFFICIENT.
- E8 `INELIGIBLE` -> FAIL.

E12 never reruns or changes E8 thresholds.

### E8 / current registry provenance

Require:

- candidate exists in the supplied registry;
- candidate fingerprint equals E8 assessment candidate fingerprint;
- registry fingerprint equals E8 assessment registry fingerprint;
- candidate is still current `CHALLENGER`.

Any mismatch is FAIL, because evidence from a different registry state must not be silently reused.

### Paper evidence provenance

E12 rebuilds exact trades from the E11 ledger by calling sealed `build_evaluated_trades(...)` using the explicit run and candidate.

It then requires:

- E10 evidence candidate equals the candidate;
- E10 `trades` equal the rebuilt E11 trade tuple byte-for-value;
- E10 report is already internally reconstructed from its E5 policy/source evidence by the sealed `TradingEvaluationEvidence` invariant;
- every rebuilt trade belongs to the candidate;
- E11 document fingerprint is valid by construction of `PaperEvaluationLedger`.

Missing E11 provenance, orphan failed-entry costs, accounting/fill mismatch, or any other E11 reconciliation defect propagates as a hard `ValueError`; E12 never downgrades corrupted/biased evidence into a normal gate result.

A clean mismatch between E11-derived trades and the supplied E10 bundle is `PAPER_EVIDENCE_PROVENANCE = FAIL`.

## Paper metrics

Use the sealed E10/E5 report for expectancy, profit factor, drawdown, and cost burden after proving its trades exactly equal E11-derived paper trades.

Use the exact rebuilt trade tuple for:

- trade count;
- distinct mint count;
- evaluation span from earliest `opened_at_unix_ms` to latest `closed_at_unix_ms`;
- largest positive trade share of total positive net PnL.

Single-winner share is undefined when there is no positive trade, which makes that gate `INSUFFICIENT`.

Minimum sample/span gates are `INSUFFICIENT` when below threshold.

Undefined profit factor or expectancy is `INSUFFICIENT`.

Economic/risk values that exist but miss thresholds are `FAIL`.

## Assessment identity and fingerprint

`CandidateProofAssessment` records:

- schema version;
- policy version;
- candidate version/fingerprint;
- registry fingerprint;
- E8 assessment fingerprint;
- paper run id;
- E11 paper ledger fingerprint;
- E10 paper evaluation fingerprint;
- canonical paper trade evidence fingerprint;
- evaluated timestamp;
- every gate exactly once in lexical order;
- overall decision;
- assessment fingerprint.

The assessment fingerprint hashes canonical material with the assessment fingerprint field zeroed. Floats use exact `.hex()` normalization before hashing, matching the existing evaluation/promotion provenance style.

## Persistence

`CandidateProofAssessmentStore(path)` exposes only:

```text
load() -> tuple[CandidateProofAssessment, ...]
append(assessment) -> tuple[CandidateProofAssessment, ...]
```

Identity:

```text
(candidate_version, policy_version, paper_run_id, evaluated_at_unix_ms)
```

Rules:

- identical duplicate append is byte-for-byte idempotent;
- conflicting same identity fails closed;
- canonical ordering is deterministic;
- load validates exact schema/field sets/enums/numbers/fingerprints;
- write uses sibling `.tmp`, flush, `os.fsync`, atomic `os.replace`, best-effort cleanup;
- no delete/rewrite/update/registry/live method exists.

## Error handling

Raise `ValueError` for malformed inputs or corrupted evidence, including:

- wrong exact input types;
- blank candidate/run/policy versions;
- malformed SHA-256 digests;
- registry/candidate lookup failure;
- E11 reconciliation exception;
- non-finite numeric evidence;
- malformed persisted JSON/schema/order/fingerprint.

Normal negative evidence is represented through gate statuses rather than exceptions.

## Authority boundary

E12 may not:

- call `RegistryStore.register`, `record_status`, or `record_status_event`;
- change champion/challenger status;
- create `TradeIntent` values;
- execute paper or live trades;
- sign or submit Solana transactions;
- enable LIVE mode;
- pick capital limits;
- claim profitability or guarantee profit.

A `SUFFICIENT` assessment means only “the supplied historical/shadow eligibility plus this paper run satisfy the explicit proof policy.” A separate future authority operation would still be required before any registry change, and Phase F remains disabled until all live-execution requirements are independently implemented and verified.

## Testing strategy

Use TDD and exact-head CI.

Tests lock:

- no policy defaults;
- exact enum/schema/model validation;
- gate ordering and decision precedence;
- E8 eligible/insufficient/ineligible mapping;
- current registry/candidate fingerprint alignment;
- exact E11 -> E10 paper-trade provenance equality;
- E11 reconciliation errors propagate fail-closed;
- trade count/distinct mint/span gates;
- expectancy/profit-factor/drawdown/cost-burden gates;
- single-winner concentration behavior;
- deterministic canonical fingerprints;
- append-only idempotent persistence and tamper rejection;
- fresh-process import firewall;
- public/store authority firewall.

## Exit criterion

E12 is complete when Shreks can take a sealed E8 historical/shadow eligibility assessment plus one restart-safe E11 paper run and deterministically produce a persisted, auditable `CandidateProofAssessment` that proves whether the paper evidence is sufficient under explicit caller-supplied thresholds, without granting registry or live-money authority.