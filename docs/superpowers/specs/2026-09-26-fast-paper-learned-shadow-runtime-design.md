# Fast PAPER Learned Shadow Runtime — Design

Date: 2026-09-26
Status: RED contract
Parent plan: `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`
Required base: `002a4a4f255736cacf54d6df72c185c1291a3128`

## Purpose

Run the exact approved Fast Lane champion on fresh canonical runtime feature rows before it receives authoritative PAPER execution authority.

This slice is shadow-only. The active `shreks-paper-campaign.service`, its authoritative `PaperLedger`, and all LIVE/signing/submission surfaces remain unchanged.

## Runtime contract

The shadow engine consumes:

- an exact `FastPaperRuntimeManifest`;
- canonical `FastTrainingFeatureRecord` values from the bounded runtime feed;
- explicit point-in-time `FastCampaignDecisionPosition` posture;
- explicit `FastCampaignActionConstraints` derived from then-known route/execution evidence;
- one evaluation timestamp per decision.

For a bounded batch it must:

1. verify manifest/champion/binary bindings;
2. build canonical `FastCampaignDecisionRequest` values;
3. call the release-bound `shreks-fast-campaign-decision` path;
4. require exact champion version/fingerprint equality;
5. require one result for every requested source identity in the same order;
6. record action, reason, selected horizon, reward/risk/execution-cost/value, posture, and latency;
7. fingerprint every evidence row and the resulting ledger deterministically;
8. return evidence only. No authoritative PAPER ledger write is permitted.

## Evidence model

`FastPaperShadowDecisionEvidence` is immutable and includes:

- manifest fingerprint and release SHA;
- champion version/fingerprint;
- action-policy version;
- source event identity, sequence, market key, decision time;
- evaluation time and event-to-decision latency;
- action/reason;
- selected horizon;
- current and target exposure;
- selected reward, risk, execution cost, and comparison value;
- explicit quote/route state label;
- record fingerprint.

`FastPaperShadowEvidenceLedger` stores canonical ordered unique evidence records and a deterministic ledger fingerprint.

## Persistence

The shadow evidence store must be separate from:

- `manifest.paper_evidence_path`;
- `manifest.checkpoint_path`;
- the authoritative legacy PAPER ledger/evidence root.

Writes are atomic, private, canonical JSON and restart-idempotent by source identity + record fingerprint.

Re-appending an identical decision is a no-op. A conflicting record for an existing source identity fails closed.

## Service boundary

A separate `deploy/systemd/shreks-fast-paper-shadow.service` may be packaged.

It must:

- run as `shreks:shreks`;
- use the immutable release Python;
- be PAPER/shadow only;
- never replace, stop, require, conflict with, or become `PartOf` the legacy `shreks-paper-campaign.service`;
- have no wallet/private-key/signing/submission environment;
- have write access only to its dedicated shadow state/evidence directory.

It is not added to `shreks.target` in this slice.

## RED acceptance

Tests require:

- exact public shadow API;
- exact champion/result population validation;
- deterministic evidence fingerprints;
- idempotent append and conflict rejection;
- score/future-label/counterfactual imports absent from the shadow module;
- authoritative PAPER paths rejected as shadow evidence destinations;
- separate non-authoritative systemd unit with no legacy-service lifecycle coupling;
- no LIVE/signing/submission authority.

## Deferred within the parent PR3 gate

A following GREEN extension may attach realistic execution to a dedicated isolated shadow `PaperLedger` and emit after-cost comparison metrics. That ledger must remain physically separate from the authoritative PAPER ledger.