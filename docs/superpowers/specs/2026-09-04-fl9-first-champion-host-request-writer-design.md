# FL9 Canonical First Champion Host Request Writer — Design

**Date:** 2026-09-04

## Status

Implementation slice after runtime-manifest hydration-policy derivation merged and sealed at
`ead8a1f504e00a6491bb2a01d3240a8bc4d91d6d` (#212).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Remove the last hand-authored JSON step before the one-command #210 first-champion host run.

This slice creates one canonical #210 request from already-authenticated source artifacts and
explicit operator evidence parameters.

It does not execute the first-champion run itself.

## Source inputs

The writer requires:

- an existing #206 proof workspace;
- the protected observer database path;
- a canonical #207/#212 hydration-policy file;
- a new request destination;
- a future #210 host-run destination.

It strict-reads the proof workspace and hydration policy before building the request.

The proof workspace provides the exact expected release source SHA.

The hydration policy provides the exact expected logical policy fingerprint.

Those identities are copied into the #210 host request; they are not typed manually.

## Observer database semantics

The writer validates that the observer database path currently resolves to a regular file.

It deliberately does **not** freeze the database byte/WAL fingerprint at request-creation time.

The observer database is live PAPER evidence and may legitimately mature between request creation
and host-run execution.

Byte/WAL coherence is owned by the execution chain:

- #207 seals DB/WAL around context hydration;
- #205 seals DB/WAL around first-champion construction;
- #208 seals DB/WAL around the complete preparation;
- #210 cross-links the resulting bundle/child fingerprints.

The writer therefore binds the exact absolute database path but does not introduce an earlier,
stale database-content seal.

## Evaluation policy

The writer accepts an exact `FastForecastEvaluationPolicy`.

Only the TEST partition is allowed.

The CLI requires every evaluation field explicitly:

- evaluation-policy version;
- probability bucket count;
- one or more liquidity-capacity quote boundaries;
- one or more round-trip-cost bps boundaries;
- binary log-loss clipping epsilon.

No evaluation segmentation default is hidden in the writer.

## Selection clock

The writer always supplies #210's only sealed selection authority:

`HOST_WALL_CLOCK_AT_RUN_START`.

No CLI argument can supply or backdate a historical selection timestamp.

The actual timestamp is captured later by #210 at execution start and sealed into the #209 plan and
the resulting artifacts.

## Remaining evidence parameters

The CLI requires explicit:

- FL4 future-path label version;
- counterfactual base quantity;
- horizon;
- minimum raw rows per partition;
- minimum TEST scored observations;
- champion version;
- model-version prefix;
- training-policy version;
- human-readable selection reason.

These are passed unchanged to #210's canonical request builder.

## Path encoding

The generated #210 request contains absolute paths for:

- proof workspace;
- observer database;
- hydration policy;
- host-run destination.

This removes working-directory ambiguity when the request is later run under the PAPER host identity.

The request destination itself is not part of the #210 request body.

## Atomic write

The writer refuses:

- an existing request destination;
- an existing host-run destination;
- identical request and host-run destinations.

The canonical request bytes are written to a sibling temporary file.

The writer:

1. writes the exact canonical payload;
2. flushes;
3. fsyncs;
4. chmods the staged file to 0600;
5. re-reads the hydration-policy source and requires byte equality;
6. re-reads the #206 proof workspace and requires identical manifest identity;
7. requires the observer DB path still resolves to a regular file;
8. requires staged bytes to equal the canonical payload;
9. rechecks request/host destinations remain absent;
10. atomically renames the staged file.

Staging is deleted on failure.

## Output

The library returns:

- written request path;
- request fingerprint;
- release source SHA;
- hydration-policy fingerprint.

The CLI prints compact machine-readable JSON with schema
`shreks.fast_first_champion_host_request_write_status` v1 and status `SUCCEEDED`.

## Console command

The release wheel exposes:

`shreks-fast-first-champion-request`.

This command only writes the canonical request.

The actual evidence run remains:

`shreks-fast-first-champion-run --request <request.json>`.

Keeping write and execute separate preserves inspectability while removing manual JSON editing.

## TDD provenance

Intentional RED:

`5d326fb51b0762dc5eac0a9be4ede18d2a01b1b1`.

The current production head is:

`8307c76934ec09cd8b42e986cefdacb3dfe680e4`.

Its CI run `33911698854` is 4/4 GREEN with **3182 Python tests passed**.

## Authority boundary

The writer contains no:

- provider/network access;
- direct SQLite queries;
- model fitting;
- fold/evidence planning;
- context hydration;
- PAPER order execution;
- trade intent;
- champion promotion;
- registry mutation;
- signer;
- transaction submission;
- LIVE authority.

It only authenticates source artifacts and writes a request for the already-sealed offline host-run
chain.

## Following work

After #213 seals, the software path from sealed PAPER runtime manifest to executable host request is
complete:

1. #212 writes a canonical hydration policy from the exact PAPER runtime manifest plus explicit
   non-derivable evidence inputs;
2. #213 writes a canonical #210 host request using authenticated #206/#212 identities;
3. #210 executes the complete first-champion evidence chain.

The next meaningful work is host execution under the existing PAPER runtime identity and preservation
of the exact success or fail-closed evidence result.

Production deployment remains protected by the existing manual `production-paper` workflow.
LIVE remains disabled.
