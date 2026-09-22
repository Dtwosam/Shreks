# G1C V2 Decision-Backed Rotation Readiness — Design

**Date:** 2026-09-22  
**Status:** software contract only; evidence-only readiness; no manifest mutation

## Purpose

The production-sealed decision-backed transition bridge emits the existing canonical
`shreks.g1c_v2_runtime_manifest_transition_binding` v1 schema so downstream
readiness compatibility remains unchanged.

That compatibility-preserving choice creates one remaining provenance gap:
the existing readiness tool authenticates the candidate and standard transition
binding, but cannot distinguish a binding created through the reviewed
decision-backed authority chain from one created through the older generic path.

This wrapper closes only that provenance gap.

## Inputs

Accept only:

- exact canonical v2 candidate runtime manifest;
- exact canonical standard transition binding;
- authenticated decision-backed candidate authority;
- exact current-release helper installation-proof bytes;
- explicit expected immutable release SHA;
- the existing readiness path/runtime/service/preflight dependencies.

The CLI accepts:

- `--candidate-runtime-manifest`;
- `--transition-binding`;
- `--decision-backed-candidate-authority`;
- `--installation-proof`;
- `--expected-release-source-sha`.

The CLI does **not** accept an operator-supplied binding fingerprint. It derives
that value from the authenticated standard binding.

It also accepts no raw paper-run id, start timestamp, quote mint, quote decimals,
entry amount, candidate-value decision, review, or sizing values.

## Provenance contract

Before delegating readiness, require:

1. candidate, binding, and authority are existing regular non-symlink files;
2. stable reads of those three inputs;
3. candidate runtime-manifest authentication;
4. standard transition-binding authentication;
5. decision-backed candidate-authority authentication;
6. candidate SHA/fingerprint/run/start/quote/entry/valuation identity equals the authority;
7. binding source/candidate/cohort/request provenance equals the authority;
8. binding downstream authority remains NOT_GRANTED/BLOCKED/DISABLED.

Then invoke only the existing
`prove_paper_manifest_rotation_readiness` implementation with:

- the exact candidate path;
- the exact binding path;
- supplied installation-proof bytes;
- `expected_binding_fingerprint_sha256` derived from the authenticated binding;
- the explicit expected release SHA;
- unchanged readiness path/runtime/service/preflight dependencies.

After delegation, require the standard readiness receipt to remain:

- `status=READY_EVIDENCE_ONLY`;
- bound to the same source/candidate/binding identities;
- bound to the explicit release SHA;
- `installation_authority=PROVEN`;
- `manifest_rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

Finally re-read candidate, binding, and authority and fail closed if any bytes changed.

Return the existing readiness receipt unchanged. Do not introduce a new readiness schema.

## Authority boundary

This wrapper does not:

- install or refresh the helper;
- create or stage candidate/binding artifacts;
- grant manifest-rotation authority;
- invoke the manifest manager;
- stop/start services except observations already owned by the evidence-only readiness implementation;
- replace the active manifest;
- retry scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

Production use requires a later separate production-presence proof and release seal.
