# FL9 V2 Discovery Authority Binding — Release Seal

**Date:** 2026-09-18  
**Implementation main SHA:** `0ae11d161ef617ec4e2ed8c8d0fd0fd271bff235`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; DISCOVERY/BINDING EVIDENCE ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified FL9 V2 discovery-authority binder that converts one trusted canonical `FOUND_COMPATIBLE` production discovery result into one exact immutable evidence binding.

This seal also includes the previously sealed telemetry discovery bridge because the binder implementation is based directly on that release line. The next protected deploy therefore needs only one new release.

## Implemented binding

Merged PR #312, `feat: bind FL9 V2 discovery authority`, adds:

1. strict canonical decoding of one `shreks.fl9_v2_discovery_control_result`;
2. mandatory top-level `FOUND_COMPATIBLE`;
3. exact expected/observed release-SHA equality;
4. exactly one authenticated prior-request authority group;
5. authenticated frozen-cohort artifact provenance carried through request-authority discovery;
6. exact nested request-fingerprint agreement;
7. exact runtime-manifest discovery schema/version and candidate-count validation;
8. automatic selection only when exactly one compatible runtime candidate exists;
9. explicit runtime-manifest fingerprint selection when multiple compatible candidates exist;
10. rejection unless that explicit fingerprint identifies exactly one compatible candidate;
11. quote-identity equality against the frozen cohort for regime mint, safety output mint, and quote-asset mint;
12. preservation of active/G8 backup provenance;
13. canonical non-overwrite mode-0600 output;
14. a binding fingerprint over the complete evidence material and the SHA-256 of the exact canonical discovery-result bytes.

The request-authority discovery report now carries `cohort_artifact_fingerprint_sha256` explicitly inside `non_manifest_input_authority`. No cohort identity is inferred from quote mint or test defaults.

## CLI

The sealed CLI is:

```sh
.venv/bin/shreks-fl9-v2-discovery-authority-bind \
  --discovery-result '<exact-canonical-discovery-result.json>' \
  --destination '<new-nonexistent-binding.json>'
```

If multiple compatible runtime-manifest candidates exist, also pass:

```sh
  --runtime-manifest-fingerprint '<exact-64-hex-runtime-manifest-fingerprint>'
```

The binder refuses freshness-, path-, timestamp-, profitability-, or backup-age-based selection.

## Verification evidence

Intentional RED head:

`bcacd58313afe0fc9ee7c0c8e6e9b0b5f0b2958b`

RED CI run:

`35347061293`

Python failed exactly because the binder module/API did not yet exist.

Final feature head:

`f680743fb5afb4c4bc68b645237e3e317ef271c3`

Final feature-head CI run:

`35347608643`

All canonical gates were green:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Independent PR #312 CI run:

`35347952720`

All four canonical gates completed successfully and no review threads remained.

Squash-merged implementation main:

`0ae11d161ef617ec4e2ed8c8d0fd0fd271bff235`

Exact merged-main CI run:

`35348229256`

All four canonical gates completed successfully.

The implementation commit subject begins `feat:`, so immutable release creation remains gated on this separate docs-only `seal:` commit.

## Authority boundary

This seal authorizes only:

- immutable release creation after exact sealed-main green CI;
- protected deployment and production verification of that exact release;
- telemetry-mediated read-only FL9 V2 protected discovery;
- creation of one canonical discovery-authority binding after a trusted `FOUND_COMPATIBLE` result.

It does not authorize:

- model fitting;
- a V2 scoring retry;
- creation or execution of a fresh scoring request;
- champion evidence publication;
- PAPER promotion;
- risk-intent creation;
- signing or transaction submission;
- LIVE trading.

A binding artifact is evidence only.

## Production continuation

After the sealed release is deployed and verified:

1. the production verifier may exercise the telemetry discovery bridge;
2. `HOLD_NO_REQUEST_AUTHORITY`, `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`, or `HOLD_NO_COMPATIBLE` remain HOLD;
3. `FAILED`, timeout, malformed output, or release mismatch are hard trust/operational failures;
4. only a canonical `FOUND_COMPATIBLE` result may proceed to binding;
5. preserve that exact canonical discovery result;
6. run the release-local binder against that exact result;
7. if more than one compatible runtime candidate exists, bind only with an explicitly supplied exact runtime-manifest fingerprint;
8. preserve the resulting binding artifact and fingerprint.

No scoring action follows automatically.

## Post-binding gate

Only after one exact binding exists may a future separately reviewed and separately sealed slice prepare a fresh release-bound V2 proof/request.

That future proof/request must independently re-establish all required proof gates, including exact release, cohort, runtime-manifest, hydration-policy, economics, quiescence, holder/evidence, database, destination, and bounded-host integrity.

Neither this seal nor a successful binding grants that later scoring authority.

## Promotion boundary

`DISCOVERY_BINDER_IMPLEMENTATION=MAIN_GREEN`

`SEALED_RELEASE=PENDING`

`PRODUCTION_DEPLOY=REQUIRED_FOR_NEW_SEAL`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_ONLY_AFTER_NEW_SEALED_DEPLOY_AND_VERIFY`

`DISCOVERY_AUTHORITY_BINDING=AUTHORIZED_ONLY_AFTER_FOUND_COMPATIBLE`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
