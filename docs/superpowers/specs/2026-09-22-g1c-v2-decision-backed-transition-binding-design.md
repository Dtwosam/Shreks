# G1C V2 Decision-Backed Transition Binding — Design

**Date:** 2026-09-22  
**Status:** software contract only; no production execution or manifest mutation

## Purpose

The exact decision-backed candidate authoring path now produces only the canonical runtime-manifest v2 candidate already committed by an authenticated decision-backed candidate authority.

The existing transition binder already performs the frozen cohort/request compatibility assessment and emits the standard immutable transition-binding schema consumed by later readiness.

The remaining provenance gap is that the existing transition binder does not authenticate the decision-backed authority chain that committed the source, candidate, cohort, and request identities.

This bridge closes that gap without changing the existing transition-binding schema.

## Inputs

The bridge accepts only explicit existing artifacts plus one new destination:

- canonical v1 source runtime manifest;
- exact canonical v2 candidate runtime manifest;
- authenticated decision-backed candidate authority;
- frozen V2 cohort directory artifact;
- authenticated V2 host request authority;
- new non-existent transition-binding destination.

It accepts no raw:

- paper-run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry input amount;
- candidate-value decision;
- quote valuation review or sizing values.

## Authentication and binding contract

The bridge must:

1. require source, candidate, decision-backed authority, and request inputs to be existing regular non-symlink files, and require the frozen cohort to be an existing non-symlink directory artifact;
2. stable-read the source, candidate, and decision-backed authority;
3. authenticate the source and candidate runtime manifests;
4. authenticate the decision-backed candidate authority;
5. require the source SHA/fingerprint/paper-run/quote identity to equal the authority;
6. require the candidate SHA/fingerprint/paper-run/start timestamp/quote mint/quote decimals/entry amount/valuation mode to equal the authority;
7. derive the existing standard transition binding into a private temporary destination by invoking the existing canonical transition binder with the supplied source/candidate/cohort/request;
8. require all overlapping standard-binding source/candidate/cohort/request provenance to equal the authenticated decision-backed authority;
9. re-read the source, candidate, and authority and fail if any bytes changed;
10. persist only the already validated standard transition-binding bytes to the requested new destination with mode 0600;
11. authenticate and round-trip the written standard transition binding.

The output file remains schema:

`shreks.g1c_v2_runtime_manifest_transition_binding` version 1.

No downstream consumer needs a schema migration.

## CLI

Register:

`shreks-g1c-v2-decision-backed-transition-bind`

Required arguments:

- `--source-runtime-manifest`
- `--candidate-runtime-manifest`
- `--decision-backed-candidate-authority`
- `--cohort`
- `--v2-host-request-authority`
- `--destination`

The CLI must not expose raw candidate economics or new-run identity/time.

## Authority boundary

A successful binding preserves:

```text
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

This bridge does not:

- execute rotation-readiness;
- install, activate, or rotate a runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

Production use requires a later, separate production-presence proof and seal.
