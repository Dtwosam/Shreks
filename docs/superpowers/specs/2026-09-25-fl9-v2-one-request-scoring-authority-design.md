# FL9 V2 One-Request Scoring Authority — Design

**Date:** 2026-09-25  
**Base main SHA:** `3fb723a81c8c155d79e6eec3400a6bbbeba088aa`  
**Status:** implementation slice only; scoring execution remains separate

## Production context

The exact production-verified release has already produced:

```text
g1c_v2_mint_state_physical_acceptance=PASS
fl9_v2_discovery_status=FOUND_COMPATIBLE
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

Main now contains exact-release-bound trusted-admin ceremonies for:

1. binding one reviewed `FOUND_COMPATIBLE` discovery result;
2. preparing one canonical discovery-backed FL9 V2 host request and evidence destination.

The preparation receipt intentionally preserves:

```text
request_preparation_authority=DISCOVERY_BOUND_REQUEST_ONLY
scoring_authority=NOT_GRANTED
champion_publication_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The missing boundary is an explicit decision artifact between request preparation and any
V2 scoring/model-fitting execution.

## Goal

Add one write-once authority artifact that can record either:

- explicit authorization for one exact discovery-backed V2 scoring/model-fitting run; or
- explicit rejection of that run.

The artifact must bind the exact prepared request bytes, preparation receipt, release,
cohort, hydration policy, runtime-manifest authority, and evidence destination.

This slice must not execute scoring.

## Inputs

The authority writer accepts:

- one canonical discovery-backed request-preparation receipt;
- one explicit decision:
  - `AUTHORIZE_ONE_SCORING_RUN`, or
  - `REJECT_SCORING_RUN`;
- one non-empty decision reason;
- one new non-existing destination.

The request path is taken only from the authenticated preparation receipt. The writer does
not accept an alternate request path.

## Authentication

Before writing authority, require:

- preparation receipt strict-decodes canonically;
- preparation authority is exactly `DISCOVERY_BOUND_REQUEST_ONLY`;
- preparation scoring/champion authority is still not granted;
- preparation PAPER promotion is blocked and LIVE is disabled;
- request path is an existing regular non-symlink file;
- request byte SHA-256 equals the preparation receipt;
- request strict-decodes as the canonical FL9 V2 host request;
- request fingerprint equals the preparation receipt;
- request release SHA equals the preparation receipt release SHA;
- request cohort fingerprint equals the preparation receipt cohort fingerprint;
- request hydration-policy fingerprint equals the preparation receipt hydration fingerprint;
- request evidence destination equals the preparation receipt evidence destination;
- preparation receipt and request bytes are unchanged immediately before publication.

## Artifact

Schema:

`shreks.fl9_v2_scoring_authority` version 1.

For an authorization decision:

```text
status=SCORING_AUTHORIZED
scoring_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN
model_fitting_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN
champion_publication_authority=SCORING_EVIDENCE_ONLY
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

For rejection:

```text
status=SCORING_REJECTED
scoring_authority=NOT_GRANTED
model_fitting_authority=NOT_GRANTED
champion_publication_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The artifact is canonical JSON, mode `0600`, fingerprinted, and never overwrites an
existing destination.

## Authority firewall

This module must not import or call:

- V2 host-run execution;
- model builder/model fitting;
- champion evidence writer;
- PAPER campaign execution;
- risk intent;
- transaction construction;
- signing/submission;
- LIVE runtime.

A later separately reviewed execution bridge may consume this authority artifact and the
exact request. This slice does not provide that bridge.

## RED proof

Add tests first that require:

- canonical write-once authority;
- exact request/preparation identity binding;
- authorize and reject semantics;
- tamper rejection;
- unchanged PAPER/LIVE blocks;
- CLI presence;
- source firewall proving no scorer/executor call is present.

Current main must fail because the module/CLI do not yet exist.

## GREEN proof

Implement only the authority artifact and CLI. Keep existing strategy, scoring, model,
PAPER, risk, manifest, promotion, and LIVE behavior unchanged.
