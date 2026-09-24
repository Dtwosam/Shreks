# G1C V2 PAPER Mint-State Freshness Design

**Date:** 2026-09-24  
**Branch:** `fix/g1c-v2-mint-state-freshness`  
**Base:** `a2798a8ecc860ea4e725bc274eb6ebe5abf04073`

## Physical defect

Candidate `1340728` reached 9/9 Fresh Launch confirmations with an executable
entry quote and score 78.22, but B1 safety was INCOMPLETE solely because critical
data was stale.

Exact point-in-time evidence at `1790274833523`:

- current market age: 9,439 ms;
- Helius holder distribution age: 483,642 ms;
- Jupiter exit quote age: 19,605 ms;
- Helius mint-state age: 28,641,760 ms;
- B1 max critical-data age: 900,000 ms.

The mint-state table contained exactly one Helius row. B1 deliberately uses the
oldest timestamp among current market, mint authority, holder distribution, and
exit quote as the critical-data timestamp.

The PAPER evidence collector currently probes mint state only when no durable row
exists. Once a row exists, it is never refreshed. That existence-cache conflicts
with B1's versioned freshness requirement and can permanently make an otherwise
eligible candidate INCOMPLETE.

## Goal

Refresh mint/freeze authority evidence for selected PAPER candidates when the
latest durable Helius mint-state row is older than the authenticated B1
`max_critical_data_age_ms`, while preserving all safety and provider-budget
semantics.

## Authority

The refresh limit comes from the authenticated campaign manifest's
`policy_bundle.safety_policy.max_critical_data_age_ms`.

The release-local Python PAPER-evidence launcher already authenticates the
campaign manifest before `execve` into the Rust evidence binary. It will derive
one additional child-process environment value:

`SHREKS_PAPER_MINT_STATE_MAX_AGE_MS`

No protected manifest bytes are changed.

## Design

1. The launcher authenticates every supported campaign manifest and exports the
   exact B1 max critical-data age as
   `SHREKS_PAPER_MINT_STATE_MAX_AGE_MS`.
2. Rust config requires that value as a positive integer and stores it as
   `mint_state_max_age`.
3. The read-only evidence candidate store gains
   `has_mint_state_since(candidate_id, minimum_observed_at, as_of)`, restricted
   to Helius rows and point-in-time bounded exactly like B1 consumption.
4. For each selected PAPER evidence candidate, the cycle computes
   `minimum = as_of - mint_state_max_age`.
5. If no Helius mint-state row exists in `[minimum, as_of]`, the cycle requests
   one mint-state refresh through the existing bounded Helius chain provider.
6. Existing fresh mint-state evidence suppresses the chain request.
7. A failed or misattributed provider response remains a provider failure and
   does not fabricate safety truth.
8. Holder and quote collection semantics remain unchanged.

The existing collector entry points retain compatibility. A new explicit refresh
control is used by the PAPER evidence cycle so other observer callers keep their
historical "backfill only when missing" behavior.

## Non-goals

No changes to:

- B1 safety thresholds or 900,000 ms freshness limit;
- Fresh Launch thresholds;
- B2 feature schema or anchor bands;
- quote mint, sizing, slippage, or Jupiter semantics;
- protected campaign manifest bytes;
- scoring/model fitting;
- PAPER promotion;
- wallet/signing;
- LIVE.

## Tests

RED/GREEN coverage must prove:

1. an existing stale mint-state row causes a selected PAPER candidate to request
   and persist one refreshed Helius row;
2. an existing row exactly at the allowed freshness boundary suppresses refresh;
3. a current row suppresses refresh;
4. provider failure while refresh is required increments the existing chain
   failure counter and persists no invented row;
5. the launcher derives the exact B1 max-age value from authenticated V1 and V2
   manifests;
6. Rust config rejects missing/zero/malformed max-age values;
7. holder/quote behavior and existing missing-mint backfill behavior remain
   green;
8. repository safety, Rust, Python, and ARM64 release checks remain green.

## Physical acceptance

After seal/release/deploy:

- release SHA exact;
- protected V2 manifest SHA unchanged;
- PAPER services healthy;
- evidence process release-local;
- selected candidates receive fresh mint-state evidence within B1's 900,000 ms
  limit when Helius succeeds;
- replay candidate `1340728` at its historical timestamp remains historically
  INCOMPLETE (no time travel), while new comparable 9/9 observations are no
  longer blocked by an existence-cached stale mint row;
- no authority changes.
