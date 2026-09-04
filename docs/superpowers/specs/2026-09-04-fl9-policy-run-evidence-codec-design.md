# FL9 Fast Policy Run Evidence Batch Codec — Design

**Date:** 2026-09-04

## Status

Persistence prerequisite after reproducible comparison input assembly merge
`3fb4c0321323a88945a3f4234116656d31d3dc71` (#191).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Problem

The eight-candidate deterministic PAPER matrix returns exact
`FastPolicyRunEvidence` values in memory.

The superiority report has a canonical codec, but run evidence does not.

A durable comparison artifact therefore cannot safely persist and reload the eight runs without ad-hoc JSON or reconstructing them from unrelated state.

## Scope

Add a pure canonical batch codec:

`encode_fast_policy_run_evidence_batch(...)`

`decode_fast_policy_run_evidence_batch(...)`

and expose:

`fast_policy_run_evidence_fingerprint_sha256(...)`

using the exact same fingerprint material as the existing run-evidence builder.

No file I/O is added in this slice.

## Run fingerprint source of truth

The existing `build_fast_policy_run_evidence` hashes material containing:

- policy proof schema name/version;
- paper run id;
- candidate version/fingerprint;
- strategy version;
- E5 evaluation fingerprint;
- event-population fingerprint;
- action-journal fingerprint;
- material/decision/distinct-market counts;
- observed from/through timestamps.

That material is extracted to one shared helper in `engine.py`.

Both the existing builder and the new public fingerprint function use the same helper.

The codec never reimplements the run fingerprint formula.

## Batch schema

`FAST_POLICY_RUN_EVIDENCE_BATCH_SCHEMA_NAME`:

`shreks.fast_policy_run_evidence_batch`

Schema version: `1`.

Top-level canonical JSON contains:

- schema name;
- schema version;
- lexical run array;
- batch fingerprint.

Each run contains every `FastPolicyRunEvidence` field.

The `trading_evaluation` field is persisted as the existing E10 canonical evaluation evidence document.

## E5 evaluation reconstruction

Encoding calls the existing evaluation codec's canonical evidence-document builder.

Decoding calls the existing sealed evaluation-document decoder.

That decoder reconstructs E5 evidence from:

- policy;
- canonical trades;
- canonical probability observations;

and recomputes the evaluation report/fingerprint.

Stored derived evaluation metrics are therefore not trusted.

Each run must contain exactly one evaluation and its candidate version must equal the run candidate version.

## Run reconstruction

After evaluation reconstruction, decoding rebuilds exact
`FastPolicyRunEvidence`.

It then recomputes the run fingerprint using
`fast_policy_run_evidence_fingerprint_sha256`.

Mismatch fails closed.

## Batch determinism

Input runs must be:

- non-empty;
- exact `FastPolicyRunEvidence`;
- unique by candidate version;
- lexical by candidate version.

The codec does not silently reorder caller input.

Batch fingerprint covers:

- schema name/version;
- every complete run document including nested evaluation evidence.

The fingerprint excludes only itself.

JSON is sorted-key compact UTF-8-compatible canonical text with no non-finite values.

Decoder requires byte-equivalent canonical JSON.

## Tamper behavior

Tests require failure for:

- changed run fingerprint;
- changed nested E5 trade/evaluation material;
- noncanonical JSON;
- nonlexical run order;
- unknown/missing schema fields through exact-key validation.

## Authority boundary

The codec:

- does not write files;
- does not read providers/databases;
- does not run PAPER;
- does not evaluate superiority;
- does not select/promote a model;
- does not sign/submit;
- grants no LIVE authority.

## TDD

Intentional RED:

`35ef9247e7464bbaf3718dce16afb9dd4a90626e`.

The following campaign-artifact slice will write this canonical payload to disk alongside the immutable comparison evidence bundle.
