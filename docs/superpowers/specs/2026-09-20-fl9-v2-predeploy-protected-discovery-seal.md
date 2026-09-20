# FL9 V2 Pre-Deploy Protected Discovery Bridge — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `255c672f23badc2a7cffa2e1fb7340c20a19f9d3`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; READ-ONLY DISCOVERY ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified correction that allows FL9 V2 protected historical discovery to authenticate the intentionally root-only frozen cohort and preserved request authority without widening the deploy account, changing protected evidence permissions, or publishing a trusted result as root.

The implementation adds one startup-only privileged read boundary during release activation, then irreversibly drops to the existing `shreks` runtime identity before publishing through the already-sealed trusted result exchange.

## Production evidence that required this correction

Prior sealed release:

`e7f76be324bbd40732f066ec6a210f25e729d2d1`

completed the full automatic chain:

`seal -> CI -> immutable release -> protected PAPER deploy -> production verify -> FL9 discovery`

Production deploy/verify run:

`35517738319`

proved:

- exact active release and release-manifest binding;
- all three core PAPER services active/running with zero restarts;
- no recent runtime restart or SQLite contention signature;
- FL9 discovery bridge available;
- trusted result delivered through the shared-memory exchange;
- terminal status `HOLD_NO_REQUEST_AUTHORITY`;
- `request_candidate_count=0`;
- `authenticated_authority_count=0`;
- `rejected_authority_count=0`.

The previous production diagnostic had already shown that the preserved canonical V2 request exists inside the intentionally root-only frozen cohort evidence tree. The cohort directory remains intentionally sealed and must not be chmod/chown/copied/ACL-widened merely to make discovery convenient.

The repository contains the prior request fingerprint and sealed provenance but not the canonical request bytes or the exact five non-manifest policy values. Reconstruction or synthesis is therefore not authorized.

## Implemented protected discovery bridge

Merged PR #328, `fix: bridge protected FL9 discovery at release activation`, adds a narrow release-bound path:

1. the automatic deploy job derives one bounded request ID from the deployment workflow run;
2. the unprivileged `shreks-deploy` account creates one canonical exact-release discovery request under `/var/tmp`;
3. the same deploy identity creates the existing trusted result-exchange directory under `/dev/shm`, mode `0733`;
4. the request contains only fixed schema/version, bounded request ID, expected sealed release SHA, and creation timestamp;
5. release activation installs the sealed PAPER campaign unit from the exact immutable release;
6. the campaign unit executes exactly one startup-only privileged preflight:
   `ExecStartPre=-+/opt/shreks/current/.venv/bin/python -m shreks_brain.telemetry.fl9_v2_predeploy_discovery`;
7. the helper requires initial effective UID 0;
8. it processes only the existing bounded FL9 discovery-control contract from `/var/tmp`;
9. it reuses the existing exact-release validation, bounded request enumeration, strict request/hydration authentication, frozen cohort authentication, runtime-manifest authentication, and compatibility discovery;
10. privileged processing uses `persist_receipts=False`, so no telemetry receipt is written while privileged;
11. the terminal canonical result exists only in process memory at the privilege boundary;
12. before publication, the helper clears supplementary groups and permanently changes GID/UID to the existing `shreks` runtime identity;
13. only after that irreversible drop does it publish through the already-sealed shared-memory result exchange;
14. the verifier still requires the result file itself to be a stable real regular file owned by `shreks`, mode `0644`, canonical JSON, and exactly request/release bound;
15. deployment removes its `/var/tmp` request after activation and passes the exact request ID to the reusable production verifier;
16. the verifier consumes and cleans only that request's result exchange;
17. manual verifier dispatch without a pre-staged request ID retains the prior unprivileged telemetry-mediated fallback.

No root-owned result is trusted.

## Availability and failure boundary

The privileged preflight uses the combined systemd command prefixes `-+`:

- the privilege override is scoped to that one release-local preflight command;
- ordinary campaign preflight and the long-running PAPER campaign remain under `User=shreks` / `Group=shreks`;
- a discovery-preflight failure does not make PAPER unavailable;
- missing, malformed, failed, or untrusted discovery output remains fail-closed in production verification.

This path is read-only with respect to protected historical evidence.

## TDD and verification evidence

Intentional RED head:

`e6bd02487534ee218c0586e0fd39cf42529df1ae`

RED CI run:

`35520597492`

Result:

- Python failed exactly on four newly introduced contracts while 3459 existing tests passed and 3 were skipped;
- Rust failed exactly on the new systemd privilege-boundary contract;
- ARM64 release build passed;
- Repository safety passed.

GREEN implementation head:

`f334217f8ea101c2d1c620e115ee59ca89ee81f8`

GREEN CI run:

`35520785972`

All four canonical gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Final PR head after documentation and newline hygiene:

`ed2846033ca698a370adeb695a2cb41e13a50cbc`

Final PR CI run:

`35520958819`

All four canonical gates passed.

Squash-merged implementation main:

`255c672f23badc2a7cffa2e1fb7340c20a19f9d3`

Exact merged-main CI run:

`35521164193`

All four canonical gates passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

## Authority boundary

This implementation and seal do not modify or authorize:

- the deploy account's sudoers command surface;
- general passwordless sudo;
- release-manager command expansion;
- protected evidence ownership, modes, or ACLs;
- frozen cohort bytes;
- preserved V2 request bytes;
- hydration-policy bytes;
- arbitrary protected paths or commands in discovery requests;
- scoring-request creation;
- V2 model fitting or scoring retry;
- champion publication;
- PAPER promotion;
- wallet/signing/submission;
- LIVE trading.

The deploy account remains unable to read protected runtime evidence directly.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment of that exact immutable release;
3. automatic production verification of that exact release;
4. staging of one fixed-schema exact-release FL9 discovery control by the existing deploy identity;
5. one startup-only privileged read-only discovery preflight from sealed release-local code;
6. irreversible drop to `shreks` before trusted result publication;
7. observation of the trusted terminal discovery result needed to choose the next implementation slice.

Trusted terminal outcomes remain evidence only:

- `HOLD_NO_REQUEST_AUTHORITY`;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- `HOLD_NO_COMPATIBLE`;
- `FOUND_COMPATIBLE`.

A terminal `FAILED`, timeout, malformed result, untrusted ownership/mode, release mismatch, or request mismatch remains fail-closed.

Even `FOUND_COMPATIBLE` does not authorize a scoring retry.

## Expected production proof

The automatic chain must demonstrate:

`seal merge -> CI -> immutable release -> pre-staged exact-release discovery control -> PAPER activation -> startup protected read -> drop to shreks -> trusted result publication -> production verify -> terminal FL9 discovery result`

Production evidence must preserve:

- exact active release SHA;
- exact manifest source SHA;
- core PAPER service health and restart counts;
- trusted result source;
- exact discovery status;
- canonical request/release binding;
- existing sanitized provenance/fingerprint fields for a successful authenticated authority result.

## Promotion boundary

`FL9_PREDEPLOY_PROTECTED_DISCOVERY_IMPLEMENTATION=MAIN_GREEN`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=PENDING_PRODUCTION_TERMINAL_RESULT`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
