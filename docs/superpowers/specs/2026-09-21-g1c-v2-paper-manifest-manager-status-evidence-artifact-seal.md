# G1C V2 PAPER Manifest Manager Status Evidence Artifact — Release Seal

**Date:** 2026-09-21  
**Implementation main SHA:** `aecfa2f971505355f8ba68c4ec77f59ff1fceb91`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY + RUNNER-SIDE HELPER-STATUS EVIDENCE ARTIFACT; HELPER INSTALLATION REMAINS SEPARATE TRUSTED-ADMINISTRATOR ACTION; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal durable, machine-retrievable evidence for the already-sealed read-only production helper-status observation.

The production verifier may preserve only the canonical helper-status JSON and its SHA-256 sidecar after the full verifier succeeds.

This seal adds no host mutation and no helper-installation authority.

## Production state before this seal

The current sealed production release is:

`fa09a459fe65c17fd1e05a9322c1be825bfd6e56`

Its production verifier established:

```text
paper_manifest_manager_status=ABSENT
```

while observer, PAPER evidence, and PAPER campaign remained active/running with zero restarts, and protected FL9 discovery remained `HOLD_NO_COMPATIBLE`.

The status-evidence artifact implementation merged to main as:

`aecfa2f971505355f8ba68c4ec77f59ff1fceb91`

Exact implementation branch CI:

`35613318571`

Result:

- Python: 3552 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Exact merged-main CI:

`35613650247`

Result:

- Python: 3552 passed, 2 warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

The implementation merge was intentionally `feat:`, so its sealed-release path remained unauthorized.

## Evidence extraction boundary

The production verifier continues to execute the already-sealed release-local read-only status CLI.

The SSH stdout is streamed normally and simultaneously captured to one runner-local temporary transcript with shell `pipefail` still active.

The runner does not upload that transcript.

Only after the entire remote production verification succeeds, the runner extracts lines beginning exactly with:

```text
paper_manifest_manager_status_json=
```

It requires exactly one such line.

## Runner-local revalidation

Before preserving evidence, the runner independently requires:

- valid JSON object;
- exact canonical sorted compact JSON bytes;
- helper-status schema name;
- schema version 1;
- exact expected production release SHA;
- one allowed observational status:
  - `ABSENT`;
  - `MATCHED_CURRENT_RELEASE`;
  - `PRESENT_DIFFERENT_BYTES`;
  - `PRESENT_METADATA_MISMATCH`;
  - `PRESENT_UNSAFE_TYPE`;
- `observation_authority = READ_ONLY`;
- `installation_authority = NOT_EXERCISED`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

Any mismatch fails verification.

## Artifact contents

The runner creates exactly:

```text
status.json
status.json.sha256
```

inside a runner-local private temporary directory.

`status.json` contains the exact canonical helper-status JSON plus one newline.

`status.json.sha256` binds the SHA-256 of those exact bytes.

Both files are mode `0600` before upload.

The GitHub Actions artifact is named:

```text
paper-manifest-manager-status-<expected-release-sha>-<run-attempt>
```

The workflow uses `actions/upload-artifact@v7`.

Missing expected evidence is a hard failure.

## Data minimization

The uploaded artifact does not include:

- SSH private key material;
- pinned known-host material;
- the SSH transcript;
- service journals;
- SQLite rows;
- E11 contents;
- G7 contents;
- campaign-manifest contents;
- FL9 discovery result bodies;
- credentials;
- wallet material;
- signing material.

It contains only the already-validated helper-status observation and its SHA-256 sidecar.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on main and exact sealed-main CI succeeds, authorize the existing automatic chain to:

1. build and verify the exact immutable release;
2. create the immutable GitHub release;
3. deploy through the existing narrow release-manager path;
4. run the existing production PAPER verifier;
5. execute the already-sealed read-only helper-status probe;
6. capture verifier stdout runner-locally;
7. extract and revalidate exactly one helper-status observation;
8. upload only `status.json` and `status.json.sha256`;
9. continue existing runtime health/process-provenance and protected FL9 verification.

## Actions not authorized

This seal does not authorize:

- helper installation;
- helper replacement;
- helper chmod/chown repair;
- helper invocation;
- helper-install proof execution;
- rotation-readiness execution;
- sudoers widening;
- service lifecycle mutation beyond the existing sealed release deployment;
- production v2 runtime-manifest rotation;
- V2 scoring;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing;
- transaction submission;
- LIVE.

## Meaning of the artifact

The artifact is durable verification evidence only.

`ABSENT` does not authorize automatic installation.

`MATCHED_CURRENT_RELEASE` does not prove the trusted-administrator installation ceremony occurred and does not replace `installation-proof.json`.

Divergent or unsafe states do not authorize automatic repair.

No helper-status artifact authorizes manifest rotation.

## Trusted-administrator boundary

The physical helper installation remains:

```text
installation-proof prepare
  -> exact sealed installer
  -> installation-proof verify
```

through a trusted administrator channel.

That channel remains separate from GitHub deployment authority.

After a canonical `VERIFIED` installation proof, the already-sealed readiness proof may be run as previously authorized.

Production v2 manifest rotation remains a later, separately explicit authority decision.

## Expected production proof

The automatic chain for this seal must show:

```text
seal merge
  -> exact sealed-main CI
  -> immutable release
  -> protected PAPER deploy
  -> successful production verify
  -> helper-status evidence artifact exists
  -> artifact contains only status.json + status.json.sha256
  -> artifact status remains observational
```

The root helper must not be installed or repaired by this chain.

## Promotion boundary

`G1C_V2_PAPER_MANIFEST_MANAGER_STATUS_ARTIFACT=SEALED_READ_ONLY_EVIDENCE`

`AUTOMATIC_STATUS_EVIDENCE_UPLOAD=AUTHORIZED_AFTER_SUCCESSFUL_VERIFY`

`AUTOMATIC_HELPER_INSTALL=DISABLED`

`TRUSTED_ADMIN_EXACT_HELPER_INSTALL=PREVIOUSLY_AUTHORIZED`

`INSTALLATION_PROOF_REQUIRED_FOR_ACCEPTANCE=YES`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
