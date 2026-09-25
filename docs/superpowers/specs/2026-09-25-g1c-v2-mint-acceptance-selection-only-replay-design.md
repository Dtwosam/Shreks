# G1C V2 Mint-State Acceptance Selection-Only Replay Design

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-mint-acceptance-selection-replay`  
**Base / deployed release:** `11e16ffc2dda363821effec8a0314bc156755b09`

## Production evidence

The exact sealed regime-replay-stage diagnostics release
`11e16ffc2dda363821effec8a0314bc156755b09` deployed successfully.

The protected G1C V2 mint-state acceptance verifier then timed out after its
180-second analysis deadline while the last sanitized progress record was:

```text
g1c_v2_mint_state_acceptance_status=TIMEOUT
g1c_v2_mint_state_acceptance_progress_stage=CYCLE_RECONSTRUCTION
```

The progress record was generated during the timeout window, so the analyzer
was still advancing through historical cycle reconstruction rather than failing
at a sealed component family.

The verifier requests a 30-minute historical window. The acceptance question is
only whether the candidates selected by the PAPER campaign had bounded,
pre-expiry mint-state refresh evidence. The analyzer currently reconstructs the
entire PAPER cycle for every historical checkpoint solely to recover
`selected_candidate_ids` and `selected_mints`.

Full cycle reconstruction additionally rebuilds market features, quotes,
safety, aggregate regime, risk context, entry ranking, and aggregate PAPER
cycle fingerprints. Those components are not needed to answer the mint-state
refresh acceptance question and have already caused both replay failures and
timeout pressure.

## Goal

Create one shared, deterministic point-in-time candidate-selection function
used by both:

1. normal observer PAPER campaign assembly; and
2. the mint-state physical-acceptance analyzer.

The acceptance analyzer should replay only candidate selection at each
checkpoint, then read the selected candidates' historical Helius mint-state
rows exactly as it does today.

## Required invariants

The extracted selection function must preserve the existing coordinator logic
exactly:

- required mints come from managed positions and pending ENTRY state;
- required mints remain first and are de-duplicated in original order;
- recent candidates use the same selection policy;
- Fresh Launch pair-age bounds remain identical;
- quote-identity filtering remains identical;
- required/recent merge behavior and conflicting-mint rejection remain
  identical;
- candidate IDs and mint ordering must match full coordinator assembly for the
  same database, state, timestamp, policy bundle, selection policy, and quote
  valuation mode.

The full coordinator must call the same extracted function rather than carrying
a second copy of selection logic.

## Acceptance boundary

The mint-state acceptance analyzer is not a general historical trading-cycle
replay verifier.

For this gate it needs only:

```text
historical checkpoint state
        ↓
exact point-in-time candidate selection
        ↓
selected candidate IDs + mints
        ↓
historical Helius mint-state rows
        ↓
pre-expiry refresh acceptance
```

It must not require regime, score, setup, risk, or PAPER execution
reconstruction merely to identify the selected candidates.

Historical point-in-time selection semantics remain unchanged.

## RED / GREEN plan

RED must prove:

1. the extracted selection function returns exactly the same selected
   candidate IDs/mints as full coordinator assembly on a representative
   fixture;
2. the acceptance analyzer uses selection-only replay and therefore does not
   invoke full PAPER cycle assembly;
3. required-position / pending-entry candidate preservation remains identical;
4. selection errors remain fail-closed through the existing sanitized
   required-mint / candidate-selection acceptance families.

GREEN is the smallest refactor that makes those tests pass.

## Non-authority

This slice must not change:

```text
CANDIDATE_SELECTION_SEMANTICS=UNCHANGED
HISTORICAL_POINT_IN_TIME_SELECTION=UNCHANGED
MARKET_DATA=UNCHANGED
SAFETY_POLICY=UNCHANGED
REGIME_POLICY=UNCHANGED
SETUP_POLICY=UNCHANGED
SCORING_POLICY=UNCHANGED
RISK_POLICY=UNCHANGED
PAPER_EXECUTION=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MODEL_CHAMPION_AUTHORITY=UNCHANGED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

The deterministic commissioning campaign remains baseline/commissioning logic
and is not the target learned market-intelligence authority.
