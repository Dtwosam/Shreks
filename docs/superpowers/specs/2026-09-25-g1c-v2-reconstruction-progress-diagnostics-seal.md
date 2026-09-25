# G1C V2 Reconstruction Progress Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `5e35bb18c1fa7d4070a5541cf1fd850604a8f630`  
**PR:** #505  
**Feature-head CI:** `36135551640`  
**Merged-main CI:** `36142613837`

## Production evidence

The exact deployed regime-reconstruction diagnostics release
`ff0ef704a81767cfea2c823e10dc83d459defc3c` remained healthy at the PAPER
service level but the protected mint-state physical-acceptance verifier timed
out while its sanitized progress marker stayed at:

```text
CYCLE_RECONSTRUCTION
```

That evidence did not justify changing strategy, safety, regime, scoring,
candidate-selection, or risk semantics. It showed only that the protected
historical reconstruction needed finer bounded progress visibility.

## Sealed refinement

This slice adds fixed, non-sensitive reconstruction substages while preserving
the same historical replay and PAPER behavior.

The allowed substages are:

```text
CYCLE_RECONSTRUCTION_SELECTION
CYCLE_RECONSTRUCTION_MARKET
CYCLE_RECONSTRUCTION_QUOTE
CYCLE_RECONSTRUCTION_SAFETY_FEATURES
CYCLE_RECONSTRUCTION_REGIME
CYCLE_RECONSTRUCTION_RISK
CYCLE_RECONSTRUCTION_FINALIZE
CYCLE_RECONSTRUCTION_AGGREGATION
```

The observer-campaign assembler accepts an optional progress callback and emits
only these fixed stage names. The coordinator emits selection/aggregation
boundaries and forwards assembler progress. The protected telemetry bridge
prefixes the fixed reconstruction stage for the existing acceptance progress
channel. The production verifier accepts only the bounded whitelist above.

Candidate identifiers, mints, SQL, checkpoint payloads, raw exceptions,
provider details, paths, credentials, and manifest contents are not exposed by
this change.

## Behavioral boundary

This release changes diagnostics only.

It does **not** change:

- selected candidate identity or ordering;
- B1 safety policy or thresholds;
- Fresh Launch/setup policy or thresholds;
- regime construction or policy;
- deterministic scoring/decision behavior;
- risk assessment or sizing;
- PAPER ledger/execution semantics;
- evidence-provider selection;
- active protected campaign-manifest bytes;
- model/champion authority;
- PAPER promotion authority;
- LIVE authority.

The deterministic commissioning campaign remains a baseline/commissioning
authority, not the target learned market-intelligence authority defined by
`SHREKS_MASTER_SOURCE_OF_TRUTH.md`.

## RED / GREEN evidence

Intentional RED head:

`6b4060cc67dff863edee6db238c70de3a0dbb448`

The RED integration test required timeout diagnostics to accept bounded
reconstruction substages before the production path emitted them.

Implementation subsequently added bounded progress emission through assembler,
coordinator, telemetry, and verifier layers.

An initial GREEN attempt exposed one stale Python assertion that still required
the single generic `CYCLE_RECONSTRUCTION` value. That test was corrected to
accept only the exact bounded substage set.

Final feature head:

`8668da22bafdbc86976b926dc050cba4bba93212`

Feature-head CI `36135551640`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`5e35bb18c1fa7d4070a5541cf1fd850604a8f630`

Merged-main CI `36142613837`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Required physical follow-up

After immutable release and protected deployment of this seal, rerun the
exact-release production verifier.

Acceptable outcomes are:

1. physical mint-state acceptance reaches `PASS`, closing the outstanding
   pre-expiry refresh acceptance gate; or
2. verification still fails/times out, but now returns the exact last bounded
   reconstruction substage. That returned substage becomes the only justified
   next diagnostic implementation slice.

Do not weaken token-level thresholds or deterministic commissioning criteria to
force PAPER trades. Those legacy criteria remain baseline/commissioning logic
and are not evidence of the learned action system's market judgment.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
SAFETY_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
