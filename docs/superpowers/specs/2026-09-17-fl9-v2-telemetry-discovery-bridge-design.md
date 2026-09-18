# FL9 V2 Protected Discovery — Telemetry Control-Plane Bridge Design

**Date:** 2026-09-17  
**Base:** `4e3e151559685a4ca613990cbad329556e688d1b`  
**Status:** APPROVED FOR IMPLEMENTATION; READ-ONLY DISCOVERY ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Remove the recurring operational dead-end between GitHub's protected production control plane and FL9 evidence that is intentionally readable only by the `shreks` runtime identity.

The current production boundary is correct and must remain intact:

- GitHub Actions connects as the dedicated unprivileged `shreks-deploy` account;
- `shreks-deploy` may deploy a verified immutable release through the narrow release-manager sudo command;
- `shreks-deploy` must not gain general read access to `/etc/shreks` or `/var/lib/shreks`;
- `shreks-telemetry.service` already runs every 60 seconds as `User=shreks`, reads protected PAPER state, is read-only with respect to trading/runtime evidence, and executes Python from `/opt/shreks/current`.

The bridge uses that existing telemetry execution boundary instead of adding a new root systemd unit, widening sudoers, changing protected evidence ownership/modes, or requiring an interactive administrator shell.

## Why telemetry is the integration point

A new `.path`/oneshot systemd pair would be technically viable but would introduce a host-bootstrap dependency: the already-installed root release manager only installs the currently sealed core unit set. Teaching it to install a new unit would require a separate privileged host update, recreating the same class of operational stall this slice is intended to eliminate.

The existing telemetry timer avoids that trap:

- its systemd unit is already installed and enabled on production;
- it runs as `shreks` and therefore already has the required read authority;
- its executable Python comes from the active immutable release virtualenv;
- changing release-local Python therefore takes effect through the normal sealed release/deploy path;
- telemetry is already an independent, read-only operations surface rather than latency-sensitive trading logic.

The bridge must remain isolated from normal telemetry snapshot correctness: a discovery-control failure must never stop `shreks.target`, mutate PAPER evidence, or grant trading authority.

## Control request transport

GitHub Actions writes one ephemeral canonical JSON request file to shared memory:

`/dev/shm/shreks-fl9-v2-discovery.<request_id>.request`

`PrivateTmp=true` isolates `/tmp` and `/var/tmp`, but does not create a private `/dev/shm`; the existing telemetry service can therefore read this marker without changing its unit file.

Each request contains exactly:

- `schema_name = "shreks.fl9_v2_discovery_control_request"`;
- `schema_version = 1`;
- `request_id`;
- `expected_release_sha`;
- `created_at_unix_ms`.

The request writer must:

1. use a safe request ID containing only ASCII letters, digits, `.`, `_`, and `-`;
2. write canonical JSON plus one trailing newline to a sibling temporary file;
3. set mode `0644` so the `shreks` telemetry service can read it;
4. atomically rename the temporary file to the request path;
5. never write under `/etc/shreks` or `/var/lib/shreks`.

The runtime request reader must fail closed unless the marker is:

- a real regular file, not a symlink;
- owned by the dedicated `shreks-deploy` account;
- mode `0644`;
- within the small request-size bound;
- stable across the read;
- canonically encoded;
- fresh within the sealed request-age window;
- bound to the exact currently active release SHA.

No request field may contain an arbitrary protected-state path or command.

## Existing telemetry invocation

`shreks-telemetry.service` already executes:

`python -m shreks_brain.telemetry.runtime --preflight`

before every normal telemetry snapshot.

The telemetry runtime will process bounded pending discovery-control requests at the start of this existing `--preflight` invocation, before loading normal telemetry configuration. This ensures discovery can still produce a result even when an unrelated telemetry snapshot source is temporarily unavailable.

Discovery-control processing is isolated:

- each marker is handled independently;
- per-marker errors become a sanitized `FAILED` result;
- discovery-control errors do not cause normal telemetry preflight to fail;
- at most a small fixed number of markers are processed per timer activation;
- normal `run_telemetry_once(...)` behavior remains unchanged.

## Protected production inputs

The bridge itself supplies only sealed production paths; the GitHub request cannot override them.

Frozen cohort:

`/var/lib/shreks/fl9-v2-cohort-acceptance-a0cdf58ac14981d44ab8a0f8ca584abc8f9e28e2`

Active PAPER runtime manifest:

`/etc/shreks/paper-campaign.json`

G8 backup root:

`/var/lib/shreks/backups`

Historical V2 request search root:

`/var/lib/shreks`

The request search is deliberately bounded. It looks only for the known preserved filename:

`v2-first-champion-request.json`

at the search root and within a bounded depth below real, non-hidden top-level directories whose names begin with `fl9-v2-`. It never performs an unbounded recursive crawl of `/var/lib/shreks`.

## Historical request authority resolution

Every candidate preserved V2 request is authenticated through the existing canonical request decoder and the request-bound hydration policy contract.

For each candidate, the bridge must:

1. stable-read and strict-decode the V2 host request;
2. require its expected cohort artifact fingerprint to match the currently authenticated frozen cohort;
3. stable-read and strict-decode the hydration policy path bound by that request;
4. recompute and require the exact hydration-policy fingerprint carried by the request;
5. extract only the five previously sealed non-manifest discovery assumptions:
   - hydration-policy version;
   - strategy families;
   - maximum EXIT quote age;
   - execution-cost-policy version;
   - expected round-trip cost bps, preserving unknown as `null`;
6. discard the stale policy's runtime-derived quote/regime/safety/provider/global-risk fields for candidate runtime-manifest construction.

Invalid or incomplete historical candidates are not used as authority. They are reported only as rejected candidate provenance.

Valid requests are grouped by a canonical fingerprint of the frozen cohort identity plus those five non-manifest assumptions. This deliberately collapses multiple preserved requests that prove the same non-manifest authority even when their stale release SHA or stale runtime-derived policy fields differ.

Resolution states are:

- no valid authority groups -> `HOLD_NO_REQUEST_AUTHORITY`;
- more than one distinct valid authority group -> `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- exactly one authority group -> choose the lexicographically first authenticated request path as deterministic provenance and invoke the already-sealed runtime-manifest discovery through request-authority mode.

No freshness, profitability, or discretionary preference may choose between distinct authority groups.

## Runtime-manifest discovery

Once exactly one historical request authority group is established, the bridge delegates to the existing sealed FL9 V2 runtime-manifest discovery implementation.

That implementation remains authoritative for:

- frozen cohort authentication;
- active runtime-manifest canonical authentication;
- full G8 backup verification before consuming historical campaign manifests;
- canonical runtime-manifest -> hydration-policy derivation;
- WSOL cohort quote-policy compatibility;
- candidate runtime-manifest and derived policy fingerprints.

The bridge does not rewrite a manifest, quote mint, decimals, probe identity, provider, regime/safety policy, or global-risk state.

## Result and journal contract

Every trusted control request produces one canonical result object with schema:

`shreks.fl9_v2_discovery_control_result` v1.

It contains only auditable, non-secret data:

- request ID;
- expected and observed release SHA;
- result status;
- historical request candidate counts;
- authority-group fingerprints/provenance;
- the existing sanitized runtime-manifest discovery report when discovery runs;
- a bounded failure code/message when the control request or authority chain cannot be trusted.

The result is printed as one compact JSON line to stdout, which systemd journals under `shreks-telemetry.service`.

Result statuses are:

- `FOUND_COMPATIBLE`;
- `HOLD_NO_COMPATIBLE`;
- `HOLD_NO_REQUEST_AUTHORITY`;
- `HOLD_AMBIGUOUS_REQUEST_AUTHORITY`;
- `FAILED`.

`FOUND_COMPATIBLE` still authorizes evidence inspection only. It does not authorize a fresh V2 scoring request by itself.

## Idempotence and stale marker handling

The telemetry identity may write only bridge receipts below:

`/var/lib/shreks/telemetry/fl9-v2-discovery-control/`

A receipt is named from the validated request ID and contains the exact canonical result emitted to the journal. Receipt writes are atomic and mode `0600` under the existing telemetry `UMask=0077` boundary.

If the same marker is observed again, the bridge re-emits the authenticated stored receipt instead of rescanning protected evidence. This prevents an abandoned GitHub marker from causing repeated expensive discovery every minute.

Requests older than the sealed freshness bound do not trigger protected discovery. They produce a fail-closed stale-control result/receipt.

GitHub Actions remains responsible for deleting its own `/dev/shm` marker after observing the result because the sticky-bit shared-memory directory prevents the `shreks` identity from deleting a marker owned by `shreks-deploy`.

## Production verification workflow integration

The existing `Verify production PAPER runtime` workflow remains the only GitHub-side production verification entry point.

After its current release identity, service health, restart, journal, and historical-read probes, it will:

1. verify `shreks-telemetry.timer` is active;
2. check whether the active release contains the bridge module;
3. generate a unique request ID from the GitHub run identity;
4. atomically write its canonical marker to `/dev/shm` as `shreks-deploy`;
5. poll `journalctl -u shreks-telemetry.service -o cat` for the exact request ID for a bounded interval covering multiple telemetry timer periods;
6. delete its marker on every terminal shell path it controls;
7. print the exact canonical result to the Actions log;
8. treat the four trusted `FOUND_`/`HOLD_` statuses as a successfully completed read-only discovery operation;
9. fail the workflow on `FAILED`, malformed output, release mismatch, inactive telemetry timer, or timeout.

For backward compatibility, verifying an older deployed release that does not contain the bridge module reports `fl9_v2_discovery_bridge=unavailable` and preserves the existing production-verification behavior instead of waiting for an impossible response.

No new GitHub secret is introduced.

## Security and authority boundary

This slice must not:

- change `/etc/sudoers.d/shreks-release-manager`;
- add general sudo commands for `shreks-deploy`;
- chmod/chown/setfacl protected evidence to make it deploy-readable;
- expose wallet material or unrestricted production secrets;
- add provider/network access to discovery;
- mutate `/etc/shreks`, cohort evidence, G8 backups, observer SQLite, PAPER ledgers, or champion evidence;
- create or execute a fresh scoring request;
- fit a model;
- publish champion evidence;
- promote a champion;
- create a risk/trade intent;
- sign or submit a transaction;
- enable LIVE.

The only new persistent write is an idempotence receipt under the already-authorized telemetry output tree.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`

## Verification requirements

TDD must prove at least:

- canonical control-request validation, owner/mode/freshness/release binding, and stable-read behavior;
- bounded candidate enumeration with no unbounded `rglob`/filesystem crawl;
- zero, one, equivalent-many, and ambiguous-many historical authority cases;
- request and hydration-policy tamper/mismatch rejection;
- delegation to existing runtime-manifest discovery only after one exact authority group exists;
- receipt atomicity/idempotence and no repeat protected scan for an already-receipted request;
- telemetry preflight processes bridge requests without changing normal snapshot semantics and without letting bridge failures break telemetry preflight;
- production workflow writes only `/dev/shm`, never reads protected paths directly for discovery, waits on telemetry journal output, cleans its marker, accepts trusted HOLD states, and fails on trust/infrastructure failure;
- no sudoers, release-manager, systemd-unit, wallet, signing, submission, PAPER-promotion, or LIVE authority changes.
