# FL9 V2 Telemetry Discovery Bridge — Release Seal

**Date:** 2026-09-18  
**Implementation main SHA:** `b41a8dbf17e79d5ae33e51f32edf277fbcce6fec`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; READ-ONLY PROTECTED DISCOVERY ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified FL9 V2 anti-stall implementation that allows protected runtime-manifest discovery to continue through the already-installed telemetry service identity without requiring an interactive administrator shell and without widening the `shreks-deploy` account's permissions.

The bridge is operational control-plane plumbing only. It does not create trading authority.

## Implemented bridge

Merged PR #310, `feat: bridge protected FL9 discovery through telemetry`, adds a bounded fail-closed request path:

1. the production verifier remains connected only as the existing unprivileged `shreks-deploy` account;
2. it writes one canonical, release-bound request marker under `/dev/shm/shreks-fl9-v2-discovery.<request-id>.request`;
3. the existing `shreks-telemetry.timer` invokes `shreks-telemetry.service` as the existing `shreks` identity;
4. telemetry preflight authenticates and processes pending FL9 discovery controls before ordinary telemetry source validation;
5. the processor verifies the expected active release identity and release manifest before protected discovery;
6. historical V2 host-request authority enumeration is bounded by depth, directory count, and candidate count rather than recursively walking all protected state;
7. every candidate request and its fingerprint-bound hydration policy is authenticated through the existing canonical request-authority chain;
8. equivalent authorities are collapsed by an exact deterministic authority-group fingerprint;
9. no authority group yields `HOLD_NO_REQUEST_AUTHORITY`;
10. multiple distinct authority groups yield `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
11. exactly one authority group delegates to the already-sealed runtime-manifest discovery implementation;
12. runtime-manifest discovery may return only `FOUND_COMPATIBLE` or `HOLD_NO_COMPATIBLE`;
13. the processor writes only an idempotence receipt under the existing telemetry writable tree and emits a sanitized canonical result to journald;
14. the production verifier polls `journalctl -u shreks-telemetry.service -o cat`, requires exact schema/request/release binding, accepts only the trusted HOLD/FOUND statuses above, and removes only its own marker.

Older releases without the bridge remain backward compatible: production verification reports `fl9_v2_discovery_bridge=unavailable` and preserves legacy verification behavior.

## Permission and authority boundary

This implementation deliberately does not change:

- `/etc/sudoers.d/shreks-release-manager`;
- `deploy/release/release_manager.py`;
- any `deploy/systemd/*.service` or `deploy/systemd/*.timer` unit;
- ownership, modes, or ACLs under `/etc/shreks` or `/var/lib/shreks`;
- wallet, signing, submission, or transaction-broadcast paths;
- PAPER promotion authority;
- LIVE authority.

The deploy account therefore remains unable to read protected runtime configuration/state directly. The bridge uses the existing `shreks` telemetry identity rather than adding privilege to `shreks-deploy`.

## Verification evidence

Final feature head:

`45c73f7fe3b6247761e72fe57485a1c8ee1f42d8`

Feature-head CI run:

`35335221784`

Result:

- Repository safety: SUCCESS;
- Python tests: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Independent PR #310 CI run:

`35335473068`

All four canonical gates completed successfully on the exact PR head.

Squash-merged implementation main:

`b41a8dbf17e79d5ae33e51f32edf277fbcce6fec`

Exact merged-main CI run:

`35335741926`

All four canonical gates completed successfully:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

The automatic release workflow correctly skipped the implementation commit because its subject begins `feat:`, not `seal:`.

## TDD evidence

The implementation was built in bounded RED/GREEN slices covering:

- reusable authenticated prior-V2-request/hydration authority;
- discovery-control marker validation and release binding;
- bounded historical authority enumeration and ambiguity handling;
- canonical 0600 atomic idempotence receipts;
- telemetry preflight ordering, result emission, exception isolation, and snapshot-path non-interference;
- production verifier request/journal transport;
- no-admin-shell operator runbook requirements.

RED runs failed only on the newly introduced contracts before the corresponding production implementation landed; existing unrelated Python/Rust/ARM64/safety lanes remained healthy.

## Immutable release and deployment gate

After this documentation-only seal lands on `main` with a commit subject beginning `seal:`, exact sealed-main CI must pass Repository safety, Python, Rust, and ARM64 release build.

Only after exact sealed-main CI is green may the automatic release workflow create immutable release `shreks-<seal-sha>`.

That exact immutable release must then be deployed through the existing protected `Deploy verified Shreks release` workflow and verified through `Verify production PAPER runtime`.

The deployment path must not add sudoers entries, relax protected filesystem permissions, or patch the active release in place.

## Production continuation after sealed deploy

After the sealed release is deployed and the ordinary production checks pass, `Verify production PAPER runtime` may exercise the bridge automatically.

The verifier will:

- bind the discovery request to the exact expected sealed release SHA;
- require `shreks-telemetry.timer` active;
- create a canonical marker under `/dev/shm`;
- wait for the matching canonical journal result;
- validate exact request ID and expected/observed release binding;
- accept only `FOUND_COMPATIBLE`, `HOLD_NO_COMPATIBLE`, `HOLD_NO_REQUEST_AUTHORITY`, or `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- fail on timeout, malformed output, release mismatch, or `FAILED`;
- remove its own marker on terminal paths.

No interactive administrator shell is required for this discovery path.

## Result boundary

`HOLD_NO_REQUEST_AUTHORITY` means no preserved authenticated V2 request/hydration authority was found in the bounded historical search. Remain HOLD.

`HOLD_AMBIGUOUS_REQUEST_AUTHORITY` means more than one distinct authenticated authority tuple exists. The bridge must not choose between them. Remain HOLD.

`HOLD_NO_COMPATIBLE` means authenticated request authority existed, but no authenticated runtime manifest produced a hydration policy compatible with the frozen V2 cohort. Remain HOLD.

`FOUND_COMPATIBLE` means one authenticated authority group and at least one compatible runtime-manifest candidate were found. Preserve the exact sanitized provenance/fingerprints emitted by discovery.

`FAILED` or timeout/malformed output is a trust or operational failure. Stop and investigate.

Even `FOUND_COMPATIBLE` does not authorize scoring.

## Post-discovery gate before any V2 scoring retry

Only after one exact authenticated compatible runtime-manifest authority is explicitly bound may a fresh release-bound V2 proof/request be prepared through canonical repository tooling.

Before any scoring retry, the existing proof gates must be re-established, including:

- exact sealed release identity;
- exact frozen cohort artifact/fingerprint;
- exact authenticated request-authority group;
- exact authenticated runtime-manifest source/fingerprint;
- exact derived hydration-policy fingerprint;
- fresh canonical request publication and strict readback;
- quiescence;
- holder/evidence completeness;
- database sentinel/consistency;
- destination absence/non-overwrite;
- training-economics and execution-cost-policy authentication;
- bounded-host evidence integrity.

No stale request may be executed as a scoring request. No manifest/policy may be synthesized or hand-edited to satisfy the cohort.

## Promotion boundary

This seal authorizes only:

- immutable release creation for the exact seal SHA after green CI;
- protected deployment and production verification of that exact release;
- telemetry-mediated read-only protected FL9 runtime-manifest discovery.

It does not authorize model fitting, a V2 scoring retry, champion evidence publication, PAPER promotion, risk-intent creation, signing/submission, or LIVE trading.

`ANTI_STALL_IMPLEMENTATION=MAIN_GREEN`

`SEALED_RELEASE=PENDING`

`PRODUCTION_DEPLOY=REQUIRED_FOR_NEW_SEAL`

`RUNTIME_POLICY_DISCOVERY=AUTHORIZED_ONLY_AFTER_NEW_SEALED_DEPLOY_AND_VERIFY`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
