# G1C V2 PAPER evidence candidate-selector alignment design

Date: 2026-09-24

## Problem

Production G1C V2 PAPER now receives fresh WSOL market evidence and reaches the decision engine, but currently selected PAPER candidates can have no matching Helius mint/holder evidence and no exact Jupiter entry/exit quote evidence.

The evidence collector and PAPER coordinator do not currently use the same market-row identity rule.

PAPER selects each candidate from one canonical current market row under:

- configured market-source priority;
- exact candidate base mint;
- authenticated manifest quote mint;
- current-market freshness;
- valid pair-created timestamp;
- fresh-launch pair-age bounds.

The Rust evidence collector instead aggregates all recent market rows for a candidate, requires all non-null pair-created timestamps in that aggregation to be identical, and does not constrain the selector by the authenticated quote mint. With a bounded `max_candidates` budget, unrelated quote pairs or multi-pair history can therefore consume or exclude evidence work before the candidates PAPER will actually evaluate.

## Goal

Align PAPER evidence candidate selection with the canonical current-market identity used by the PAPER coordinator while preserving evidence prewarming for too-young pairs.

## Non-goals

This change does not:

- change PAPER selection, safety, setup, scoring, decision, risk, or execution thresholds;
- change the 120-second PAPER market freshness ceiling;
- change the 1-to-30-minute fresh-launch strategy window;
- change quote economics, quote amount, slippage, taker, or provider;
- change the protected V2 manifest;
- grant model-fitting, promotion, wallet, signing, or LIVE authority.

## Design

Extend `EvidenceCandidateStore::fresh_launch_candidates` with a required quote mint supplied from `PaperEvidenceRuntimeConfig.quote_asset_mint`.

For candidates with recent market observations, resolve one canonical current market row by:

1. iterating configured market sources in priority order;
2. requiring `base_mint = candidate mint`;
3. requiring `quote_mint = configured quote asset mint`;
4. requiring the observation inside the configured current-market lookback;
5. rejecting rows where pair-created time is missing or later than observation;
6. choosing the newest matching row for the first source with a match.

Apply the maximum pair-age bound to that canonical row. Preserve the existing preferred-minimum-age ordering so too-young pairs may still be prewarmed after in-window candidates rather than being discarded.

Sort eligible candidates by:

1. in-window before too-young prewarm;
2. newest canonical current observation;
3. candidate id.

Apply `max_candidates` only after exact quote/source/current-row filtering.

## Acceptance

Tests must prove:

- a candidate with multiple recent pair-created timestamps is not discarded when its canonical exact-quote current row is valid;
- a more recent wrong-quote candidate cannot consume the bounded evidence budget ahead of an exact-quote candidate;
- source allow-list / priority remains deterministic;
- stale and expired candidates remain excluded;
- too-young prewarming remains available after in-window candidates;
- the evidence cycle passes the configured quote asset into selection and still collects exact bidirectional evidence;
- no trade, promotion, wallet, signing, or LIVE authority is introduced.

## Authority firewall

```text
PAPER_EVIDENCE_SELECTOR=ALIGN_TO_CANONICAL_MARKET_IDENTITY
TOO_YOUNG_PREWARM=PRESERVED
PAPER_THRESHOLDS=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
SCORING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
