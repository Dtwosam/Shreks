# G1C V2 Regime Replay Stage Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `b6d692ec78988d9eaefddbd9916fab13344e9665`  
**PR:** #509  
**RED CI:** `36152772312`  
**Feature-head GREEN CI:** `36153290281`  
**Merged-main CI:** `36154101965`

## Production evidence

The exact sealed regime-quote diagnostics release
`44bf978eff638ce92a71b8a2a835fb017cbe2d97` deployed successfully.

Its protected G1C V2 mint-state physical-acceptance verifier completed and
returned:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

Because the release already recognized known aggregate-regime quote failure
shapes, this result disproved the narrower quote-only diagnostic hypothesis.

Inspection of `ObserverCampaignStore.build_regime_market_window` showed that
candidate decoding, market reconstruction, safety reconstruction, entry-quote
reconstruction, and final regime-window construction were still inside a broad
fallback that could collapse `sqlite3.Error`, `TypeError`, or `ValueError`
into a generic replay family.

## Sealed refinement

Aggregate-regime replay now fails closed through fixed non-sensitive stage
messages:

```text
observer aggregate regime candidate replay failed
observer aggregate regime market replay failed
observer aggregate regime safety replay failed
observer aggregate regime quote replay failed
observer aggregate regime finalize replay failed
```

The acceptance analyzer maps them to fixed families:

```text
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_CANDIDATE_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_MARKET_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_SAFETY_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FINALIZE_FAILED
```

Existing market, safety, and quote families are reused. Only candidate and
finalize are new allowlisted families.

The existing regime-window boundary family remains unchanged:

```text
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_WINDOW_FAILED
```

Unknown/unsealed regime failures still fail closed rather than exposing raw
detail.

No mint, candidate ID, raw exception text, stored value, SQL, path, route
detail, checkpoint payload, provider detail, credential, or manifest content is
added to the protected surface.

## RED / GREEN evidence

RED head:

`e050bc3b7e7b164b56b970c92e0fda87aaf7feb5`

RED CI `36152772312`:

- Python: expected FAIL;
- repository safety: PASS;
- ARM64 release build: PASS;
- Rust: PASS.

The RED failures demonstrated that:

- store-level stage errors still surfaced through the broad replay wrapper;
- stable candidate/market/safety/quote/finalize stage messages were not yet
  classified;
- candidate/finalize families were not yet allowlisted at the protected
  control surface.

Final feature head:

`1bb2ce4d6d70d08ef8b9709977539e54192d94f6`

Feature-head CI `36153290281`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`b6d692ec78988d9eaefddbd9916fab13344e9665`

Merged-main CI `36154101965`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This slice changes diagnostic error boundaries only.

It does **not** change:

- which candidates are selected;
- historical point-in-time evidence selection;
- market-window values;
- safety assessment semantics;
- quote identity or route semantics;
- aggregate regime calculations;
- regime policy or thresholds;
- Fresh Launch/setup policy or thresholds;
- scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution or accounting;
- active protected campaign-manifest bytes;
- model/champion authority;
- PAPER promotion;
- LIVE authority.

The deterministic commissioning campaign remains baseline/commissioning logic
and must not be interpreted as Shreks' target learned market-intelligence
authority.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
production verifier.

The returned fixed regime family becomes the only justified next slice:

- `...REGIME_CANDIDATE_FAILED` -> candidate evidence decoding/attribution;
- `...REGIME_MARKET_FAILED` -> market snapshot/window reconstruction;
- `...REGIME_SAFETY_FAILED` -> aggregate safety evidence reconstruction;
- `...REGIME_QUOTE_FAILED` -> aggregate entry-quote reconstruction;
- `...REGIME_FINALIZE_FAILED` -> aggregate regime-window finalization;
- `...REGIME_WINDOW_FAILED` -> requested-window evidence boundary;
- `...REGIME_OTHER_FAILED` -> refine only the next stable unsealed family.

If physical mint-state acceptance reaches `PASS`, close the outstanding
physical acceptance gate.

Do not alter strategy thresholds, deterministic commissioning rules, or
learned-model authority to force this acceptance check.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
MARKET_EVIDENCE=UNCHANGED
SAFETY_POLICY=UNCHANGED
QUOTE_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
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
