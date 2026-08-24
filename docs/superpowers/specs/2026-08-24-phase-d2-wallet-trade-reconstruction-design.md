# Phase D2 Wallet Trade Reconstruction Design

**Date:** 2026-08-24  
**Base:** sealed D1 head `0e8872f84ef357f059c884f04f95269eb0361f6c`  
**Source order:** Phase D2 — Wallet Trade Reconstruction

## Goal

Estimate wallet entries, exits, and closed trade outcomes from normalized D1 wallet observations where the evidence is sufficient, while making uncertainty explicit and refusing to manufacture precision when inventory or economics become ambiguous.

D2 is research intelligence only. It does not rank wallets, create smart-wallet features, change any B/C trading decision, call providers, read SQLite itself, or enable live money.

## Source constraints

The build order requires D2 to “estimate entries/exits/outcomes where possible without pretending uncertain reconstruction is exact.” D3 later builds confidence-weighted wallet profiles, D4 handles independence/clustering, and D5 exposes validated wallet features. Therefore D2 produces reconstructable trade episodes plus explicit unresolved evidence; it does not decide whether a wallet is good.

The master architecture remains unchanged:

- Rust owns D1 Solana-facing normalized wallet observation truth and operational storage.
- Python owns wallet intelligence and research.
- `observed_at_unix_ms`, not optional chain time, is the point-in-time availability clock.
- Missing/uncertain evidence stays missing/uncertain.
- V1 remains Solana-only and live execution remains disabled.

## Package boundary

Create `python/src/shreks_brain/wallets/` as the Python wallet-intelligence package. D2 adds only:

- `models.py` — immutable observation/reconstruction models and stable vocabularies,
- `reconstruction.py` — pure deterministic episode reconstruction,
- `__init__.py` — exact public API.

No storage/provider dependency is imported. A later adapter may translate D1 SQLite/Rust observations into the Python `WalletObservation` mirror, but D2 itself consumes caller-supplied point-in-time observations only.

## Python D1 observation mirror

D2 mirrors the stable D1 fields needed by Python research without redefining provider or venue policy.

### `WalletActionKind`

Stable string values matching D1:

- `buy`
- `sell`
- `transfer`
- `liquidity_event`
- `creator_action`
- `other`

### `WalletObservationEvidence`

- `direct`
- `inferred`

### `WalletObservation`

Immutable fields:

- `provider: str`
- `wallet: str`
- `candidate_mint: str`
- `action: WalletActionKind`
- `evidence: WalletObservationEvidence`
- `signature: str`
- `event_index: int`
- `slot: int`
- `observed_at_unix_ms: int`
- `occurred_at_unix_ms: int | None`
- `candidate_token_delta_raw: int | None`
- `counter_asset_mint: str | None`
- `counter_asset_delta_raw: int | None`
- `venue: str | None`
- `counterparty: str | None`

Validation mirrors D1’s durable boundary: nonblank identity strings, nonnegative event index/slot/timestamps, nonblank optional strings, and counter-asset delta requiring a counter-asset mint. Python integers preserve the Rust `u64`/`i128` value ranges without narrowing.

D2 does not require `occurred_at <= observed_at`. Optional chain time is audit metadata only.

## Reconstruction output

### `WalletTradeEpisodeState`

- `OPEN` — a clean known-inventory episode has not yet returned to zero.
- `CLOSED` — observed qualifying BUY/SELL legs returned known inventory to zero using one counter asset.
- `UNRESOLVED` — the episode became ambiguous and no outcome may be claimed.

### `WalletTradeEvidenceQuality`

- `DIRECT` — every economic BUY/SELL leg was classified from direct evidence.
- `MIXED` — both direct and inferred economic legs were used.
- `INFERRED` — every economic leg was inferred.

This is evidence provenance, not a wallet-quality score or probability.

### `WalletTradeFindingCode`

Stable audit reasons:

- `BUY_ECONOMICS_INCOMPLETE`
- `SELL_ECONOMICS_INCOMPLETE`
- `BUY_DELTA_DIRECTION_INVALID`
- `SELL_DELTA_DIRECTION_INVALID`
- `SELL_WITHOUT_KNOWN_ENTRY`
- `SELL_EXCEEDS_KNOWN_INVENTORY`
- `COUNTER_ASSET_CHANGED`
- `NON_TRADE_INVENTORY_CHANGE`
- `OPEN_POSITION`

Structural duplicate/future/input contradictions raise `ValueError` instead of being converted into trade findings.

### `WalletTradeEpisode`

One clean or unresolved inventory episode contains:

- wallet/mint,
- deterministic zero-based `episode_index`,
- state and evidence quality,
- first/last local observation timestamps,
- optional close timestamp,
- single counter-asset mint when known,
- total candidate quantity bought/sold in raw units,
- remaining known quantity,
- observed entry cost in positive counter-asset raw units,
- observed exit proceeds in positive counter-asset raw units,
- `estimated_realized_pnl_counter_raw: int | None`,
- `estimated_return_pct: float | None`,
- ordered BUY/SELL observation identities used,
- ordered findings.

A CLOSED clean episode computes:

`estimated_realized_pnl_counter_raw = total_exit_proceeds_counter_raw - total_entry_cost_counter_raw`

`estimated_return_pct = (total_exit_proceeds_counter_raw / total_entry_cost_counter_raw - 1) * 100`

No PnL/return is emitted for OPEN or UNRESOLVED episodes.

Because the episode closes at zero known inventory, D2 never needs to invent a proportional raw-unit cost allocation for partial exits. Partial sells are accumulated until the known inventory reaches zero; only then is a closed outcome computed.

The values remain explicitly **estimated** because observation coverage, fees, and classifications may still be incomplete even when arithmetic over the supplied deltas is exact.

### `WalletTradeReconstruction`

Report fields:

- wallet,
- candidate mint,
- as-of timestamp,
- ordered episode tuple,
- report-level finding tuple,
- `halted_on_uncertain_inventory: bool`.

Once inventory continuity becomes uncertain, D2-v1 halts further reconstruction for that wallet/mint. It will not start a later apparently-clean trade cycle because unknown pre-existing inventory could contaminate subsequent sells.

## Point-in-time and duplicate rules

`reconstruct_wallet_trades(wallet, candidate_mint, observations, as_of_unix_ms)` is pure and deterministic.

It requires every supplied observation to match the requested wallet/mint and to have `observed_at_unix_ms <= as_of_unix_ms`. Future local observations are rejected even if their chain time is old.

Ordering is by:

`observed_at_unix_ms, provider, signature, event_index`

`occurred_at_unix_ms` never controls historical ordering.

Duplicate D1 identities use:

`provider + signature + event_index + wallet + candidate_mint`

Exact duplicate evidence is deduplicated before arithmetic and the earliest local observation timestamp wins. A duplicate identity with different immutable economic/classification evidence is a structural contradiction and raises `ValueError`.

## Qualifying BUY/SELL economics

A reconstructable BUY requires:

- action `buy`,
- `candidate_token_delta_raw > 0`,
- counter-asset mint present,
- `counter_asset_delta_raw < 0`.

Entry cost is `abs(counter_asset_delta_raw)`.

A reconstructable SELL requires:

- action `sell`,
- `candidate_token_delta_raw < 0`,
- counter-asset mint present,
- `counter_asset_delta_raw > 0`.

Sold quantity is `abs(candidate_token_delta_raw)` and proceeds are the positive counter-asset delta.

Missing economics or contradictory signs make inventory/economics unresolved rather than guessed.

## Episode state machine

1. A qualifying BUY with no active episode starts known inventory.
2. More qualifying BUYs using the same counter asset add quantity/cost.
3. Qualifying SELLs using the same counter asset reduce known quantity and add proceeds.
4. A SELL larger than known quantity invalidates continuity.
5. When known quantity returns exactly to zero, the episode closes and outcome is computed from aggregate observed cost/proceeds.
6. A later qualifying BUY may start a new clean episode after a clean CLOSED episode.
7. A SELL before a known entry halts reconstruction: starting inventory is unknown.
8. Changing counter asset inside an episode halts reconstruction because D2-v1 has no point-in-time FX conversion layer.
9. A transfer/liquidity/creator/other observation with a nonzero candidate-token delta halts reconstruction because inventory moved outside the reconstructed BUY/SELL path.
10. A non-trade observation with no/zero candidate-token delta is ignored for inventory arithmetic.
11. If a clean episode remains open at `as_of_unix_ms`, it is returned OPEN with an `OPEN_POSITION` finding and no outcome.

## Evidence quality

Only economic BUY/SELL legs contribute to episode evidence quality.

- all direct => `DIRECT`
- all inferred => `INFERRED`
- mixture => `MIXED`

D2 does not translate this enum into a numeric confidence. D3 owns confidence weighting across histories/sample sizes.

## Safety and research integrity

D2 must never:

- infer a BUY/SELL from a transfer solely because balances changed,
- convert missing counter-asset economics into zero,
- use future local observations,
- use chain time to backdate availability,
- aggregate different counter assets without an explicit conversion layer,
- claim a realized outcome while known inventory remains open,
- resume outcome reconstruction after inventory continuity is lost,
- label an episode or wallet “smart,”
- feed wallet evidence into B2/B7/B8/B9/C4 yet.

## Public API

Exact D2 public symbols:

1. `WalletActionKind`
2. `WalletObservation`
3. `WalletObservationEvidence`
4. `WalletTradeEpisode`
5. `WalletTradeEpisodeState`
6. `WalletTradeEvidenceQuality`
7. `WalletTradeFinding`
8. `WalletTradeFindingCode`
9. `WalletTradeReconstruction`
10. `reconstruct_wallet_trades`

## TDD / CI strategy

To minimize CI churn while preserving RED/GREEN evidence:

- one combined RED commit adds model, engine, and public-API tests and must fail because `shreks_brain.wallets` does not exist;
- one focused GREEN commit adds only the D2 package and must make the full repository CI green;
- one final README/verification commit freezes the branch and triggers one exact-head seal CI.

## D2 exit condition

D2 is complete when caller-supplied D1 observations can be deterministically reconstructed into clean OPEN/CLOSED episodes or explicit UNRESOLVED evidence without leakage or false precision, with closed same-counter-asset outcomes estimated only after known inventory returns to zero.

This does not prove wallet behavior improves Shreks trading. D3 profile construction is next.