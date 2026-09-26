# Fast Lane Learned PAPER Shadow Restart Orchestration — Design

**Date:** 2026-09-26  
**Base main SHA:** `18a655c9fd198f7b859a5b05a42b6f45523f081a`  
**Migration plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Make the merged learned shadow-decision path restart-safe without granting
authoritative PAPER execution authority.

This slice processes an explicit ordered batch of point-in-time shadow inputs,
persists one authenticated decision artifact per record, and advances the Fast
PAPER runtime cursor only after the corresponding artifact is durable.

It does not fetch provider/network data, mutate a `PaperLedger`, change
systemd topology, or grant PAPER/LIVE trading authority.

## Feature-record binding

The existing `shreks.fast_paper_shadow_decision` artifact binds event identity,
quotes, constraints, champion identity, and the exact Rust result, but durable
replay also needs to prove that the same canonical feature row is being reused.

The shadow decision evidence schema therefore advances to v2 and adds:

`feature_record_fingerprint_sha256`

It is the canonical logical fingerprint of the one-record tuple:

`feature_logical_fingerprint_sha256((record,))`

The evaluator computes and seals this fingerprint. The reader authenticates it
through the outer evidence fingerprint.

## Shadow cycle input

Add one exact runtime-local model:

`FastPaperShadowCycleInput`

It binds:

- one `FastTrainingFeatureRecord`;
- one explicit `FastCampaignDecisionPosition`;
- evaluation timestamp;
- maximum exposure fraction;
- ENTRY quote evidence;
- EXIT quote evidence;
- ordered reduction quote evidence;
- force-sell flag.

This model contains no score, ledger, provider client, or LIVE authority.

## Durable batch runner

Add:

`run_fast_paper_shadow_batch(...)`

Inputs:

- exact runtime manifest;
- exact authenticated runtime state;
- non-empty tuple of exact shadow cycle inputs;
- explicit shadow evidence directory.

The runner requires:

- state authenticates against the manifest;
- if the durable checkpoint exists, it exactly equals the supplied state;
- if the checkpoint is absent, supplied state must be the initial cursor-less
  state;
- record decision sequences strictly advance from the supplied cursor;
- source identities are unique within the batch;
- evidence directory is distinct from the authoritative
  `manifest.paper_evidence_path`.

## Per-record commit ordering

For each input:

1. derive a deterministic destination filename from decision sequence plus a
   SHA-256 digest of source identity;
2. if the evidence file is absent:
   - evaluate through the merged shadow-decision function;
   - write and fsync the canonical mode-0600 evidence artifact;
3. if the evidence file already exists:
   - read it;
   - require exact replay compatibility with the current input and manifest;
   - do **not** invoke the decision binary again;
4. build the next authenticated runtime state for exactly that record;
5. re-read the durable checkpoint when present and require it still equals the
   expected prior state;
6. atomically write the next runtime checkpoint.

Therefore:

`evidence durable -> cursor advance`

never the reverse.

If evidence publication succeeds but checkpoint publication fails, restart
reuses the existing authenticated evidence and advances the checkpoint without
re-running inference.

If record N succeeds and record N+1 fails, the checkpoint remains at N.

## Replay compatibility

Existing evidence may be reused only when all of these match:

- release SHA;
- manifest fingerprint;
- champion fingerprint;
- action-policy version;
- one-record feature fingerprint;
- source event ID / market / sequence / observation timestamp;
- evaluation timestamp;
- position;
- ENTRY/EXIT/reduction quote evidence;
- maximum exposure fraction;
- force-sell value.

Any mismatch fails closed before cursor advancement.

## Evidence filenames

Filenames never embed raw signatures.

Format:

`shadow-<20-digit-sequence>-<16-hex-identity-digest>.json`

The digest is SHA-256 over canonical:

`{"decision_ordinal":...,"decision_signature":"..."}`

This prevents path traversal or filesystem ambiguity from event signatures.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EVIDENCE_PATH=UNCHANGED
SHADOW_DECISION_REPLAY=IDEMPOTENT_AUTHENTICATED
SHADOW_LEDGER_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_ACCESS=FORBIDDEN
SYSTEMD_CUTOVER=NOT_GRANTED
FAST_LANE_PAPER_EXECUTION=NOT_GRANTED
LIVE=DISABLED
```

## Following slice

After this restart-safe batch runner is merged, the next PR3 slice may bind a
read-only persisted execution-evidence resolver and a separate shadow service
entrypoint. It must still leave the authoritative PAPER ledger untouched.
