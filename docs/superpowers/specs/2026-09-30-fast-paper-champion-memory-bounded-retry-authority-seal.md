# Fast PAPER Champion Memory-Bounded Retry Authority — Release Seal

**Date:** 2026-09-30  
**Implementation main SHA:** `34c50b1cbc072b45fc37421203931f2b5b59aa53`  
**Status:** SEAL PENDING; EXACTLY ONE FRESH MEMORY-BOUNDED FORECAST-CHAMPION RETRY AUTHORIZED ONLY AFTER EXACT SEALED RELEASE DEPLOY/VERIFY; FAST SHADOW START, PAPER CUTOVER, AUTOMATIC PROMOTION, SIGNING/SUBMISSION, AND LIVE REMAIN DISABLED

## Purpose

Authorize one separately reviewed retry of the missing score-free Fast Lane
forecast champion after the prior bounded bootstrap authority was consumed by a
physical host OOM failure.

This seal is separate from the implementation change. The memory-bounded
implementation landed on `main` as:

`34c50b1cbc072b45fc37421203931f2b5b59aa53 — fix: bound first-champion bootstrap memory`

Exact merged-main CI for that implementation passed Python, Rust, ARM64 release
verification, and repository safety.

The retry remains the same score-free forecast-champion evidence operation. It
does not restore or authorize the historical FL9 V2 scoring/control path.

## Consumed attempt incident

The prior authority was consumed when the protected host invoked:

`shreks-fast-first-champion-run --request <canonical-request>`

for request fingerprint:

`63b246ddf209491fdd086e1b5808dedf7d1631bd39ba0a9c8df325e626f3c71a`

The invocation failed before publishing a host-run artifact.

Physical host evidence showed:

- systemd result `oom-kill`;
- approximately 11.3 GiB peak resident memory;
- approximately 7.8 GiB peak swap use from an 8 GiB temporary swapfile;
- no published first-champion host-run;
- no authenticated forecast champion;
- legacy observer, PAPER evidence, and PAPER campaign services restored active;
- Fast PAPER shadow remained inactive;
- temporary swap cleanup completed.

The previous authority is permanently consumed. This seal does not reinterpret
that failed invocation as unused.

## Memory-bounded implementation

The retry-capable tree keeps the historical full runtime-bundle behavior for
callers that do not request a horizon, but the first-champion chain now passes
its explicit horizon through every bundle construction.

For the requested horizon, the implementation:

1. authenticates the complete pinned training-economics overlay while retaining
   only the requested horizon and label version;
2. derives the exact selected decision population from those authenticated
   economics rows;
3. streams the immutable feature JSONL, verifies its complete source SHA-256 and
   canonical identity/order rules, and retains only the selected decisions;
4. loads canonical FL4 labels only for those exact selected identities,
   requested horizon, and label version;
5. requires exact selected-population equality across features, FL4 labels,
   economics rows, and canonical counterfactual provenance;
6. preserves the existing execution-cost projection, counterfactual labeling,
   chronological validation, TEST evaluation, five forecast targets, model
   families, champion codec, and fingerprint chain;
7. verifies proof workspaces with a streaming bounded reader rather than
   retaining the complete proof feature dataset;
8. releases the host logical bundle before preparation and releases the
   preparation logical bundle before reopening hydration / entering the nested
   file-backed champion run.

No forecast target, model family, evidence threshold, action policy, score,
promotion rule, or runtime trading authority is changed by this seal.

## Fresh-release prerequisite

This seal may authorize a retry only after the docs-only seal commit itself:

1. lands on `main`;
2. passes exact sealed-main Python, Rust, ARM64, and repository-safety CI;
3. produces the immutable ARM64 release for that exact sealed SHA;
4. deploys that exact release through the verified production release manager;
5. passes normal protected legacy PAPER production verification.

The retry must pin:

```text
EXPECTED_RELEASE_SHA=<exact deployed retry-seal SHA>
CURRENT_RELEASE=/opt/shreks/releases/<EXPECTED_RELEASE_SHA>
readlink -f /opt/shreks/current == CURRENT_RELEASE
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

No path may choose a release by freshness.

## Failed-input non-reuse boundary

The consumed request and its current-release inputs are historical failure
evidence only.

The retry must not reuse the old request as executable authority.

Before new large artifacts are reclaimed or removed, the trusted administrator
must preserve a root-private incident receipt containing at least:

- failed unit identity and invocation identity when available;
- complete failed-unit journal;
- relevant kernel OOM lines;
- consumed request path and request fingerprint;
- proof-workspace artifact fingerprint;
- economics-overlay manifest fingerprint;
- training execution-cost policy fingerprint;
- release SHA;
- host-run absent result;
- Fast champion absent result;
- legacy PAPER restored result;
- Fast shadow inactive result.

The old large proof/economics copies may be reclaimed only after that incident
receipt is reviewed and only if they are not referenced by active runtime
authority. The receipt does not create retry authority.

## Fresh retry inputs

After the exact retry-seal release is deployed and verified, build fresh
current-release-bound inputs:

1. a new `shreks.fast_proof_workspace` from the authoritative observer
   database using the exact release-local proof workspace command;
2. a new runtime-backed hydration policy from the exact active legacy PAPER
   runtime manifest;
3. a new authenticated training-economics overlay from the new proof workspace;
4. a new authenticated training execution-cost policy;
5. a new canonical host request from the exact retry-seal release;
6. a new absent host-run destination.

The old `cf991...` proof workspace, economics overlay, hydration policy,
request, and host-run destination may not be relabeled or reused as current
retry inputs.

## Fixed semantic request policy

The retry preserves the reviewed non-release semantic parameters from the
consumed request:

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

Any change to these semantic values requires separate review rather than being
hidden inside the retry ceremony.

## Host resource gate

Storage and memory pressure were part of the physical failure, so resource
headroom is an explicit precondition rather than an implicit assumption.

Before creating the fresh proof/economics set, the host must have at least
30 GiB available on the root filesystem after deliberate removal/archive of
only obsolete, unreferenced evidence/releases.

Before the final retry invocation, after all fresh inputs exist and legacy PAPER
is still running normally, the host must have at least:

- 20 GiB root-filesystem space available before temporary swap allocation;
- approximately 10 GiB physical memory available after the bounded quiescence;
- no pre-existing retry swapfile;
- no host-run destination;
- no host-run staging residue.

The trusted retry ceremony may create exactly one temporary 8 GiB swapfile for
OOM protection. After swap allocation, at least 10 GiB root-filesystem space
must remain before invoking the runner.

The temporary swapfile is operational headroom only. It does not change model
or evidence semantics and must be removed after the attempt when safely
possible.

Failure of any resource gate occurs before the retry runner is invoked and does
not consume the retry authority.

## One-retry authority

After every fresh input and resource gate authenticates, a trusted
administrator may invoke exactly once:

`shreks-fast-first-champion-run --request <fresh-canonical-retry-request.json>`

using the exact retry-seal release.

Retry authority is consumed when that command is invoked.

If the command fails for any reason, this seal grants no additional retry.
Preserve the fail-closed evidence and require another separate authority review.

No automatic retry loop, service restart policy, scheduler, or background
re-invocation is authorized.

## Success proof

A successful retry must publish one strictly readable immutable host-run whose
nested champion authenticates as:

`schema_name=shreks.fast_lane_forecast_champion`

and binds at least:

- exact retry-seal release SHA;
- fresh host-request fingerprint;
- fresh proof-workspace fingerprint;
- fresh hydration-policy fingerprint;
- fresh economics-overlay manifest fingerprint;
- training execution-cost policy fingerprint;
- chronological plan fingerprint;
- training-bundle fingerprint;
- preparation fingerprint;
- champion version;
- champion fingerprint;
- champion-file SHA-256;
- host-run artifact fingerprint.

Legacy PAPER must then be restored and independently shown active. Fast shadow
must remain inactive.

## Post-success authority boundary

Successful champion publication advances only:

`FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=AUTHENTICATED_IMMUTABLE_ARTIFACT`

It does not authorize:

- installation of Fast PAPER authority files under `/etc/shreks`;
- systemd daemon reload for Fast shadow;
- Fast shadow start;
- automatic champion promotion;
- legacy PAPER replacement;
- authoritative Fast PAPER mutation;
- signing or transaction submission;
- LIVE.

The separately sealed Fast PAPER shadow host-preparation, physical
commissioning, FL11 evidence, promotion, baseline, and cutover gates remain
mandatory.

## Authority state before retry

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_PREVIOUS_AUTHORITY=CONSUMED_FAILED_OOM
FAST_CHAMPION_MEMORY_BOUNDED_RETRY_AUTHORITY=SEALED_ONE_EXPLICIT_ATTEMPT_AFTER_EXACT_DEPLOY
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

No other authority changes until the separately required ceremonies succeed.
