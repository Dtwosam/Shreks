# FL9 V2 Discovery-Backed Request Preparation Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic request preparation or scoring

## Purpose

The discovery-backed V2 request-preparation bridge is implemented and merged separately.

Before a trusted administrator may use it against protected production-paper evidence, the
ordinary production verifier must prove that the exact active immutable release contains the
preparation CLI and module.

This slice adds exact-release presence/provenance proof and one bounded runbook ceremony only.

## Production verifier contract

Require:

- release-local console script `shreks-fl9-v2-discovery-backed-request-prepare`;
- regular non-symlink executable;
- resolved script path exactly under the expected immutable release;
- module `shreks_brain.fl9_v2_discovery_backed_request_preparation`;
- module path resolving inside that same expected release.

Expected evidence:

```text
fl9_v2_discovery_backed_request_prepare=present
fl9_v2_discovery_backed_request_prepare_path=<exact-release-local-path>
fl9_v2_discovery_backed_request_prepare_module=<exact-release-local-module-path>
```

The production verifier must not execute the preparation command.

## Trusted-admin preparation ceremony

Document one root-private ceremony that supplies only reviewed existing evidence plus explicit
request-policy inputs to the release-local preparation tool.

The ceremony must provide:

- exact discovery-authority binding;
- exact proof workspace;
- observer database;
- frozen V2 cohort;
- hydration policy;
- training-economics overlay;
- training execution-cost policy;
- TEST evaluation policy;
- new non-existing request destination;
- new non-existing future evidence destination;
- new non-existing preparation-receipt destination;
- explicit future-path label version;
- explicit counterfactual base quantity;
- explicit champion/model/training policy versions;
- explicit reason.

The preparation tool authenticates the binding-selected runtime manifest and the exact
release/cohort/hydration identities, delegates canonical request construction to the sealed V2
request writer, and emits one immutable companion preparation receipt.

A successful receipt remains evidence only:

```text
request_preparation_authority=DISCOVERY_BOUND_REQUEST_ONLY
scoring_authority=NOT_GRANTED
champion_publication_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## Authority boundary

This slice does not authorize:

- automatic preparation execution;
- V2 scoring or model fitting;
- champion evidence publication;
- PAPER promotion;
- risk intent;
- wallet access;
- signing/submission;
- LIVE.

A separate later decision must explicitly authorize any scoring execution.
