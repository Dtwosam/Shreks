# FL9 V2 Runtime-Manifest Discovery — Prior-Request Authority Design

**Date:** 2026-09-17  
**Status:** DESIGN APPROVED FOR IMPLEMENTATION; SCORING NOT AUTHORIZED

## Purpose

Remove manual re-entry of the five FL9 hydration assumptions that are intentionally absent from the PAPER runtime manifest. The discovery command may authenticate one preserved canonical V2 first-champion host request, authenticate the hydration-policy file bound by that request, and reuse only those five non-manifest assumptions while deriving all runtime authority from each candidate PAPER runtime manifest.

This slice does not reuse a stale request for scoring. It uses the request only as historical evidence that one exact hydration-policy fingerprint was bound into the frozen V2 first-champion evidence chain.

## Authority chain

The new authority path must:

1. stable-read an existing real V2 host-request file;
2. strict-decode it with `decode_fast_first_champion_v2_host_request`;
3. authenticate the current frozen cohort and require its artifact fingerprint to equal the request's expected cohort fingerprint;
4. resolve the request's hydration-policy path;
5. stable-read that existing real policy file;
6. strict-decode it with `decode_fast_forecast_context_hydration_policy`;
7. recompute the hydration-policy fingerprint and require exact equality with `request.expected_hydration_policy_fingerprint_sha256`;
8. extract only:
   - `version`;
   - `strategy_families`;
   - `max_exit_quote_age_ms`;
   - `execution_cost_policy_version`;
   - `expected_round_trip_cost_bps`;
9. call the already-sealed runtime-manifest discovery path with those five values;
10. preserve request/policy provenance in the discovery report.

The prior hydration policy's runtime-derived fields are not reused. In particular, its quote mint, quote decimals, regime/safety policy, probe identity, provider, and global-risk state are discarded for candidate construction and are replaced only by the authenticated candidate runtime manifest through `build_fast_forecast_context_hydration_policy_from_runtime_manifest`.

## CLI contract

Add `--v2-host-request-authority <path>` as a second, fail-closed authority mode.

Two modes are allowed:

- historical request authority: supply `--v2-host-request-authority` and none of the five explicit non-manifest flags;
- explicit authority: preserve the existing five required values for controlled/test use.

Mixing the modes, omitting any explicit value, or supplying duplicate/partial authority must fail before runtime-manifest enumeration.

## Report provenance

The request-authority mode must emit a `non_manifest_input_authority` object containing only auditable provenance and the five extracted assumptions:

- authority kind `v2_host_request`;
- canonical request path and request fingerprint;
- request release source SHA;
- canonical hydration-policy path and hydration-policy fingerprint;
- hydration policy version;
- strategy families;
- max EXIT quote age;
- execution-cost-policy version;
- expected round-trip cost bps, preserving `null` for unknown.

No request destination, proof payload, training economics rows, secrets, runtime environment, or wallet material is emitted.

## Fail-closed requirements

Discovery must fail if the request is non-canonical/tampered, the current cohort fingerprint differs, the referenced hydration policy is missing/symlinked/changes during read, the policy is non-canonical/tampered, or its fingerprint differs from the request binding.

All existing G8 backup verification, runtime-manifest authentication, quote-policy compatibility, and no-write/no-trading-authority checks remain unchanged.

## Authority boundary

This slice authorizes read-only authority recovery and runtime-manifest discovery only. It does not authorize a fresh V2 scoring request, model fitting, evidence publication, PAPER promotion, risk-intent creation, signing/submission, or LIVE trading.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
