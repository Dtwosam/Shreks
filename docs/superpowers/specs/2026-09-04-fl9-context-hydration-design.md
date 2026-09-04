# FL9 Point-in-Time Forecast Context Hydration — Design

**Date:** 2026-09-04

## Status

Implementation slice after the sealed proof-workspace exporter merged and sealed as
`fc35dd86580468c4e525824ac6336f0d0dae835c` (#206).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Produce the exact FL8.4 point-in-time context population needed by the first FL9 champion without
guessing missing evidence and without duplicating sealed FL8.3 leakage/quarantine semantics.

The existing components are:

- #201: exact logical FL8.1 bundle from canonical feature JSONL + read-only observer SQLite;
- FL8.3: chronological folds, leakage quarantine, and exact validation/TEST prediction identities;
- #204: canonical authenticated `FastForecastEvaluationContext` corpus;
- #205: file-backed first-champion request consuming that corpus;
- #206: authenticated host-side FL8.1 feature workspace.

This slice supplies the missing bridge from persisted observer evidence to #204 context rows.

## Exact evaluation population

FL8.4 requires exactly one context row for every unique prediction identity in the FL8.3
validation/TEST population and rejects extra rows.

The hydrator must therefore not select rows by timestamp alone and must not copy FL8.3 quarantine
logic.

Instead it runs the sealed `run_fast_chronological_validation(...)` engine with one fixed,
dependency-free population request:

- model family: `MEAN_REGRESSOR`;
- target: `ENDPOINT_RETURN_BPS`;
- requested horizon: the caller-supplied champion horizon;
- population model version:
  `fl9-context-population-mean-v1:<horizon>ms`;
- training-policy version:
  `fl9-context-population-naive-v1`.

The model output is irrelevant. The emitted validation + TEST prediction identities are the
authoritative context population.

This is safe because FL8.3 leakage quarantine and prediction-row inclusion are target-independent
for a fixed bundle/fold policy, while the naive family requires no optional learning dependency.

Prediction identities must be non-empty and unique.

Every identity must map back to one exact FL8.1 feature record.

## Hydration policy

`FastForecastContextHydrationPolicy` is explicit immutable evidence, not runtime defaults.

It contains:

- semantic version;
- canonical strategy-family tuple;
- exact `ObserverRegimeReadPolicy`;
- exact `RegimePolicy`;
- exact `SafetyPolicy`;
- exact `ObserverSafetyProbeIdentity`;
- explicit global-risk-halt state;
- EXIT quote provider;
- quote-asset decimals;
- maximum accepted EXIT quote age;
- execution-cost policy version;
- expected round-trip cost in bps, or explicit unknown.

The policy requires:

- sorted unique non-empty strategy families;
- consistent regime/exit probe semantic version;
- identical quote asset between regime read policy and exit probe output;
- identical taker/slippage between regime and exit probes;
- valid quote decimals;
- finite non-negative expected cost when supplied.

The policy is serialized as canonical JSON and carries its own SHA-256 fingerprint.

Integer scalar types are preserved. Python floats are encoded with exact `float.hex()` tags.
Raw JSON floats and non-finite values are rejected.

## Strategy-family context

Strategy families are copied only from the explicit hydration policy.

They are not inferred from:

- which strategy later produced profit;
- which candidate later became champion;
- realized PnL;
- future returns;
- counterfactual winners.

This keeps strategy segmentation point-in-time and outcome-independent.

## Candidate attribution

For each FL8.3 prediction identity:

1. resolve exactly one observer candidate by the FL8.1 mint using sealed
   `ObserverMarketStore.resolve_candidate(...)`;
2. reject not-found or ambiguous candidate identity;
3. require candidate discovery timestamp to be at/before the decision timestamp;
4. require persisted candidate venue to equal the FL8.1 decision venue.

The venue equality is supported by the shared canonical Fast Lane venue vocabulary
(`pump_fun_bonding_curve`, `pump_swap`, etc.).

No fuzzy venue mapping is introduced.

## Point-in-time market regime

For the decision timestamp, the hydrator calls sealed
`ObserverCampaignStore.build_regime_market_window(...)` with the exact policy objects and then
sealed `assess_regime(...)`.

All observer-store reads are already bounded at/before the supplied `as_of_unix_ms`.

Recent strategy-performance evidence is intentionally passed as `None` in hydration v1. This
means the context is a reproducible **market-evidence regime** under the explicit regime policy,
with the existing `PERFORMANCE_UNAVAILABLE` finding. It never uses future or non-persisted
performance to manufacture a healthier regime.

The resulting `MarketRegime.value` becomes the FL8.4 `market_regime`.

## EXIT capacity evidence

The hydrator constructs one exact directional EXIT quote identity from:

- resolved observer candidate id;
- explicit EXIT provider;
- hydration probe policy version;
- FL8.1 decision mint as input;
- FL8.1 quote mint as output;
- explicit taker;
- explicit raw probe input amount;
- explicit slippage.

It calls the sealed point-in-time `latest_paper_quote(..., decision_time)`.

Semantics:

- no matching persisted quote -> `executable_exit_capacity_quote = None`;
- quote older than `max_exit_quote_age_ms` -> `None`;
- explicit route-unavailable quote -> `0.0`;
- fresh route-available quote -> conservative guaranteed quote output:
  `minimum_output_amount / 10**quote_asset_decimals`.

The hydrator never interprets missing quote evidence as zero liquidity.

The use of `minimum_output_amount`, rather than optimistic `output_amount`, makes the segment
conservative for the exact probe quantity.

## Expected cost context

`expected_round_trip_cost_bps` comes only from the explicit versioned hydration policy.

It may be `None` when no trustworthy point-in-time cost estimate has been supplied.

Hydration v1 does not derive cost from future realized fills and does not silently compose a new
execution-cost model.

A following host orchestration can bind this explicit policy to the same execution-cost policy used
by comparison campaigns.

## Result

`FastForecastContextHydrationResult` contains:

- result version;
- hydration-policy fingerprint;
- the exact population FL8.3 validation run;
- canonical #204 context corpus;
- context count;
- fresh route-available capacity count;
- explicit route-unavailable count;
- missing/stale quote count.

The three exit-evidence counts must reconcile exactly to the context population.

## Durable hydration artifact

Schema:

`shreks.fast_forecast_context_hydration_artifact` v1.

Root entries are exactly:

- `contexts.json`;
- `policy.json`;
- `manifest.json`.

The artifact is staged in a private sibling directory and strict-read before atomic rename.
Existing destinations are never overwritten.

### Full chronological policy

The manifest stores the **complete exact `FastChronologicalValidationPolicy`**, not merely its
version string, plus a canonical validation-policy SHA-256 fingerprint.

This makes the fold intervals that determined the post-quarantine context population independently
auditable from the artifact.

### Manifest provenance

The manifest binds:

- full chronological validation policy;
- validation-policy fingerprint;
- champion horizon;
- FL8.1 training-bundle fingerprint;
- FL8.1 feature-source JSONL SHA;
- observer database SHA;
- optional observer WAL SHA;
- hydration-policy fingerprint;
- population FL8.3 validation-run fingerprint;
- context logical fingerprint;
- context/evidence counts;
- context file SHA;
- policy file SHA;
- top-level artifact fingerprint.

## Database race seal

Before hydration, the artifact writer hashes:

- observer database;
- optional SQLite WAL.

Each file is checked for device/inode/size/mtime stability while hashing.

After the complete context population has been hydrated, the database + WAL are hashed again.

Any difference aborts publication.

This does not add Python query semantics: SQLite evidence is read only through the already-sealed
observer stores.

## Strict reopen

The artifact reader requires:

- real non-symlink directory;
- exact three-file root set;
- canonical manifest JSON;
- valid manifest fingerprint;
- exact validation-policy reconstruction and fingerprint;
- context/policy file byte hashes;
- exact hydration-policy reconstruction and fingerprint;
- strict #204 context-corpus read;
- exact context logical fingerprint/count.

A policy or corpus copied from another hydration artifact is rejected.

## TDD provenance

Intentional RED:

`2db11aafde9672aa7ae46f776227b17bf4a7e559`.

RED matrix:

- Python: expected failure because `shreks_brain.fast_context_hydration` did not exist;
- Repository safety: GREEN;
- Rust: GREEN;
- ARM64: GREEN.

During implementation two fixture-only defects were caught:

1. the first test imported `chronological_policy` from the wrong fixture module;
2. the synthetic regime window was 999 ms while its policy required 1,000 ms, so the sealed regime
   engine correctly classified it DEAD.

Both fixtures were corrected. Production validation/regime checks were not weakened.

After those fixture fixes, the hydration production tree passed 3147 Python tests before the final
validation-policy provenance hardening.

## Authority boundary

The hydrator contains no:

- provider/network access;
- trade intent construction;
- PAPER execution;
- automatic model/champion selection;
- registry/promotion mutation;
- signer;
- transaction submission;
- LIVE mode.

It uses read-only observer stores and offline forecasting/evaluation primitives only.

## Following work

After #207 seals, the remaining host workflow should become one atomic first-champion preparation:

1. read/verify #206 proof workspace;
2. build #201 logical bundle against the current read-only observer DB;
3. run #207 hydration artifact with explicit production policy;
4. construct #205 request pointing to `hydration/contexts.json`;
5. verify #205 request validation policy exactly equals the #207 sealed validation policy;
6. run #205;
7. preserve #206/#207/#205 manifests as one evidence chain;
8. if a genuine champion exists, use only a post-selection population for #202/#199/#198.

If runtime evidence is missing, ambiguous, immature, or races during capture, the pipeline must
report insufficient evidence rather than manufacture context.

LIVE remains disabled.
