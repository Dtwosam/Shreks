# G2 production PAPER seal — canonical Fresh Launch pair selection

Date: 2026-08-28

## Purpose

Seal the production diagnosis and correction for Fresh Launch candidate selection when one token mint has market snapshots for multiple Solana pairs with different pair-creation timestamps.

**LIVE TRADING: DISABLED.**

## Physical production diagnosis

Read-only VPS diagnostics against the then-deployed PAPER runtime reported the following selector contract:

- selection lookback: `1800000` ms;
- Fresh Launch minimum pair age: `60000` ms;
- Fresh Launch maximum pair age: `1800000` ms;
- current-market maximum age: `120000` ms;
- market source priority: `dexscreener,meteora`;
- maximum entry candidates: `2`.

The read-only selector funnel at `1787910926965` ms was:

- recent market candidates: `543`;
- pair-created timestamp missing: `2`;
- pair-created timestamp contradictory across snapshots: `270`;
- pair-created timestamp globally consistent: `271`;
- pair-age eligible under the old global-consistency query: `0`;
- final selector eligible: `0`.

Market activity was healthy enough to reject a generic freshness outage explanation:

- DEX Screener: `624` snapshots / `288` candidates in five minutes, newest age `451` ms;
- Meteora: `391` snapshots / `70` candidates in five minutes, newest age `7428` ms.

The same host reported `40655` candidates discovered in 24 hours and `1015` market snapshots in five minutes. No write was performed by the diagnosis and LIVE remained disabled.

## Root cause

`ObserverCampaignCandidateStore.recent_candidates()` previously applied Fresh Launch pair age by grouping every market snapshot for one candidate and requiring:

`MIN(pair_created_at_unix_ms) = MAX(pair_created_at_unix_ms)`

A token can legitimately have several Solana pairs. DEX Screener token-pair reads can therefore persist multiple `pair_address` values, each with its own creation timestamp, under the same observed candidate. The old selector treated this normal multi-pair condition as contradictory age evidence and excluded the candidate.

That contract disagreed with the already-sealed downstream `ObserverMarketStore.load_window()` behavior. The market adapter chooses one deterministic current snapshot using:

1. configured source priority;
2. the configured current-market freshness window;
3. newest `observed_at_unix_ms`;
4. stable row-id ordering;

and then locks the feature window to that snapshot's exact source and pair address.

Therefore Fresh Launch age eligibility and downstream feature assembly could reason about different pair identities.

## Corrected behavior

When both a Fresh Launch pair-age window and an `ObserverMarketReadPolicy` are supplied, the candidate selector now:

1. enumerates point-in-time recent candidates;
2. resolves the same deterministic current snapshot semantics used by the downstream market adapter;
3. uses that current snapshot's `pair_created_at_unix_ms` for Fresh Launch age eligibility;
4. excludes candidates whose canonical current snapshot has no usable pair-created timestamp;
5. keeps the existing mature-before-too-young prioritization;
6. keeps deterministic ordering by current observation time and candidate id;
7. keeps the existing maximum candidate bound.

The generic selector path with no market-read policy retains its previous behavior. No safety, score, decision, risk, sizing, execution, fill, exit, or LIVE threshold was changed.

## TDD evidence

RED branch commit:

`16fbfdcd0d01b3e6ea9301d2b19083ecfeceeab6`

RED CI run:

`33161615435`

Python failed causally with exactly one new regression failure and `2627` existing tests passing. The failing case had one fresh canonical DEX Screener pair plus one expired secondary pair for the same candidate. Production returned no candidate where the canonical-pair contract required selection.

GREEN implementation commit:

`289f2568cb6df4114837122747a4a9cb749b34e2`

GREEN PR CI run:

`33161927033`

All four repository gates passed:

- Python tests GREEN;
- Rust tests GREEN;
- repository safety GREEN;
- native ARM64 release build GREEN.

The regression suite proves both directions:

1. a fresh canonical current pair is not rejected merely because another pair for the same mint is older; and
2. a fresh secondary pair cannot rescue a candidate whose canonical current pair is expired.

PR #69 was squash-merged as:

`b15a90df55d38eda5ddafecf18317229a2ddb30c`

Merged-main CI run:

`33162130191`

All four repository gates passed again.

## Preserved safety and authority invariants

- B1 safety vetoes remain unchanged.
- Missing or stale current market evidence still fails closed.
- Missing canonical pair-created evidence still fails closed.
- Fresh Launch minimum and maximum age thresholds are unchanged.
- Liquidity, holder, flow, score, decision, risk, sizing, loss, drawdown, slippage, fill, and exit thresholds are unchanged.
- No wallet, signing, transaction-submission, promotion, or LIVE authority is added.
- LIVE remains disabled.
- Profitability remains unproven until production PAPER evidence establishes sufficient independent trades after realistic costs.

## Remaining production question

This fix removes false multi-pair rejection only. It does not claim that the broad DEX Screener profile/boost discovery stream reliably supplies genuinely new 1–30 minute launches, nor that the high-resolution sampler can keep up with all broad-discovery candidates. Physical post-deploy selector evidence is required before attributing any remaining zero-trade condition to scoring/risk or changing strategy thresholds.
