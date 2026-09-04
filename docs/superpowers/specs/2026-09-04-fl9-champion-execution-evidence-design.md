# FL9 Champion-Derived FL3 Execution Evidence — Design

**Date:** 2026-09-04

## Status

Implementation slice after low-capacity FL6 SKIP merge
`78f9a48f2da5a27889d0bbd72b13ae06e521307e` (#188).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The point-in-time comparison hydrator now requires explicit shared FL6 entry execution economics.

Until this slice, `forecast_exit_price_quote` could still be caller-authored.

That is too weak for real FL9 evidence. A caller could supply a favorable forecast price while claiming an unrelated model source.

The repository already has a sealed FL8 champion format with:

- explicit selection evidence;
- embedded authenticated runtime forecast artifacts;
- chronological validation fingerprints;
- unseen TEST evaluation fingerprints;
- exact target/horizon member lookup;
- deterministic pure-Python inference.

FL9 should consume that contract directly rather than invent another forecasting surface.

## Source contract

Add:

`build_fast_champion_entry_execution_evidence(...)`

Inputs:

- canonical champion JSON path;
- exact FL8.1 `FastTrainingFeatureRecord`;
- exact requested horizon;
- explicit `FastOfflineExecutionCostModel`;
- explicit intended base quantity;
- explicit exit capacity;
- explicit required edge bps;
- explicit risk margin bps;
- named execution-policy source version;
- named exit-capacity source version.

The function has no default cost, size, liquidity, edge, or risk-margin assumptions.

## Champion authentication

The function calls only the sealed:

`read_fast_forecast_champion(...)`

That codec:

- requires exact schema keys;
- authenticates embedded FL8.2 artifact fingerprints;
- authenticates the top-level champion fingerprint;
- fails on tampering.

The execution adapter does not parse champion JSON itself.

## Exact forecast member

FL3 needs a **gross future exit price before execution costs**.

Therefore the only allowed forecast target is:

`FastForecastTarget.ENDPOINT_RETURN_BPS`.

Lookup is exact:

`champion.member_for(ENDPOINT_RETURN_BPS, horizon_ms)`.

No fallback is allowed to:

- a nearby horizon;
- MFE;
- MAE;
- best cost-adjusted return;
- endpoint cost-adjusted return;
- reversal probability;
- route-unavailability probability.

Cost-adjusted return targets are especially forbidden because FL3 independently applies entry and exit costs. Feeding a cost-adjusted target into FL3 would double-count costs.

## Point-in-time chronology

Two independent chronology gates apply before inference.

### Champion selection

`champion.selection.decided_at_unix_ms <= record.decision_observed_at_unix_ms`.

A model selection made after the trade cannot be used as decision-time evidence for that trade.

### Runtime model training

`artifact.max_training_decision_observed_at_unix_ms < record.decision_observed_at_unix_ms`.

Strict inequality is required.

A final-refit runtime artifact may legitimately be trained on more history than any one FL8.3 fold. For real decision evidence, however, it must not include the row being evaluated or any later row.

This is the decisive anti-leakage gate for applying an FL8 champion to a chronological FL9 campaign.

## Forecast conversion

The sealed FL8 inference returns raw endpoint return basis points.

FL3 requires a gross quote-denominated exit price.

For exact FL8.1 decision price `p0` and predicted endpoint return `r_bps`:

`forecast_exit_price_quote = p0 * (1 + r_bps / 10_000)`.

The result must be finite and strictly positive.

The adapter does not apply any fee, slippage, latency, network, failure, or risk adjustment to this price. Those remain explicit FL3 inputs.

## Execution evidence

The adapter creates one exact `FastOfflineEntryExecution`:

- caller-supplied exact cost model;
- intended base quantity;
- FL8.1 decision executable entry price;
- champion-derived gross forecast exit price;
- explicit exit capacity;
- explicit required edge bps;
- explicit risk margin bps.

That object can be shared unchanged across FL6.1–FL6.4 by the already-sealed point-in-time hydrator.

Low exit capacity remains valid evidence. If capacity is below intended size, FL6 records `InsufficientExitCapacity` SKIP and the sealed PAPER authority adapter returns no BUY authority.

## Result provenance

`FastChampionEntryExecutionEvidence` records:

- contract version;
- champion version;
- champion fingerprint;
- exact member key;
- FL8.3 validation-run fingerprint;
- FL8.4 TEST evaluation-report fingerprint;
- exact `FastForecastPrediction`;
- exact `FastOfflineEntryExecution`;
- forecast source version;
- execution-policy source version;
- exit-capacity source version.

Forecast source version binds:

- champion version;
- champion fingerprint;
- exact endpoint-return member key;
- model version;
- embedded model artifact fingerprint.

The execution-policy source version is expected to identify the source of the cost model **and** required edge/risk-margin assumptions. No hidden execution-policy fields are created by this adapter.

## Authority boundary

No:

- provider/network access;
- SQLite access;
- wall clock;
- future-label input;
- direct PAPER execution;
- superiority evaluation;
- model selection logic;
- signing/submission;
- LIVE authority.

The champion selection is consumed as immutable upstream evidence; this slice does not choose a model.

## TDD

Intentional RED:

`2fcaf40638b8bbd05cc63f1a5b512a131c21a448`.

Tests require:

1. authenticated champion read;
2. exact endpoint-return member lookup;
3. gross forecast price conversion;
4. explicit cost/size/capacity/edge/margin propagation;
5. champion/model/validation/test provenance;
6. selection-after-decision rejection;
7. training-through-decision rejection;
8. cost-adjusted-only champion rejection;
9. non-positive forecast exit rejection;
10. source firewall.

## Following slice

Use this adapter to construct hydration inputs for a real post-selection FL8.1/observer population, then write the immutable comparison bundle and run the eight-candidate PAPER matrix.

Only rows after the authenticated champion selection and runtime training cutoff are eligible.
