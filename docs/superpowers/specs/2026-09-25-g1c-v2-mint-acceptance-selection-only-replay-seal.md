# G1C V2 Mint-State Acceptance Selection-Only Replay Seal

**Date:** 2026-09-25  
**Integration SHA:** `cdafe1e8869fb88be9a21163049f2ffa0d6859e3`  
**PR:** #510  
**RED CI:** `36157820891`  
**Feature-head GREEN CI:** `36158285072`  
**Merged-main CI:** `36158595145`

## Production evidence

The exact sealed regime-replay-stage diagnostics release
`11e16ffc2dda363821effec8a0314bc156755b09` deployed successfully.

Its protected G1C V2 mint-state physical-acceptance verifier used the normal
30-minute historical evidence window and a 180-second analyzer deadline. The
analyzer timed out while its latest sanitized progress record was still being
updated during historical cycle reconstruction:

```text
g1c_v2_mint_state_acceptance_status=TIMEOUT
g1c_v2_mint_state_acceptance_progress_stage=CYCLE_RECONSTRUCTION
```

The mint-state physical-acceptance question needs the exact point-in-time
candidates selected by the PAPER campaign, then the historical Helius
mint-state rows for those candidates. The prior analyzer reconstructed full
PAPER cycles for every checkpoint solely to recover the selected candidate
IDs/mints.

Full cycle reconstruction also rebuilt market features, entry/exit quotes,
safety, aggregate regime, risk context, score/ranking, and aggregate cycle
fingerprints. Those downstream components are not evidence required by this
mint-state refresh acceptance gate and had created unnecessary replay cost.

## Sealed refinement

The coordinator now exposes one shared deterministic function:

```text
select_observer_paper_campaign_candidates(...)
```

That function contains the exact selection path formerly embedded inside full
campaign assembly:

- required mints from managed positions and pending entry state;
- point-in-time required-mint resolution;
- the same recent-candidate selection policy;
- the same Fresh Launch pair-age bounds;
- the same market-read policy;
- the same quote-identity requirement;
- the same required/recent de-duplication and ordering.

Normal PAPER campaign assembly now calls that shared function.

The mint-state acceptance analyzer also calls that same function for each
historical checkpoint and then immediately reads the selected candidates'
historical mint-state rows. It no longer reconstructs market/setup/score/regime/
risk/PAPER execution components merely to identify selected candidates.

## Selection equivalence

Focused tests require the selection-only replay to return the same selected
candidate IDs and mints as full coordinator assembly for the same database,
state, timestamp, policy bundle, selection policy, and quote valuation mode.

The full coordinator and acceptance analyzer therefore do not maintain
independent copies of candidate-selection logic.

## RED / GREEN evidence

RED head:

`53fc8c31f0fdd7a013089a9c75521a771b883649`

RED CI `36157820891`:

- Python: expected FAIL;
- repository safety: PASS;
- ARM64 release build: PASS;
- Rust: PASS.

The two intended RED failures were:

1. the shared selection-only coordinator function did not yet exist;
2. the acceptance analyzer still invoked full PAPER-cycle assembly.

Final feature head:

`80740408a62f896885ff518af5e3344d6c19530c`

Feature-head CI `36158285072`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:

`cdafe1e8869fb88be9a21163049f2ffa0d6859e3`

Merged-main CI `36158595145`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This is a historical acceptance-verifier efficiency/refactor slice.

It does **not** change:

- production candidate-selection semantics or ordering;
- PAPER campaign candidate authority;
- market observations or feature values;
- safety policy or thresholds;
- Fresh Launch/setup policy or thresholds;
- regime construction or thresholds;
- scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution or accounting;
- active protected campaign-manifest bytes;
- model/champion authority;
- learned action authority;
- PAPER promotion;
- LIVE authority.

The deterministic commissioning campaign remains baseline/commissioning logic,
not Shreks' target learned market-intelligence authority.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
production verifier against the normal historical evidence window.

Acceptable outcomes are:

1. mint-state physical acceptance reaches `PASS`, closing the outstanding
   pre-expiry mint refresh gate;
2. it reaches `HOLD_INSUFFICIENT_EVIDENCE` without timeout, proving the
   historical analysis path is now bounded but the sampled production window
   lacks a qualifying pre-expiry refresh transition;
3. it fails closed with a selection or mint-state evidence family, which alone
   drives the next diagnostic slice.

A return to the previous full-cycle market/regime/risk reconstruction families
would indicate architecture drift and must not be worked around by increasing
strategy thresholds or changing trading policy.

## Explicit non-authority

```text
CANDIDATE_SELECTION_SEMANTICS=UNCHANGED
HISTORICAL_POINT_IN_TIME_SELECTION=UNCHANGED
MARKET_EVIDENCE=UNCHANGED
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
