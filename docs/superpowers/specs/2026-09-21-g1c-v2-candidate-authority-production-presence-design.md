# G1C V2 Candidate Authority Production Presence — Design

**Date:** 2026-09-21  
**Status:** implementation slice; read-only production presence proof only; no candidate execution or production values

## Purpose

The candidate-input authority binder is implemented on `main`, but trusted production use must not rely on package assumptions alone.

This slice extends the existing production verifier to prove that the exact active immutable release physically contains:

- the release-local console script `shreks-g1c-v2-runtime-manifest-candidate-authority-bind`;
- the Python module `shreks_brain.g1c_v2_runtime_manifest_candidate_authority`;
- module provenance inside the exact expected deployed release directory.

The verifier does not execute the binder.

## Verification contract

The production verifier requires the console-script path to:

- exist as a regular file;
- not be a symlink;
- be executable;
- resolve exactly to the expected active immutable release.

It imports the module through the exact current release Python environment and requires the resolved module path to be below that same expected release.

It then emits only presence/provenance evidence:

- `g1c_v2_candidate_authority=present`;
- resolved console-script path;
- resolved module path.

The verifier must not invoke `candidate_authority.main(...)` and must not execute the console script.

## Runbook contract

The release runbook documents the offline binding command shape with placeholders for every explicit new-run value.

The runbook states that the binder does not choose production candidate values. Unit-test/example values and historical USDC hydration values are not defaults.

The authority artifact destination is operator-selected and write-once; the documented example uses a private `candidate-authority.json` path.

## Authority boundary

This slice adds no:

- source/candidate manifest mutation;
- protected manifest rotation;
- service control;
- sudoers expansion;
- SQLite write;
- scoring or model fitting;
- PAPER promotion;
- signing/submission;
- LIVE authority.

Production verification proves code presence only.

A later separate production-value authority decision is still required before one exact candidate-authority artifact may be created for the live PAPER host.
