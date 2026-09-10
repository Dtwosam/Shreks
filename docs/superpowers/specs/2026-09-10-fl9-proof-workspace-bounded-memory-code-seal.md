# FL9 Proof Workspace Bounded Memory — Code Seal

## Status

**SEALED IMPLEMENTATION CANDIDATE.**

This seal records the production-derived FL9 proof-workspace memory correction merged on `main` at:

```text
6fd2bf3d66c216a41b8a48b6ffa5ec61cca82677
```

Implementation PR: **#273** — `fix: bound FL9 proof workspace memory`.

The exact PR head:

```text
8c2dd7e464ef69c02d09011f7e0537f0d7a52570
```

passed all four required PR CI gates in run:

```text
34484963024
```

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS (`3369 passed`)
- ARM64 release build: PASS

The merged implementation commit:

```text
6fd2bf3d66c216a41b8a48b6ffa5ec61cca82677
```

passed all four merged-main CI gates in run:

```text
34486210750
```

LIVE remains disabled. PAPER promotion remains blocked.

## Supersedes the failed physical-attempt release

The immutable release:

```text
shreks-12d756f070b491d0e6229c8bb690f1e0e16bd79f
```

must **not** be reused for another physical FL9 V2 first-champion attempt.

That release successfully incorporated the earlier bounded FL8.1 training replay correction, but a fresh production proof-workspace attempt exposed a separate production-scale memory defect in the Python proof-workspace validation path.

The failed physical run root is:

```text
/var/lib/shreks/fl9-v2-first-champion-12d756f070b491d0e6229c8bb690f1e0e16bd79f-20260910T130403Z
```

Its incomplete staging directory is preserved as failed evidence and must not be renamed, published, overwritten, or reused.

No final proof workspace was published from that attempt. No V2 champion evidence artifact was created.

## Physical failure evidence

The quiesced production wrapper reached all proof-host gates before starting the sealed FL8.1 workspace export:

```text
paper_stop_settle=PASS
v2_proof_host_quiescence=PASS
database_holders=NONE
```

The known observer graceful-shutdown defect was recorded without weakening the gate:

```text
observer_graceful_shutdown=FAIL_TIMEOUT_RECORDED
observer_process_gone=YES
observer_failed_bookkeeping_reset=YES
```

After the exact four-unit host gate passed, the release-bound proof workspace command started against the quiesced production database.

The exporter produced the staged feature JSONL:

```text
1279920706 bytes
```

at:

```text
.../.proof-workspace.tmp-aa8hszcw/features.jsonl
```

before the Python proof-workspace process was killed.

The wrapper recorded:

```text
Killed
exit_rc=137
```

and correctly restored the PAPER runtime.

Kernel evidence proved a global OOM kill of PID `431849` (`shreks-fast-pro`) at approximately 11.57 GB anonymous RSS on a host with approximately 12 GB RAM and no swap:

```text
Out of memory: Killed process 431849 (shreks-fast-pro)
...
anon-rss:11569292kB
```

This was not an SSH disconnect, exporter timeout, disk-capacity failure, or SQLite mutation failure.

## Root cause

Before PR #273, `read_fast_training_feature_jsonl(...)` performed production-scale JSONL ingestion by:

1. calling `Path.read_bytes()` for the full feature file;
2. calling `splitlines()` over that full byte payload;
3. retaining every parsed JSON mapping in a Python list;
4. converting all mappings into a full tuple of `FastTrainingFeatureRecord` values;
5. retaining the original full raw bytes until dataset construction completed.

The logical fingerprint path then additionally materialized:

1. a complete canonicalized Python payload for every record;
2. one complete encoded canonical JSON byte string for the full dataset;
3. a SHA-256 over that full encoded payload.

The proof-workspace preparation path also retained the first parsed `FastTrainingFeatureDataset` while reopening the staged workspace strictly, allowing multiple complete record sets to overlap in memory.

At the physical production feature size of approximately 1.28 GB, these overlapping allocations exhausted host memory.

## Sealed correction

PR #273 makes the following narrow changes.

### 1. Streaming raw JSONL ingestion

`read_fast_training_feature_jsonl(...)` now opens the source in binary mode and reads one line at a time.

Each exact raw line is fed immediately into the source SHA-256 digest before parsing.

This preserves the exact source-file fingerprint semantics while removing the whole-file `read_bytes()` allocation.

### 2. Incremental row validation

Each JSON object is parsed and validated immediately.

Duplicate decision identity, canonical order, and strictly increasing sequence checks remain fail-closed and are applied incrementally while rows are consumed.

The implementation no longer retains a separate full list of parsed JSON mappings.

Only the final `FastTrainingFeatureRecord` values required by existing downstream interfaces are retained.

### 3. Streaming logical fingerprint

`feature_logical_fingerprint_sha256(...)` now feeds SHA-256 incrementally with bytes equivalent to the existing canonical JSON array:

```text
[
record_1_canonical_json,
record_2_canonical_json,
...
]
```

The existing canonicalization contract remains unchanged:

- dictionary keys remain sorted;
- separators remain compact;
- UTF-8 / `ensure_ascii=False` semantics remain unchanged;
- non-finite floats remain rejected;
- float values remain represented through the existing `__float_hex__` canonical form.

Regression coverage explicitly proves the new streamed fingerprint equals the legacy whole-payload fingerprint for the same records.

No fingerprint schema or identity has been intentionally changed.

### 4. Bounded proof-workspace dataset lifetime

`prepare_fast_proof_workspace(...)` now copies only the small scalar metadata needed for the manifest and explicitly releases the initial parsed feature dataset before staged strict reopen.

The staged verification artifact is released before the final post-rename strict reopen.

This prevents two or three full feature datasets from remaining resident simultaneously.

### 5. No temporary full bounds tuples

Feature sequence/timestamp bounds are now computed directly with generator expressions rather than allocating complete temporary sequence and timestamp tuples.

The manifest fields and their semantics are unchanged.

## TDD evidence

The correction was developed test-first.

RED PR CI run:

```text
34484041191
```

produced exactly the two intended failures while `3367` Python tests passed:

1. the feature reader still used whole-file `Path.read_bytes()`;
2. the initial parsed feature dataset was still alive at strict workspace reopen.

The fingerprint compatibility regression already passed in RED, proving that test itself was not dependent on the implementation change.

GREEN PR CI run:

```text
34484963024
```

passed all four required gates, including:

```text
3369 passed
```

for the Python suite.

Merged-main CI run:

```text
34486210750
```

also passed all four required gates.

## Unchanged contracts

This correction does **not** change:

- FL8.1 feature schema name or version;
- the seven sealed FastMarketState windows;
- bounded replay conflict-quarantine semantics;
- lifecycle canonicalization semantics;
- source JSONL SHA-256 semantics;
- logical feature fingerprint semantics;
- proof-workspace manifest schema;
- proof-workspace atomic publication rules;
- before/after database and WAL fingerprint checks;
- release-source SHA binding;
- proof-tool authentication;
- V2 physical cohort identity;
- V2 generalization member definitions;
- V2 natural TEST or unseen-mint TEST floors;
- training-economics authority;
- execution-cost policy authority;
- PAPER runtime authority;
- LIVE trading authority.

## Release authority

The merged implementation commit is **not itself an immutable release** because its subject begins with `fix:`.

The automatic release workflow correctly skipped the implementation commit after merged-main CI.

This docs-only `seal:` commit is the release authority candidate.

After this seal lands on `main`:

1. seal-main CI must pass Repository safety, Rust, Python, and ARM64;
2. automatic `Build sealed Shreks release` must build the exact seal SHA on `aarch64-unknown-linux-gnu`;
3. verify immutable release `shreks-<seal-sha>` with exactly three expected assets;
4. deploy that exact release through the protected `Deploy verified Shreks release` workflow to `production-paper`;
5. verify `/opt/shreks/current`, release manifest source SHA, service executable/working-directory identity, and restart counts;
6. verify filesystem headroom without deleting or mutating preserved `/var/lib/shreks` evidence;
7. stop `shreks.target` and wait for all proof-host members to reach terminal stop state;
8. preserve the known observer timeout as a recorded lifecycle defect and reset only failed bookkeeping after `MainPID=0` if the same exact timeout recurs;
9. require `shreks.target`, `shreks-observe.service`, `shreks-paper-evidence.service`, and `shreks-paper-campaign.service` to be exactly `inactive`;
10. require zero PAPER holders of the database, WAL, and SHM before creating a fresh proof run root;
11. create a **new** release-bound proof workspace using the exact deployed seal SHA and authenticated sealed proof tools;
12. require successful atomic workspace publication and strict readback before proceeding to V2 request construction;
13. authenticate the existing frozen physical V2 cohort;
14. create the matching training-economics overlay only from authoritative production parameters;
15. choose a new immutable V2 evidence destination;
16. create the canonical V2 host request binding the deployed release, workspace, database, cohort, hydration policy, training economics, execution-cost policy, and evidence destination;
17. execute one quiesced read-only V2 first-champion evidence attempt;
18. read back the immutable evidence artifact;
19. restore PAPER after the V2 command exits;
20. verify exact deployed-release runtime identity again;
21. freeze artifact fingerprints and counts before inspecting model/economic metrics.

The prior failed roots remain non-authoritative and must not be reused.

## Physical proof boundary

This code seal does **not** claim that the memory-bounded proof workspace has yet succeeded on the production database.

Physical acceptance still requires a fresh immutable ARM64 release and one fresh quiesced production attempt that proves at minimum:

```text
deployed_release_identity=PASS
proof_workspace_atomic_publication=PASS
proof_workspace_strict_readback=PASS
database_source_fingerprint_stable=PASS
physical_cohort_fingerprint_verified=YES
database_quiescence=PASS
database_data_version_stable=PASS
bundle_identity_reconciliation=PASS
v2_generalization_members=5
natural_test_floor_per_target=PASS
unseen_mint_test_floor_per_target=PASS
runtime_compatible_champion=CREATED_AND_VERIFIED
v2_evidence_artifact=CREATED_AND_VERIFIED
paper_runtime_restored=PASS
paper_promotion=BLOCKED
live_trading=DISABLED
```

A successful CI result is not a substitute for the physical production proof.

## Authority boundary

This seal authorizes only:

- creation of a new immutable ARM64 release;
- protected deployment of that exact release to `production-paper`;
- release-bound proof input generation;
- one fresh quiesced read-only FL9 V2 first-champion evidence attempt.

This seal does **not** authorize:

- learned-vs-deterministic superiority claims;
- PAPER champion promotion;
- action-policy promotion;
- risk or sizing promotion;
- registry promotion;
- transaction construction;
- signing;
- submission;
- LIVE trading.

Final authority remains:

```text
paper_promotion=BLOCKED
live_trading=DISABLED
```
