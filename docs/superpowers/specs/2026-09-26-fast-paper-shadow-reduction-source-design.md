# Fast PAPER Shadow Reduction Read Source — Design

**Date:** 2026-09-26  
**Base main SHA:** `41b3facd4c8884e8ef602f7cbd5b0578be3c75cc`

## Purpose

Add a canonical write-once source record for explicit target-specific OPEN
reduction quote read authority.

The service and coordinator now accept
`FastPaperShadowReductionRead` values, but an unattended supervised process
still needs durable authority that survives restart. This source must
authenticate explicit raw quote input amounts without deriving them from
normalized PAPER float holdings.

## Record contract

Add schema:

`shreks.fast_paper_shadow_reduction_source` version `1`.

Each record binds:

- exact runtime manifest fingerprint;
- exact isolated ledger binding fingerprint;
- exact latest PAPER checkpoint sequence and payload SHA-256;
- exact latest learned runtime-state fingerprint;
- exact market key;
- exact durable position id and mint;
- exact durable learned current exposure;
- the complete ordered set of currently eligible action-policy reduction
  targets;
- one explicit positive raw base input amount for every eligible target;
- canonical record fingerprint.

Eligible targets are exactly the manifest action policy
`reduce_target_exposure_candidates` strictly below the durable current
exposure. Omitting an eligible target would alter the learned action comparison,
so partial target populations are forbidden.

The source does not infer or validate a float-to-raw conversion. Raw amounts are
explicit caller authority.

## API

Add:

- `FastPaperShadowReductionSourceRecord`;
- `build_fast_paper_shadow_reduction_source_record(...)`;
- `write_fast_paper_shadow_reduction_source_record(...)`;
- `read_fast_paper_shadow_reduction_source_record(...)`.

The builder requires the exact latest checkpoint/runtime pair and one durable
OPEN mapping for the supplied market key.

The writer uses deterministic state+market identity, canonical JSON, private
mode `0600`, and write-once publication.

The reader recomputes the expected current durable posture and complete target
set. State advance, posture drift, action-policy drift, tamper, unknown fields,
symlinks, malformed raw amounts, or missing/extra targets fail closed.

## Filename

Use SHA-256 over canonical:

```text
runtime_state_fingerprint_sha256
market_key
```

and suffix `.json`.

This preserves historical records while making lookup deterministic from the
current authenticated state.

## Authority boundary

```text
RAW_REDUCTION_AMOUNT_DERIVATION=FORBIDDEN
RAW_REDUCTION_AMOUNT_AUTHORITY=EXPLICIT_SOURCE_ONLY
REDUCTION_TARGET_SET=ACTION_POLICY_COMPLETE
SOURCE_RECORD=WRITE_ONCE_AUTHENTICATED
SHADOW_STATE_BINDING=EXACT_LATEST
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_LEDGER_MUTATION=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- public reduction-source schema/type/build/write/read API;
- exact durable OPEN posture binding;
- complete eligible reduction-target coverage;
- explicit raw amounts only;
- deterministic canonical private write-once source;
- stale-state/tamper/unknown-field/symlink refusal;
- no float-to-raw conversion, execution, ledger mutation, observer DB,
  provider/network, scoring, cutover, or LIVE authority.

Current main is expected to fail during Python collection because the reduction
source module/API does not exist.
