# FL9 V2 Bounded Economics Reader — Code Seal

## Status

**SEALED IMPLEMENTATION CANDIDATE.**

This seal records the production-derived FL9 V2 economics-reader correction merged on `main` at:

```text
bf74a74e2a6bbedf898f0e21c56e09f5427318cb
```

Implementation PR: **#277** — `fix: bound FL9 V2 economics reads`.

The exact final PR head:

```text
793b8029d70a7288f1c65c86086e6610821f1dcf
```

passed all required PR CI gates in run:

```text
34649148669
```

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

The merged implementation commit passed all four merged-main CI gates in run:

```text
34649454712
```

LIVE remains disabled. PAPER promotion remains blocked.

## Production condition that required this correction

The prior sealed release `shreks-31a4ace537fedb38ce37d21cb5f9fb8a4cee0dbf` successfully produced the full immutable training-economics overlay:

```text
row_count: 1763328
rows.jsonl bytes: 2190070355
manifest_fingerprint_sha256: 0937b39800c05cab7b4927b12fa62b74e691f6983659209a0ce1cbd4402737ea
feature_source_jsonl_sha256: 1295a4ddadb501850e9dd651648702381fbf0b4334ad2b4765c0d4904ea7c7ef
```

The Rust exporter remained physically bounded at about 21 MB RSS, proving the exporter correction. The next sealed Python V2 path, however, called `Path.read_bytes()` on the complete 2.19 GB `rows.jsonl` and then retained every decoded economics row in a tuple. That recreated a multi-GB memory-risk boundary immediately after the bounded Rust export.

No V2 champion scoring was attempted through that unbounded reader. No PAPER promotion, transaction construction/signing/submission, or LIVE activation occurred.

## Root cause

The generic Python economics reader authenticated the artifact by first materializing the complete raw JSONL bytes, then splitting and decoding all rows, then retaining the complete decoded population. The V2 host request, host preflight, and bundle path each invoked that full reader even when they only needed manifest authentication or the frozen 30,000 ms horizon.

## Sealed correction

The implementation preserves the economics artifact schema and semantic validation while bounding the V2 physical path:

- row bytes are streamed once from `rows.jsonl` while the exact raw-byte SHA-256 is updated incrementally;
- every row is still decoded and subjected to exact schema, provenance, canonical-order, status-count, timestamp-range, label-version, quantity, duplicate-identity, and manifest reconciliation checks;
- validation-only callers retain no economics rows;
- the V2 bundle retains only rows for the frozen V2 horizon and requested label version;
- duplicate detection keeps decision-level state plus immediate row identity rather than a full 1.76M-row identity set;
- the legacy full reader remains available for callers that explicitly require the entire dataset;
- V2 request creation and host preflight now use validation-only scans;
- V2 bundle construction uses the filtered horizon reader.

No artifact schema, economics output, cohort authority, model policy, evaluation policy, trading authority, PAPER promotion, transaction, signing, submission, LIVE, CLI, database, or systemd contract is expanded.

## Regression proof

The correction was developed test-first.

RED regressions proved that the V2 production path still depended on the full materializing reader and that the streaming APIs were absent. The final GREEN implementation adds contract coverage requiring:

- no `Path.read_bytes()` in the streaming scanner;
- validation-only scans to preserve full artifact authentication while retaining no row population;
- horizon-filtered scans to preserve full artifact authentication while retaining only the requested V2 horizon;
- V2 request/host paths to use validation-only authentication;
- V2 bundle construction to use the horizon-filtered reader.

Local Python-only verification completed with 34 tests passing and one Rust-backed fixture intentionally deselected because the Mac has no Cargo toolchain. PR and merged-main CI supplied the authoritative Rust, Python, repository-safety, and native ARM64 verification.

## Authorized physical continuation

After this seal lands and the automatic immutable ARM64 release succeeds, the next bounded physical sequence is:

1. verify immutable release `shreks-<seal-sha>` and exact release assets;
2. deploy that exact release through the protected `production-paper` workflow;
3. verify `/opt/shreks/current`, release manifest, service executable/cwd identities, runtime health, and zero failed units;
4. stop PAPER plus telemetry for the read-only proof boundary and verify zero unexpected SQLite/WAL/SHM holders;
5. reuse the already-published immutable economics artifact only after strict source/fingerprint checks bind it to the preserved successful proof workspace and current V2 frozen cohort authority;
6. run the new validation-only reader against the complete 2.19 GB artifact while observing physical memory;
7. run the horizon-filtered reader for the frozen 30,000 ms V2 horizon while observing physical memory and verifying the selected row population;
8. create a canonical V2 host request only if every explicit hydration, evaluation, version, and execution-cost input is production-authoritative under existing source-of-truth rules;
9. run exactly one authorized V2 first-champion evidence attempt if all gates pass;
10. strictly read back immutable V2 evidence before any interpretation or promotion decision;
11. restore PAPER and telemetry on every success or failure path.

The completed economics artifact must not be regenerated merely because the reader release changed: it is immutable data produced by the prior sealed exporter and may be reused only if its full fingerprints and source bindings still authenticate exactly.

## Safety boundary

This seal does **not** authorize PAPER promotion or LIVE trading. It does not authorize transaction construction, signing, or submission. It authorizes only deployment of the bounded Python read path and continuation of the existing read-only V2 evidence runbook under fail-closed gates.

## Release trigger correction

The first documentation-seal merge commit `61e482bd74f9c9f1c4c083e6684d2bba0bea2ebf` used a merge-commit subject and was therefore correctly skipped by the automatic release workflow. This follow-up documentation-only seal exists solely to produce the repository-required `seal:` main subject; it changes no implementation semantics or authority.
