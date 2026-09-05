# FL3/FL8.1 Size-Aware Training Economics Overlay — Design

**Date:** 2026-09-05  
**Base:** `62e7fc1e5393cdd351a31a8df1d99e2b97dd87b4`  
**Branch:** `feat/fl3-training-economics-overlay`

## Status

Design for the next implementation slice after physical FL4 covered-event population on the production VPS.

The physical FL4 proof established one immutable session-3 population with:

- 512 chronological decision rows;
- 6,144 FL4 labels across the 12 sealed horizons;
- complete coverage through the one-hour horizon;
- zero pre-existing FL4 labels before population;
- zero FL4 execution-economics annotations, as required.

A read-only source inventory over the exact 512-decision window established:

- Pump bonding curve: 176 canonical decisions, 176 raw source rows, 135 execution-economics sidecars, 41 missing sidecars, zero conflicts;
- PumpSwap: 336 canonical decisions, 336 raw source rows, 336 execution-economics sidecars, 336 full extended-economics rows, 336 physical-reserve rows, zero conflicts.

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Problem

FL4 intentionally records market-path truth without binding that path to Shreks' hypothetical size or a mutable execution policy.

The runtime FL8.1 builder currently accepts an explicit positive `counterfactual_base_quantity`, but the existing FL5 source loader correctly leaves requested-quantity BUY/SELL evidence unknown because immutable FL4 rows do not prove:

- executable entry quote for Shreks' requested size;
- executable future exit quote for the same size;
- exact effective fee when immutable history cannot prove one;
- non-source execution costs such as latency, network, priority, failure, or additional slippage assumptions.

The repository already has the necessary sealed primitives:

- canonical FastEvent identities and reserve reconstruction;
- `project_entry(...)`;
- `project_exit(...)`;
- `maximum_exit_capacity(...)`;
- exact PumpSwap effective-fee normalization;
- causal same-side PumpSwap fee-context lookup;
- immutable FL4 labels;
- FL5 counterfactual label generation;
- runtime FL8.1 logical-bundle construction.

The missing seam is a separate, versioned, size-aware training-economics overlay that combines those existing contracts without mutating FL4 or inventing unavailable historical economics.

## Goal

Add a deterministic, read-only PumpSwap-first training-economics overlay that can prove requested-quantity BUY and future SELL execution evidence for eligible FL4 decision/horizon rows.

The overlay must:

1. use one explicit caller-supplied counterfactual base quantity;
2. reuse Rust FL3 reserve projection rather than reimplementing AMM math in Python;
3. use exact causal PumpSwap effective-fee evidence only when source semantics support an exact integer basis-point rate;
4. apply only explicit, versioned non-source execution-cost policy for components not recoverable from immutable source history;
5. preserve explicit unavailable/unknown states rather than fabricating values;
6. keep Pump bonding-curve execution economics unavailable in version 1;
7. leave `fast_future_path_labels` unchanged;
8. integrate into the existing runtime FL8.1 builder so proven executable rows become ordinary FL5 `ExecutableTradeEvidence` and unavailable rows remain `UNKNOWN`.

## Non-goals

This slice does not:

- define Pump bonding-curve effective-fee semantics;
- backfill missing migration-15 sidecars;
- write derived economics into FL4;
- modify provider ingestion;
- call providers or networks;
- infer a position size, order request, or risk allocation from `counterfactual_base_quantity`;
- create strategy thresholds;
- alter PAPER execution or ledgers;
- select or promote a champion;
- evaluate FL9 superiority;
- sign or submit transactions;
- enable LIVE.

## Architecture

The overlay has two authority layers.

### 1. Rust source-evidence exporter

Rust remains authoritative for:

- canonical source identity;
- reserve reconstruction;
- requested-size entry projection;
- requested-size endpoint exit projection;
- causal PumpSwap fee selection;
- exact PumpSwap effective-fee normalization;
- conflict quarantine;
- deterministic source provenance.

The exporter opens the operational SQLite database read-only and emits a canonical JSONL artifact. It never writes SQLite.

### 2. Python policy/application layer

Python remains authoritative for:

- explicit versioned non-source execution-cost policy;
- applying that policy to Rust-projected gross quotes;
- constructing FL5 `ExecutableTradeEvidence`;
- preserving unavailable rows as `UNKNOWN`;
- joining the resulting counterfactual outcomes into the existing FL8.1 logical training bundle.

Python must not reimplement Pump/PumpSwap reserve algebra or derive protocol fee semantics independently.

## Rust exporter command

Add an offline host subcommand before normal provider/PAPER runtime configuration:

`shreks-observe export-training-economics`

Required explicit inputs:

- `--database <path>`;
- `--feature-jsonl <path>`;
- `--future-path-label-version <positive integer>`;
- `--counterfactual-base-quantity <positive finite decimal>`;
- `--pump-swap-fee-maximum-age-ms <non-negative integer>`;
- `--output <directory>`.

The command:

1. opens SQLite read-only;
2. authenticates and parses the exact Rust-exported FL8.1 feature JSONL;
3. loads matching FL4 labels for the requested label version;
4. requires exact feature/FL4 decision-identity alignment;
5. computes one overlay row for every exact FL4 decision/horizon/version identity;
6. creates the requested output directory and writes exactly `rows.jsonl` plus `manifest.json`;
7. performs no provider/network access and no trading action.

The destination directory must not already exist. The exporter is an immutable artifact writer, not an in-place updater.

## Overlay schema

Version 1 uses:

- schema name: `shreks.fast_training_economics_overlay`;
- schema version: `1`.

One row exists for every exact FL4 decision/horizon/version identity, including unavailable rows.

Each row records:

### Identity

- `decision_signature`;
- `decision_ordinal`;
- `decision_sequence`;
- `decision_observed_at_unix_ms`;
- `mint`;
- `quote_mint`;
- `venue`;
- `horizon_ms`;
- `future_path_label_version`;
- `counterfactual_base_quantity`.

### Endpoint identity

- `endpoint_signature`;
- `endpoint_ordinal`;
- `endpoint_sequence`;
- `endpoint_observed_at_unix_ms`.

All endpoint fields are null together when FL4 has no canonical endpoint for the horizon.

### Status

`status` is exactly one of:

- `available`;
- `unsupported_venue`;
- `no_endpoint`;
- `entry_reserve_unavailable`;
- `exit_reserve_unavailable`;
- `entry_projection_unavailable`;
- `exit_projection_unavailable`;
- `entry_fee_missing`;
- `entry_fee_stale`;
- `entry_fee_rate_unknown`;
- `exit_fee_missing`;
- `exit_fee_stale`;
- `exit_fee_rate_unknown`.

Conflict-quarantined or internally contradictory source evidence is not a status. It is a hard exporter error.

Version 1 supports `venue = pump_swap` only.
`pump_fun_bonding_curve` rows must emit `unsupported_venue`.

### Reserve provenance

For available PumpSwap rows, record exact reserve-source identities for both legs:

- decision reserve source signature/ordinal/sequence/time;
- endpoint reserve source signature/ordinal/sequence/time;
- raw base reserve;
- raw physical quote reserve;
- raw signed virtual quote reserve;
- base decimals;
- quote decimals.

The exporter must obtain these through existing canonical reserve reconstruction. It must not query sidecars and rebuild reserve formulas independently.

### Entry projection

For an available row, record the exact output from existing `project_entry(...)`:

- requested base quantity raw;
- gross quote input raw;
- scaled base quantity;
- gross quote input;
- gross average entry price.

The requested raw quantity is derived from the explicit decimal `counterfactual_base_quantity` using the authoritative base decimals. Conversion must be exact. A decimal quantity that cannot be represented exactly in raw base units fails closed rather than being rounded.

### Exit projection

For an available row, record the exact output from existing `project_exit(...)` at the canonical FL4 endpoint reserve state for the same raw base quantity:

- requested base quantity raw;
- gross quote output raw;
- scaled base quantity;
- gross quote output;
- gross average exit price.

Version 1 does not claim maximum route capacity. It proves deterministic PumpSwap pool-state projection for exactly the requested base quantity. A projection failure produces `exit_projection_unavailable`.

### Executability semantics

An `available` overlay row proves that, at the immutable historical PumpSwap pool states and exact requested quantity:

- the pool reserve math supports the requested BUY quantity at the decision;
- the pool reserve math supports the same requested SELL quantity at the canonical endpoint;
- exact causal source fee rates are available for both legs;
- the explicit non-source cost policy can be applied without arithmetic contradiction.

It does **not** prove:

- Jupiter or another aggregator exposed a route;
- a transaction would have landed;
- account contention, compute, blockhash, RPC, or priority conditions would have succeeded;
- maximum route capacity.

The downstream FL5 `ExecutableTradeEvidence` created by this slice is therefore specifically a **training-research pool-execution projection**. Its evidence version must identify this overlay contract. It must not be reused as provider-route or transaction-landing proof by PAPER/LIVE authority code.

## Fee provenance

Entry fee context is selected for:

- same mint;
- same quote mint;
- PumpSwap;
- BUY side;
- `sequence <= decision_sequence`;
- `observed_at_unix_ms <= decision_observed_at_unix_ms`.

Exit fee context is selected for:

- same mint;
- same quote mint;
- PumpSwap;
- SELL side;
- `sequence <= endpoint_sequence`;
- `observed_at_unix_ms <= endpoint_observed_at_unix_ms`.

Selection uses the existing sealed no-fallback causal lookup.

For each leg, preserve:

- source signature;
- source ordinal;
- source canonical sequence;
- source observation timestamp;
- age milliseconds;
- market quote amount raw;
- user quote amount raw;
- signed user-cost delta raw;
- exact effective fee bps.

`Missing`, `Stale`, and `RateUnknown` map directly to the explicit row statuses above.

No rounding, ceiling, floor, floating approximation, or component-field summation is allowed to manufacture a fee rate.

## Chronology

All source selection is point-in-time.

Decision-time entry evidence may use only observations at or before the decision.

Endpoint exit evidence may use only observations at or before the exact canonical FL4 endpoint.

The exporter may read later database state only to locate immutable historical rows. It may not use later fee or reserve observations as substitutes for missing earlier evidence.

No selection may depend on the realized return, MFE, MAE, or any other future outcome.

## No-trade horizons

A complete FL4 horizon with no canonical endpoint remains valid market-path evidence but cannot prove a future requested-size exit.

Such rows emit:

`status = no_endpoint`

Python must preserve `BUY_NOW = UNKNOWN` for those horizon rows.

## Non-source cost policy

Python adds a new exact frozen policy:

`FastTrainingExecutionCostPolicy`

Version 1 contains:

- `version`: non-empty source identity;
- `additional_entry_slippage_bps`;
- `additional_exit_slippage_bps`;
- `entry_latency_bps`;
- `exit_latency_bps`;
- `entry_network_fee_quote`;
- `exit_network_fee_quote`;
- `entry_priority_fee_quote`;
- `exit_priority_fee_quote`;
- `entry_expected_failure_cost_quote`;
- `exit_expected_failure_cost_quote`.

All numeric fields are explicit non-negative finite values.
Basis-point fields must satisfy the existing FL3 execution-cost bounds.

The policy must not contain:

- effective protocol fee bps;
- reserve-derived price impact bps;
- current Pump/PumpSwap fee constants;
- route-capacity assumptions.

Protocol fee comes from the Rust overlay.
Requested-size AMM impact is already embodied in `project_entry` and `project_exit`.

Applying a separate reserve-impact bps charge would double-count the same economic effect and is forbidden.

## Cost application

For an `available` row, Python constructs requested-size FL5 execution evidence directly from projected gross quote amounts.

Let:

- `E_gross` = Rust gross entry quote input;
- `X_gross` = Rust gross exit quote output;
- `f_entry` = exact source entry effective fee bps;
- `f_exit` = exact source exit effective fee bps;
- `s_entry` / `s_exit` = explicit additional slippage bps;
- `l_entry` / `l_exit` = explicit latency bps;
- fixed leg costs be the sum of network, priority, and expected failure quote costs.

Then:

`entry_total_quote = E_gross * (1 + (f_entry + s_entry + l_entry) / 10_000) + entry_fixed_quote`

`exit_net_quote = X_gross * (1 - (f_exit + s_exit + l_exit) / 10_000) - exit_fixed_quote`

The exit variable rate must remain strictly below 100%.

Both results must be finite and strictly positive.

This application is a training-research economics overlay. It does not alter FL3 runtime trading policy.

## FL5 evidence construction

For an `available` row Python creates:

### BUY_NOW

`ExecutableTradeEvidence` with:

- side = BUY;
- requested counterfactual base quantity;
- status = EXECUTABLE;
- `quote_amount = entry_total_quote`;
- observation time = decision observation time;
- source event identity = decision identity;
- evidence version derived from overlay schema/version, policy version, and overlay manifest fingerprint.

### Exit at horizon

`ExecutableTradeEvidence` with:

- side = SELL;
- same requested base quantity;
- status = EXECUTABLE;
- `quote_amount = exit_net_quote`;
- observation time = endpoint observation time;
- source event identity = endpoint identity;
- same bound evidence-version family.

The existing pure `label_entry_counterfactuals(...)` remains the only FL5 outcome calculator.

For any overlay status other than `available`:

- `buy_now = None`;
- `exit_at_horizon = None`;
- `BUY_NOW = UNKNOWN`;
- `SKIP = EXECUTABLE` with zero PnL by existing FL5 semantics.

No unavailable row is dropped silently.

## Runtime FL8.1 integration

Extend:

`build_fast_training_bundle_from_runtime_sources(...)`

to require:

- `training_economics_overlay_path`;
- exact `FastTrainingExecutionCostPolicy`.

The existing explicit `counterfactual_base_quantity` remains required.

The builder must verify:

1. overlay schema/version;
2. overlay manifest fingerprint;
3. overlay feature-source fingerprint equals the exact feature JSONL fingerprint;
4. overlay FL4 logical fingerprint equals the FL4 dataset loaded from SQLite;
5. overlay label version equals requested label version;
6. overlay counterfactual quantity equals the requested quantity exactly;
7. one overlay row exists for every FL4 decision/horizon/version identity and no extras exist;
8. row identity/provenance matches the canonical FL4 source loader;
9. available row BUY/SELL evidence uses the exact same base quantity.

After validation, the builder converts each overlay row into the existing FL5 context and delegates to the unchanged logical FL8.1 component builder.

## Artifact manifest

The Rust exporter writes a canonical manifest containing:

- schema name/version;
- row count;
- available row count;
- status counts by exact status string;
- feature-source JSONL SHA-256;
- FL4 logical fingerprint SHA-256;
- future-path label version;
- counterfactual base quantity in canonical decimal representation;
- PumpSwap fee maximum age ms;
- minimum and maximum decision observation timestamps;
- ordered-row logical fingerprint SHA-256;
- manifest fingerprint SHA-256.

The ordered-row fingerprint is computed over rows sorted by:

1. decision sequence;
2. decision signature;
3. decision ordinal;
4. horizon ms;
5. label version.

Canonical JSON encoding uses sorted keys, UTF-8, no NaN/Infinity, and one normalized newline per JSONL row.

## Failure model

Hard fail:

- unreadable or missing inputs;
- incompatible schema/version;
- feature/FL4 identity mismatch;
- duplicate decision/horizon rows;
- canonical source conflict quarantine;
- canonical/raw reserve contradiction;
- impossible decimal-to-raw quantity conversion;
- arithmetic overflow;
- malformed source evidence;
- output destination already exists;
- fingerprint mismatch.

Row unavailable, not hard fail:

- unsupported Pump bonding-curve venue;
- no canonical endpoint;
- missing/stale/inexact PumpSwap fee context;
- missing authoritative PumpSwap virtual quote reserve;
- requested quantity outside deterministic reserve projection bounds.

The distinction is intentional:

- corrupted/contradictory evidence aborts the artifact;
- truthful absence of sufficient economics produces an explicit unavailable row.

## Security and authority boundary

The Rust exporter and Python overlay application have no:

- provider/network access;
- wallet/private-key access;
- signer access;
- transaction construction;
- transaction submission;
- direct PAPER execution;
- LIVE authority.

The exporter opens SQLite read-only.
Python opens the canonical database only through the existing read-only loaders.

No secret-bearing environment dump is required.

## TDD requirements

Implementation must begin RED and prove at minimum:

1. PumpSwap available row uses exact requested raw quantity.
2. Entry uses existing `project_entry`.
3. Exit uses existing `project_exit`.
4. PumpSwap signed virtual quote reserve affects both projections.
5. BUY fee context is same-side and causal at decision time.
6. SELL fee context is same-side and causal at endpoint time.
7. No fallback to an older fee after stale/rate-unknown latest source.
8. Inexact fee ratio remains unavailable.
9. Negative/rebate-like signed user-cost delta remains rate unknown.
10. Pump bonding-curve row is `unsupported_venue`.
11. No-endpoint FL4 row is `no_endpoint`.
12. Conflict-quarantined source aborts export.
13. Exact decimal counterfactual quantity converts without rounding.
14. Non-representable decimal quantity fails closed.
15. Overlay output is deterministic and fingerprint-authenticated.
16. Python policy rejects hidden protocol-fee and impact fields by construction.
17. Python cost application does not add a second reserve-impact charge.
18. Available overlay row becomes executable BUY/SELL FL5 evidence.
19. Unavailable overlay row keeps BUY_NOW unknown and SKIP executable.
20. Runtime bundle rejects overlay/feature/FL4 fingerprint drift.
21. Runtime bundle requires exact population equality: no missing or extra overlay rows.
22. SQLite remains unchanged after export and runtime-bundle construction.
23. Provider/PAPER environment may be cleared for the exporter command.
24. Full Rust workspace, Python suite, repository-safety gates, and native ARM64 release build remain green.

## Physical acceptance after merge/deploy

After the implementation is sealed and deployed, physical evidence should use the already-proven immutable session-3 FL4 population.

The acceptance run must:

1. export the overlay for the exact 512-decision / 6,144-label FL4 population;
2. report all 2,112 Pump decision/horizon rows (176 decisions × 12 horizons) as `unsupported_venue`;
3. evaluate all 4,032 PumpSwap decision/horizon rows (336 decisions × 12 horizons) according to exact evidence availability;
4. show zero hard source conflicts;
5. report exact counts for `available`, fee-unavailable, projection-unavailable, and no-endpoint statuses;
6. build a real runtime FL8.1 logical bundle from the exported overlay;
7. verify that executable FL5 BUY rows come only from `available` overlay rows;
8. verify unavailable rows remain explicit UNKNOWN rather than being removed;
9. leave the production SQLite FL4 rows byte-for-byte/logically unchanged.

No acceptance threshold may require a favorable economic result. Truthful `UNKNOWN`, `FAILED`, or insufficient coverage remains valid evidence.

## Following work

After this overlay is physically proven:

1. quantify the resulting real executable FL5 population by horizon;
2. determine whether it is large enough for the sealed FL8.1 chronological training/evaluation path;
3. build or rerun the first non-fixture champion only when chronology and population gates pass;
4. assemble post-selection deterministic comparison evidence;
5. run the eight-candidate PAPER matrix;
6. evaluate FL9 superiority exactly as measured.

Pump bonding-curve fee normalization remains a separate future slice and must be based on proven source semantics, not current protocol constants.

FL9 remains **EVIDENCE PENDING**.
LIVE remains disabled.
