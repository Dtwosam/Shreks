# FL9 Runtime-Backed Forecast Context Hydration Policy — Design

**Date:** 2026-09-04

## Status

Operational-input bridge after the one-command first-champion host path was sealed and released as
`7fcc5d0b9301419e0e319adf76853fa3e2db2723`.

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Create the canonical #207 `FastForecastContextHydrationPolicy` file from the already-authenticated
PAPER campaign runtime manifest without duplicating or inventing regime, safety, quote-asset, or
global-risk state.

The release containing #210 can already consume a canonical hydration-policy file. The remaining
operational risk was that an operator could manually reconstruct nested regime/safety/probe objects
and accidentally drift from the policy actually used by the PAPER runtime.

This bridge removes that drift while keeping every assumption not present in the runtime manifest
explicit.

## Source of authority

Input is one canonical
`ObserverPaperCampaignRuntimeManifest`
(`g1c-paper-campaign-runtime-manifest-v1`).

The existing sealed runtime-manifest codec is authoritative.

Both file and in-memory bridge paths call
`encode_observer_paper_campaign_runtime_manifest(...)`
before deriving policy. That encoder recomputes the complete manifest fingerprint and rejects stale
or hand-mutated dataclasses.

The file path additionally strict-decodes the source bytes first.

## Fields derived from the PAPER runtime manifest

The bridge copies exactly:

- `regime_read_policy` from `policy_bundle.regime_read_policy`;
- `regime_policy` from `policy_bundle.regime_policy`;
- `safety_policy` from `policy_bundle.safety_policy`;
- `safety_probe_identity` from `policy_bundle.safety_probe_identity`;
- `global_risk_halt` from the top-level runtime manifest;
- `exit_quote_provider` from the bundled canonical entry quote provider;
- `quote_asset_decimals` from the bundled quote asset.

The existing
`ObserverFreshLaunchPolicyBundle`
already proves that:

- entry quote provider is the sealed Jupiter provider;
- entry/regime/safety probe policy versions align;
- quote asset mints align;
- taker and slippage identities align.

The bridge does not relax those checks.

## Fields that remain explicit

The current runtime manifest does **not** authoritatively define the following FL9 evaluation
assumptions:

1. hydration policy version;
2. strategy-family segmentation labels;
3. maximum accepted age of a persisted EXIT quote;
4. execution-cost policy version;
5. expected round-trip cost bps.

The bridge therefore requires all five.

Expected round-trip cost accepts either:

- an explicit non-negative finite number; or
- the literal `unknown`, which maps to #207's existing `None` semantics.

Unknown is not converted to zero.

Strategy-family inputs must be non-empty and unique. Their order is canonicalized because the target
#207 policy schema requires sorted family labels.

No strategy family is inferred from later outcome, champion selection, PnL, or model performance.

## File writer

The writer requires:

- existing real non-symlink runtime manifest file;
- absent destination.

It:

1. stable-reads source bytes with device/inode/size/mtime checks;
2. strict-decodes the G1C runtime manifest;
3. fingerprint-authenticates the manifest again through the sealed encoder;
4. constructs the exact existing #207 policy object;
5. encodes with #207's canonical policy codec;
6. stages in a sibling temporary file;
7. flushes and `fsync`s;
8. applies mode `0600`;
9. stable-rereads the source and requires byte equality;
10. requires staged bytes still equal encoded bytes;
11. refuses a destination that appeared during execution;
12. atomically renames the staged file.

Any failure removes staging.

The writer never overwrites an existing policy file.

## Output provenance

`FastRuntimeHydrationPolicyWriteResult` returns:

- published path;
- authenticated PAPER runtime-manifest fingerprint;
- canonical #207 hydration-policy fingerprint.

The console command emits those same fingerprints as compact JSON.

## Console command

The release wheel exposes:

`shreks-fast-context-policy-from-runtime`.

Required arguments:

- `--runtime-manifest`;
- `--destination`;
- `--version`;
- one or more `--strategy-family`;
- `--max-exit-quote-age-ms`;
- `--execution-cost-policy-version`;
- `--expected-round-trip-cost-bps <number|unknown>`.

There are no hidden economic defaults.

## TDD provenance

Intentional RED:

`a950cfe3df9f97ab376132950e49acee4c361f46`.

Python failed only during collection with:

`ModuleNotFoundError: No module named 'shreks_brain.fast_runtime_hydration_policy'`.

Repository safety was already GREEN.

The implementation intentionally keeps direct in-memory manifest authentication. A test that needs
a different global-risk-halt state rebuilds the runtime manifest through its sealed builder rather
than using `dataclasses.replace` with a stale fingerprint.

## Authority boundary

The module contains no:

- provider/network calls;
- direct SQLite queries;
- new regime or safety logic;
- model fitting;
- PAPER trade execution;
- trade intent construction;
- registry/promotion mutation;
- signing;
- transaction submission;
- LIVE authority.

It transforms one authenticated policy artifact into another.

## Following work

Once this slice is sealed and released, the production first-champion workflow no longer requires
manual reconstruction of nested runtime policy.

The remaining host-side inputs are intentionally small and auditable:

1. deploy the sealed ARM64 release through the existing protected production-PAPER workflow;
2. run #206 against the protected observer DB;
3. run this bridge against the exact active PAPER runtime manifest with explicit FL9-only assumptions;
4. create the canonical #210 host request pinned to release SHA + policy fingerprint;
5. run `shreks-fast-first-champion-run`;
6. preserve either the immutable host-run artifact or the exact fail-closed evidence result.

LIVE remains disabled.
