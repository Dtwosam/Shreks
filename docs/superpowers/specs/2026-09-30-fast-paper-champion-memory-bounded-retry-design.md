# Fast PAPER Champion Bootstrap Memory-Bounded Retry Design

**Date:** 2026-09-30  
**Base main SHA:** `cf991001d3a569c1629899a77708d3c9c8269834`  
**Status:** IMPLEMENTATION DESIGN ONLY; RETRY AUTHORITY NOT GRANTED

## Incident

The one explicit forecast-champion bootstrap attempt authorized by the
2026-09-29 bootstrap authority seal was invoked on the protected production
host and was therefore consumed.

The request fingerprint was:

`63b246ddf209491fdd086e1b5808dedf7d1631bd39ba0a9c8df325e626f3c71a`

The process was killed by the host OOM killer before a host-run artifact was
published. Physical resource evidence showed approximately:

- 11.3 GiB peak resident memory;
- 7.8 GiB peak swap use from an 8 GiB temporary swapfile;
- no published first-champion host-run;
- automatic restoration of the legacy PAPER observer, evidence collector, and
  campaign services;
- Fast PAPER shadow still inactive.

The failed invocation does **not** create retry authority. The prior seal states
that authority is consumed when the runner is invoked and that failure requires
a separate reviewed retry decision.

## Root cause

The existing first-champion path materializes several large authenticated
populations in Python at the same time:

1. the complete proof-workspace feature dataset;
2. every future-path horizon for the label version;
3. every training-economics row for the label version;
4. provenance maps, projected labels, and counterfactual outcomes;
5. repeated logical bundles across host planning, preparation, and the nested
   file-backed champion runner.

The protected economics artifact contains 2,037,662 rows while the bootstrap
trains exactly one requested horizon. Retaining all horizons is unnecessary for
the selected forecast target and was the dominant avoidable memory multiplier.

## Design

The generic score-free first-champion path gains an explicit memory-bounded
mode when the caller supplies its already-required `horizon_ms`.

The bounded path:

1. strictly authenticates the complete training-economics overlay and its
   manifest while retaining only rows for the requested horizon and label
   version;
2. derives the exact selected decision population from those authenticated
   horizon rows;
3. streams the immutable feature JSONL, validates canonical ordering and
   duplicate identity rules, verifies the full source-file SHA-256, and retains
   only the selected decision identities;
4. loads canonical FL4 labels only for the selected identities, horizon, and
   label version;
5. requires exact selected-population equality among features, FL4 labels,
   economics rows, and canonical counterfactual provenance;
6. preserves the existing execution-cost projection and counterfactual labeling
   semantics;
7. preserves the existing training, chronological validation, TEST evaluation,
   five forecast targets, model families, champion codec, and fingerprinted
   artifact chain;
8. explicitly releases a host-stage logical bundle before entering preparation;
9. explicitly releases the preparation-stage logical bundle immediately after
   hydration publication and before reopening hydration / entering the nested
   file-backed champion run;
10. verifies proof workspaces through a streaming manifest-bounded reader that
    authenticates the full feature source without retaining the full feature
    dataset.

The historical full-population runtime-bundle behavior remains available when
no horizon is supplied. The first-champion host/preparation/file-run path
supplies the explicit requested horizon.

## Evidence semantics

This change is a resource-bound implementation change, not a policy change.

It does not change:

- the frozen proof feature bytes;
- the authenticated training-economics bytes;
- future-path label version;
- counterfactual base quantity;
- requested forecast horizon;
- chronological evidence floors;
- TEST evaluation policy;
- forecast targets or model families;
- training policy;
- execution-cost policy;
- champion schema;
- score-free decision architecture.

The bounded logical bundle contains exactly the identities for which the pinned
economics artifact has the requested horizon. The complete economics artifact
remains authenticated, including its full feature-source SHA-256 and original
future-path fingerprint. Each retained economics row is then matched against
the exact canonical FL4 row and canonical source provenance for that selected
identity.

## Proof requirements

Before this implementation can support a physical retry, repository proof must
show at minimum:

- bounded proof-reader parity with the existing strict manifest;
- bounded proof verification does not materialize the complete feature dataset;
- bounded feature selection authenticates the full source SHA-256 and returns
  exactly the requested identities;
- horizon-bounded runtime bundle construction does not invoke the historical
  full feature, full FL4, or full economics materializers;
- bounded selected-population joins still fail closed on missing, duplicate, or
  mismatched evidence;
- host and preparation chain fingerprints remain cross-bound;
- large bundle objects are not intentionally retained across nested
  first-champion stages;
- existing unbounded runtime-bundle callers keep their historical behavior;
- repository safety, Python, Rust, and ARM64 release gates are green.

## Retry authority boundary

Merging, sealing, releasing, or deploying the memory-bounded implementation
does not by itself authorize another champion invocation.

A later separately reviewed retry seal must bind:

- the exact deployed retry-capable release SHA;
- the preserved OOM incident evidence;
- continued absence of a canonical forecast champion;
- one fresh current-release proof workspace;
- one fresh current-release hydration policy;
- one authenticated training-economics overlay and execution-cost policy;
- one fresh canonical host request;
- an absent host-run destination and absent staging residue;
- explicit host memory/disk headroom;
- exactly one retry invocation.

A failed retry would again fail closed and would require another separately
reviewed authority decision. No automatic retry loop is permitted.

## Authority state

After the OOM and before any later retry seal:

```text
FAST_LANE_FORECAST_CHAMPION_PHYSICAL_PRESENCE=ABSENT
FAST_CHAMPION_BOOTSTRAP_AUTHORITY=CONSUMED_FAILED_OOM
SCORING_CONTROL_PATH=FORBIDDEN
LEGACY_SCORE_PAPER_RUNTIME=UNCHANGED_TEMPORARY_AUTHORITY
FAST_PAPER_SHADOW_START_AUTHORITY=NOT_GRANTED
FAST_PAPER_CUTOVER_AUTHORITY=NOT_GRANTED
AUTOMATIC_CHAMPION_PROMOTION=DISABLED
SIGNING_SUBMISSION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```

This implementation adds no scoring authority, PAPER cutover authority,
signing/submission authority, or LIVE authority.
