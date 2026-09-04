# FL9 Reproducible Comparison Input Assembly — Design

**Date:** 2026-09-04

## Status

Implementation slice after observer-probe execution evidence merge
`ff372a02c95f491ec6bfc0ac974f928c9b08f135` (#190).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Remove manual construction of `FastDeterministicComparisonHydrationInput`.

The repo now has sealed seams for:

- exact FL8.1 decision rows;
- observer ENTRY/EXIT quote hydration;
- probe-derived intended size and exit capacity;
- authenticated FL8 champion raw endpoint forecast;
- FL3 execution economics and PAPER entry authority;
- exact eight-candidate deterministic comparison;
- immutable v2 evidence bundle.

The remaining plumbing gap is combining those contracts reproducibly for every row.

## Execution policy

`FastDeterministicComparisonExecutionPolicy` is frozen/versioned and contains:

- `version`;
- forecast `horizon_ms`;
- exact `FastOfflineExecutionCostModel`;
- `required_edge_bps`;
- `risk_margin_bps`.

The version is the explicit source identity for the complete entry-execution policy consumed by this assembly seam.

No defaults are supplied.

## Point-in-time context

`FastDeterministicComparisonPointInTimeContext` contains only evidence/context that is not derivable from the FL8.1 row or directional quote probes:

- observer candidate id;
- state version;
- explicit evaluation clock;
- exact ENTRY quote identity;
- exact EXIT quote identity;
- quote asset;
- graduation boost context;
- wallet-cohort evidence;
- longer-runner evidence;
- MarketRegime;
- deterministic risk environment;
- wallet/graduation/continuation/regime/risk source versions.

The FL8.1 source event id is not caller supplied. It is derived exactly from the row.

Wallet and continuation source presence must match their evidence payloads.

## Assembly flow

`assemble_fast_deterministic_comparison_hydration_inputs(...)` consumes:

- read-only observer database path;
- exact FL8.1 feature dataset;
- authenticated champion path;
- exact execution policy;
- one positional context per FL8.1 row.

For each row:

1. require positional context population match;
2. load canonical observer directional probe;
3. call the sealed observer-probe -> champion execution adapter;
4. receive either authenticated execution proof or `None`;
5. derive one exact FL8.1 market snapshot for graduation evidence;
6. place the exact same execution object into FL6.1–FL6.4;
7. derive forecast/cost/capacity provenance from sealed outputs;
8. construct one exact `FastDeterministicComparisonHydrationInput`.

No caller creates per-entry-family economics.

## Graduation snapshot

The assembler reconstructs `FastOfflineMarketSnapshot` only from the exact FL8.1 row:

- mint/quote mint/venue;
- snapshot as-of clock;
- last sequence/price;
- reserve context;
- lifecycle event;
- exact sealed windows.

No separate market snapshot may be supplied for FL6.4 pre-graduation context.

## Execution-proof validation

When champion execution evidence exists, assembly verifies:

- prediction decision identity equals the FL8.1 row;
- execution entry price equals the FL8.1 decision executable price;
- execution base quantity equals the canonical ENTRY probe quantity;
- execution exit capacity equals the canonical EXIT probe capacity;
- execution-policy source version equals the assembly policy version;
- prediction horizon equals policy horizon;
- execution cost model equals policy cost model;
- required edge equals policy required edge;
- risk margin equals policy risk margin;
- exit-capacity source equals the canonical observer EXIT source.

The already-sealed hydrator subsequently re-reads the point-in-time probe and independently verifies size/capacity alignment again.

This gives two fail-closed boundaries around the assembled execution object.

## Unavailable route behavior

If either ENTRY or EXIT route is unavailable, the sealed observer/champion adapter returns `None`.

Assembly then emits:

- all FL6.1–FL6.4 execution fields `None`;
- entry forecast source `None`;
- forecast horizon `None`;
- execution cost source `None`;
- exit capacity source `None`.

Directional quote evidence is still preserved later by hydration.

No missing route is replaced with synthetic zero economics.

## Result

`FastDeterministicComparisonInputAssemblyResult` stores aligned tuples of:

- canonical observer probes;
- optional authenticated champion execution evidence;
- exact hydration inputs.

All populations must have identical positional length and exact types.

The proof objects remain inspectable even though the immutable v2 bundle ultimately stores the normalized comparison evidence/provenance.

## Integration proof

The TDD integration test takes assembled hydration inputs and passes them directly into the already-sealed point-in-time hydrator.

That proves:

`observer DB + policy + row context -> probe -> champion execution -> four FL6 evidences -> hydration input -> hydrated comparison row`.

The champion call is test-doubled only in this slice because the authenticated champion adapter itself is separately sealed by #189. The assembler still validates its returned evidence contract.

## Authority boundary

No:

- database writes;
- direct sqlite access;
- provider/network calls;
- hidden clock;
- future-label input;
- direct PAPER fill execution;
- superiority evaluation;
- model selection;
- signing/submission;
- LIVE authority.

## TDD

Intentional RED:

`b27b633642a710acdd2d970e7bfa86ae350660e7`.

Coverage includes:

1. exact policy/context contracts;
2. exact positional population requirement;
3. real observer-probe read;
4. one shared execution across FL6.1–FL6.4;
5. derived FL8.1 graduation snapshot;
6. forecast/cost/capacity provenance;
7. direct handoff into sealed hydration;
8. unavailable ENTRY yields no execution/provenance;
9. source authority firewall.

## Following slice

Build the durable campaign artifact command that:

1. reads an exact FL8.1 Parquet population;
2. reads explicit row contexts + versioned execution policy;
3. assembles hydration inputs;
4. hydrates point-in-time comparison evidence;
5. writes the immutable v2 comparison bundle;
6. runs the eight deterministic PAPER candidates;
7. emits authenticated comparison results for the later superiority evaluator.

A real run still requires non-fixture champion and observer evidence.
