# FL9 Deterministic Campaign Console Launcher — Design

**Date:** 2026-09-04

## Status

Implementation slice after campaign invocation-seal merge
`d4dd6db16439868f2b9b5afe53c9c4cd8c4a14a2` (#195).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Expose exactly one installable command for the sealed FL9 deterministic PAPER campaign path.

Invocation:

`shreks-fast-deterministic-campaign <request.json>`

The command accepts exactly one positional canonical request file and delegates only to:

`run_fast_deterministic_campaign_invocation_file(...)`.

## Output

On success stdout contains exactly one canonical JSON line:

- schema name/version;
- request fingerprint;
- source-snapshot fingerprint;
- campaign-artifact fingerprint;
- invocation fingerprint;
- invocation-seal path.

This gives operators and automation one machine-readable completion record without parsing logs.

## Packaging

`python/pyproject.toml` registers:

`shreks-fast-deterministic-campaign = "shreks_brain.fast_deterministic_campaign.cli:main"`

No separate shell wrapper or duplicate execution path is introduced.

## Authority boundary

The launcher does not assemble inputs, read provider data, hydrate evidence, run candidate logic directly, evaluate superiority, select a strategy, sign, submit, or enable LIVE.

All campaign behavior remains in the already sealed lower layers.

## TDD

Intentional RED:

`a8f6a6b4d40bc226191419d79ec5105499b08d1c`.

Tests require:

1. exactly one request argument;
2. direct delegation to the invocation-seal runner;
3. canonical one-line output;
4. registered installable script;
5. no duplicated campaign logic or authority expansion.

## Following step

Use the launcher on real non-fixture post-selection evidence.

The repository currently contains no committed real FL8.1 Parquet, observer DB, or non-fixture champion, so economic superiority cannot truthfully be claimed until runtime-produced evidence is supplied and executed.
