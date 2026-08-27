# G2 production PAPER fix — Fresh Launch current-market selection

Date: 2026-08-27

## Physical PAPER evidence

The dedicated production VPS was running immutable release `shreks-489de693d252d62e5ac5c8f6c480ade236635df9` after the Fresh Launch pair-age prioritization correction. Physical host proof showed the expected release active, all Shreks services active, zero campaign restarts, checkpoint sequence 253, and regular selection choosing two candidates inside the configured Fresh Launch age window while excluding expired candidates.

A subsequent read-only decision diagnostic exposed a second selector/assembler contract gap. Candidate `9267` was selected as a regular Fresh Launch candidate, but cycle assembly failed with:

`no fresh observer market snapshot matches caller source priority`

The diagnostic itself made no persistent changes.

## Root cause

The regular Fresh Launch selector required compatible pair age but could still select a candidate whose latest candidate-specific market snapshot did not satisfy the downstream `ObserverMarketReadPolicy` current-evidence contract.

The assembler loads the candidate market window using the versioned `market_read_policy`, which requires a snapshot:

- from a source in the configured `source_priority` set; and
- observed within `max_current_age_ms` of the cycle timestamp.

The selector previously used the broader campaign recent-observation lookback for candidate enumeration, so an age-valid token could consume a new-entry slot and then fail closed during downstream assembly because its market evidence was stale or from a disallowed source.

Production runtime cycles use wall-clock point-in-time timestamps, so the physical diagnostic reproduced a real runtime contract gap rather than a diagnostic-only clock artifact.

## Corrected behavior

For regular new-entry selection in the Fresh Launch campaign:

- existing pair-age compatibility and in-window prioritization remain unchanged;
- a candidate must also have at least one candidate-specific market snapshot from the existing configured `market_read_policy.source_priority` within the existing `market_read_policy.max_current_age_ms` window before it can consume a regular new-entry slot;
- the selector reuses the existing versioned market-read policy and introduces no new market-freshness threshold;
- a fresh snapshot from a source outside the configured source-priority set does not make the candidate eligible;
- required mints for existing managed positions or a pending entry continue to be resolved separately and are not silently dropped by the regular new-entry filter;
- required-position/pending-entry assembly continues to fail closed if its critical evidence is stale or unusable.

## TDD and verification evidence

Exact RED branch commit: `2eaa590b6d1ed904ed30204b5fa3aa9678d711e7`.

RED CI run: `33093850261`.

The regression failed for the intended production reason with `1 failed, 2622 passed`:

`ObserverCampaignCoordinatorError: observer candidate 2 assembly failed: observer paper cycle assembly failed: no fresh observer market snapshot matches caller source priority`

Final PR head: `d0bc3e689d059df47484fb8c8b7fbd1e0ce5ae2f`.

GREEN PR CI run: `33094429348`:

- Python GREEN: `2624 passed`;
- Rust GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

The final test set includes both:

1. an age-valid candidate with no current market snapshot; and
2. an age-valid candidate with a fresh snapshot only from a source outside the configured source-priority set.

Both are excluded from regular new-entry selection.

Merged behavior commit: `6d25b83c6f8642e0d54a51e9ed731cdb07c943ce` via PR #61.

Exact merged-main CI run: `33094648281`:

- Python GREEN;
- Rust GREEN;
- repository safety GREEN;
- native ARM64 release-build verification GREEN.

## Preserved safety and authority invariants

- B1 safety vetoes remain unchanged and continue to override scoring.
- Missing, stale, contradictory, or source-incompatible critical evidence is not guessed.
- Fresh Launch age, liquidity, flow, score, decision, risk, sizing, loss, drawdown, slippage, exit, and execution thresholds are unchanged.
- PAPER fill economics are unchanged.
- Existing open positions and pending entries are not discarded by the regular-entry eligibility filter.
- No wallet/signing/submission authority was added.
- No strategy or learning model can self-promote to LIVE.
- LIVE remains disabled.
- Profitability remains unproven: the production PAPER run still had zero entry provenance, zero executions, zero closed positions, and zero evaluated trades at the latest physical proof before this seal.

This documentation-only commit is the production release seal for the Fresh Launch current-market selection correction.