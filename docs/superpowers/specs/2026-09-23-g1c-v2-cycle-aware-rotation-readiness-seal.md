# G1C V2 Cycle-Aware Rotation Readiness — Release Seal

**Date:** 2026-09-23  
**Implementation main SHA:** `5c2f2a80525c07ecda8b854d14b6de7a0d56301a`  
**Implementation PR:** #473  
**Merged-main CI:** `35893618388`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READINESS FIX ONLY; MANIFEST ROTATION/SCORING/PAPER PROMOTION/LIVE BLOCKED

## Purpose

Seal the fail-closed readiness correction discovered after the reviewed WSOL v2 PAPER rotation rolled back safely.

The prior readiness proof authenticated the release, helper, source/candidate/binding chain, G7 state, service lifecycle, and candidate bootstrap. It did not prove that the candidate could assemble its first real production-shaped PAPER cycle using current observer evidence and dynamic quote-USD valuation.

That gap allowed a v2 candidate to receive `READY_EVIDENCE_ONLY`, pass systemd bootstrap preflight, and then fail during protected activation. The manifest manager restored the exact source manifest and wrote terminal rollback evidence.

## Production state before this seal

The active production release is:

`bc7c8f54c0099716eb3fa74f4eeeb438a68da80d`

The protected source PAPER manifest was restored after the failed rotation and remains the active authority.

The failed transition binding fingerprint is:

`d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`

Its protected rotation evidence directory contains immutable `prepared.json` and `rolled-back.json` receipts and no `activated.json`.

That binding is consumed terminal evidence. Do not delete its evidence directory and do not retry that binding.

Scoring authority remains `NOT_GRANTED`, PAPER promotion remains `BLOCKED`, and LIVE remains `DISABLED`.

## Root cause of the readiness gap

The candidate runtime bootstrap validates canonical manifest content, durable PAPER state, and runner construction without advancing a cycle.

A real PAPER iteration additionally performs current observer candidate selection and component cycle assembly. For runtime-manifest v2, route economics can require `exact_market_ratio` quote-USD evidence at the current market row.

The production diagnostic showed the WSOL candidate bootstrap reached `READY`, while the protected rotation later rolled back before durable activation. The existing readiness proof never exercised the production-shaped next-cycle assembly path.

## Fix

PR #473 adds:

`preflight_observer_paper_campaign_next_cycle`

to the PAPER runtime.

This helper:

- authenticates and bootstraps the candidate through the existing runtime path;
- accepts one explicit non-negative as-of timestamp;
- assembles one aggregate production-shaped PAPER cycle against the configured observer database;
- exercises current candidate selection, candidate-specific quote identity, route evidence, and dynamic quote-USD valuation;
- never calls `run_paper_cycle`;
- never writes E11 evidence;
- never writes PAPER checkpoints;
- never mutates the observer database;
- never invokes the protected manifest manager;
- never stops/starts/restarts services.

Protected rotation readiness now requires, inside the same private-candidate readiness window:

1. the existing durable-state/bootstrap preflight; and
2. one read-only next-cycle assembly at the current wall-clock timestamp.

The existing readiness receipt schema remains unchanged. On success:

`candidate_preflight_status=PASSED`

now means both bootstrap and read-only next-cycle assembly passed.

This is point-in-time readiness evidence only. It does not guarantee market evidence will remain fresh indefinitely.

## Regression proof

PR #473 final head:

`84df8dbea23a6fc543caa66d47cc952442974563`

The regression models the production failure shape:

- authenticated v2 candidate uses WSOL with `exact_market_ratio`;
- a matching routed WSOL entry quote exists;
- exact WSOL market evidence is deliberately unavailable;
- ordinary bootstrap succeeds;
- the new next-cycle assembly preflight fails closed;
- no checkpoint or E11 state is written.

Final PR CI run:

`35893281341`

Result:

- Python: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

Merged main:

`5c2f2a80525c07ecda8b854d14b6de7a0d56301a`

Merged-main CI:

`35893618388`

Result: SUCCESS across all four canonical gates.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and its exact merged-main CI succeeds, authorize the existing automatic release/deploy chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. carry the cycle-aware readiness implementation;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. keep the restored protected source PAPER manifest in place;
6. verify ordinary production release/service health and read-only tooling presence.

Automatic deployment must not:

- delete or alter the failed rotation evidence;
- retry binding `d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`;
- rotate `/etc/shreks/paper-campaign.json`;
- manufacture a replacement candidate or transition binding;
- refresh helper installation proof;
- execute rotation readiness;
- execute a rotation plan;
- invoke `shreks-paper-manifest-manager rotate`;
- execute scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Helper/proof boundary after release change

The manifest-manager source itself is unchanged by this readiness fix. The currently installed helper must still be observed and authenticated against the newly active immutable release.

Any prior helper installation proof is release-bound and becomes stale after the release SHA changes.

Before any later protected readiness ceremony, a trusted administrator must create a fresh exact-release helper installation proof under the newly active release.

A fresh helper proof does not authorize rotation.

## Failed binding and future candidate boundary

The rolled-back binding is terminal and must not be reused.

This seal does not authorize creating a replacement candidate, changing production economics, selecting a new paper-run identity, changing start time, or manufacturing a new transition binding.

Any future candidate/binding chain is a separate reviewed authority decision. It must be compatible with the current source/frozen cohort/request authority and must pass the newly strengthened readiness check before a read-only plan can even be considered.

## Authority firewall

This seal grants no runtime-manifest mutation authority.

Expected authority remains:

```text
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## Promotion boundary

`CYCLE_AWARE_ROTATION_READINESS=SEALED_FOR_RELEASE`

`FAILED_BINDING_REUSE=FORBIDDEN`

`AUTOMATIC_HELPER_PROOF_REFRESH=DISABLED`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED`

`SCORING_AUTHORITY=NOT_GRANTED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
