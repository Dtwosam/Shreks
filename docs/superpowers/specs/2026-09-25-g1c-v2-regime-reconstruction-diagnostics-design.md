# G1C V2 Regime Reconstruction Diagnostics Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-regime-reconstruction-diagnostics`  
**Base / deployed release:** `285daecd353203d9e3326047c8244828c2cef9b9`

## Production evidence

The exact deployed reconstruction-diagnostics release returned:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED
```

The failure is therefore inside the aggregate regime context used while
historically reconstructing one selected PAPER candidate.

## Goal

Refine only known regime-reader failure shapes into fixed non-sensitive enums:

```text
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_WINDOW_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_MARKET_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_SAFETY_FAILED
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED
```

The existing `CYCLE_RECONSTRUCTION_COMPONENT_REGIME_FAILED` remains the
fallback for regime errors that do not match the sealed regime-store shapes.

## Boundary

Only errors carrying the stable regime-store prefixes are refined:

- `aggregate regime consumed evidence ...` -> window/boundary;
- `observer aggregate regime replay failed: ...` -> inspect the nested trusted
  in-process text and map only to market, safety, or other.

No raw nested error, mint, candidate ID, path, SQL, provider detail, or
checkpoint content is emitted.

## Non-authority

Replay, regime policy, safety policy, candidate selection, thresholds,
permissions, PAPER promotion, and LIVE state are unchanged.

## TDD

RED requires exact fixed mapping for the four sealed regime-store families,
generic regime fallback for unrelated regime messages, and sanitized control
forwarding only.
