# G1C V2 Reconstruction Store-Init Progress Seal

**Date:** 2026-09-25  
**Integration SHA:** `a6ed8049334bbbcff519d1256cdf16f2b253e48f`  
**PR:** #506  
**RED CI:** `36147124799`  
**Feature-head GREEN CI:** `36147426247`  
**Merged-main CI:** `36147768442`

## Production evidence

The exact sealed reconstruction-progress diagnostics release
`d88e3694964dfbe6cdd280982e3f4e4c929737e2` deployed successfully, but the
protected G1C V2 mint-state physical-acceptance verifier timed out.

The sanitized timeout result was:

```text
g1c_v2_mint_state_acceptance_status=TIMEOUT
g1c_v2_mint_state_acceptance_progress_stage=CYCLE_RECONSTRUCTION
```

The prior release already emitted bounded substages beginning at
`CYCLE_RECONSTRUCTION_SELECTION`. Remaining at the generic reconstruction
stage therefore proves the analyzer did not reach selection.

Repository inspection showed that, after the generic reconstruction marker,
`assemble_observer_paper_campaign_cycle` constructs
`ObserverCampaignCandidateStore`, opens the database read-only, and validates
the required candidate-store schema before emitting `SELECTION`.

This evidence justifies visibility at that exact boundary only.

## Sealed refinement

Immediately before `ObserverCampaignCandidateStore(database_path)`, the
coordinator now emits the fixed progress value:

```text
STORE_INIT
```

The protected acceptance path prefixes it as:

```text
CYCLE_RECONSTRUCTION_STORE_INIT
```

The production verifier accepts that exact fixed value in its bounded progress
whitelist.

No identifiers, mints, SQL, schema contents, filesystem paths, raw exceptions,
checkpoint payloads, provider details, credentials, or manifest contents cross
the protected diagnostic boundary.

## RED / GREEN evidence

RED requirement head:

`9fec5688e41d3ac201872c1329f01abe2b3c7180`

RED CI `36147124799` failed only the two new expected Python assertions:

- historical analyzer did not yet emit
  `CYCLE_RECONSTRUCTION_STORE_INIT`;
- production verifier did not yet whitelist
  `CYCLE_RECONSTRUCTION_STORE_INIT`.

Repository safety and ARM64 release build passed in the RED run.

Final feature head:

`2b20853f8a7063e0e03d26261d978793458020cf`

Feature-head CI `36147426247`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`a6ed8049334bbbcff519d1256cdf16f2b253e48f`

Merged-main CI `36147768442`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This slice changes diagnostics only.

It does **not** change:

- candidate selection semantics;
- database read/write authority;
- historical replay semantics;
- B1 safety policy or thresholds;
- Fresh Launch/setup policy or thresholds;
- regime construction or policy;
- scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution or ledger behavior;
- evidence collection;
- active protected campaign-manifest bytes;
- champion/model authority;
- PAPER promotion;
- LIVE authority.

The deterministic commissioning campaign remains baseline/commissioning logic
and is not the target learned market-intelligence authority.

## Required physical follow-up

After immutable release and deployment, rerun the exact-release production
verifier.

Interpret the sanitized progress result as follows:

- if physical acceptance reports `PASS`, close the outstanding mint-state
  pre-expiry physical gate;
- if timeout remains at `CYCLE_RECONSTRUCTION_STORE_INIT`, the next
  investigation is restricted to candidate-store path resolution/read-only
  open/schema validation;
- if progress advances to `CYCLE_RECONSTRUCTION_SELECTION` or a later bounded
  substage, the returned stage becomes the only justified next diagnostic
  slice.

Do not change token thresholds, deterministic commissioning criteria, strategy
rules, or learned-model authority based on this diagnostic gate.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
DATABASE_AUTHORITY=READ_ONLY
SAFETY_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
