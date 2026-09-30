# Fast PAPER Champion Bootstrap Retry Authority — Release Seal

**Date:** 2026-09-30  
**Code-bearing parent main SHA:** `34c50b1cbc072b45fc37421203931f2b5b59aa53`  
**Status:** SEAL PENDING; EXACTLY ONE MEMORY-BOUNDED FORECAST-CHAMPION RETRY AUTHORIZED ONLY AFTER THIS SEAL IS MERGED, THE EXACT SEALED RELEASE IS BUILT/DEPLOYED/VERIFIED, AND FRESH CURRENT-RELEASE INPUTS AUTHENTICATE

## Purpose

Authorize one reviewed retry of the missing Fast Lane forecast-champion bootstrap after the first
physical attempt failed closed from host memory exhaustion.

This seal exists only because the prior one-attempt authority was consumed when
`shreks-fast-first-champion-run` was invoked. It does not reinterpret that failed invocation as
retryable authority.

The retry must use the memory-bounded first-champion implementation merged at code-bearing parent:

`34c50b1cbc072b45fc37421203931f2b5b59aa53`

No earlier release is retry-capable authority.

## Preserved OOM incident evidence

The consumed attempt used request fingerprint:

`63b246ddf209491fdd086e1b5808dedf7d1631bd39ba0a9c8df325e626f3c71a`

Protected-host evidence established:

- the exact pre-attempt release gate passed;
- the request, proof workspace, and economics artifact authenticated;
- the legacy PAPER observer/evidence/campaign services were quiesced;
- the detached Fast shadow remained inactive;
- the champion runner was invoked once;
- the process was killed by the kernel OOM killer;
- the systemd unit reported approximately 11.3 GiB memory peak and 7.8 GiB swap peak;
- no host-run destination was published;
- the legacy PAPER observer/evidence/campaign services were restored;
- the temporary 8 GiB swapfile was removed;
- the prior one-attempt authority was marked consumed.

The wrapper's recorded `exit_code=0` is not a success signal for that incident. The authoritative
unit result was `oom-kill`, no host-run artifact existed, and no canonical champion was published.

## Retry-capable implementation

The merged memory-bounded implementation changes resource behavior only.

For an explicit champion horizon, the generic score-free path now:

1. strictly authenticates the complete training-economics overlay while retaining only the requested
   horizon;
2. derives the exact requested-horizon decision population from those authenticated rows;
3. streams the immutable feature JSONL, validates canonical ordering/duplicates, authenticates the
   complete source SHA-256, and retains only selected identities;
4. loads only the matching canonical FL4 identities/horizon/version;
5. requires exact selected-population equality across features, FL4 labels, economics rows, and
   canonical counterfactual provenance;
6. keeps the existing execution-economics projection, counterfactual labels, chronological
   validation, TEST evaluation, five forecast targets, model families, training policy, champion
   codec, and artifact fingerprints unchanged;
7. releases large logical bundle objects before entering nested preparation/file-run stages;
8. verifies proof workspaces through a streaming manifest-bounded reader instead of retaining the
   entire proof feature population.

Repository proof for the code-bearing parent passed:

- Python tests;
- Rust tests;
- native ARM64 release build/verification;
- repository safety.

This is not a scoring-path change and grants no scoring authority.

## Exact sealed release prerequisite

This docs-only seal must land on `main` before any retry.

The physical retry must run only from one exact immutable release whose source SHA is the merged
seal SHA, or another later explicitly reviewed docs-only seal descendant that contains the same
code-bearing parent with no intervening implementation change.

The trusted administrator must prove:

```text
EXPECTED_RELEASE_SHA=<exact deployed retry-sealed SHA>
CURRENT_RELEASE=$(readlink -f /opt/shreks/current)
CURRENT_SHA=$(basename "$CURRENT_RELEASE")
CURRENT_SHA == EXPECTED_RELEASE_SHA
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

If implementation files differ from the code-bearing parent named above, this seal does not
authorize execution.

The exact release must remain unchanged through proof preparation, request creation, retry
invocation, strict readback, and retry evidence capture.

## Fresh retry inputs

The consumed request and consumed host-run destination may not be reused as retry authority.

The retry requires all of the following to be freshly generated or freshly authenticated against
the exact deployed retry-sealed release:

1. one new `shreks.fast_proof_workspace` produced by the exact release-local proof exporter;
2. one new canonical runtime-backed hydration policy produced from the exact active legacy PAPER
   runtime state;
3. one authenticated training-economics overlay and exact execution-cost policy accepted by the
   current-release request writer;
4. one new canonical first-champion host request;
5. one new absent host-run destination;
6. no matching staging residue;
7. continued physical absence of an authenticated
   `shreks.fast_lane_forecast_champion` artifact.

Every explicit evidence/evaluation parameter remains visible in the new request. This seal supplies
no hidden numeric model, evaluation, scoring, or promotion defaults.

## Capacity and quiescence prerequisites

Immediately before the retry invocation, preserve a read-only preflight record containing at least:

- `free -h`;
- `df -h /`;
- active swap devices and free swap;
- exact host-run destination/staging absence;
- exact current release SHA;
- active legacy PAPER service states;
- Fast shadow state.

The retry ceremony may create temporary swap as an operational safety measure, but temporary swap
does not replace the memory-bounded implementation requirement and does not expand retry authority.

Before invoking the runner:

- the exact legacy PAPER target and observer/evidence/campaign services must be inactive;
- the Fast shadow must be inactive;
- the authoritative observer database must be stable under the sealed readers;
- the retry destination and staging paths must be absent;
- the retry-capable exact release and all fresh inputs must authenticate.

The retry wrapper must preserve fail-safe restoration of the legacy PAPER services and cleanup of
temporary swap on every exit path.

## Exactly one retry

After all prerequisites pass, a trusted administrator may invoke exactly one retry:

`shreks-fast-first-champion-run --request <fresh-current-release-request.json>`

Retry authority is consumed when that command is invoked.

There is no automatic retry loop, fallback invocation, second request, process restart, or
"try again" interpretation under this seal.

A successful retry must publish and strictly reopen an immutable host-run artifact whose nested
champion authenticates as:

`schema_name=shreks.fast_lane_forecast_champion`

The success evidence must bind at least:

- exact retry-sealed release SHA;
- fresh host-request fingerprint;
- fresh proof-workspace fingerprint;
- fresh hydration-policy fingerprint;
- authenticated economics fingerprint;
- execution-cost-policy fingerprint;
- memory-bounded training-bundle fingerprint;
- chronological plan fingerprint;
- champion version;
- champion fingerprint;
- canonical champion-file SHA-256;
- immutable host-run artifact fingerprint.

## Failure handling

Any retry failure consumes this seal.

Failure includes, without limitation:

- another OOM kill;
- nonzero runner failure;
- systemd unit failure even if an outer cleanup wrapper exits zero;
- release drift;
- request/input fingerprint mismatch;
- database instability;
- evidence-plan insufficiency;
- chronological TEST evaluation failure;
- missing or malformed champion;
- host-run strict-read failure;
- destination/staging conflict;
- inability to restore legacy PAPER services.

A failure publishes no PAPER/LIVE authority and does not authorize another retry. Preserve the
exact evidence and require another separately reviewed authority decision.

## Post-success boundary

A successful retry advances only the physical forecast-champion presence state.

It does not itself authorize:

- Fast authority installation under `/etc/shreks`;
- daemon reload for Fast authority;
- detached Fast shadow start;
- production Fast PAPER cutover;
- replacing legacy PAPER authority;
- automatic champion promotion;
- signing/submission;
- LIVE.

The existing shadow-host preparation, commissioning, evidence, promotion, baseline, and physical
cutover gates remain mandatory.

## Explicit authority state

After this seal is merged/deployed/verified and before the one retry is invoked:

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_AUTHORITY=SEALED_ONE_MEMORY_BOUNDED_RETRY_AFTER_EXACT_DEPLOY
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

When the runner is invoked:

`FAST_CHAMPION_BOOTSTRAP_AUTHORITY=CONSUMED_RETRY_INVOKED`

Only after a successful strict-read retry may:

`FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=AUTHENTICATED_IMMUTABLE_ARTIFACT`

All other authority boundaries remain unchanged.

## Next slice after successful retry

After one authentic immutable forecast champion physically exists:

1. inspect and authenticate the exact champion/host-run evidence;
2. construct the initial Fast PAPER shadow authority candidate bundle using that exact champion and
   exact release-local decision/feature-feed binaries;
3. pass the existing protected authority preflight/install and host commissioning gates;
4. only then consider detached Fast shadow start under its separately required authority.

Do not jump from champion publication directly to production Fast PAPER cutover.
