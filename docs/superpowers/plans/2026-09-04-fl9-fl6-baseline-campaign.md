# FL9 FL6 Same-Population Baseline Campaign — Implementation Plan

**Date:** 2026-09-04  
**Base:** `dc198ef2d0b22367f9eb49c7d77d9c2ef2a9b6fe`

## Goal

Add one pure composer that evaluates a specific sealed FL6 baseline from the exact immutable FL8.1 row used by the learned campaign, with caller-supplied posture and baseline-specific evidence only.

## Scope

Production:

- new `crates/shreks-storage/src/fast_baseline_campaign.rs`;
- export wiring in `crates/shreks-storage/src/lib.rs`.

Tests:

- new `crates/shreks-storage/tests/fl9_fast_baseline_campaign.rs`.

Docs:

- design;
- this plan.

No migration/database query/provider/runtime/PAPER/risk/promotion/signer/LIVE files.

## TDD

### RED

Commit contract tests before production module exists.

Required imports:

- `FAST_BASELINE_CAMPAIGN_VERSION`;
- `FastBaselineCampaignInput`;
- `FastBaselineCampaignAssessment`;
- `FastBaselineCampaignError`;
- `evaluate_fast_baseline_campaign`.

Required cases:

- Impulse Scalp direct replay parity + exact population identity;
- wrong-posture explicit not-applicable;
- execution market/timestamp mismatch wraps replay failure;
- Longer Runner missing-continuation REDUCE parity;
- Graduation Flow explicit pre snapshot/current hydrated post snapshot;
- deterministic repeat;
- source-authority firewall.

Open draft PR at intentional missing-contract head and record exact Rust RED.

### GREEN

Implement the smallest composer:

1. hydrate exact record with `hydrate_fast_baseline_snapshot`;
2. map campaign input variant to one `FastBaselineReplayInput`;
3. inject `&hydration.snapshot` as current/post snapshot;
4. delegate to `replay_fast_baseline`;
5. fail closed if returned replay market/time disagree with hydration;
6. return exact identity and typed assessment.

No economic calculation belongs in this module.

### Verification

Require:

1. Repository safety;
2. Python;
3. Rust workspace;
4. native ARM64 release build.

Freeze candidate while CI runs.

### Audit

Confirm:

- exact 4-field identity parity with Python campaign;
- current snapshot cannot be caller-substituted;
- graduation pre snapshot is explicit;
- no future labels/counterfactuals;
- no PAPER quote/fill code;
- no risk mutation/promotion/LIVE authority.

### Seal

After exact-head 4/4 GREEN:

- update PR with RED/GREEN chain;
- mark ready;
- guarded squash merge with expected head SHA;
- root next branch at exact merge SHA.

## Following work

Build authoritative adapters for explicit baseline evidence and ordered baseline decision streams, then execute learned/baseline streams with identical contemporaneous PAPER quote evidence through the sealed FL7/E11/E5/FL9 proof chain.
