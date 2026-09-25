# G1C V2 PAPER Mint-State Reconstruction Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `7550f6584895a1c7f6005632d7e606a596f87f9c`  
**PR:** #501  
**Merged-main CI:** `36128421519`

## Production trigger

The exact deployed release
`814f2a452e6890750db3276068116d7f0d6bef53` successfully completed the
mint-acceptance control transport and returned a terminal, sanitized analyzer
failure:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

Deploy workflow: `36126942516`  
Production verifier job: `108045933038`

That evidence proves the protected request/result exchange, release binding,
database open, bounded checkpoint read, and checkpoint decoding reached the
historical campaign-cycle reconstruction boundary.

The generic code did not identify the next safe implementation slice.

## Sealed diagnostic change

Historical reconstruction failures are now mapped to fixed, non-sensitive
families:

```text
CYCLE_RECONSTRUCTION_REQUIRED_MINT_FAILED
CYCLE_RECONSTRUCTION_CANDIDATE_SELECTION_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_MARKET_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_QUOTE_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_SAFETY_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_OTHER_FAILED
CYCLE_RECONSTRUCTION_AGGREGATION_FAILED
CYCLE_RECONSTRUCTION_FAILED
```

The final generic value remains the fallback for unrecognized coordinator
errors.

The control bridge exposes only the existing generic failure message plus the
allow-listed `ANALYSIS_<CODE>` value. It does not emit the original
`ObserverCampaignCoordinatorError` text.

## Classification boundary

The classifier consumes only trusted in-process coordinator errors and maps
stable message families to enums.

It does not return:

- candidate IDs;
- token mints;
- provider responses;
- SQLite details;
- filesystem paths;
- checkpoint payloads;
- dynamic exception text;
- wallet/signing information.

Recognized families distinguish:

- required historical mint recovery;
- recent candidate selection and quote-identity filtering;
- per-candidate market assembly;
- per-candidate quote/valuation assembly;
- per-candidate safety assembly;
- per-candidate regime assembly;
- other per-candidate assembly;
- aggregate attribution/ranking/cycle assembly.

No underlying coordinator behavior is changed.

## RED / GREEN evidence

RED head:
`9e221b1ea165394cefca4839cf3ad3f6aec4d514`

CI run `36127794550`:

- Python: failed exactly the ten new diagnostics assertions;
- 3,722 existing Python tests passed;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Final GREEN head:
`5c04e0f1308ca0e818b9484f74064001b7308444`

CI run `36128130661`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`7550f6584895a1c7f6005632d7e606a596f87f9c`

Merged-main CI run `36128421519`:

- Python: PASS;
- Rust: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

The implementation diff is confined to:

- reconstruction diagnostics design/seal documentation;
- mint-state acceptance diagnostic classification;
- control allow-list expansion for the fixed codes;
- analyzer/control tests.

## Required production follow-up

Deploy the immutable release for this seal and rerun the exact-release
production verifier.

The returned reconstruction-family code becomes the next implementation slice.

Do not change replay semantics, selector behavior, safety thresholds, provider
budgets, or verifier acceptance criteria before that physical evidence exists.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No scoring, model fitting, threshold relaxation, manifest rotation, PAPER
promotion, signing, wallet, transaction submission, or LIVE authority is
granted by this seal.
