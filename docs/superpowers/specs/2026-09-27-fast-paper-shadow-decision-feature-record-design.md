# Fast PAPER Shadow Decision Embedded Feature Record — Design

**Date:** 2026-09-27  
**Base main SHA:** `cfc60f9bad46dd66f7f4e0bec3915defe54cfe10`

## Purpose

Make each durable learned shadow decision self-contained for later execution-
authority composition.

The current v2 decision artifact seals only the logical fingerprint of the
canonical `FastTrainingFeatureRecord`. That proves identity, but after the
decision cursor advances the runtime feature feed cannot safely replay that row
without the exact prior feed cursor. The execution checkpoint intentionally
does not retain the full feature-feed cursor.

Persist the exact point-in-time feature row inside the already write-once
decision artifact before the decision cursor advances.

This slice does not derive BUY authority, write BUY-authority sources, publish
execution inputs, or execute PAPER.

## Schema

Advance:

`shreks.fast_paper_shadow_decision` from version `2` to version `3`.

Add one required top-level field:

`feature_record`

It is the canonical JSON-compatible representation of the exact
`FastTrainingFeatureRecord` used by learned inference.

Keep:

`feature_record_fingerprint_sha256`

as the logical one-record fingerprint:

`feature_logical_fingerprint_sha256((feature_record,))`.

## Construction

`evaluate_fast_paper_shadow_decision(...)` must:

1. require exact `FastTrainingFeatureRecord`;
2. retain the exact feature row in the returned decision evidence;
3. compute the existing feature fingerprint from that same exact row;
4. include the canonical feature row in the outer decision-evidence
   fingerprint.

No feature reconstruction or alternate mapping is allowed.

## Encoding and reading

The writer must encode the embedded row using the same canonical logical shape
used by Fast Lane training/runtime feature records.

The reader must decode only through
`fast_training_feature_record_from_mapping(...)`.

On read and dataclass validation require:

- embedded feature logical fingerprint equals the sealed feature fingerprint;
- source event id equals
  `decision_signature:decision_ordinal`;
- source sequence equals `decision_sequence`;
- as-of timestamp equals `decision_observed_at_unix_ms`;
- market key equals `venue:mint:quote_mint`;
- decision entry reference identity remains consistent with the embedded row.

Unknown/missing feature fields, malformed nested feature evidence, non-finite
numbers, duplicate JSON keys, canonical-JSON drift, or feature tampering fail
closed.

## Restart boundary

The existing commit ordering remains:

`decision evidence durable -> decision cursor advance`.

Therefore once the cursor advances, the exact feature row needed by a later
BUY-authority writer is already durable in the authenticated decision artifact.

Existing replay behavior remains idempotent and must require the supplied
feature row to equal the embedded feature row as well as its fingerprint.

## Authority boundary

```text
FEATURE_ROW_DURABILITY=WRITE_ONCE_DECISION_EVIDENCE
FEATURE_SEMANTICS=UNCHANGED_CANONICAL_FAST_LANE
LEARNED_INFERENCE=UNCHANGED
BUY_AUTHORITY_DERIVATION=NOT_GRANTED
BUY_AUTHORITY_WRITE=NOT_GRANTED
EXECUTION_SOURCE_PUBLICATION=NOT_GRANTED
PAPER_EXECUTION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
PROVIDER_NETWORK_ACCESS=FORBIDDEN
SCORING_CONTROL_PATH=FORBIDDEN
FUTURE_LABELS_COUNTERFACTUALS=FORBIDDEN
LIVE=DISABLED
```

## RED acceptance

Intentional RED tests require:

- decision schema version 3;
- exact embedded feature row on newly evaluated evidence;
- canonical write/read round trip preserves the exact row;
- embedded row participates in outer evidence fingerprint;
- reader rejects a feature-row/fingerprint mismatch;
- restart replay rejects any supplied feature-row drift.

Current main is expected to fail only the new feature-record contract because
v2 evidence does not yet embed the row.

## Following slice

Add the write-once BUY-authority writer cycle. It can now select the oldest
unexecuted BUY, read the exact embedded feature row from the authenticated
decision evidence, invoke the persisted-evidence adapter, and publish the
existing BUY-authority source record with exact collision read-back.
