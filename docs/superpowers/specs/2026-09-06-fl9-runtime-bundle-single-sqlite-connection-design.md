# FL9 Runtime-Bundle Single SQLite Connection Design

**Date:** 2026-09-06  
**Scope:** first-champion runtime bundle provenance validation performance only  
**Base seal:** `9897aae031be4690562662558cc7be4208ec4796`

## Problem

The real 2,560-decision first-champion planner reached runtime-bundle assembly with 30,720 FL4 decision/horizon rows. The current runtime builder calls `load_entry_counterfactual_from_sqlite(...)` once per row. That loader opens and closes a read-only SQLite connection for every lookup.

Physical VPS evidence showed the planner at ~100% CPU for more than 80 minutes while PAPER was intentionally quiesced. The authenticated feature workspace and training-economics v3 overlay had already completed successfully. The planner was aborted cleanly before any champion artifact existed.

The canonical database had a ~1.97 GB WAL during the run. Reopening SQLite 30,720 times is unnecessary and dominates this slice.

## Invariants

This change must not weaken any source validation:

- canonical FL4 decision and endpoint joins remain exact;
- conflict-quarantined decision/endpoint sources still fail closed;
- execution-economics presence checks remain exact;
- missing canonical rows still fail closed;
- the database remains read-only;
- runtime target projection remains in-memory only;
- no PAPER/LIVE authority is added;
- the fresh cohort floor and all predeclared first-champion policies are unchanged.

## Design

Add one batch provenance loader in `research.counterfactual_source`.

It:

1. accepts an explicit non-empty tuple of unique canonical lookup identities;
2. validates each identity with the existing lookup validator;
3. opens exactly one read-only SQLite connection;
4. calls the existing provenance loader for every identity while passing that shared connection;
5. closes the shared connection in a `finally` block;
6. returns one provenance object per requested identity.

The existing single-row public loaders retain their current behavior and still own one connection per standalone call.

The private provenance loader gains an optional already-open connection. It only closes a connection it opened itself.

`build_fast_training_bundle_from_runtime_sources(...)` batch-loads provenance for the already-authenticated FL4 key population once, then performs the same per-row equality checks against the returned provenance.

## Tests

Add regression coverage proving:

- the batch loader reuses one connection across multiple requested identities;
- duplicate batch identities fail closed before source processing;
- the runtime bundle opens the counterfactual-source database exactly once for the mixed authenticated fixture;
- existing counterfactual source read-only, canonical-identity, conflict-quarantine, and runtime-bundle logical-evidence tests remain unchanged and GREEN.

## Non-goals

- no schema/index migration;
- no new cache;
- no change to training economics;
- no change to first-champion thresholds, horizon, selection logic, or model families;
- no champion construction or promotion;
- no LIVE enablement.
