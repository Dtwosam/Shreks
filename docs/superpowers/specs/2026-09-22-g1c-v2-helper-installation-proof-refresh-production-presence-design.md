# G1C V2 Helper Installation-Proof Refresh Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic proof refresh

## Purpose

The exact-release helper installation-proof refresh is implemented and merged separately.

Before a trusted administrator may use it to produce a fresh proof for the active release,
the ordinary production verifier must prove that the exact active immutable release
contains the refresh CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script
  `shreks-g1c-v2-paper-manifest-manager-install-proof-refresh`;
- regular non-symlink executable;
- resolved script path exactly under the expected immutable release;
- module
  `shreks_brain.g1c_v2_paper_manifest_manager_installation_proof_refresh`;
- module path resolving inside that same expected release.

Expected evidence:

```text
paper_manifest_manager_installation_proof_refresh=present
paper_manifest_manager_installation_proof_refresh_path=<exact-release-local-path>
paper_manifest_manager_installation_proof_refresh_module=<exact-release-local-module-path>
```

The production verifier must not execute proof refresh.

## Trusted-admin ceremony contract

Document one root-private ceremony that accepts only the exact current immutable release SHA.

The helper must already match that exact release. The refresh fails closed when the helper
is absent, has different bytes, or has different metadata. It never installs, replaces,
chmods, or chowns the helper.

A successful command writes one fresh canonical existing-schema
`shreks.g1c_v2_paper_manifest_manager_installation_proof` v1 document into a root-private
evidence directory.

The proof remains:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

## Authority boundary

This slice does not authorize:

- automatic proof refresh;
- decision-backed readiness execution;
- candidate/binding/readiness staging;
- helper installation or repair;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
