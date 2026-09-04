# FL9 Atomic First Champion Preparation — Design

**Date:** 2026-09-04

## Status

Implementation slice after point-in-time context hydration merged and sealed as
`1eba5696ed1dc5921c55b5f32e4c0d559cb24d83` (#207).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Collapse the already-sealed first-champion evidence steps into one atomic, cross-linked artifact.

This slice adds no new forecasting, validation, regime, execution-cost, campaign, or trading
semantics. It orchestrates:

1. #206 proof workspace;
2. #201 runtime logical training bundle;
3. #207 point-in-time context hydration;
4. #205 file-backed first-champion request/artifact.

The objective is to make it impossible to accidentally combine a feature export, context corpus,
training bundle, request, and champion from different evidence populations.

## Inputs

The preparation API requires explicit:

- existing #206 proof-workspace path;
- observer SQLite path;
- destination;
- #207 hydration policy;
- chronological validation policy;
- FL8.4 evaluation policy;
- FL4 future-path label version;
- FL5 counterfactual base quantity;
- champion version;
- explicit selection decision reference/time/reason;
- forecast horizon;
- model-version prefix;
- training-policy version;
- minimum TEST scored-observation count.

This slice is a library orchestration boundary.

It intentionally does **not** yet invent a production CLI encoding for these nested policies.
A following thin file-backed request/CLI slice should expose this safely to the VPS operator/runtime.

## Self-contained child evidence

The source #206 proof workspace is strict-read first.

The preparation then copies the full proof workspace into its private staging root as:

`proof-workspace/`.

The copied workspace and the source workspace are strict-read again.

The source/copy manifests and feature byte/logical fingerprints must remain identical.

This makes the published preparation retain the exact feature JSONL and #206 manifest rather than
depending on an external proof-workspace directory remaining available.

The raw observer SQLite database is not copied. Its exact current database + optional WAL content is
bound cryptographically in the preparation and child artifacts.

## Database source seal

Before any #201/#207/#205 work, the preparation hashes:

- main observer SQLite database;
- optional SQLite WAL.

Stable-file hashing checks device/inode/size/mtime around each streamed hash read.

The same snapshot is required by:

- #207 hydration artifact;
- #205 first-champion artifact;
- parent #208 preparation manifest.

After the first champion is complete, the parent hashes database + WAL again.

Any change aborts publication and removes staging.

The #207 and #205 child layers already independently perform their own before/after source checks,
so the parent provides an additional end-to-end seal rather than replacing them.

SQLite SHM remains outside durable content identity, consistent with the earlier proof boundaries.

## Runtime training bundle

#208 calls sealed #201
`build_fast_training_bundle_from_runtime_sources(...)`
using:

- copied `proof-workspace/features.jsonl`;
- current read-only observer DB;
- explicit FL4 label version;
- explicit counterfactual base quantity.

The resulting feature byte fingerprint and feature logical fingerprint must exactly equal the
copied #206 proof workspace.

Any mismatch fails before context hydration.

## Context hydration

The preparation invokes sealed #207 with the exact bundle, DB, validation policy, horizon, and
hydration policy.

The resulting hydration artifact is stored as:

`context-hydration/`.

#208 requires:

- exact chronological validation policy equality;
- exact horizon equality;
- exact training-bundle fingerprint equality;
- exact feature-source fingerprint equality;
- exact DB/WAL snapshot equality.

No context row is manufactured by #208.

## First-champion request

After hydration succeeds, #208 constructs a sealed #205 request with internal relative evidence
paths:

- `feature_jsonl_path = proof-workspace/features.jsonl`;
- `context_corpus_path = context-hydration/contexts.json`;
- `destination_path = first-champion`.

The observer database remains an explicit absolute source path because #205 must re-read point-in-time
FL4/FL5 evidence while building the champion.

The request carries the exact same chronological validation policy and horizon used by #207.

It is written as:

`first-champion-request.json`.

## First champion

The request is executed by sealed
`run_fast_first_champion_file_request(...)`.

The resulting artifact is stored as:

`first-champion/`.

It is strict-read immediately after creation.

#208 then requires exact equality across the evidence chain:

- request object/fingerprint;
- feature JSONL SHA;
- DB SHA;
- WAL SHA;
- training-bundle fingerprint;
- context file SHA;
- context logical fingerprint.

Any independently valid child artifact from another run is rejected.

## Preparation artifact

Schema:

`shreks.fast_first_champion_preparation` v1.

Root entries are exactly:

- `proof-workspace/`;
- `context-hydration/`;
- `first-champion-request.json`;
- `first-champion/`;
- `manifest.json`.

Staging is a private sibling directory.

The full staged artifact is strict-read before atomic rename.

Existing destinations are never overwritten.

All staging is removed on failure.

## Parent manifest

The manifest binds:

### Proof workspace
- release source SHA;
- #206 artifact fingerprint;
- feature JSONL SHA;
- feature logical fingerprint;
- DB/WAL identity used at feature export.

### Current evidence source
- current observer DB SHA;
- current observer WAL SHA.

The feature-export DB identity and current DB identity are intentionally separate. A proof workspace
may have been exported from an earlier immutable observer state while later-matured FL4/FL5 evidence
exists in the current DB. #201 remains responsible for validating that the components join
correctly.

### Bundle/context
- training-bundle fingerprint;
- chronological validation-policy fingerprint from #207;
- #207 artifact fingerprint;
- hydration-policy fingerprint;
- population FL8.3 validation-run fingerprint;
- #204 context fingerprint.

### Request/champion
- request fingerprint;
- request file SHA;
- #205 artifact fingerprint;
- champion fingerprint;
- champion version;
- explicit selection decision reference;
- selection timestamp;
- selection reason.

### Parent
- top-level preparation artifact fingerprint.

## Strict reopen

The parent reader first verifies:

- exact root entry set;
- child directory/file kinds;
- canonical manifest JSON;
- exact manifest keys;
- top-level fingerprint;
- request file SHA.

It then strict-reads:

- #206 proof workspace;
- #207 context hydration;
- canonical #205 request;
- #205 first-champion artifact.

It cross-links every child to the parent manifest and to each other.

It additionally requires:

- request validation policy == #207 validation policy;
- request horizon == #207 horizon;
- exact internal evidence paths;
- champion child request == parent request;
- champion selection fields == parent selection provenance.

## Failure semantics

#208 publishes nothing when:

- source/copy proof workspaces differ;
- copied feature evidence differs from #201 bundle;
- DB/WAL changes at any time;
- hydration policy/population/bundle/source differs;
- request differs from hydration;
- first champion differs from request, bundle, DB, or context;
- staged parent fails strict reopen;
- destination exists or appears during preparation.

There is no partial-success artifact.

If #201, #207, or #205 reports insufficient evidence through failure, #208 also fails closed. A later
host status layer may classify such failures for operator reporting without weakening this
provenance boundary.

## Authority boundary

The module contains no:

- provider/network calls;
- direct SQLite queries;
- new forecasting/model math;
- new regime logic;
- execution-cost estimation;
- PAPER order execution;
- trade intent;
- campaign selection;
- registry/promotion mutation;
- signer;
- transaction submission;
- LIVE mode.

It calls only already-sealed offline/read-only evidence components.

## TDD provenance

Intentional RED:

`173b653dfcd407dd878218e6fa5ac065b4bd8b36`.

The first implementation CI correctly rejected a fixture whose mocked #206 logical feature
fingerprint did not equal the mocked #201 bundle's real logical fingerprint. The fixture was made
truthful; production cross-link validation was retained.

A subsequent fixture hardening added the child validation-policy fingerprint and explicit champion
selection provenance required by the parent manifest.

## Following work

After #208 seals, the next slice should be a thin canonical **file-backed preparation request + CLI**
that:

1. encodes all #208 inputs without hidden defaults;
2. reuses #207's canonical hydration-policy codec;
3. reuses #205's exact validation/evaluation policy semantics;
4. exposes one release-wheel console command;
5. resolves relative paths against the request file;
6. runs #208 as the existing `shreks` runtime identity;
7. emits machine-readable success/insufficient/failure status without weakening evidence gates.

That command will make the sealed chain operational on the VPS.

LIVE remains disabled.
