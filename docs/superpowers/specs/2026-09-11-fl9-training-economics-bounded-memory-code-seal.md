# FL9 Training Economics Bounded Memory — Code Seal

## Status

**SEALED IMPLEMENTATION CANDIDATE.**

This seal records the production-derived FL9 training-economics memory correction merged on `main` at:

```text
35ebf2134cf60d81c14caf59b336a28fb3b89ed8
```

Implementation PR: **#275** — `fix: bound FL9 training economics memory`.

The exact final PR head:

```text
ffc59543d63fcbbab39bb707edd7952c403bf2d3
```

passed all required PR CI gates in run:

```text
34580727818
```

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

The merged implementation commit passed all four merged-main CI gates in run:

```text
34582476947
```

LIVE remains disabled. PAPER promotion remains blocked.

## Production failure that required this correction

The prior sealed release:

```text
shreks-48b4973bd840d76aef8192b84e2f5bae87aa8675
```

successfully completed the fresh physical proof workspace, but the subsequent quiesced training-economics export was globally OOM-killed before publishing an immutable economics artifact.

Kernel evidence recorded the exporter at approximately 11.58 GB anonymous RSS:

```text
Out of memory: Killed process 441576 (shreks-observe)
anon-rss:11582456kB
```

No `training-economics/rows.jsonl` or `training-economics/manifest.json` was published from that failed attempt. The failed evidence remains preserved and must not be reused as successful evidence.

PAPER was restored after the failed exporter. No V2 champion scoring, PAPER promotion, transaction construction/signing/submission, or LIVE activation occurred.

## Root cause

The production exporter combined two unbounded behaviors:

1. reserve-aware economics replay loaded complete PumpSwap market histories while chronological labels repeatedly switched between markets;
2. immutable artifact generation overlapped whole-file feature bytes, decoded feature populations, FL4 label/output populations, and a complete in-memory `rows.jsonl` buffer.

The production dataset proved those lifetimes were sufficient to exhaust the approximately 12 GB host.

## Sealed correction

The implementation preserves external economics semantics and authority while bounding the physical path:

- reserve reconstruction uses the existing bounded decision-to-endpoint reserve-aware replay primitive instead of full-market replay;
- unrelated quarantined PumpSwap history outside the canonical decision/endpoint evidence interval no longer poisons the row;
- canonical decision and endpoint conflict quarantine remains fail-closed;
- `features.jsonl` is streamed through a buffered reader while hashing exact source bytes;
- feature population identity is checked in deterministic FL4 decision order without retaining a second full feature population;
- economics rows are emitted directly to staged `rows.jsonl` while the ordered row fingerprint and status counts are updated incrementally;
- the future-path logical fingerprint is reproduced incrementally in the same canonical JSON array byte shape;
- manifest generation, staging cleanup, no-overwrite behavior, file sync, and atomic directory rename remain intact.

No trading, PAPER promotion, transaction, signing, submission, LIVE, schema, CLI, or systemd authority was expanded.

## Regression proof

The implementation was developed test-first.

The reserve-replay RED regression proved that the old implementation failed when an unrelated earlier PumpSwap source was conflict-quarantined. The bounded replay correction made that regression GREEN while existing canonical conflict tests remained fail-closed.

A second RED regression proved the writer still contained whole-file feature and whole-output buffering. The final implementation removed those complete-file buffers and added parity assertions proving:

- streamed feature SHA-256 equals exact source-file SHA-256;
- streamed future-path logical fingerprint equals the legacy canonical fingerprint;
- immutable writer output remains exactly two files and never overwrites an existing destination.

## Authorized physical continuation

After this seal lands and its automatic immutable ARM64 release succeeds, the next bounded physical sequence is:

1. verify immutable release `shreks-<seal-sha>` with exactly the expected release assets;
2. deploy that exact release through the protected `production-paper` workflow;
3. verify `/opt/shreks/current`, release manifest, service executable/cwd identities, and runtime health;
4. stop the PAPER target and enforce the exact four-unit inactive gate;
5. verify zero unexpected database/WAL holders;
6. create a brand-new release-bound FL9 V2 proof run root;
7. generate and strictly read back a fresh proof workspace;
8. generate fresh training-economics evidence with counterfactual base quantity `2`, PumpSwap fee maximum age `60000` ms, and future-path label version `1`;
9. require immutable economics publication and strict manifest/fingerprint readback before any V2 request is created;
10. continue the existing V2 first-champion runbook only after all prior gates pass;
11. restore PAPER on every failure path.

The new physical run must not reuse any failed run root, staging directory, or failed economics artifact.

## Safety boundary

This seal does **not** authorize PAPER promotion or LIVE trading. It does not authorize transaction construction, signing, or submission. It only authorizes a fresh quiesced read-only physical evidence attempt on the new immutable release under the existing V2 runbook and fail-closed gates.
