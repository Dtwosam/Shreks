# FL9 One-Command First Champion Host Run — Design

**Date:** 2026-09-04

## Status

Implementation slice after the deterministic first-champion evidence planner merged as
`21a4fcf77eb66e6589088f5951a60f66ba5fa76f` (#209).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Expose the sealed first-champion evidence chain as one production-shaped host command without
introducing new model, validation, context, execution-cost, or trading semantics.

The command composes already-sealed layers:

1. #206 authenticated proof workspace;
2. #201 dependency-free runtime training bundle;
3. #209 deterministic first-champion evidence plan;
4. #207 authenticated point-in-time hydration policy/context;
5. #208 atomic first-champion preparation;
6. #205 immutable first-champion artifact underneath #208.

This slice is operational orchestration only.

## Canonical host request

Schema:

`shreks.fast_first_champion_host_request` v1.

The request explicitly contains:

- proof-workspace path;
- observer database path;
- hydration-policy path;
- destination path;
- expected release source SHA;
- expected hydration-policy fingerprint;
- selection-clock policy;
- FL4 future-path label version;
- counterfactual base quantity;
- forecast horizon;
- minimum raw rows per chronological partition;
- minimum TEST scored observations;
- exact FL8.4 evaluation policy;
- champion version;
- model-version prefix;
- training-policy version;
- explicit selection reason;
- request fingerprint.

No model family, target set, fold boundaries, selection time, release identity, hydration policy, or
economic evidence floor is hidden in the command implementation.

The five required FL9 target/model-family pairs remain fixed by sealed #203.

## Selection clock

V1 supports exactly:

`HOST_WALL_CLOCK_AT_RUN_START`.

At run start the host captures `time.time_ns() // 1_000_000` once.

That captured millisecond timestamp is not used to search alternate models or economic outcomes.
It serves only as the point-in-time selection boundary supplied to sealed #209.

This is intentionally different from taking a user-supplied historical selection timestamp:
the operational command cannot backdate selection after inspecting later evidence.

The captured timestamp is written into:

- the #209 plan;
- the #208 first-champion selection record;
- the outer host-run manifest.

Given the same bundle and captured timestamp, #209 remains deterministic.

## Source authentication

Before planning, the host run strict-reads the #206 proof workspace and requires its release source
SHA to equal the request's explicit expected SHA.

The canonical #207 hydration-policy file is strict-decoded and its logical fingerprint must equal the
request's explicit expected hydration-policy fingerprint.

The current logical #201 runtime bundle is rebuilt from:

- the proof workspace's canonical feature JSONL;
- the protected read-only observer database;
- explicit FL4 label version;
- explicit counterfactual base quantity.

The bundle's feature byte and logical fingerprints must equal #206.

## Deterministic evidence planning

The host run calls sealed #209 using:

- the exact current logical bundle;
- explicit horizon;
- captured selection timestamp;
- explicit raw-partition evidence floor;
- explicit TEST scored-observation floor.

#209 alone owns fold planning and target dry-runs.

The host layer does not search alternate partitions after inspecting model metrics or economic
performance.

The plan is persisted as `plan.json`.

## Atomic first-champion preparation

The host run passes the exact #209 validation policy and selection timestamp into sealed #208.

The #208 preparation receives:

- #206 proof workspace;
- current read-only observer DB;
- exact #207 hydration policy;
- exact #209 validation policy;
- exact request evaluation policy;
- explicit FL4/FL5 parameters;
- champion/model/training versions;
- decision reference derived from the #209 plan fingerprint;
- explicit reason;
- horizon;
- TEST evidence floor.

The decision reference is:

`first-champion-plan:<plan_fingerprint_sha256>`.

This makes the first champion's selection provenance directly traceable to the deterministic plan.

## Outer host-run artifact

Schema:

`shreks.fast_first_champion_host_run` v1.

Root entries are exactly:

- `request.json`;
- `hydration-policy.json`;
- `plan.json`;
- `preparation/`;
- `manifest.json`.

The #208 preparation is self-contained and already carries its proof workspace, context hydration,
generated first-champion request, and first-champion artifact.

The outer layer therefore adds the operational request, captured selection clock, and deterministic
plan without duplicating the child evidence files.

## Outer manifest

The host-run manifest binds:

- host request fingerprint/file SHA;
- hydration-policy fingerprint/file SHA;
- selection-clock policy;
- captured selection timestamp;
- expected release source SHA;
- #206 proof-workspace artifact fingerprint;
- feature-source JSONL SHA;
- #209 plan fingerprint/file SHA;
- training-bundle fingerprint;
- validation-policy fingerprint;
- #208 preparation artifact fingerprint;
- context fingerprint;
- champion fingerprint;
- champion version;
- top-level artifact fingerprint.

## Cross-layer validation

Before publication the host layer requires:

- #208 proof-workspace release and artifact identity == request/#206;
- #209 bundle fingerprint == current #201 bundle == #208 bundle;
- #209 feature source == #206 feature source;
- #208 hydration-policy fingerprint == request/#207;
- #208 context-hydration validation policy == #209 validation policy;
- #208 first-champion request evaluation policy == host request evaluation policy;
- #208 first-champion horizon/selection time/evidence floor == #209;
- #208 decision reference == #209 plan fingerprint reference;
- #208 champion version == host request.

The strict reopen path repeats the child artifact readers and the same cross-links.

An individually valid child artifact from another population cannot be substituted.

## Mutation and atomicity

The host run rereads the source request and hydration-policy bytes after #208 completes and requires
exact byte equality.

The #206 proof workspace is strict-read again and its manifest must be unchanged.

Database/WAL races are handled independently by #207, #205, and #208, while the bundle and child
fingerprint cross-links prevent the host plan from silently spanning a different logical DB state.

The host result is staged in a private sibling directory.

The staged result is strict-read before atomic rename.

Existing destinations are never overwritten.

All staging is removed on failure.

## Console command

The release wheel exposes:

`shreks-fast-first-champion-run --request <canonical-request.json>`.

On success it emits compact JSON with:

- status `SUCCEEDED`;
- artifact path;
- captured selection timestamp;
- plan fingerprint;
- champion fingerprint.

Failures remain non-zero and do not create a valid outer host-run artifact.

A later operator-status layer may classify specific evidence insufficiency reasons without weakening
the underlying exception/evidence gates.

## TDD provenance

Intentional RED:

`3752e46a60caa132cc0231e44cca35767be14bd3`.

The initial implementation matrix was green for repository safety, Rust, and ARM64 but Python
correctly failed because the required console-script entry point was absent.

During the script fix, a literal backslash-n was accidentally written into `pyproject.toml`.
Pip rejected the malformed TOML before tests. The actual GitHub bytes were audited and replaced
with a real newline; no host-run logic was weakened.

## Authority boundary

The module contains no:

- provider/network calls;
- direct SQLite queries;
- new model fitting or target selection;
- alternate-fold search;
- new regime/context derivation logic;
- new execution-cost estimation;
- PAPER order execution;
- trade intent;
- promotion/registry mutation;
- signing;
- transaction submission;
- LIVE authority.

It is an offline/read-only evidence orchestration command.

## Following work

Once #210 is sealed, the software path required for the first genuine non-fixture champion is
present in the release wheel.

The next step is operational evidence execution, not another synthetic model layer:

1. build/deploy a verified release containing #206-#210;
2. run #206 under the existing `shreks` PAPER runtime identity against the protected observer DB;
3. create the canonical production #207 hydration-policy file from explicit current policies;
4. create a canonical #210 host request pinned to release/policy fingerprints;
5. run `shreks-fast-first-champion-run`;
6. preserve the resulting host-run artifact or the exact fail-closed evidence error;
7. if a genuine champion exists, evaluate only post-selection evidence through #202/#199/#198.

LIVE remains disabled.
