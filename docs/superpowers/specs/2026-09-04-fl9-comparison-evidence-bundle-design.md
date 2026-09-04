# FL9 Immutable Comparison Evidence Bundle — Design

**Date:** 2026-09-04

## Status

Design after deterministic comparison evidence binder merge
`f4021a72f713fe41174f47c8556a0b5551f861e9` (#183).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create one immutable, self-contained replay artifact for the exact point-in-time population that can feed the learned FL9 policy and the eight authenticated deterministic lifecycle candidates.

The bundle must preserve what was knowable at each decision. It must not copy FL4 future-path labels or FL5 counterfactual labels into the decision-evidence surface.

## Bundle layout

Exactly three files:

```text
fast_training_features.parquet
comparison_evidence.jsonl
manifest.json
```

### Feature file

`fast_training_features.parquet` is the sealed FL8.1 point-in-time feature dataset format.

The bundle copies only the feature table, not the future-path or counterfactual tables from a broader training bundle.

### Comparison sidecar

One canonical JSONL row per exact FL8.1 feature row, same order.

Each sidecar row carries only explicit decision-time comparison evidence:

- exact record identity;
- state version and evaluation clock;
- contemporaneous directional PAPER ENTRY and EXIT quote evidence;
- MarketRegime;
- shared deterministic risk environment;
- exact catalog candidate entry authority;
- explicit source provenance for ENTRY quote, EXIT quote, entry forecast/horizon, execution costs, exit capacity, wallet evidence, graduation context, continuation forecast, regime, risk environment, and entry authority;
- Impulse Scalp evidence;
- Micro Pullback evidence;
- Pre-Graduation evidence;
- Graduation Flow evidence;
- Wallet/Cohort evidence;
- Longer Runner protective/continuation evidence.

The FL8.1 record itself remains authoritative and is not duplicated in the sidecar.

Provenance is semantic, not decorative. If entry execution evidence is present, forecast source/horizon, cost-model source, and exit-capacity source are required. Wallet evidence requires wallet provenance. Longer Runner continuation requires provenance matching its exact `forecast_source_version`. Provenance source identity must equal the exact FL8.1 source event.

### Manifest

Schema:

`shreks.fast_deterministic_comparison_evidence_bundle` v2. V1 is superseded before real economic evidence collection because it carried one ambiguous generic quote.

The manifest records:

- exact eight-candidate catalog fingerprint;
- row count;
- FL8.1 logical/source fingerprints;
- physical SHA-256 of feature Parquet;
- logical and physical SHA-256 of the evidence sidecar;
- bundle fingerprint over all manifest material.

## Population invariant

For every row, the embedded comparison row record must equal the feature dataset record positionally.

Writing fails before creating the bundle if:

- counts differ;
- any row differs;
- candidate authority coverage differs from the supplied authenticated catalog.

Reading reattaches each sidecar row only to its exact FL8.1 record identity and reconstructs the strict comparison row model, which re-runs chronology, quote attribution, dynamic-risk chronology, and entry-authority provenance validation.

## Immutability

The writer refuses an existing destination. V2 also rejects legacy single-quote rows and requires both directional quotes.

The reader requires exactly the three bundle files and authenticates physical file fingerprints before consuming their contents.

Canonical JSON rules:

- UTF-8;
- sorted keys;
- compact separators;
- no NaN/Infinity;
- every JSONL record newline-terminated.

Manual edits invalidate physical/logical fingerprints.

## Evidence authority

This bundle is a transport/replay artifact. It does not invent missing evidence.

In particular it does not manufacture:

- executable quotes;
- cost assumptions;
- expected exit price;
- expected future capacity;
- wallet evidence;
- continuation forecast;
- regime;
- risk health;
- candidate entry authority.

Those must come from an explicit point-in-time evidence-hydration source in the following slice.

Missing legitimate evidence remains missing and may cause deterministic baselines to SKIP/REDUCE under their sealed semantics.

## Leakage boundary

The bundle module must not import or encode:

- FL4 future-path labels;
- FL5 counterfactual outcomes;
- realized future returns;
- PAPER run results.

The feature Parquet is the FL8.1 point-in-time feature file only.

## Authority boundary

No provider/network/SQLite access.
No PAPER execution.
No superiority evaluation.
No promotion.
No signing/submission.
No LIVE authority.

## TDD

Intentional RED head:
`a49872cd335b7f637612c7d23f573771477e7421`.

Tests require:

1. self-contained three-file round trip;
2. exact schema/catalog/feature/evidence fingerprints;
3. existing destination rejected as immutable;
4. feature/sidecar population drift rejected;
5. sidecar tampering rejected;
6. feature-file tampering rejected;
7. provenance population/source drift is rejected;
8. execution/wallet/continuation evidence cannot exist without matching provenance;
9. source firewall excludes future labels, provider/storage/subprocess execution, superiority, and LIVE authority.

## Following slice

Build the explicit evidence hydrator that creates bundle rows from approved point-in-time sources.

The hydrator must separately prove provenance for:

- contemporaneous quote/capacity;
- cost model;
- expected exit/continuation forecast source;
- wallet/cohort evidence;
- graduation pre-state/BOOST context;
- protective state;
- regime and risk-health facts;
- entry sizing/price authority.

Only after a real bundle exists should Shreks run:

`learned PAPER run + eight deterministic matrix runs -> sealed FL9 superiority evaluator`.

Fixtures prove plumbing only, never economic edge.
