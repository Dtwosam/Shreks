# G1C V2 Regime Quote Reconstruction Diagnostics Seal

**Date:** 2026-09-25  
**Integration SHA:** `b742131abeef2a1bb99658ca4e20a1de72d20771`  
**PR:** #507  
**RED CI:** `36150003092`  
**Feature-head GREEN CI:** `36150286129`  
**Merged-main CI:** `36150587815`

## Production evidence

The exact sealed reconstruction store-init progress release
`fea682c3639b71b0378e1e6f2e99403c86206dd9` deployed successfully and the
protected G1C V2 mint-state physical-acceptance analyzer completed rather than
timing out.

Its sanitized fail-closed result was:

```text
g1c_v2_mint_state_acceptance_status=FAILED
g1c_v2_mint_state_acceptance_failure_code=ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED
g1c_v2_mint_state_acceptance_failure_message=mint-state acceptance analysis failed closed
```

Repository inspection showed that aggregate-regime replay reconstructs not only
market and safety evidence but also PAPER entry-quote evidence. The existing
sanitizer distinguished regime window, market, safety, and other families, but
had no fixed quote-specific family.

This slice therefore refines only known quote-related aggregate-regime replay
errors.

## Sealed refinement

The analyzer now recognizes fixed quote-related nested replay terms including:

- quote;
- route;
- slippage;
- input amount;
- output amount;
- probe policy.

Those trusted in-process shapes map to:

```text
CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED
```

The protected control surface allowlists and forwards only the corresponding
sanitized code:

```text
ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED
```

Raw exception text, mints, candidate IDs, route labels, amounts, SQL, database
paths, checkpoint payloads, provider details, credentials, and manifest
contents remain private.

Unknown regime-replay failures still fail closed as
`CYCLE_RECONSTRUCTION_COMPONENT_REGIME_OTHER_FAILED`.

## RED / GREEN evidence

Intentional RED head:
`68f3e40de7b9d86dcb87a727ead6744de7a5440f`

RED CI `36150003092`:

- Python failed exactly the new quote-family analyzer/control expectations;
- the analyzer still returned `REGIME_OTHER_FAILED` instead of the required
  fixed quote family;
- the protected control still reduced the unallowlisted family to
  `ANALYSIS_FAILED`;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Final feature head:
`f2428fc4e8e5a9edaf9dbc19d9f499af72808662`

Feature-head CI `36150286129`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

Merged integration SHA:
`b742131abeef2a1bb99658ca4e20a1de72d20771`

Merged-main CI `36150587815`:

- Python: PASS;
- Rust: PASS;
- repository safety: PASS;
- ARM64 release build: PASS.

## Behavioral boundary

This slice changes diagnostics only.

It does **not** change:

- historical replay semantics;
- candidate selection;
- PAPER quote construction or route selection;
- safety policy or thresholds;
- Fresh Launch/setup policy or thresholds;
- regime policy or thresholds;
- scoring/decision behavior;
- risk assessment or sizing;
- PAPER execution or ledger behavior;
- evidence collection;
- active protected campaign-manifest bytes;
- champion/model authority;
- PAPER promotion;
- LIVE authority.

The deterministic commissioning campaign remains baseline/commissioning logic,
not the target learned market-intelligence authority defined by
`SHREKS_MASTER_SOURCE_OF_TRUTH.md`.

## Required physical follow-up

After immutable release and protected deployment, rerun the exact-release
production verifier.

Interpret the result as follows:

- if the prior regime-other family was quote-related, the verifier should now
  return
  `ANALYSIS_CYCLE_RECONSTRUCTION_COMPONENT_REGIME_QUOTE_FAILED`;
- if it returns another fixed family, that family alone drives the next
  implementation slice;
- if it still returns `REGIME_OTHER_FAILED`, do not broaden behavior or relax
  trading thresholds; refine only the next stable evidence family;
- if physical mint-state acceptance reaches `PASS`, close the outstanding
  physical acceptance gate.

## Explicit non-authority

```text
HISTORICAL_REPLAY=UNCHANGED
CANDIDATE_SELECTION=UNCHANGED
QUOTE_EXECUTION_POLICY=UNCHANGED
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
