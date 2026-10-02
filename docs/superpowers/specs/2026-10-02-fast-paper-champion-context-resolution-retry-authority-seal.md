# Fast PAPER Champion Context-Resolution Retry Authority — Release Seal

**Date:** 2026-10-02  
**Implementation main SHA:** `58b13e503a46d55ced75461d32dbebf4ebb8c590`  
**Status:** SEAL PENDING; EXACTLY ONE FRESH FORECAST-CHAMPION RETRY AUTHORIZED ONLY AFTER THIS SEAL LANDS ON `main`, THE EXACT SEALED RELEASE IS BUILT/DEPLOYED/VERIFIED, AND FRESH CURRENT-RELEASE INPUTS AUTHENTICATE; FAST SHADOW START, PAPER CUTOVER, AUTOMATIC PROMOTION, SIGNING/SUBMISSION, AND LIVE REMAIN DISABLED

## Purpose

Authorize one separately reviewed retry of the missing score-free Fast Lane
forecast champion after the memory-bounded retry authority was consumed by a
fail-closed context-candidate ambiguity.

This seal is separate from the implementation fix. The context-resolution
implementation landed on `main` as:

`58b13e503a46d55ced75461d32dbebf4ebb8c590 — fix: resolve Fast hydration candidates at decision boundary`

Exact merged-main CI for that implementation passed Python, Rust, native ARM64
release verification, and repository safety.

The retry remains the same score-free forecast-champion evidence operation. It
does not restore or authorize the historical FL9 V2 scoring/control path.

## Consumed retry incident

The prior memory-bounded retry authority was consumed when the protected host
invoked:

`shreks-fast-first-champion-run --request <fresh-canonical-retry-request.json>`

using exact deployed release:

`3df008ef29446bb519d32b87c1d9161082c5401b`

and request fingerprint:

`89d60815447ed721f1505ebce24c33e40439ed6df91139770f436c0b5ee03b14`

The protected attempt ran as:

- systemd unit `shreks-fast-champion-retry-3df008ef2944.service`;
- systemd invocation `69f4e74839794f258174fa9a4d968d9c`;
- request file SHA-256
  `aa5b33534c5cb9cc8f967154409eee5527aaae55cd1dd5b48f92b12f3a41838b`.

Every final pre-invocation gate passed before the runner was invoked:

- exact release and request identity;
- physical champion absence;
- fresh proof, hydration, economics, and execution-cost authentication;
- legacy PAPER quiescence;
- approximately 10 GiB or more physical memory available after quiescence;
- database/WAL stability;
- host-run destination and staging absence;
- one temporary 8 GiB retry swapfile;
- at least 10 GiB root filesystem space after swap allocation;
- Fast shadow inactive.

The authority was then consumed at the explicit one-shot runner invocation.

The runner failed closed during forecast-context hydration with:

`ValueError: context candidate resolution failed ... observer candidate identity is ambiguous`

The failure occurred because hydration used a mint-only candidate lookup while
the authoritative observer database contained more than one candidate identity
for that mint.

Physical evidence established:

- runner exit code `1`;
- systemd result `exit-code`;
- approximately 1.6 GiB memory peak;
- 0 B swap peak;
- no published host-run destination;
- no authenticated Fast Lane forecast champion;
- temporary swap disabled and removed;
- legacy observer, PAPER evidence, and PAPER campaign services restored active;
- Fast PAPER shadow remained inactive;
- post-attempt cleanup passed.

This was not an OOM failure. The prior memory-bounded retry authority is
permanently consumed. This seal does not reinterpret that invocation as unused.

## Context-resolution implementation

The implementation fix changes only candidate identity resolution for
historical forecast-context hydration.

The retry-capable tree now:

1. resolves observer candidates at the exact decision timestamp rather than
   through an unrestricted mint-only lookup;
2. requires the decision venue during point-in-time candidate resolution;
3. uses the first sealed regime source-priority entry as the preferred discovery
   source;
4. considers only candidates discovered no later than the decision timestamp;
5. preserves the existing snapshot-owner and preferred-source disambiguation
   rules;
6. remains fail-closed when multiple same-venue candidates remain plausible;
7. retains the existing post-resolution venue consistency check;
8. leaves forecast targets, model families, feature schema, training policy,
   future-path labels, economics projection, chronological validation, TEST
   evaluation, champion selection, champion codec, and fingerprint chain
   unchanged.

No score, score threshold, score-backed promotion, execution policy, PAPER
authority, signing/submission authority, or LIVE authority is introduced.

## Exact sealed release prerequisite

This docs-only seal must itself land on `main` before any new physical retry.

The physical retry must run only from one exact immutable release whose source
SHA is the merged seal SHA, or another later explicitly reviewed docs-only seal
descendant containing the same implementation parent with no intervening code
change.

Before retry preparation, the trusted administrator must prove:

```text
EXPECTED_RELEASE_SHA=<exact merged retry-seal SHA>
CURRENT_RELEASE=/opt/shreks/releases/<EXPECTED_RELEASE_SHA>
readlink -f /opt/shreks/current == CURRENT_RELEASE
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

No path may select a release by freshness.

## Failed-input non-reuse boundary

The consumed `3df008...` request and its release-bound proof, hydration,
training-economics, execution-cost, staging, and host-run paths are historical
failure evidence only.

They may not be relabeled or reused as executable authority for the new retry.

Before any consumed-attempt artifacts are reclaimed, preserve a root-private
incident receipt containing at least:

- failed unit identity and systemd invocation identity;
- complete failed-unit journal;
- exact runner exception and exit code;
- consumed release SHA;
- consumed request path, request fingerprint, and request-file SHA-256;
- proof-workspace artifact fingerprint;
- hydration-policy fingerprint;
- economics-overlay manifest fingerprint;
- execution-cost-policy fingerprint;
- pre-invocation resource and database-stability evidence;
- host-run absent result;
- authenticated Fast champion absent result;
- swap cleanup result;
- legacy PAPER restored result;
- Fast shadow inactive result.

The receipt is incident evidence only and creates no retry authority.

## Fresh retry inputs

After the exact retry-seal release is deployed and verified, build fresh
current-release-bound inputs:

1. a new `shreks.fast_proof_workspace` from the authoritative observer
   database using the exact release-local proof exporter;
2. a new runtime-backed hydration policy from the exact active legacy PAPER
   runtime manifest;
3. a new authenticated training-economics overlay from the new proof workspace;
4. a new authenticated training execution-cost policy;
5. a new canonical first-champion host request from the exact retry-seal release;
6. a new absent host-run destination and absent matching staging residue.

The new proof and economics paths must not be aliases or relabels of the
consumed `3df008...` inputs.

## Fixed semantic request policy

The retry preserves the reviewed non-release semantic parameters:

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

Any change to these values requires separate review and may not be hidden inside
the retry ceremony.

## Host resource and quiescence gate

Before creating the fresh proof/economics set, the host must have at least
30 GiB available on the root filesystem after deliberate removal or archive of
only obsolete, unreferenced evidence/releases.

Immediately before the final retry invocation, after fresh inputs exist and
legacy PAPER is still running normally, require:

- at least 20 GiB root-filesystem space available before temporary swap
  allocation;
- approximately 10 GiB physical memory available after bounded legacy PAPER
  quiescence;
- no pre-existing retry swapfile or other unexpected active swap;
- no host-run destination;
- no host-run staging residue;
- exact current retry-seal release still active;
- Fast shadow inactive;
- stable authoritative observer database and WAL state across final input
  authentication.

The trusted ceremony may create exactly one temporary 8 GiB swapfile as OOM
protection. After allocation, at least 10 GiB root-filesystem space must remain.

The retry wrapper must preserve non-masking runner failure semantics and
systemd-level cleanup that restores legacy PAPER and removes the temporary swap
when safely possible.

Failure of any gate before runner invocation does not consume retry authority.

## Exactly one new retry

After every fresh release, input, resource, destination, quiescence, and
database-stability gate passes, a trusted administrator may invoke exactly once:

`shreks-fast-first-champion-run --request <fresh-current-release-request.json>`

using the exact retry-seal release.

The new retry authority is consumed when that command is invoked.

If the command fails for any reason, this seal grants no additional invocation.
Preserve the fail-closed evidence and require another separately reviewed
authority decision.

No retry loop, service restart policy, scheduler, fallback invocation, or
automatic second request is authorized.

## Success proof

A successful retry must publish one strictly readable immutable host-run whose
nested champion authenticates as:

`schema_name=shreks.fast_lane_forecast_champion`

and binds at least:

- exact retry-seal release SHA;
- fresh host-request fingerprint and request-file SHA-256;
- fresh proof-workspace fingerprint;
- fresh hydration-policy fingerprint;
- fresh economics-overlay manifest fingerprint;
- execution-cost-policy fingerprint;
- chronological plan fingerprint;
- training-bundle fingerprint;
- preparation fingerprint;
- champion version;
- champion fingerprint;
- champion-file SHA-256;
- host-run artifact fingerprint.

Legacy PAPER must then be independently shown active. Fast shadow must remain
inactive.

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
commissioning, evidence, promotion, baseline, and cutover gates remain
mandatory.

## Authority state before new retry

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_PREVIOUS_AUTHORITY=CONSUMED_FAILED_OOM
FAST_CHAMPION_MEMORY_BOUNDED_RETRY_AUTHORITY=CONSUMED_FAILED_CONTEXT_AMBIGUITY
FAST_CHAMPION_CONTEXT_RESOLUTION_RETRY_AUTHORITY=SEALED_ONE_EXPLICIT_ATTEMPT_AFTER_EXACT_DEPLOY
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

No other authority changes until the separately required ceremonies succeed.
