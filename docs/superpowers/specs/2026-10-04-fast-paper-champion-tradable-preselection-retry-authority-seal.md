# Fast PAPER Champion Tradable-Preselection Retry Authority — Release Seal

**Date:** 2026-10-04  
**Implementation main SHA:** `f1b62be23d40063bf5a08ec1f18ec035eb4b90bc`  
**Status:** SEAL PENDING; EXACTLY ONE FRESH SCORE-FREE FORECAST-CHAMPION RETRY AUTHORIZED ONLY AFTER THIS SEAL LANDS ON `main`, THE EXACT SEALED RELEASE IS BUILT/DEPLOYED/VERIFIED, ONE STABLE OBSERVER SNAPSHOT PRODUCES FRESH PRESELECTION-BOUND INPUTS, AND EVERY PRE-INVOCATION GATE PASSES. FAST SHADOW START, PAPER CUTOVER, AUTOMATIC PROMOTION, SIGNING/SUBMISSION, AND LIVE REMAIN DISABLED.

## Purpose

Authorize one separately reviewed retry of the missing score-free Fast Lane
forecast champion after the previous context-resolution retry authority was
consumed by a fail-closed historical PumpSwap coverage gap.

This seal is separate from the implementation fix. The authenticated
tradable-preselection implementation landed on `main` as:

`f1b62be23d40063bf5a08ec1f18ec035eb4b90bc — fix: preselect V1 champion by tradable universe`

This seal MUST NOT merge unless exact merged-main CI for that implementation
SHA succeeds for Python tests, Rust tests, native ARM64 release build, and
repository safety.

The retry remains the same score-free forecast-champion evidence operation. It
does not restore or authorize the historical FL9 V2 scoring/control path.

## Consumed retry incident

The previous context-resolution retry authority was consumed when the protected
host invoked exactly once:

`shreks-fast-first-champion-run --request /var/lib/shreks/fast-paper-champion-retry-39985879d2c69d19e70fc086c4b5127e1af02418/retry-request.json`

using exact deployed release:

`39985879d2c69d19e70fc086c4b5127e1af02418`

with:

- request file SHA-256
  `3b79fe71d048eca5fbae094fbada7b0e126c5cc1f74037ab3faca979406603e1`;
- request fingerprint
  `51502c11c890d33fa5b58ac6c063dbf9ef2f4a13ac46ca61d1ac42ee5d7d7808`;
- systemd unit
  `shreks-fast-champion-context-final-39985879d2c69.service`;
- systemd invocation
  `2a748e2dd8a042ee8e3f001d55dc9f94`.

Every final pre-invocation gate passed before that runner invocation:

- exact release and request identity;
- physical champion absence;
- fresh proof, hydration, economics, and execution-cost authentication;
- bounded legacy PAPER quiescence;
- database/WAL stability;
- host-run destination and staging absence;
- approximately 10 GiB or more physical memory available after quiescence;
- one temporary 8 GiB retry swapfile;
- required root-filesystem headroom;
- Fast shadow inactive.

The authority was consumed at the one-shot runner invocation.

The runner later failed closed during forecast-context hydration for decision
signature:

`5chWKZyjzvLtZiMtwrxQLmdr2sJ1TgtcK8T1DNnkNByXDZw6FnrKd8vKpUYGsHWD3SbkfgFEFeYiANwDoXmVDCpx`

with:

`observer candidate not found at point-in-time boundary`.

Read-only incident analysis proved that decision evidence itself was coherent:

- canonical FastEvent venue was `pump_swap`;
- the future-path label preserved `pump_swap`;
- matching canonical PumpSwap source evidence existed;
- a verified
  `pump_fun_bonding_curve -> pump_swap` graduation existed before the
  decision;
- the observer database contained only one prior candidate identity for the
  mint at the decision boundary, and that candidate row was the historical
  bonding-curve candidate;
- no exact PumpSwap market snapshot existed for the decision boundary.

The production classification was therefore:

`ONLY_OTHER_VENUE_CANDIDATES_EXIST_AT_DECISION`.

The failed feature identity was:

- mint
  `5VG4QtDFrYAkM9PFgSkmeU47ba13fb4bWqfTcPNXpump`;
- decision sequence `14287993`;
- decision ordinal `2147483759`;
- decision observed-at `1788691164424`;
- decision venue `pump_swap`.

The runner returned exit code `1`. No host-run was published and no Fast
forecast champion authenticated.

Post-attempt cleanup succeeded:

- temporary retry swap was disabled and removed;
- legacy `shreks.target`, observe, PAPER evidence, PAPER campaign, and
  telemetry timer were restored active;
- Fast shadow remained inactive;
- no additional runner invocation occurred.

The previous context-resolution retry authority is permanently consumed. This
seal does not reinterpret that invocation as unused.

## Preserved incident evidence

The trusted host preserved the consumed failure receipt at:

`/root/shreks-fast-champion-context-final-failure-39985879d2c69d19e70fc086c4b5127e1af02418`

including authority state, invocation ID, complete unit journal, unit state, and
fresh-input SHA-256 receipt.

That receipt is historical incident evidence only and creates no retry
authority.

## Tradable-preselection implementation

The implementation fixes the mismatch by moving the already-sealed FL9
tradable-universe boundary ahead of first-champion partitioning.

The retry-capable tree now:

1. creates one immutable
   `shreks.fast_first_champion_tradable_preselection` artifact;
2. applies the existing immutable `fl9-tradable-universe-v1` policy to each
   post-floor feature identity without using future targets, model results, or
   execution outcomes;
3. requires verified migration plus exact point-in-time PumpSwap market
   evidence under the existing source/freshness/liquidity/volume policy;
4. excludes missing, stale, ambiguous, contradictory, or below-threshold market
   evidence before chronological partitioning;
5. binds the exact accepted decision identities;
6. binds the selected candidate and exact snapshot identity for every accepted
   decision;
7. binds the FL9 policy fingerprint, proof-workspace fingerprint, feature-source
   SHA-256, observer database SHA-256, observer WAL presence/SHA-256,
   assessment-evidence fingerprint, accepted-identity fingerprint, and
   candidate-binding fingerprint;
8. requires the live observer database/WAL snapshot to remain byte-identical to
   the preselection snapshot in the canonical host-request writer, host runner,
   preparation, nested champion request, and strict readback chain;
9. restricts every first-champion runtime-bundle rebuild to the authenticated
   accepted decision identities;
10. passes the authenticated decision-to-candidate binding into first-champion
    hydration rather than re-resolving candidate identity through a
    contradictory candidate-row venue requirement;
11. closes persisted evaluation contexts to the authenticated chronological
    validation/TEST domain;
12. copies and strictly re-authenticates the preselection artifact through
    host-run, preparation, and final champion evidence;
13. bumps the affected V1 request/artifact schemas so historical bytes cannot be
    silently reinterpreted under the new contract.

The implementation does not change:

- the FL9 tradable-universe policy thresholds or version;
- forecast target definitions;
- model families;
- feature schema;
- future-path label semantics;
- economics projection;
- chronological split algorithm;
- TEST-only evaluation policy;
- score-free champion selection;
- execution policy;
- PAPER authority;
- signing/submission authority;
- LIVE authority.

## Exact implementation-CI prerequisite

Before this seal may merge, GitHub Actions for exact implementation main SHA:

`f1b62be23d40063bf5a08ec1f18ec035eb4b90bc`

must complete successfully for:

- Python tests;
- Rust tests;
- ARM64 release build;
- repository safety.

A failed or cancelled implementation-main gate invalidates this seal proposal
until separately reviewed.

## Exact sealed release prerequisite

This docs-only seal must itself land on `main` before any new physical retry
preparation.

The authorized physical retry must run only from the exact immutable release
whose source SHA is the merged seal SHA, or a later explicitly reviewed
docs-only seal descendant containing the identical implementation tree with no
intervening code change.

Before input preparation, prove:

```text
EXPECTED_RELEASE_SHA=<exact merged tradable-preselection retry-seal SHA>
CURRENT_RELEASE=/opt/shreks/releases/<EXPECTED_RELEASE_SHA>
readlink -f /opt/shreks/current == CURRENT_RELEASE
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

No path may select a release by freshness.

The normal release pipeline must independently pass exact sealed-main CI,
native ARM64 release verification, immutable GitHub Release creation, verified
production deployment, and protected legacy PAPER verification.

## Failed-input non-reuse boundary

Every executable input from the consumed `39985879...` attempt is historical
failure evidence only.

The following may not be relabeled or reused as executable inputs for this new
authority:

- consumed proof workspace;
- consumed hydration policy;
- consumed training-economics overlay;
- consumed training execution-cost policy;
- consumed request;
- consumed host-run/staging paths.

The old release had no tradable-preselection artifact, so no preselection may be
retroactively manufactured and attached to that consumed request.

The new attempt requires fresh current-release paths and fingerprints.

## Fixed semantic request policy

The new retry preserves the reviewed non-release semantics:

```text
future_path_label_version=1
counterfactual_base_quantity=2
horizon_ms=10000
minimum_decision_observed_at_unix_ms=1788687596439
minimum_raw_rows_per_partition=300
minimum_test_scored_observations=100
evaluation_policy_version=fast-paper-champion-bootstrap-test-evaluation-v1
probability_bucket_count=10
liquidity_capacity_quote_boundaries=()
round_trip_cost_bps_boundaries=()
binary_log_loss_clip_epsilon=1e-12
champion_version=fast-paper-champion-bootstrap-runtime-v1
model_version_prefix=fast-paper-champion-bootstrap
training_policy_version=fast-paper-champion-bootstrap-training-v1
reason=bounded score-free Fast PAPER forecast champion bootstrap
```

Any semantic change requires separate review and may not be hidden inside this
retry ceremony.

## Stable-snapshot input-preparation boundary

The new implementation makes the authoritative observer database/WAL snapshot a
first-class authenticated input.

Therefore fresh preselection and request construction may not occur while
legacy PAPER continues mutating the observer database.

After exact release verification and before creating the fresh proof workspace,
the trusted ceremony must perform bounded legacy PAPER quiescence.

The ceremony must:

- stop the telemetry trigger that can initiate new legacy work;
- quiesce the PAPER campaign;
- stop PAPER evidence only at a safe completed-cycle boundary when necessary;
- stop observe/target participation needed to prevent further authoritative DB
  mutation;
- prove unexpected observer-database holders are absent;
- prove the authoritative database/WAL state is stable before input
  construction;
- keep that exact database/WAL state unchanged through preselection, canonical
  request construction, final input authentication, and the one runner
  invocation.

If bounded quiescence cannot complete safely, abort before runner invocation.
That does not consume retry authority.

No manual database edit, WAL checkpoint mutation, candidate insertion, snapshot
backfill, or historical evidence repair is authorized.

## Fresh current-release inputs

Under that one stable observer snapshot, build fresh inputs using only the exact
retry-seal release-local commands:

1. fresh `shreks.fast_proof_workspace` from the authoritative stable observer
   database;
2. fresh runtime-backed hydration policy from the exact legacy PAPER runtime
   authority;
3. fresh authenticated training-economics overlay from the new proof workspace;
4. fresh authenticated training execution-cost policy;
5. fresh immutable
   `shreks.fast_first_champion_tradable_preselection` from the new proof
   workspace and the same stable observer database/WAL snapshot;
6. fresh canonical first-champion host request that binds the exact
   preselection artifact fingerprint;
7. one new absent host-run destination and absent matching staging residue.

The fresh proof export database/WAL identity, preselection database/WAL identity,
and live database/WAL identity used by request creation must reconcile exactly.

The preselection must strictly authenticate at least:

- policy version and policy fingerprint;
- proof-workspace artifact fingerprint;
- feature-source JSONL SHA-256;
- fixed minimum decision timestamp;
- observer database SHA-256;
- observer WAL absence or SHA-256;
- assessed row count;
- eligible row count;
- eligibility-reason counts;
- accepted-identity fingerprint;
- candidate-binding fingerprint;
- assessment-evidence fingerprint;
- accepted-file SHA-256;
- preselection artifact fingerprint.

The canonical host request must be written only after those bindings pass.

## Pre-invocation resource gates

Before large fresh input construction, the root filesystem must have at least
30 GiB available after deliberate removal/archive of only obsolete,
unreferenced evidence or releases.

Immediately before the runner invocation require:

- exact current retry-seal release still active;
- the same observer database/WAL snapshot still authenticated;
- fresh proof/preselection/economics/hydration/request authentication complete;
- no host-run destination;
- no matching host-run staging residue;
- Fast shadow inactive;
- no unexpected active swap;
- at least 20 GiB root-filesystem space before temporary swap allocation;
- approximately 10 GiB available physical memory after legacy PAPER
  quiescence.

The ceremony may create exactly one temporary 8 GiB retry swapfile as bounded
OOM protection.

After swap allocation, at least 10 GiB root-filesystem space must remain.

The wrapper must preserve the runner exit status and provide cleanup that:

- disables/removes the temporary retry swap when safely possible;
- restores legacy PAPER services and telemetry after terminal success/failure;
- keeps Fast shadow inactive;
- does not mask the runner result.

## Non-consuming pre-runner failures

Failure during release verification, quiescence, proof construction,
preselection, hydration-policy construction, economics construction, cost-policy
construction, request creation, resource gating, destination checking, or final
authentication occurs before the runner invocation and does not consume this
runner authority.

Partial or failed input artifacts may not be reused as if successful.

Any renewed pre-invocation preparation must use fresh absent destinations and
repeat the stable-snapshot and authentication gates.

This clause does not authorize a second runner invocation.

## Exactly one new runner invocation

Only after every exact-release, stable-snapshot, fresh-input, resource,
destination, quiescence, and final-authentication gate passes may a trusted
administrator invoke exactly once:

`shreks-fast-first-champion-run --request <fresh-current-release-request.json>`

using the exact retry-seal release.

This authority is consumed when that command is invoked.

If the command fails for any reason, this seal grants no additional runner
invocation.

No retry loop, restart policy, scheduler, fallback request, automatic second
attempt, or operator-invented second invocation is authorized.

## Success proof

A successful attempt must publish one strictly readable immutable host-run
whose nested champion authenticates as:

`schema_name=shreks.fast_lane_forecast_champion`

and whose evidence chain binds at least:

- exact retry-seal release SHA;
- fresh host-request fingerprint and request-file SHA-256;
- fresh hydration-policy fingerprint and file SHA-256;
- fresh proof-workspace artifact fingerprint and feature-source SHA-256;
- fresh tradable-preselection policy fingerprint;
- fresh tradable-preselection artifact fingerprint;
- accepted-identity fingerprint;
- candidate-binding fingerprint;
- observer database SHA-256 and WAL identity;
- fresh economics-overlay manifest fingerprint;
- execution-cost-policy fingerprint;
- chronological plan fingerprint and file SHA-256;
- training-bundle fingerprint;
- validation-policy fingerprint;
- preparation artifact fingerprint;
- context fingerprint;
- champion version;
- champion fingerprint;
- champion-file SHA-256;
- final champion artifact fingerprint;
- host-run artifact fingerprint.

Strict readback must prove that persisted contexts belong only to the
authenticated accepted validation/TEST population.

After terminal cleanup:

- legacy PAPER must independently authenticate active;
- telemetry must be restored;
- temporary retry swap must be absent;
- Fast shadow must remain inactive.

## Post-success authority boundary

Successful champion publication advances only:

`FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=AUTHENTICATED_IMMUTABLE_ARTIFACT`

It does not authorize:

- installation or mutation of Fast PAPER authority files under `/etc/shreks`;
- systemd daemon reload for Fast shadow;
- Fast shadow start;
- automatic champion promotion;
- legacy PAPER replacement;
- authoritative Fast PAPER mutation;
- signing or transaction submission;
- LIVE.

The separately sealed Fast PAPER shadow host-preparation, physical
commissioning, evaluation, promotion, baseline, and cutover gates remain
mandatory.

## Authority state before the new retry

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_PREVIOUS_AUTHORITY=CONSUMED_FAILED_OOM
FAST_CHAMPION_MEMORY_BOUNDED_RETRY_AUTHORITY=CONSUMED_FAILED_CONTEXT_AMBIGUITY
FAST_CHAMPION_CONTEXT_RESOLUTION_RETRY_AUTHORITY=CONSUMED_FAILED_HISTORICAL_PUMPSWAP_COVERAGE_GAP
FAST_CHAMPION_TRADABLE_PRESELECTION_RETRY_AUTHORITY=SEALED_ONE_EXPLICIT_ATTEMPT_AFTER_EXACT_DEPLOY
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

No other authority changes until the separately required ceremonies succeed.
