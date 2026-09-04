# FL9 Deterministic Candidate Manifest — Design

**Date:** 2026-09-04

## Status

Design after deterministic lifecycle canonical wire merged as `5d90afa561c8f78b2ebc067bfcbc26167dd2a35a` (PR #172).

FL9 economic exit remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Create an honest, canonical deterministic candidate identity for FL9 baseline comparison campaigns.

The merged lifecycle decision-batch fingerprint authenticates one ordered result batch. It is not stable candidate provenance and must not be reused as `candidate_fingerprint_sha256`.

This slice fingerprints the actual deterministic candidate configuration.

## Candidate identity

Schema:

`shreks.fast_deterministic_candidate_manifest`, version `1`.

Manifest fields:

- `candidate_version` — explicit caller-selected immutable candidate label;
- `strategy_family = "fast_deterministic_lifecycle"`;
- `strategy_version` — explicit caller-selected strategy attribution;
- lifecycle policy:
  - lifecycle version;
  - selected FL6.1–FL6.4 entry kind;
  - selected FL6.5–FL6.6 manager kind;
  - entry target exposure fraction;
  - REDUCE remaining-exposure fraction;
- exact selected entry-policy parameters;
- exact selected manager-policy parameters;
- `candidate_fingerprint_sha256`.

The fingerprint excludes only `candidate_fingerprint_sha256` itself.

## What the fingerprint covers

For the selected entry policy, every policy field is included:

### FL6.1 Impulse Scalp

- version;
- signal/context windows;
- count/actor thresholds;
- imbalance thresholds;
- velocity/acceleration/expansion thresholds;
- recovery/drawdown thresholds.

### FL6.2 Micro Pullback

- version;
- reclaim/structure windows;
- impulse/pullback/reclaim thresholds;
- buy/sell arrival thresholds;
- count/flow/velocity/acceleration thresholds.

### FL6.3 Pre-Graduation

- version;
- signal/context windows;
- graduation reserve target/boundary;
- buy/actor/arrival thresholds;
- count/flow/velocity/acceleration/expansion thresholds;
- remaining-reserve participation threshold.

### FL6.4 Graduation Flow

- version;
- flow window;
- max graduation age;
- pre/post buy thresholds;
- post actor/arrival/sell thresholds;
- post count/flow/velocity/acceleration thresholds;
- post/pre velocity ratio.

For the selected manager policy, every policy field is included:

### FL6.5 Wallet Cohort

- version;
- support count/weight/independence thresholds;
- hold-horizon weight threshold;
- reduce-after-median-hold ratio;
- reduce exit-weight/pressure thresholds;
- sell exit-weight/pressure/independence thresholds.

### FL6.6 Longer Runner

- version;
- downside risk weight;
- minimum hold continuation bps;
- maximum sell continuation bps.

No market evidence, current position, quote, execution economics, forecast observation, decision output, PAPER fill, or evaluation result is part of candidate configuration identity.

## Rust API

Add `crates/shreks-storage/src/fast_deterministic_candidate_manifest.rs`.

Public typed inputs:

- `FastDeterministicEntryPolicyRef<'a>` with variants for FL6.1–FL6.4 policy references;
- `FastDeterministicManagerPolicyRef<'a>` with variants for FL6.5–FL6.6 policy references.

Public output/codec:

- manifest schema constants;
- wire structs;
- `build_fast_deterministic_candidate_manifest(...)`;
- `encode_fast_deterministic_candidate_manifest_json(...)`;
- `decode_fast_deterministic_candidate_manifest_json(...)`.

Builder requirements:

- exact lifecycle version;
- entry/manager enum variants must match lifecycle kinds;
- selected policy versions must match their sealed FL6 baseline versions;
- caller strings non-empty;
- all floating policy values finite;
- canonical SHA-256 fingerprint.

The builder does not evaluate market state and has no execution authority.

## Python package

Extend `shreks_brain.fast_deterministic_lifecycle` with immutable candidate-manifest models/codec.

Public:

- manifest schema constants;
- manifest dataclasses;
- `decode_fast_deterministic_candidate_manifest(...)`.

Python validation mirrors Rust:

- exact fields;
- canonical JSON;
- fingerprint authentication before semantic validation;
- entry/manager kind matches lifecycle policy;
- component parameter shape matches declared kind;
- component versions equal sealed FL6 versions;
- finite numeric values;
- non-empty identity strings.

The decoded manifest supplies the exact:

- `candidate_version`;
- `candidate_fingerprint_sha256`;
- `strategy_family`;
- `strategy_version`

required by the existing Fast Campaign PAPER identity model.

## Shared golden fixture

Commit one canonical fixture:

`python/tests/fixtures/fast_deterministic_candidate_manifest_v1.json`

Use an explicit Impulse Scalp + Longer Runner candidate matching the existing lifecycle test policy values.

Rust and Python must accept identical bytes and identical `candidate_fingerprint_sha256`.

## Boundary

This slice does not:

- include decision-batch fingerprints in candidate identity;
- include dynamic market/PAPER evidence in candidate identity;
- create a registry candidate;
- create PAPER fills;
- source quotes;
- create risk authority;
- create E11/E5 evidence;
- claim superiority;
- promote;
- enable LIVE.

## Next slice

Add a deterministic lifecycle PAPER adapter that accepts:

1. decoded deterministic candidate manifest;
2. decoded lifecycle decision batch;
3. explicit contemporaneous quote/risk/economic evidence;

and routes the exact actions through the already-sealed FL7 PAPER executor with the manifest's real candidate identity.

No synthetic fills. No candidate fingerprint aliases.
