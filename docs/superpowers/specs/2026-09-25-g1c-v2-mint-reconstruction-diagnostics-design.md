# G1C V2 Mint-State Reconstruction Diagnostics Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-reconstruction-diagnostics`  
**Base / deployed release:** `814f2a452e6890750db3276068116d7f0d6bef53`

## Production evidence

The exact deployed heredoc-hotfix release successfully completed the protected
mint-acceptance control exchange and returned:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

This proves the request transport, exact-release binding, protected database
access, checkpoint-window read, and checkpoint decode reached historical cycle
reconstruction. The existing result is intentionally too coarse to identify the
next evidence-backed fix.

## Goal

Classify only stable internal reconstruction failure families while preserving
the generic fail-closed message and never emitting dynamic coordinator text.

Allowed analyzer codes:

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

The existing generic code remains the fallback for an unrecognized error family.

## Classification boundary

The classifier consumes only the trusted in-process
`ObserverCampaignCoordinatorError` message and maps recognized stable prefixes
or vocabulary to one fixed enum. The raw message is never returned by the
analyzer or control bridge.

Families:

- required-mint recovery: required historical candidate cannot be uniquely
  recovered or lacks point-in-time market evidence;
- candidate selection: recent-candidate enumeration, quote-identity filtering,
  or ambiguity fails;
- component market: per-candidate assembly fails around observer market/window
  evidence;
- component quote: per-candidate quote/valuation/route evidence fails;
- component safety: per-candidate safety evidence/assessment fails;
- component regime: per-candidate regime evidence/assessment fails;
- component other: a per-candidate assembly error does not match the known
  market/quote/safety/regime families;
- aggregation: component attribution, ranking, duplicate merge, or aggregate
  paper-cycle construction fails.

No candidate ID, mint, provider response, path, SQL, checkpoint payload, or
exception string crosses the control boundary.

## Non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=UNCHANGED
DATABASE_PERMISSIONS=UNCHANGED
SUDO_AUTHORITY=UNCHANGED
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

This slice changes diagnostics only.

## TDD

RED requires:

1. known coordinator failure families map to exact fixed analyzer codes;
2. arbitrary dynamic details never appear in the analyzer error text;
3. unknown coordinator messages retain `CYCLE_RECONSTRUCTION_FAILED`;
4. the control allow-list forwards the fixed code only as
   `ANALYSIS_<CODE>`;
5. no raw coordinator message appears in the control result.
