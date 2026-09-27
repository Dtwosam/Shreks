# Fast Lane FL11.2b Missed-Opportunity Proof — Design

**Date:** 2026-09-28  
**Base main SHA:** `269553024f8c0c8665630f0ef8d9074ad1601ce0`

## Purpose

Complete the remaining required FL11.2 economics item: missed-opportunity cost.

FL11.2a already reports executed closed-trade economics, cost burden, capacity,
expected-versus-realized value, entry efficiency, exit timing, and
strategy/regime/horizon performance. FL11.2b evaluates only learned-shadow
`SKIP` decisions against independently produced canonical FL4 future-path
labels.

This is hindsight evaluation evidence. It must never feed future information
back into the decision runtime.

## Inputs

The read-only CLI consumes:

- the exact Fast PAPER runtime manifest;
- the exact isolated shadow ledger path and run id, only to authenticate the
  FL11.1 binding;
- the learned-shadow decision-evidence directory;
- the canonical FL11.1 sample-proof JSON;
- the exact release SHA and evidence window;
- an explicit FL4 future-path label version.

The FL4 SQLite source is the manifest-pinned observer database. A caller cannot
substitute a different future-path database.

## FL11.1 prerequisite

The FL11.1 proof must:

- be canonical and fingerprint-valid;
- say `SUFFICIENT_SAMPLE`;
- match the exact release, manifest, champion, action-policy, ledger binding,
  and requested window;
- have the same decision count as the authenticated learned-shadow decision
  population selected for the window.

## SKIP population

Only authenticated learned decisions with:

```text
action=SKIP
position.kind=FLAT
```

are evaluated as missed entry opportunities.

Each SKIP uses the exact `FastTrainingFeatureRecord.decision_identity` carried
inside immutable decision evidence.

The evaluated horizons are exactly
`manifest.action_policy.horizons_ms`. No caller-selected horizon subset is
allowed, preventing hindsight cherry-picking.

## Future-path evidence

For each policy horizon, use the existing
`load_future_path_training_labels_for_identities_from_sqlite(...)` loader.

That loader already fails closed on:

- missing requested identities;
- duplicate labels;
- decision/endpoint mismatch with canonical FastEvents;
- conflict-quarantined sources;
- malformed completeness/coverage semantics.

FL11.2b does not rebuild FL4 labels.

## Scoring one SKIP/horizon

A SKIP/horizon is **scorable** only when:

1. the FL4 label is `complete`; and
2. either:
   - `no_trade_events=true`, which is an explicit zero missed opportunity; or
   - `best_cost_adjusted_return_bps` is present.

For a scorable label:

```text
missed_opportunity_bps = max(0, best_cost_adjusted_return_bps)
```

For a complete `no_trade_events` label the value is exactly zero.

Incomplete labels or complete labels lacking cost-adjusted execution economics
remain unavailable. They are counted explicitly and are never imputed as zero.

## Cross-horizon missed opportunity

A SKIP receives a single hindsight
`best_missed_opportunity_bps_across_policy_horizons` only if **every** policy
horizon is scorable.

The value is the maximum non-negative missed-opportunity value across policy
horizons. Ties choose the shortest horizon deterministically.

If even one policy horizon is unavailable, the cross-horizon value is
`null`. This prevents partial future coverage from understating the missed
opportunity.

## Report

The report contains:

- authenticated decision and SKIP counts;
- policy horizons and FL4 label version;
- per-horizon completeness/scorability counts;
- per-horizon missed-opportunity distribution;
- fully scorable versus partially/unscorable SKIP counts;
- positive missed-opportunity count/rate;
- p50/p95/mean/max best missed opportunity among fully scorable SKIPs;
- deterministic per-SKIP audit rows;
- canonical FL4 dataset fingerprints per horizon.

The report is descriptive. It does not set a promotion threshold.

## Authority firewall

The module is read-only and contains no:

- Fast PAPER execution or ledger mutation;
- future-path label creation/backfill;
- champion/registry mutation;
- scoring control path;
- provider/network client;
- systemd mutation;
- signing/submission;
- LIVE mode.

Every report records:

```text
promotion_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Acceptance

Repository tests must prove:

1. exact matching FL11.1 `SUFFICIENT_SAMPLE` is mandatory;
2. decision count reconciles with FL11.1;
3. SKIPs use exact immutable feature identities;
4. evaluation horizons equal the runtime action-policy horizons;
5. complete cost-adjusted labels produce non-negative missed-opportunity bps;
6. complete no-trade labels produce explicit zero;
7. negative cost-adjusted paths produce zero missed opportunity;
8. incomplete or economics-missing horizons remain unavailable;
9. a cross-horizon best value exists only with complete scorable horizon
   coverage;
10. canonical FL4 loader failures propagate fail-closed;
11. report/future-label fingerprints are deterministic;
12. no promotion/PAPER cutover/signing/LIVE authority is added;
13. Python, Rust, repository-safety, and ARM64 release gates stay green.

## FL11.2 exit after this slice

Together, FL11.2a + FL11.2b provide every economics item explicitly required by
the repository build order. A later composition/readiness proof may bind the two
reports before FL11.3 latency proof begins.

LIVE remains disabled.
