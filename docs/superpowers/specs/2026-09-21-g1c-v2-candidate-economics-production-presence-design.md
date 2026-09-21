# G1C V2 Valuation + Sizing Production Presence — Design

**Date:** 2026-09-21  
**Status:** production-presence and runbook slice only; no evidence capture executed automatically

## Purpose

Two offline/evidence-only tools now exist on `main`:

- `shreks-g1c-v2-quote-valuation-reference`;
- `shreks-g1c-v2-entry-sizing-proposal`.

Before either is used against protected production evidence, the ordinary production verifier must prove both tools come from the exact active immutable release.

This follows the same release-provenance pattern already used for candidate authority and the trusted-admin ceremony tools.

## Production verifier

For each CLI, the verifier must require:

- regular file;
- non-symlink;
- executable;
- resolved console-script path exactly inside the expected immutable release;
- imported module path exactly inside the expected immutable release.

The verifier emits presence/provenance evidence only.

It must not execute either CLI.

No protected database read is added to automatic verification by this slice.

## Runbook

The release runbook documents two explicit trusted-admin operations after a sealed release containing these tools is active and production verification has proved their provenance.

### 1. Quote-valuation reference

The operator supplies all exact market-selection inputs:

- database path;
- candidate id;
- as-of timestamp;
- source;
- venue;
- base mint;
- target quote mint;
- freshness bound;
- optional exact expected market row id;
- private destination.

The CLI opens observer evidence through the already-sealed read-only market store and writes one `REFERENCE_EVIDENCE_ONLY` artifact.

There are no production selector defaults.

### 2. Entry-sizing proposal

The operator supplies:

- authenticated v1 source runtime manifest;
- target quote mint;
- target quote decimals;
- the exact quote USD-per-token value from a reviewed reference;
- that reference's exact fingerprint;
- that reference's observation timestamp;
- a private destination.

The CLI writes one `PROPOSAL_EVIDENCE_ONLY` artifact.

The runbook may show how to extract fields from the already-reviewed reference artifact, but it must not claim that extraction authorizes the resulting proposed value.

## Authority boundary

Production presence proves code provenance only.

A quote reference is evidence only.

A sizing proposal is evidence only.

Neither authorizes:

- production candidate values;
- candidate-authority invocation;
- candidate authoring;
- transition binding;
- readiness;
- manifest rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- signing/submission;
- LIVE.

The automatic release/deploy chain must not invoke either evidence CLI.

No sudoers change is required.

## Next boundary

After this presence slice is merged and separately sealed/deployed, a trusted administrator may perform a bounded read-only production inspection to identify exact WSOL market evidence, capture one or more reference artifacts, and produce a sizing proposal.

That physical evidence must be reviewed before any separate production candidate-value decision.
