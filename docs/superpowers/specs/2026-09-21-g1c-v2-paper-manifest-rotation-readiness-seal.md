# G1C V2 Protected PAPER Manifest Rotation Readiness — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `c132a0443b45418469d734486cdbb49af8f6f49c`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF READ-ONLY ROTATION-READINESS CODE; TRUSTED-ADMINISTRATOR READINESS USE AUTHORIZED ONLY AFTER SUCCESSFUL HELPER-INSTALL PROOF; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the evidence-only readiness proof for one future protected PAPER runtime-manifest v1 -> v2 rotation.

The readiness tool exists to prove that the host, helper, source manifest, v2 candidate, transition binding, G7 state, protected runtime paths, sudoers boundary, and runtime service lifecycle are mutually consistent before any separate production-rotation authority is considered.

It does not rotate the manifest.

## Production state before this seal

The currently sealed production release is:

`781a17ef3068d43146dfb080ad84bf7a09f6687e`

Its immutable release/deploy chain completed successfully.

Production verification showed:

- current release equals the expected sealed SHA;
- observer active/running;
- PAPER evidence service active/running;
- PAPER campaign service active/running;
- zero unexpected restarts;
- protected FL9 discovery remains read-only;
- FL9 status remains `HOLD_NO_COMPATIBLE`.

The readiness implementation merge:

`c132a0443b45418469d734486cdbb49af8f6f49c`

was intentionally a `feat:` commit.

Its automatic release and deploy workflow invocations were correctly skipped.

Therefore production does not yet contain the readiness CLI merely because the implementation landed on `main`.

## Readiness implementation

The implementation adds the release-local console script:

```text
shreks-g1c-v2-paper-manifest-rotation-readiness
```

implemented by:

```text
shreks_brain.g1c_v2_paper_manifest_rotation_readiness
```

The CLI accepts:

```text
<candidate-runtime-manifest>
<transition-binding>
<successful-installation-proof>
<expected-binding-fingerprint-sha256>
<expected-release-source-sha>
```

It requires effective uid 0 because it reads protected host evidence.

It does not invoke the helper installer.

It does not invoke the manifest manager.

## Exact release and helper identity

The readiness proof re-authenticates:

- `/opt/shreks/current`;
- canonical release manifest source SHA;
- exactly one manifest-hashed Shreks wheel;
- the exact sealed PAPER manifest-manager member in that wheel;
- the installed `/usr/local/sbin/shreks-paper-manifest-manager` bytes;
- installed helper uid 0, gid 0, and mode `0755`.

The supplied helper-installation proof must be:

- canonical JSON;
- fingerprint-valid;
- `status = VERIFIED`;
- bound to the same release, wheel, manager digest, destination, and narrow authority fields.

A stale or unrelated installation proof is rejected.

## Sudoers and runtime-path invariants

The readiness tool independently re-reads:

```text
/etc/sudoers.d/shreks-release-manager
```

It must remain root:root `0440`, contain only the exact existing release-manager deployment rule, and retain the exact SHA-256 recorded by the helper-installation proof.

The readiness tool also requires `/etc/shreks/shreks.env` to preserve the exact protected paths for:

- observer SQLite DB;
- E11 evidence;
- active PAPER campaign manifest;
- G7 operator-control state.

No alternate protected path is accepted.

## Source, candidate, and transition binding

The active source manifest must be:

- an existing regular non-symlink file;
- mode `0640`;
- authenticated canonical v1 authority.

The staged candidate must be authenticated canonical v2.

The transition binding must be canonical and fingerprint-valid.

The explicit operator-supplied binding fingerprint must equal the binding fingerprint.

The proof checks the same manager-critical identities:

- source raw SHA-256;
- source runtime-manifest fingerprint;
- source paper run ID;
- source quote mint;
- candidate raw SHA-256;
- candidate runtime-manifest fingerprint;
- candidate paper run ID;
- candidate start timestamp;
- candidate quote mint;
- candidate quote decimals.

Any mismatch fails closed.

## G7 invariant

The operator risk-control state must decode successfully.

The readiness receipt records:

- revision;
- halt-new-entries state;
- kill-switch state.

The exact G7 state must remain unchanged across the readiness proof window.

The readiness tool does not alter operator controls.

## Service-lifecycle invariant

The readiness tool reuses the already-sealed read-only service-observation surface.

For:

- `shreks-observe.service`;
- `shreks-paper-evidence.service`;
- `shreks-paper-campaign.service`;

it records:

- ActiveState;
- SubState;
- NRestarts;
- MainPID;
- ExecMainStatus;
- ActiveEnterTimestampMonotonic.

Each service must be healthy and the full observations must remain exactly unchanged through the readiness proof.

The tool contains no stop/start/restart/reload/enable/disable authority.

## Candidate preflight

The authenticated candidate bytes are copied to a private temporary directory.

The candidate copy is mode `0600`.

The existing PAPER runtime preflight runs against that exact private copy using the real protected:

- observer SQLite state;
- E11 evidence;
- G7 operator-control state.

No campaign cycle is advanced.

The active protected campaign manifest is not replaced.

The temporary candidate copy is removed when the command exits.

## Stability recheck

After candidate preflight, the tool rechecks:

- current immutable release identity;
- sealed wheel/manager identity;
- installed helper bytes and metadata;
- deployment sudoers;
- protected runtime env paths;
- active source bytes;
- staged candidate bytes;
- transition-binding bytes;
- G7 state;
- service lifecycle observations.

Any drift fails closed.

## Successful readiness receipt

Success emits canonical JSON with:

- `status = READY_EVIDENCE_ONLY`;
- exact release/wheel/manager identity;
- helper-installation proof fingerprint;
- sudoers SHA-256;
- source and candidate hashes/fingerprints/run IDs;
- binding fingerprint;
- G7 state;
- service observations;
- `candidate_preflight_status = PASSED`;
- `runtime_env_contract = MATCHED`;
- `service_lifecycle_unchanged = true`;
- readiness fingerprint.

Authority remains:

- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

`READY_EVIDENCE_ONLY` is evidence, not permission.

## Implementation proof

Implementation PR:

`#351 — G1C: prove protected PAPER manifest rotation readiness`

Final implementation branch head:

`927274fa7c4dd1fdc877a845a9e7030b0053dc08`

Exact repaired branch CI:

`35601015871`

Result:

- Python: 3545 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The warnings are the existing intentional duplicate-ZIP-member warnings in negative transport tests.

Squash-merged implementation main:

`c132a0443b45418469d734486cdbb49af8f6f49c`

Exact merged-main CI:

`35601314997`

Result:

- Python: 3545 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The implementation merge correctly triggered no immutable release because its subject was `feat:`.

Its downstream workflow records were:

- release `35601608055`: SKIPPED;
- deploy `35601613847`: SKIPPED.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build the exact immutable ARM64 release;
2. include the readiness CLI in the release-local Python environment;
3. include the already-sealed installer, installation proof, and manager content already present in the source tree;
4. verify the release bundle;
5. create the immutable GitHub release;
6. deploy it through the existing release manager;
7. activate the ordinary protected PAPER runtime;
8. verify runtime service health and release/process provenance;
9. perform protected FL9 read-only discovery.

Automatic deployment must not run:

- helper-install proof `prepare`;
- the helper installer;
- helper-install proof `verify`;
- rotation-readiness proof;
- the manifest manager;
- any manifest rotation.

## Trusted-administrator readiness authority granted by this seal

Only after all of the following are true:

1. this exact sealed release is active on production;
2. ordinary production verification succeeds;
3. the release-bound helper has been installed through the separately sealed installer;
4. the helper-installation proof has succeeded with `status = VERIFIED`;

a trusted administrator is authorized to run the release-local readiness proof.

The readiness evidence should be stored in a root-private directory.

The exact current release SHA and exact transition-binding fingerprint must be passed explicitly.

A failed readiness proof stops the progression.

A failed readiness proof is not permission to repair protected state by widening sudoers, replacing manifests, restarting services, or bypassing G7.

## No automatic helper install

This seal does not add the installer, installation proof, readiness proof, or manifest manager to GitHub deployment actions.

The `shreks-deploy` sudoers rule remains exactly unchanged.

No automatic workflow receives authority for:

```text
/usr/local/sbin/shreks-paper-manifest-manager
```

No automatic workflow receives authority to execute root readiness proof.

## Production manifest-rotation boundary

Even after a successful `READY_EVIDENCE_ONLY` receipt, production v2 runtime-manifest rotation remains unauthorized.

A future separately explicit rotation authority must bind the exact evidence and intended action.

The sealed manifest manager independently rechecks its own source/candidate/binding/release/env/G7 conditions at invocation time.

This seal does not invoke:

```text
shreks-paper-manifest-manager rotate
```

This seal does not authorize invocation of that command.

## Scoring and promotion boundary

This seal does not authorize:

- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- transaction signing;
- transaction submission;
- LIVE trading.

Protected FL9 discovery remains read-only evidence.

## Expected production result

The automatic chain for this seal must demonstrate:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> runtime health/process provenance
  -> protected FL9 read-only discovery
```

The expected result is a production current release containing the readiness CLI.

The automatic chain must not install the root helper and must not rotate the campaign manifest.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_ROTATION_READINESS=SEALED_EVIDENCE_ONLY`

`TRUSTED_ADMIN_READINESS_USE=AUTHORIZED_AFTER_VERIFIED_HELPER_INSTALL`

`AUTOMATIC_READINESS_EXECUTION=DISABLED`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
