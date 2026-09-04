# FL9 File-Backed First Champion Request — Design

**Date:** 2026-09-04

## Status

Implementation slice after the authenticated FL8.4 evaluation-context corpus merged and sealed as
`e6d6bdfc94a1bb6df5206d752eb878ce1ef585b4` (#204).

FL9 economic superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Purpose

Create the first durable host-side command boundary capable of producing a genuine, non-fixture
FL8.5 forecast champion from production-shaped FL9 evidence without PyArrow, scikit-learn, NumPy,
provider access, or live trading authority.

The already-sealed components are:

- #201: build the exact logical FL8.1 bundle from Rust feature JSONL + read-only SQLite;
- #203: build the dependency-free five-member first champion from an in-memory bundle and explicit
  TEST context/policies;
- #204: authenticate the exact FL8.4 point-in-time context corpus.

This slice binds those components into a canonical request and an immutable result artifact.

## Request schema

Schema:

`shreks.fast_first_champion_file_request` v1.

The request contains exactly:

- feature JSONL path;
- observer SQLite path;
- authenticated context-corpus path;
- artifact destination path;
- FL4 future-path label version;
- counterfactual base quantity;
- exact chronological validation policy;
- exact TEST evaluation policy;
- champion version;
- explicit selection decision reference;
- explicit selection timestamp;
- explicit selection reason;
- forecast horizon;
- model-version prefix;
- training-policy version;
- explicit minimum TEST scored-observation count;
- request fingerprint.

No hidden defaults choose a model family, target, selection decision, economic threshold, or clock.
The target/family set remains fixed by sealed #203.

## Canonical request codec

The request is encoded as compact sorted UTF-8 JSON with exactly one trailing newline.

Numeric values preserve type:

- integers remain JSON integers;
- Python floats use exact `float.hex()` tagged encoding;
- raw JSON floats are rejected;
- NaN and infinities are rejected.

The validation policy persists every fold interval explicitly.

The evaluation policy persists:

- TEST partition;
- probability-bucket count;
- liquidity boundaries;
- cost boundaries;
- log-loss clip epsilon.

The request fingerprint is SHA-256 over the canonical request material, excluding the fingerprint
field itself.

The request constructor and decoder independently recompute the fingerprint.

Unknown/missing keys, duplicate JSON keys, non-canonical JSON, malformed tagged values, or a
fingerprint mismatch fail closed.

## Path semantics

A request file is the resolution anchor.

Relative source/destination paths resolve against the directory containing the request file.
Absolute paths remain absolute.

The request copied into the result artifact is provenance evidence. The runner never silently
rewrites its path strings.

Production host requests should prefer explicit paths under the private PAPER evidence root so their
operational meaning remains obvious when audited.

## Runtime source snapshot

Before any model/evaluation work, the runner authenticates:

1. feature JSONL bytes;
2. observer SQLite database bytes;
3. observer SQLite `-wal` bytes when present;
4. context corpus bytes.

Each regular file is stat-checked before/after its hash read so a mutation during hashing fails.

The SQLite `-shm` file is intentionally excluded, matching the existing deterministic invocation
seal: SHM is volatile coordination state, while database + WAL are the durable SQLite content
boundary.

The context corpus is then read from bytes whose SHA must equal the captured context-file SHA.

The #201 runtime bundle must report a feature-source SHA equal to the captured JSONL SHA. A mocked or
real bundle cannot claim different source bytes and still pass this boundary.

## Build flow

The runner:

1. reads and strictly decodes the canonical request;
2. resolves all paths;
3. refuses an existing destination;
4. captures the source snapshot;
5. decodes the authenticated #204 context corpus;
6. calls `build_fast_training_bundle_from_runtime_sources(...)`;
7. requires the bundle feature-source hash to equal the authenticated JSONL;
8. calls sealed #203 `build_fast_first_champion(...)`;
9. requires every TEST report to carry the exact context-corpus logical fingerprint;
10. recaptures all mutable sources;
11. requires the before/after source snapshots to be identical;
12. rereads the request and requires byte identity with the original request payload;
13. only then stages the immutable artifact.

Any request/source race produces no published champion artifact.

## Result artifact

Schema:

`shreks.fast_first_champion_artifact` v1.

The root contains exactly:

- `request.json`;
- `contexts.json`;
- `champion.json`;
- five target-specific TEST evaluation report files;
- `manifest.json`.

The exact authenticated context corpus is copied into the artifact, rather than storing only its
hash. This keeps the FL8.4 segmentation evidence inspectable even if the original runtime context
file is later rotated.

The feature JSONL and SQLite database are not duplicated into every champion artifact. Their exact
content identities are bound by source hashes and the FL8.1 bundle fingerprint.

## Manifest

The manifest binds:

- request fingerprint;
- request file SHA;
- feature JSONL SHA;
- observer database SHA;
- optional observer WAL SHA;
- context-corpus file SHA;
- context logical fingerprint;
- FL8.1 training-bundle fingerprint;
- champion fingerprint;
- champion file SHA;
- exactly five evaluation-report entries;
- top-level artifact fingerprint.

Each evaluation entry binds:

- target;
- horizon;
- file name;
- file SHA;
- FL8.3 validation-run fingerprint;
- FL8.4 evaluation-report fingerprint;
- TEST scored count;
- TEST unavailable count.

Evaluation entries use unique lexical file names.

## Atomic publication

Output uses a private sibling temporary directory.

The runner writes all files, constructs the manifest, and calls the strict artifact reader on the
staged directory.

Only a fully reopenable staged artifact may be renamed to the requested destination.

If any exception occurs, staging is removed.

If the destination appears during staging, publication fails instead of overwriting it.

## Strict artifact reopen

The reader requires the exact manifest keys and exact root file set.

It recomputes:

- manifest artifact fingerprint;
- request/champion/context/report file hashes;
- request logical fingerprint;
- context logical fingerprint;
- champion fingerprint through the sealed FL8.5 reader;
- every evaluation-report fingerprint through the sealed FL8.4 reader.

It also cross-links:

- request selection identity/time/reason -> champion selection;
- manifest training-bundle fingerprint -> champion;
- manifest context fingerprint -> copied context corpus and all TEST reports;
- each TEST report -> its manifest entry;
- each TEST report -> the corresponding champion member's validation/report/count evidence.

A report or champion that is individually valid but belongs to a different evidence chain is
rejected.

## Failure semantics

This slice does not fabricate an `INSUFFICIENT_EVIDENCE` champion.

If #201 cannot build a valid bundle, #204 context coverage is incomplete, #203 TEST evidence is too
small, target labels are immature, source bytes race, or any sealed provenance check fails, the
request fails and no artifact is published.

A later host orchestration/status layer may classify those failures for operator reporting without
weakening this evidence boundary.

## Authority boundary

The module contains no:

- provider/network calls;
- direct SQLite query implementation;
- PAPER execution;
- trade-intent construction;
- model-family ranking;
- automatic champion selection;
- governance mutation;
- signing;
- transaction submission;
- LIVE mode.

SQLite is accessed for training evidence only through the already-sealed #201 read-only runtime
bundle builder.

## TDD provenance

Intentional RED:

`5418c1f2c1da5b58c050a4d0a423179fff31d7e3`.

RED matrix:

- Python: expected failure — new `file_request` module absent;
- Repository safety: GREEN;
- Rust: GREEN;
- ARM64: GREEN.

The first implementation CI exposed a test-fixture provenance error: its mocked bundle retained the
synthetic fixture feature-source SHA instead of the authenticated test JSONL SHA. Production
correctly rejected it. The fixture was corrected to carry the real source hash and a recomputed
bundle fingerprint; the production check was retained.

## Following work

After this slice is sealed, the remaining host gap is execution orchestration under the existing
`shreks` runtime identity:

1. materialize the authenticated #200 native proof tools;
2. run the sealed Rust feature exporter against the private runtime DB;
3. prepare/capture the real #204 context corpus without inventing missing fields;
4. construct the first-champion file request;
5. run this file-backed builder;
6. inspect whether a genuine champion was produced or evidence was insufficient;
7. use the resulting champion only on a post-selection population;
8. feed that population through #202 deterministic baselines and #199 learned comparison;
9. let #198 report `SUPERIOR`, `FAILED`, or `INSUFFICIENT_EVIDENCE`.

LIVE remains disabled.
