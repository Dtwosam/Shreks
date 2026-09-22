# FL9 V2 Discovery-Backed Request Preparation — Design

**Date:** 2026-09-22  
**Status:** software contract only; fresh request/provenance preparation; scoring execution not authorized

## Purpose

A sealed `FOUND_COMPATIBLE` discovery result can already be converted into one exact
`shreks.fl9_v2_discovery_authority_binding` artifact.

The existing V2 first-champion request writer can already authenticate proof workspace,
database, frozen cohort, hydration policy, training economics, and execution-cost policy
and write one canonical non-overwrite host request.

The missing provenance link is that an ordinary V2 host request does not carry the
selected runtime-manifest identity or the discovery-authority binding that established
that runtime/hydration compatibility.

This slice adds a preparation bridge that:

1. authenticates one discovery-authority binding;
2. verifies its release/cohort/hydration identities against freshly supplied request sources;
3. verifies the exact selected runtime-manifest source still authenticates to the binding;
4. delegates request construction to the existing canonical V2 request writer;
5. writes one immutable companion preparation receipt linking the discovery binding to the
   exact canonical request bytes and request fingerprint;
6. executes no scoring/model fitting.

## Inputs

Required existing sources:

- discovery-authority binding;
- proof workspace;
- observer database;
- frozen V2 cohort;
- hydration policy;
- selected runtime manifest named by the binding;
- training-economics overlay;
- training execution-cost policy.

Required new destinations:

- canonical V2 host request;
- future V2 evidence directory path, which must not already exist;
- preparation receipt.

Request policy inputs remain exactly those already accepted by
`write_fast_first_champion_v2_host_request_from_sources`:

- future-path label version;
- counterfactual base quantity;
- TEST evaluation policy;
- champion version;
- model version prefix;
- training policy version;
- explicit reason.

No horizon, split, selection timestamp, or scoring-floor tuning is added.

## Authority checks

Before request publication require:

- discovery binding canonical/fingerprint-valid;
- discovery binding release SHA equals the proof workspace release SHA;
- discovery binding cohort fingerprint equals the physical frozen cohort fingerprint;
- discovery binding hydration-policy fingerprint equals the supplied hydration policy;
- selected runtime-manifest path is a real non-symlink file;
- selected runtime-manifest fingerprint equals the discovery binding;
- selected runtime-manifest quote mint/decimals equal the discovery binding.

After the existing request writer returns require:

- request strict-decodes canonically;
- request release SHA equals discovery binding release SHA;
- request cohort fingerprint equals discovery binding cohort fingerprint;
- request hydration fingerprint equals discovery binding hydration fingerprint;
- request destination is the exact supplied future evidence destination;
- all immutable source inputs remain stable.

## Preparation receipt

Write one canonical mode-0600 non-overwrite artifact:

`shreks.fl9_v2_discovery_backed_request_preparation` version 1.

It records at least:

- discovery binding SHA-256 and binding fingerprint;
- selected runtime-manifest fingerprint/source provenance;
- release/cohort/hydration identities;
- request SHA-256 and request fingerprint;
- request path;
- future evidence destination;
- preparation fingerprint.

Authority remains:

```text
request_preparation_authority=DISCOVERY_BOUND_REQUEST_ONLY
scoring_authority=NOT_GRANTED
champion_publication_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## CLI

Register:

`shreks-fl9-v2-discovery-backed-request-prepare`

The CLI may publish only the request and companion preparation receipt.

It must not import or call:

- `run_fast_first_champion_v2_host_request`;
- model builders;
- scoring/evaluation execution;
- champion evidence writers;
- PAPER/risk/signing/submission/LIVE surfaces.

## Authority boundary

This slice authorizes software construction and offline request preparation only after a
later separate seal.

It does not authorize production execution of the preparation tool, V2 scoring retry,
model fitting, champion evidence publication, PAPER promotion, risk intent, signing,
submission, or LIVE.
