# Phase D1 Wallet Observation Store Design

**Date:** 2026-08-24  
**Base:** sealed C6 head `898224329ac23d90ec4696c688669ded077cc7ef`  
**Source order:** Phase D1 — Wallet Observation Store

## Goal

Build the first durable wallet-evidence layer for Shreks by recording normalized wallet actions relevant to already-observed candidate mints.

D1 is observation infrastructure only. It must preserve what Shreks actually observed and when Shreks first observed it. It must not rank wallets, reconstruct exact trades, infer coordinated clusters, create smart-wallet features, or change any trading decision.

## Source constraints

The project source of truth requires D1 to “record relevant wallet actions around candidates.” D2 later owns trade reconstruction, D3 wallet profiles, D4 independence/clustering heuristics, and D5 smart-wallet features. Therefore D1 must not pre-empt those phases.

Existing architecture remains unchanged:

- Rust owns Solana-facing normalized event creation and operational storage.
- Python owns later wallet intelligence/research.
- SQLite WAL remains the operational store.
- V1 stays Solana-only and free-source compatible.
- No live-money path is introduced.

## Scope

D1 adds:

1. normalized Rust wallet-observation domain types,
2. SQLite migration 0007 for durable wallet observations,
3. idempotent/contradiction-safe persistence,
4. deterministic time-bounded queries by candidate mint and wallet,
5. restart persistence tests,
6. README documentation of the D1 boundary.

## Explicit non-scope

D1 does **not** add:

- Helius polling/subscriptions or new RPC calls,
- historical wallet backfills,
- trade reconstruction or realized wallet PnL,
- wallet quality scores or rankings,
- estimated expectancy,
- wallet clustering/link analysis,
- “smart wallet” confirmations,
- B2 feature-schema changes,
- strategy/setup/score/decision/risk changes,
- paper execution/accounting changes,
- signer/transaction construction/submission,
- live trading.

Provider ingestion can be wired later once the normalized storage boundary is proven.

## Domain model

Add `crates/shreks-core/src/wallet.rs` and re-export the stable D1 types from `shreks_core`.

### `WalletActionKind`

Stable broad action vocabulary:

- `Buy`
- `Sell`
- `Transfer`
- `LiquidityEvent`
- `CreatorAction`
- `Other`

These labels describe the normalized observation classification. They are not a claim that D1 has reconstructed full entry/exit economics.

### `WalletObservationEvidence`

- `Direct`
- `Inferred`

`Direct` means the adapter had explicit transaction/account evidence for the action classification. `Inferred` means the adapter normalized the action from indirect but still recorded evidence. D1 stores this distinction rather than silently promoting inferred evidence to fact.

### `WalletObservation`

Fields:

- `provider: ProviderId`
- `wallet: String`
- `candidate_mint: String`
- `action: WalletActionKind`
- `evidence: WalletObservationEvidence`
- `signature: String`
- `event_index: u32`
- `slot: u64`
- `observed_at_unix_ms: i64`
- `occurred_at_unix_ms: Option<i64>`
- `candidate_token_delta_raw: Option<i128>`
- `counter_asset_mint: Option<String>`
- `counter_asset_delta_raw: Option<i128>`
- `venue: Option<VenueId>`
- `counterparty: Option<String>`

### Point-in-time semantics

`observed_at_unix_ms` is the decision-safe local observation clock. Optional `occurred_at_unix_ms` is chain/audit metadata only and cannot make an observation historically available before Shreks actually observed it.

A historical chain action fetched later therefore remains available only from its local observation timestamp onward.

### Raw amounts

Candidate-token and counter-asset deltas are signed raw integer units, not floating-point UI amounts. This avoids decimal/rounding loss and preserves direction without pretending D1 knows exact trade cost basis.

The candidate delta may be absent. A counter-asset delta requires a counter-asset mint. D1 does not require every action to expose both sides of a swap.

`i128` is used in memory so the signed representation can safely cover full-width Solana token amounts. SQLite stores these deltas as canonical decimal text rather than signed 64-bit integers.

Full-width Solana `u64` slots are also stored as decimal text, matching existing storage precedent.

## Validation

The normalized domain/storage boundary rejects:

- blank wallet, candidate mint, or signature,
- negative local/chain timestamps,
- blank optional counter-asset mint/counterparty values,
- a counter-asset delta without a counter-asset mint,
- unsupported enum strings recovered from storage,
- malformed decimal-text slots/deltas,
- candidate mints that are not already present in `token_candidates` at write time.

D1 deliberately does **not** require `occurred_at <= observed_at` because chain block times and local clocks are not guaranteed to be perfectly aligned.

D1 also does not require wallet observations to occur after candidate discovery. Pre-discovery activity around a mint can be valuable research evidence once the mint becomes a candidate, but its local observation time still controls historical availability.

## Durable identity and replay

The immutable event identity is:

`provider + signature + event_index + wallet + candidate_mint`

This supports multiple normalized wallet actions from one transaction while keeping deterministic replay.

For an existing identity:

- if all immutable evidence fields match, replay is idempotent;
- `observed_at_unix_ms` may be later on replay; storage preserves the earliest local observation time;
- any difference in action, evidence class, slot, chain time, deltas, counter asset, venue, or counterparty is a contradiction and the write fails closed;
- no replay silently rewrites economic/classification history.

A successful new insert returns `Inserted`; an identical replay returns `AlreadyPresent`.

## SQLite migration 0007

Create `wallet_observations` with fields corresponding to the normalized model.

Key storage choices:

- `slot TEXT NOT NULL`
- signed raw deltas as nullable `TEXT`
- `event_index INTEGER NOT NULL CHECK (event_index >= 0)`
- nonnegative timestamp checks
- action/evidence `CHECK` constraints
- uniqueness on `(provider, signature, event_index, wallet, candidate_mint)`
- check that `counter_asset_delta_raw` cannot exist without `counter_asset_mint`

Indexes:

- `(candidate_mint, observed_at_unix_ms, signature, event_index)`
- `(wallet, observed_at_unix_ms, signature, event_index)`
- `(provider, signature)`

No foreign key is placed directly on `candidate_mint` because `token_candidates.mint` is indexed but intentionally not globally unique across pair/source identities. The storage API performs an explicit candidate-existence check before inserting.

## Storage API

Add a small dedicated `wallet` storage module.

Public storage types:

### `WalletObservationWrite`

- `Inserted`
- `AlreadyPresent`

### Methods on `ShreksDb`

`record_wallet_observation(&WalletObservation) -> Result<WalletObservationWrite, StorageError>`

`wallet_observations_for_mint(mint, observed_from_unix_ms, observed_through_unix_ms, limit) -> Result<Vec<WalletObservation>, StorageError>`

`wallet_observations_for_wallet(wallet, observed_from_unix_ms, observed_through_unix_ms, limit) -> Result<Vec<WalletObservation>, StorageError>`

Query rules:

- inclusive time bounds,
- `from <= through`,
- positive bounded limit,
- chronological deterministic order by `observed_at_unix_ms`, then provider/signature/event index/wallet/mint as needed for a total order,
- no wall-clock reads during query,
- query returns the normalized core type, not raw SQLite rows.

## Candidate relevance rule

D1 records observations only after the mint is already known to the observer as a candidate. The existence check is by mint rather than one specific candidate row so duplicate pair/source discovery identities do not duplicate the same on-chain wallet event.

D1 does not claim that every holder or every historical wallet is relevant. Selection/backfill policy belongs to later ingestion work and must respect free-provider budgets.

## Safety and research integrity

- Missing wallet evidence remains missing.
- `Inferred` remains distinguishable from `Direct`.
- Transfers are not automatically reclassified as buys or sells.
- Creator actions are not automatically negative or positive.
- One wallet action is not a trading signal.
- D1 does not create a wallet score or confidence.
- No wallet action may override B1 safety or any existing trading guardrail.

## TDD contract

One combined RED gate will require:

1. stable enum string vocabulary,
2. full-width slot and signed raw-delta round-trip,
3. migration schema version 7/table/indexes,
4. candidate-existence enforcement,
5. insert + identical replay idempotency,
6. earliest local observation timestamp preservation on replay,
7. contradictory replay rejection without mutation,
8. deterministic bounded queries by mint and wallet,
9. invalid chronology/bounds/input rejection,
10. file-backed restart persistence.

Then one focused GREEN implementation will add only the core model, migration, storage module/exports, and minimal schema-version test alignments.

## D1 exit condition

D1 is complete when Shreks can durably and reproducibly store normalized wallet actions around known candidate mints, replay them safely, query them deterministically after restart, and preserve uncertainty without exposing any wallet-derived trading signal.

This does not prove that wallet behavior improves trading results. That question belongs to D2–D6 and later evaluation.