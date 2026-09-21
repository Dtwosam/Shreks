# G1C V2 Runtime-Manifest Candidate Input Authority — Design

**Date:** 2026-09-21  
**Status:** implementation slice; explicit candidate-input binding only; production candidate values remain separately reviewed

## Purpose

The exact release-bound PAPER manifest-manager helper is now physically installed and canonically verified on production. Rotation-readiness cannot run because no canonical G1C v2 candidate or transition binding exists, and the repository deliberately provides no production defaults for the new run's quote economics.

This slice adds the smallest missing authority surface: bind one set of **explicitly supplied** new-run candidate inputs to the exact authenticated v1 source, frozen FL9 V2 cohort, and preserved authenticated V2 request authority.

It does not choose values and does not infer them from test fixtures, the cohort, recent quote evidence, or the historical USDC hydration policy.

## Explicit inputs

The binder requires all of the following from the caller:

- authenticated canonical v1 source runtime-manifest path;
- frozen FL9 V2 cohort path;
- preserved authenticated V2 host-request authority path;
- new `paper_run_id`;
- new-run `start_at_unix_ms`;
- target quote mint;
- target quote decimals;
- target raw `entry_input_amount`;
- a new destination path.

No production default is provided for any new-run value.

## Authentication and validation

The binder:

1. stable-reads and authenticates the exact v1 source manifest;
2. authenticates the preserved V2 request against the frozen cohort using the existing sealed request-authority path;
3. re-reads the frozen cohort and requires its artifact fingerprint to remain equal to the authenticated request authority;
4. derives the cohort's single quote mint only to validate the caller's explicit target quote mint;
5. rejects any target quote mint that does not exactly equal the frozen cohort quote mint;
6. calls the existing canonical G1C v2 candidate-authoring function in memory with the explicit values;
7. canonical-encodes and decodes that candidate and commits to its exact raw SHA-256 and runtime-manifest fingerprint;
8. stable-reads the source again and rejects source mutation across the operation.

The cohort does not supply quote decimals or raw entry amount. The historical request/hydration policy does not supply replacement runtime quote economics.

## Artifact

The result is one canonical JSON file written once with mode `0600`.

It commits to:

- source raw SHA-256, runtime-manifest fingerprint, run id, and quote mint;
- exact derived candidate raw SHA-256 and runtime-manifest fingerprint;
- explicit candidate run id, start timestamp, quote mint, quote decimals, and raw entry amount;
- candidate `exact_market_ratio` valuation mode;
- frozen cohort artifact fingerprint and quote mint;
- preserved request fingerprint and release-source SHA;
- preserved request hydration-policy fingerprint;
- explicit authority boundaries;
- one SHA-256 fingerprint over all material fields.

The artifact records `candidate_authoring_authority=EXPLICIT_INPUTS_BOUND`. This means the exact supplied values are bound; it is not production manifest installation or rotation permission.

## Authority boundary

The artifact always records:

- `installation_authority = NOT_GRANTED`;
- `activation_authority = NOT_GRANTED`;
- `rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

The implementation contains no protected-host default paths, service control, database reads, scoring/model fitting, promotion, wallet/signing, submission, or LIVE path.

## Fail-closed behavior

No artifact is written when:

- source authentication fails;
- request/cohort authentication fails;
- the cohort changes across authentication;
- the cohort does not contain exactly one quote mint;
- the explicit target quote mint differs from the frozen cohort;
- any explicit candidate input violates the existing canonical authoring contract;
- the source changes while candidate identity is derived;
- the destination already exists;
- canonical write/readback changes the artifact;
- decoder authority fields or the artifact fingerprint are altered.

## Next separate slice

After implementation is GREEN and separately sealed for production use, a reviewed production artifact may bind the exact chosen values.

Only then should the existing canonical candidate-authoring path emit the candidate bytes, followed by the existing read-only compatible assessment and transition binding.

Rotation-readiness, production manifest rotation, V2 scoring, PAPER promotion, signing/submission, and LIVE remain blocked.
