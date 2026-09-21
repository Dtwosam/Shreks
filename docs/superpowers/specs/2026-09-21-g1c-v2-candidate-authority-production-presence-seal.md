# G1C V2 Candidate Input Authority + Production Presence — Release Seal

**Date:** 2026-09-21  
**Candidate-authority implementation main SHA:** `cf2986ac55c89b66a4dd51d2327760d881257d8b`  
**Production-presence implementation main SHA:** `1584eb7459e9cc267cce4f6ad3343454734ff6c4`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF CANDIDATE-AUTHORITY CODE PRESENCE; EXPLICIT PRODUCTION CANDIDATE VALUES NOT AUTHORIZED; CANDIDATE/BINDING CREATION NOT AUTOMATIC; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the offline G1C v2 candidate-input authority binder and its read-only production-presence proof.

The binder closes one narrow authority gap discovered after the trusted-administrator helper installation was physically proven:

- the current production host had no pre-existing canonical v2 runtime-manifest candidate;
- no pre-existing transition binding existed;
- the frozen V2 cohort requires WSOL as quote mint;
- the historical authenticated hydration policy remains USDC-derived context and is not authority for new WSOL runtime economics;
- the repository deliberately contained no production defaults for the new run's `paper_run_id`, start timestamp, quote decimals, or raw entry amount.

This seal deploys the code that can bind one separately reviewed set of explicit candidate inputs.

This seal does **not** choose, approve, infer, or create those production values.

## Current production state before this seal

The currently deployed sealed production release is:

`0fba6030c9ff53ecd6c1edbddc3a5e77ac5a6ed5`

That release was automatically built, deployed, and production-verified.

A trusted administrator subsequently completed the exact release-bound helper ceremony.

The canonical installation proof returned:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
proof_fingerprint_sha256=176a14b5301130781118dfd9dd3c2b4cc7e1690739bbc98724214668a5f7a2f1
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The installed helper is:

`/usr/local/sbin/shreks-paper-manifest-manager`

with the exact sealed manager SHA-256:

`e612ca524d633fb5ee58be2e4bb38ad5e1ff1bba418354ca2176561a74fef104`

A bounded protected-evidence inspection then proved:

```text
transition_binding_count=0
v2_runtime_manifest_count=0
search_status=NO_PREEXISTING_G1C_V2_ARTIFACTS
```

The canonical staging paths were also absent.

Therefore rotation-readiness cannot truthfully run yet.

## Preserved V2 request authority

The protected host evidence identified three authenticated historical V2 request artifacts.

All three collapse to one authority group:

`f144dc01919d1caff902f2ce2ce8950481722645ae7a411135d74e01009a49c5`

The selected request is:

`/var/lib/shreks/fl9-v2-post-fix-c6473a1a8b1252ade0ad1883ab4ce2f33bf70f46-20260915T193846Z/v2-first-champion-request.json`

with request fingerprint:

`28e7427206b2a919cb29c4bf514ee991b54b2c4c6bc45ac23f43b6a877852a02`

The frozen V2 cohort quote mint is WSOL:

`So11111111111111111111111111111111111111112`

The preserved historical hydration policy is context only and does not authorize replacement runtime quote decimals or raw entry amount.

## Candidate-authority implementation

The implementation adds:

```text
shreks-g1c-v2-runtime-manifest-candidate-authority-bind
```

implemented by:

```text
shreks_brain.g1c_v2_runtime_manifest_candidate_authority
```

The binder requires every new-run value explicitly:

- `paper_run_id`;
- `start_at_unix_ms`;
- target quote mint;
- target quote decimals;
- raw `entry_input_amount`.

It also requires:

- one authenticated canonical v1 source runtime manifest;
- the frozen FL9 V2 cohort;
- the preserved authenticated V2 request authority;
- a new write-once destination.

There are no production defaults.

## Authentication and binding behavior

The binder:

1. authenticates the exact canonical v1 source;
2. authenticates the preserved V2 request against the frozen cohort;
3. rechecks the frozen cohort fingerprint;
4. derives the cohort's single quote mint only to validate the caller's explicit target mint;
5. rejects a target quote mint that differs from the frozen cohort;
6. uses the already-sealed canonical v2 candidate-authoring function in memory with the explicit inputs;
7. canonical-encodes and decodes that candidate;
8. commits to the exact source/candidate raw SHA-256 values and runtime-manifest fingerprints;
9. rechecks source stability;
10. writes one canonical private authority artifact exactly once.

The binder does not emit or stage the candidate runtime-manifest file.

It does not create a transition binding.

It does not execute rotation-readiness.

## Candidate-authority artifact

A successful artifact records:

```text
authority_kind=explicit_new_run_candidate_inputs
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_authoring_authority=EXPLICIT_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The artifact is canonical JSON, write-once, and mode `0600`.

Its self-fingerprint commits the exact explicit candidate values and the exact authenticated source/cohort/request identities.

## Production-presence proof

The production verifier now proves, without executing the binder, that the exact active immutable release physically contains:

- the candidate-authority console script;
- an executable regular non-symlink script path;
- a script path resolving inside the exact expected release;
- the candidate-authority Python module imported by the exact release-local Python;
- a module path resolving inside that same exact release.

Expected verifier evidence includes:

```text
g1c_v2_candidate_authority=present
g1c_v2_candidate_authority_path=<exact-release-local-path>
g1c_v2_candidate_authority_module=<exact-release-local-module-path>
```

The production verifier does not invoke the binder.

## TDD and implementation proof

### Candidate-authority binder

Intentional RED evidence was established before implementation.

Final implementation PR:

`#370 — feat: bind explicit G1C v2 candidate inputs`

Final implementation head:

`07451ad04f9e2e2cf03eb68cfd908c10d38362af`

PR CI:

`35648840029`

Result:

- Python: 3566 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`cf2986ac55c89b66a4dd51d2327760d881257d8b`

Exact merged-main CI:

`35649194900`

Result:

- Python: 3566 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

### Production-presence proof

Intentional RED head:

`757771f288387785696f3b1668ee93d904963ba1`

RED PR CI:

`35649517680`

Result:

- Python: 1 failed, 3566 passed, 2 warnings;
- the only failure was the intentionally absent candidate-authority production-presence contract;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Final presence-proof PR:

`#371 — feat: prove candidate authority production presence read-only`

Final head:

`8282b249ba21f3c678e1c87209efa5392a3e0511`

PR CI:

`35649788410`

Result:

- Python: 3567 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged presence-proof main:

`1584eb7459e9cc267cce4f6ad3343454734ff6c4`

Exact merged-main CI:

`35650565652`

Result:

- Python: 3567 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The two warnings are the already-known intentional duplicate-ZIP-member warnings from negative transport tests.

Both implementation merge commits are `feat:` commits, so their automatic release/deploy workflow invocations correctly do not create production releases.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build an immutable ARM64 release for the exact seal SHA;
2. include the candidate-authority CLI and module in the release-local Python environment;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service health, restart state, process provenance, existing ceremony-tool presence, candidate-authority presence, and protected FL9 read-only discovery.

Automatic deployment must not execute:

- the candidate-authority binder;
- candidate authoring;
- transition binding;
- rotation-readiness;
- the manifest manager;
- V2 scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

No automatic workflow receives production candidate values.

## Existing root helper across this release

The root-installed helper is outside immutable release directories.

Automatic deployment must not create, replace, chmod, chown, or execute:

`/usr/local/sbin/shreks-paper-manifest-manager`

The candidate-authority changes do not modify the sealed manager source.

The ordinary production verifier may therefore observe the already-installed helper as an exact match to the new current release if the sealed manager bytes remain identical.

Any byte or metadata mismatch is a failed production state, not authority to replace the helper automatically.

## Fresh installation proof required before later readiness

The existing successful installation proof is bound to release:

`0fba6030c9ff53ecd6c1edbddc3a5e77ac5a6ed5`

After this seal deploys, `/opt/shreks/current` will identify the new sealed release SHA.

The old installation proof must therefore **not** be reused for rotation-readiness.

Before any later readiness proof, a trusted administrator must create a fresh before/after installation proof bound to the exact new current sealed release.

Because the helper is already present, the first-install planner is not the correct path: it deliberately requires helper state `ABSENT`.

Use the already-sealed three-step proof sequence instead:

1. installation-proof `prepare` for the exact new current release;
2. invoke the already-sealed exact release-bound installer;
3. installation-proof `verify`.

If the existing helper bytes and metadata still match exactly, the installer may report:

`ALREADY_INSTALLED`

That is an accepted installer receipt status under the existing installation-proof seal.

This seal adds no helper-install authority beyond the already-sealed installer/proof authority.

## Explicit production-value boundary

This seal does not authorize concrete values for:

- `paper_run_id`;
- `start_at_unix_ms`;
- target quote decimals;
- raw `entry_input_amount`.

It also does not convert:

- unit-test constants;
- example values;
- historical USDC runtime fields;
- historical hydration-policy values;
- quote-evidence diagnostics

into production candidate authority.

A later separately explicit production-value decision must establish the exact values before one production candidate-authority artifact is created.

## Candidate and transition-binding boundary

Even after exact values are separately authorized and one candidate-authority artifact is created:

1. the canonical candidate bytes must be emitted from those exact values through the existing candidate-authoring path;
2. that exact candidate must pass the existing read-only V2 candidate assessment against the frozen cohort/request authority;
3. the exact compatible candidate must be committed into the existing immutable transition binding.

Only after the canonical candidate and transition binding both exist may rotation-readiness run.

## Rotation, scoring, promotion, and LIVE boundary

This seal does not authorize:

- production v2 manifest rotation;
- invocation of `shreks-paper-manifest-manager rotate`;
- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing;
- transaction construction;
- transaction submission;
- LIVE trading.

A successful future readiness receipt remains evidence only.

## Promotion boundary

`G1C_V2_CANDIDATE_INPUT_AUTHORITY=SEALED_EXPLICIT_INPUT_BINDER`

`CANDIDATE_AUTHORITY_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_CANDIDATE_AUTHORITY_EXECUTION=DISABLED`

`PRODUCTION_CANDIDATE_VALUES=NOT_AUTHORIZED`

`AUTOMATIC_CANDIDATE_STAGING=DISABLED`

`AUTOMATIC_TRANSITION_BINDING=DISABLED`

`AUTOMATIC_ROTATION_READINESS_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
