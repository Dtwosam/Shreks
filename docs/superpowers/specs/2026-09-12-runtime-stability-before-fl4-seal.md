# Runtime Stability Before FL4 Backfill — Code Seal

## Status

**SEALED RUNTIME-STABILITY CANDIDATE.**

This seal records runtime-stability implementation PR **#282**, merged on `main` at:

```text
6bf22c4bdbe63044657cb6b2c7ce29911b1374e5
```

The exact implementation PR head was:

```text
1f36b1f5361047cb5059d31af771c87ef6fce2ed
```

PR CI run `34711009214` passed Repository safety, Rust tests, Python tests, and the native ARM64 release build. The merged implementation commit passed the same four gates in main CI run `34711202206`.

LIVE remains disabled. No FL4 production labels were changed by this implementation or its verification.

## Production condition requiring this repair

After deployment of the prior sealed FL4 cohort-backfill release, production diagnostics showed three runtime-stability failures before the historical backfill could safely run:

- the observer repeatedly restarted after the single authorized `SolanaPublic` realtime lane returned `InvalidResponse` beyond its former outer reconnect bound;
- Python PAPER checkpoint persistence failed on transient SQLite `database is locked` contention;
- PAPER evidence collection failed on transient SQLite `DatabaseBusy` contention at storage boundaries.

PAPER campaign bootstrap itself repeatedly reached `READY`; the observed failures occurred after bootstrap during runtime operation. The FL4 backfill therefore remained on HOLD.

## Sealed correction

The merged implementation makes only these bounded runtime changes:

- malformed `SolanaPublic` responses remain rejected as evidence, but the same authorized public lane rebuilds and reconnects instead of restarting the entire observer after a finite malformed-response burst;
- no paid-provider or alternate realtime fallback is introduced;
- ordinary persistent public-provider unavailability retains its existing bounded fail-closed behavior;
- Python PAPER checkpoint writes receive exactly one additional retry for SQLite `BUSY`/`LOCKED`, with a 250 ms application retry delay and no change to the existing SQLite timeout;
- persistent checkpoint contention remains fail-closed;
- PAPER safety-evidence storage calls reuse the existing Rust two-attempt SQLite `BUSY`/`LOCKED` retry helper;
- provider requests are not repeated by the PAPER evidence storage retry.

No database schema, strategy, score, model policy, risk policy, PAPER economics, signer, transaction builder, submission path, or LIVE authority is changed.

## Verification proof

The repair was developed test-first:

- a Rust regression reproduced termination of the public realtime lane after malformed responses exceeded the former outer bound, then passed after the same-source recovery change;
- a Python regression held a real `BEGIN IMMEDIATE` lock beyond the existing five-second busy timeout and reproduced `PaperCheckpointError: database is locked`, then passed with the bounded retry;
- a companion Python regression proves persistent checkpoint contention still fails closed and creates no checkpoint;
- a Rust regression held a real SQLite writer lock beyond the busy timeout and reproduced `DatabaseBusy` in `SafetyEvidenceCollector`, then passed after storage-only retry was added;
- existing persistent public-unavailability fail-closed coverage remains green.

The final implementation head and merged-main commit both passed all four canonical CI lanes.

## Authorized physical continuation

After this seal lands and its immutable ARM64 release succeeds, the authorized continuation is:

1. verify the immutable `shreks-<seal-sha>` release and release assets;
2. deploy that exact release through the protected production-paper deployment workflow;
3. verify `/opt/shreks/current` and `RELEASE_MANIFEST.json` resolve to the exact seal SHA;
4. verify observer, PAPER evidence, and PAPER campaign service executable/cwd identities and restart counters;
5. inspect fresh service journals and prove the observer is not in a `SolanaPublic InvalidResponse` restart storm, PAPER evidence is not failing on SQLite contention, and the PAPER campaign remains operational;
6. rerun the frozen-cohort/FL4 preflight read-only checks;
7. only if all runtime and release gates are clean, continue the previously sealed quiesce-and-backfill procedure for the frozen 274,334-decision FL9 V2 cohort.

Any release-identity drift, repeated service restart, unresolved SQLite contention, campaign failure, cohort fingerprint mismatch, source-session drift, unexpected database writer, or prestate count drift is a HOLD.

## Safety boundary

This seal does **not** authorize PAPER promotion or LIVE trading. It does not authorize transaction construction, signing, or submission. It authorizes only release/deployment of the runtime-stability repair, production PAPER health verification, and—only after those gates pass—resumption of the already sealed historical FL4 cohort-backfill procedure.
