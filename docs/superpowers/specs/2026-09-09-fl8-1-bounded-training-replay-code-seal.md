# FL8.1 Bounded Training Replay — Code Seal

## Status

**SEALED IMPLEMENTATION CANDIDATE.**

This seal records the production-derived FL8.1 replay correction merged on `main` at:

```text
ec6f1ca6a5a01613b1bc765e92d4ae7ca5d626be
```

Implementation PR: **#271** — `fix: bound FL8.1 training replay to feature evidence windows`.

The exact PR head `2a713ce553d92269318a8dd6fcada9361b4507ab` passed all four required PR CI gates in run `34400417940`:

- Repository safety: PASS
- Rust tests: PASS
- Python tests: PASS
- ARM64 release build: PASS

The merged implementation commit `ec6f1ca6a5a01613b1bc765e92d4ae7ca5d626be` passed all four merged-main CI gates in run `34401708341`.

LIVE remains disabled. PAPER promotion remains blocked.

## Production blocker that forced this correction

The physical FL9 V2 first-champion proof attempt against immutable release:

```text
86070aa2f4906b194edb6a16680017df2a80fd97
```

failed before proof publication because the sealed FL8.1 exporter rejected a full-market replay with:

```text
FastEvent market replay blocked by 1 conflict-quarantined canonical identities
for venue 'pump_fun_bonding_curve'
```

The failed proof destination was never published. No V2 champion evidence artifact was created.

A separate capped execution of the exact sealed exporter reproduced the same fail-closed error before output creation.

## Read-only production localization

Read-only SQLite localization on the production observer database found:

- `pump_trade_evidence_conflicts=600`
- `pump_swap_trade_evidence_conflicts=1`
- 7 canonical FastEvent identities intersect the conflict tables
- only 2 of those canonical conflicts belong to markets that contain V1 FL4 training decisions

For both affected V1 training markets:

- the quarantined canonical identity is **not** a V1 decision;
- the quarantined canonical identity is **not** a V1 endpoint;
- the market contains exactly one V1 decision;
- the quarantined identity occurs far before the decision:
  - 138,014,254 ms before one decision;
  - 127,605,647 ms before the other decision;
- the sealed maximum FastMarketState feature window is only 10,000 ms.

Therefore those quarantined identities cannot contribute to any sealed FL8.1 feature value for the relevant decisions.

The production conflict rows remain preserved and unresolved. This correction does not delete, rewrite, accept, suppress, or reclassify them.

## Root cause

Before PR #271, `fast_training_feature_records` grouped FL4 decisions by market and called:

```text
fast_events_for_market_with_reserve_context(...)
```

That path delegates to unbounded `fast_events_for_market(...)`, whose quarantine fence rejects the entire market if **any** canonical identity in that market appears in the venue conflict table.

That contract is correct for unbounded trusted market replay, but it is too broad for FL8.1 point-in-time feature generation because `FastMarketState` only retains the sealed default rolling windows:

```text
100, 250, 500, 1000, 2000, 5000, 10000 ms
```

An unrelated quarantined FastEvent outside every required decision lookback interval cannot influence a training snapshot.

## Sealed correction

PR #271 made the following narrow changes.

### 1. Bounded reserve-context replay

`ShreksDb` now exposes:

```text
fast_events_for_market_observed_window_with_reserve_context(...)
```

It delegates quarantine selection to the already-sealed bounded replay:

```text
fast_events_for_market_observed_window(...)
```

and then reconstructs reserve context through the same immutable raw venue evidence used by full-history replay.

Full-history reserve-context replay remains unchanged for all existing callers.

### 2. Exact FL8.1 feature evidence intervals

For each FL4 training decision, FL8.1 derives the inclusive evidence interval:

```text
[max(0, decision_observed_at_unix_ms - 10000),
 decision_observed_at_unix_ms]
```

Intervals are sorted and only overlapping or touching intervals are merged.

This intentionally preserves gaps between widely separated decisions. A quarantined event inside an irrelevant gap does not poison either independent feature snapshot.

### 3. Existing FastMarketState remains the feature calculator

The correction does not reimplement rolling feature logic.

All returned bounded FastEvents are still replayed through the existing sealed:

```text
FastMarketState::with_default_windows
```

The exact feature schema and exact seven default windows remain unchanged.

### 4. Conflict quarantine remains fail-closed where evidence is relevant

A conflict-quarantined canonical identity inside any required FL8.1 feature evidence interval still causes the bounded replay to fail closed.

No caller receives ambiguous event economics as trusted feature evidence.

### 5. Lifecycle semantics remain unchanged

Lifecycle evidence continues to be loaded and canonicalized independently from the trade replay.

The earlier lifecycle exact-semantic duplicate canonicalization and substantive same-time disagreement fail-closed behavior remain unchanged.

## Regression coverage

The implementation adds focused Rust coverage proving:

1. a conflict before the required feature interval does not poison export;
2. a conflict in an irrelevant gap between widely separated decision intervals does not poison export;
3. a conflict inside the required 10-second feature interval still fails closed;
4. existing early-timestamp fixtures remain valid by clamping the lower bound to zero;
5. existing deterministic exporter, lifecycle, reserve-context, Rust workspace, Python integration, and ARM64 build coverage remain GREEN.

## Release authority

The merged implementation commit is **not itself an immutable release**, because its commit subject begins with `fix:`. The automatic release workflow correctly skipped run `34401945928`.

This docs-only `seal:` commit is the release authority candidate.

After this seal lands on `main`:

1. seal-main CI must pass Repository safety, Rust, Python, and ARM64;
2. automatic `Build sealed Shreks release` must build the exact seal SHA;
3. verify immutable release `shreks-<seal-sha>` with exactly three assets;
4. deploy that exact release through the protected `Deploy verified Shreks release` workflow to `production-paper`;
5. verify `/opt/shreks/current`, manifest source SHA, service executable/working-directory identity, and restart counts;
6. only then create a **fresh** FL9 V2 proof run root and rerun the quiesced release-bound proof workspace.

The failed proof root under release `86070aa2f4906b194edb6a16680017df2a80fd97` remains non-authoritative and must not be reused.

## Physical proof boundary

This code seal does **not** claim that the corrected exporter has yet succeeded on the production database.

Physical acceptance still requires a new immutable ARM64 release and one fresh quiesced read-only proof run that proves:

- exact release binding;
- database/WAL immutability across export;
- stable SQLite `data_version` in the V2 host runner;
- exact frozen V2 cohort authentication;
- matching training-economics overlay identity;
- 5 V2 generalization members;
- natural TEST floor per target;
- unseen-mint TEST floor per target;
- runtime-compatible champion creation;
- immutable V2 evidence publication;
- PAPER runtime restoration.

## Authority boundary

This seal does not authorize:

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
