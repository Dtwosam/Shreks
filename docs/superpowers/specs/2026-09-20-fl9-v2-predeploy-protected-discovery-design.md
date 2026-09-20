# FL9 V2 Pre-Deploy Protected Discovery Bridge — Design

**Date:** 2026-09-20  
**Status:** IMPLEMENTATION PR PENDING; READ-ONLY DISCOVERY ONLY; V2 SCORING NOT AUTHORIZED

## Production evidence

Immutable sealed release `e7f76be324bbd40732f066ec6a210f25e729d2d1` completed the automatic chain:

`seal -> CI -> immutable release -> protected PAPER deploy -> production verify`

Production verification confirmed:

- exact active release and release-manifest binding;
- all three core PAPER services active/running with zero restarts;
- no recent runtime restart or SQLite contention signature;
- trusted FL9 result exchange functioning;
- terminal discovery status `HOLD_NO_REQUEST_AUTHORITY`;
- `request_candidate_count=0`;
- `authenticated_authority_count=0`;
- `rejected_authority_count=0`.

The prior sealed run had already proven that the preserved canonical V2 request exists inside the intentionally protected frozen-cohort evidence tree, where an unprivileged telemetry process receives `EACCES`.

The cohort remains intentionally sealed. Its ownership/modes/ACLs must not be weakened, copied, or rewritten merely to make discovery convenient.

## Problem

The existing telemetry bridge is correct for evidence readable by the `shreks` service identity, but the only known preserved V2 request authority and the frozen cohort it authenticates are inside a root-only historical evidence boundary.

Therefore:

- widening `shreks-deploy` is forbidden;
- widening `shreks` access to the frozen cohort is forbidden;
- copying the old request or its hydration policy into a readable location would create a new provenance problem and is forbidden;
- reconstructing the request or its five non-manifest assumptions from documentation is forbidden;
- continuing to run the same unprivileged search can only remain `HOLD_NO_REQUEST_AUTHORITY`.

The required correction is a narrow read-only privilege transition, not a scoring or evidence mutation path.

## Design

The normal automatic deployment path pre-stages one canonical discovery control immediately before release activation:

- request file:
  `/var/tmp/shreks-fl9-v2-discovery.<request-id>.request`
- result exchange:
  `/dev/shm/shreks-fl9-v2-discovery.<request-id>.result.d`

The request remains owned by `shreks-deploy`, mode `0644`, and carries only:

- fixed schema name/version;
- bounded request ID;
- exact expected sealed release SHA;
- creation timestamp.

The result exchange remains owned by `shreks-deploy`, mode `0733`.

The request contains no arbitrary command, protected path, policy value, credential, wallet material, or trading instruction.

### Release activation preflight

The already release-managed `shreks-paper-campaign.service` runs exactly one additional command before its ordinary unprivileged campaign preflight:

`ExecStartPre=-+/opt/shreks/current/.venv/bin/python -m shreks_brain.telemetry.fl9_v2_predeploy_discovery`

The command is:

- release-local and therefore bound to the exact immutable release;
- startup-only;
- read-only with respect to protected evidence;
- non-blocking for PAPER startup if discovery itself fails;
- the only campaign command using the full-privilege systemd command prefix.

The main campaign process remains `User=shreks`, `Group=shreks`, with its existing sandbox and LIVE-disabled authority.

### Privileged read / unprivileged publish split

The helper:

1. requires initial effective UID 0;
2. processes only the existing bounded FL9 discovery-control schema from `/var/tmp`;
3. authenticates the exact active release;
4. performs the existing bounded historical request enumeration;
5. authenticates candidate V2 request/hydration authority through existing strict codecs and fingerprints;
6. authenticates the frozen cohort and candidate runtime manifests through existing discovery code;
7. does **not** persist telemetry receipts while privileged;
8. holds only the canonical terminal result in memory;
9. permanently clears supplementary groups;
10. permanently switches GID and UID to the existing `shreks` runtime identity;
11. publishes the result through the existing trusted `/dev/shm` exchange;
12. never regains root authority.

The verifier continues to require the result file itself to be:

- a real regular file;
- mode `0644`;
- owned by the `shreks` UID;
- stable across lstat/open/fstat;
- canonical JSON;
- exactly bound to request ID and expected/observed release SHA.

Root-owned result publication is not accepted.

## Race avoidance

The privileged startup request is staged under `/var/tmp`, not under the normal telemetry marker location in `/dev/shm`.

This prevents the still-running old telemetry timer from consuming the new-release request before `/opt/shreks/current` switches.

Only the result exchange is pre-created under `/dev/shm`; normal telemetry does not treat that directory as a request marker.

After activation returns, deployment removes the `/var/tmp` request. The reusable production verifier receives the exact request ID from the deploy job and consumes the already-created result exchange.

Manual verifier dispatch without a pre-staged request ID retains the existing telemetry-mediated fallback.

## Failure behavior

Protected discovery remains evidence-only and must not make PAPER unavailable.

Therefore the privileged `ExecStartPre` command is failure-ignored at the systemd unit boundary. Internal processing/publishing errors produce no trusted success.

The verifier remains the fail-closed authority:

- trusted `HOLD_*` or `FOUND_COMPATIBLE`: verification may complete;
- trusted `FAILED`: verification fails with bounded diagnostics;
- missing/malformed/untrusted result: verification fails;
- timeout: verification fails.

A failed discovery preflight never authorizes scoring and never widens runtime permissions.

## Explicit non-authority

This design does not authorize or modify:

- sudoers;
- the release-manager command surface;
- protected evidence ownership/modes/ACLs;
- frozen cohort bytes;
- preserved V2 request bytes;
- hydration-policy bytes;
- scoring-request creation;
- model fitting or V2 scoring retry;
- champion publication;
- PAPER promotion;
- wallet/signing/submission;
- LIVE trading.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
