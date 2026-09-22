# G1C V2 Decision-Backed Candidate Authoring Production Presence — Design

**Date:** 2026-09-22  
**Status:** read-only production presence proof only; no automatic candidate authoring

## Purpose

The decision-backed exact candidate author is implemented and tested separately.

Before a trusted administrator may use it against protected source/authority artifacts, the ordinary production verifier must prove that the exact active immutable release physically contains the authoring CLI and module.

This slice adds presence/provenance proof and runbook documentation only.

## Production verifier contract

Require:

- release-local console script `shreks-g1c-v2-decision-backed-candidate-author`;
- regular non-symlink executable;
- resolved console-script path exactly under the expected immutable release;
- module `shreks_brain.g1c_v2_decision_backed_candidate_authoring`;
- module path resolving inside that same expected release.

Expected evidence:

```text
g1c_v2_decision_backed_candidate_authoring=present
g1c_v2_decision_backed_candidate_authoring_path=<exact-release-local-path>
g1c_v2_decision_backed_candidate_authoring_module=<exact-release-local-module-path>
```

The production verifier must not execute the author.

## Runbook contract

Document one trusted-admin ceremony over explicit existing:

- canonical v1 source runtime manifest;
- authenticated decision-backed candidate authority;
- new private candidate destination.

The command has no raw:

- paper-run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry input amount;
- cohort;
- request authority;
- candidate-value decision.

Those values must come only from the authenticated decision-backed authority.

The author must reproduce the authority-committed candidate SHA/fingerprint and write the exact canonical candidate bytes to a new mode-0600 file.

## Authority boundary

This slice adds no automatic candidate authoring and no:

- transition binding;
- readiness;
- installation/activation/manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

A later separate seal/deploy step is required before protected production use.
