# G1C V2 PAPER Manifest Manager Status Evidence Artifact — Design

**Date:** 2026-09-21  
**Status:** implementation slice; production artifact publication remains unauthorized until separately sealed

## Purpose

Preserve the already-authenticated production helper-status observation as a small machine-retrievable GitHub Actions artifact after a complete successful production PAPER verification.

The current verifier prints the canonical status JSON into job logs. That proves the state, but operators and later tooling should not need to scrape logs to retrieve the exact evidence bytes.

This slice does not add any new host read or host write authority.

## Evidence source

The existing release-local command remains the sole producer of helper-status facts:

`shreks-g1c-v2-paper-manifest-manager-status <expected-release-sha>`

The production verifier already validates the status schema and narrow authority fields on the host.

The SSH stdout is additionally captured into a runner-local temporary transcript while still streaming to the normal job log.

The remote verifier command remains governed by outer `set -euo pipefail`, so piping through `tee` does not turn a remote failure into success.

## Runner-local extraction

Only after the entire remote production verifier succeeds, the runner:

1. finds lines beginning exactly with `paper_manifest_manager_status_json=`;
2. requires exactly one such line;
3. parses the value as JSON;
4. requires one JSON object;
5. reconstructs canonical sorted compact JSON and requires exact byte equality;
6. requires the exact expected release SHA;
7. requires the exact helper-status schema and version;
8. requires one of the five sealed observational statuses;
9. rechecks:
   - `observation_authority = READ_ONLY`;
   - `installation_authority = NOT_EXERCISED`;
   - `manifest_rotation_authority = NOT_GRANTED`;
   - `scoring_authority = NOT_GRANTED`;
   - `paper_promotion_authority = BLOCKED`;
   - `live_authority = DISABLED`.

Any mismatch fails the production verification job.

## Artifact contents

The runner writes a private temporary evidence directory containing exactly:

```text
status.json
status.json.sha256
```

`status.json` is the canonical helper-status JSON terminated by one newline.

`status.json.sha256` contains the SHA-256 of those exact bytes.

Both files are mode `0600` before upload.

The artifact name is:

`paper-manifest-manager-status-<expected-release-sha>-<run-attempt>`

The workflow uses `actions/upload-artifact@v7` and fails if the expected evidence directory is missing.

## Data minimization

The artifact does not contain:

- SSH private keys;
- pinned host-key material;
- the full SSH transcript;
- journal output;
- SQLite data;
- E11 evidence;
- G7 state;
- campaign manifest contents;
- discovery result bodies;
- wallet or signing material.

It contains only the already-public-to-the-job helper-status observation and its SHA-256 sidecar.

## Authority boundary

Artifact extraction and upload occur entirely on the GitHub runner after successful read-only verification.

This slice adds no:

- helper installation;
- helper replacement;
- chmod/chown;
- sudoers change;
- service lifecycle command;
- manifest rotation;
- readiness execution;
- scoring;
- promotion;
- signing;
- transaction submission;
- LIVE authority.

An artifact whose status is `MATCHED_CURRENT_RELEASE` still does not replace the root helper-installation proof.

An artifact whose status is `ABSENT` still does not authorize automatic installation.

## Tests

Static repository tests require:

- runner-local verification transcript capture;
- exactly-one-line evidence extraction;
- local release/authority revalidation;
- canonical JSON output;
- SHA-256 sidecar creation;
- `actions/upload-artifact@v7`;
- deterministic release-bound artifact naming;
- fail-closed missing-file behavior.

Existing status-probe tests continue to prove the host observation itself is non-mutating.

## Production boundary

Merging this implementation does not deploy the changed verifier.

A later seal is required before automatic production verification may publish this evidence artifact.

**HELPER STATUS EVIDENCE ARTIFACT: IMPLEMENTED, NOT YET SEALED.**  
**HELPER INSTALLATION: SEPARATE TRUSTED-ADMINISTRATOR ACTION.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
