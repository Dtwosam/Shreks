# Phase D1 Wallet Observation Store Implementation Plan

**Goal:** Add durable, normalized wallet observations around known candidate mints without creating wallet intelligence or changing trading behavior.

**Base:** sealed C6 head `898224329ac23d90ec4696c688669ded077cc7ef`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-d1-wallet-observation-store-design.md`.

## Constraints

- Solana-only V1.
- Free-source compatible.
- Rust owns normalized wallet observation + SQLite persistence.
- No provider/RPC wiring in D1.
- No Python wallet score/profile/feature work.
- No trade reconstruction.
- No changes to B/C trading decisions, execution, accounting, or live-money authority.
- Missing/inferred wallet evidence must never be upgraded silently.
- TDD: one combined RED contract, one focused GREEN implementation, then README/final seal.
- Keep draft PR stacked on sealed C6 and unmerged.

---

## Task 1 — Design + plan

Create:

- `docs/superpowers/specs/2026-08-24-phase-d1-wallet-observation-store-design.md`
- `docs/superpowers/plans/2026-08-24-phase-d1-wallet-observation-store.md`

Commit atomically before implementation.

---

## Task 2 — Combined D1 RED contract

Create tests first:

- `crates/shreks-core/tests/wallet_observation.rs`
- `crates/shreks-storage/tests/wallet_observations.rs`

Modify schema test expectations only as required to assert migration 0007.

RED must require:

### Core domain

- exact `WalletActionKind` strings: `buy`, `sell`, `transfer`, `liquidity_event`, `creator_action`, `other`
- exact `WalletObservationEvidence` strings: `direct`, `inferred`
- normalized `WalletObservation` carrying provider/wallet/candidate/action/evidence/signature/event index/full u64 slot/local time/optional chain time/raw signed deltas/optional counter asset/venue/counterparty
- raw signed amount support beyond SQLite i64 range

### Migration/store

- schema version 7
- `wallet_observations` table and three intended indexes
- full-width u64 slot stored/recovered exactly
- signed i128 raw deltas stored/recovered exactly
- candidate mint must already exist in `token_candidates`
- blank critical identifiers and invalid timestamps fail closed
- counter-asset delta without mint fails closed
- first write returns `Inserted`
- identical replay returns `AlreadyPresent`
- replay with later local observation timestamp preserves earliest local observation
- replay changing action/evidence/slot/chain time/deltas/counter asset/venue/counterparty is rejected and original row remains unchanged
- same transaction may carry distinct event indexes
- deterministic inclusive time-bounded query by mint
- deterministic inclusive time-bounded query by wallet
- invalid `from > through`, zero limit, and over-limit request rejected
- file-backed close/reopen returns exact observations in the same deterministic order

The expected RED is missing core wallet types/storage API/migration 0007—not unrelated failures.

Open draft PR after RED commit so all subsequent CI is attached to the stacked review.

---

## Task 3 — Focused D1 GREEN implementation

Create:

- `crates/shreks-core/src/wallet.rs`
- `crates/shreks-storage/migrations/0007_wallet_observations.sql`
- `crates/shreks-storage/src/wallet.rs`

Modify:

- `crates/shreks-core/src/lib.rs` only to export the D1 domain types
- `crates/shreks-storage/src/lib.rs` only to register migration 0007, expose the D1 storage result type/module, and add the two query/write methods if method placement requires it
- existing schema-version tests only where the latest version changes from 6 to 7

Implementation rules:

- no wall-clock read for a wallet observation; caller supplies local observation time
- slots and raw signed deltas persist as canonical decimal text
- provider/action/evidence/venue parse from explicit allow-listed strings only
- candidate existence is checked by mint before insert
- uniqueness identity is provider/signature/event_index/wallet/candidate_mint
- identical immutable event evidence is idempotent
- later replay may only move stored local observation time earlier, never later
- contradictory immutable evidence fails before any mutation
- deterministic query order and inclusive bounds
- no dynamic SQL and no raw connection export

Run one CI inspection on GREEN head. Fix only concrete D1 defects.

---

## Task 4 — Documentation + final seal

Update `README.md` with one D1 section covering:

- normalized wallet action vocabulary,
- direct vs inferred evidence,
- point-in-time local observation clock,
- exact raw amount/slot preservation,
- idempotent/contradiction-safe replay,
- deterministic restart-safe queries,
- explicit non-scope of D2–D5 wallet intelligence.

Replace this plan with a concise verification record after implementation evidence is complete. Do not put the eventual final SHA/run into tracked docs.

Freeze branch and compare exact C6 -> D1 diff.

Require one fresh exact-head CI with:

- Rust tests GREEN,
- workspace metadata GREEN,
- Python tests GREEN unchanged,
- repository safety GREEN.

Put the final D1 SHA/run only in draft PR metadata. Leave PR draft/unmerged.

## Expected D1 diff

Target files:

- `README.md`
- `crates/shreks-core/src/lib.rs`
- `crates/shreks-core/src/wallet.rs`
- `crates/shreks-core/tests/wallet_observation.rs`
- `crates/shreks-storage/migrations/0007_wallet_observations.sql`
- `crates/shreks-storage/src/lib.rs`
- `crates/shreks-storage/src/wallet.rs`
- `crates/shreks-storage/tests/database.rs`
- `crates/shreks-storage/tests/outcome_checkpoints.rs` only if it still hard-codes latest schema
- `crates/shreks-storage/tests/pump_migration_storage.rs` only if it still hard-codes latest schema
- `crates/shreks-storage/tests/wallet_observations.rs`
- `docs/superpowers/plans/2026-08-24-phase-d1-wallet-observation-store.md`
- `docs/superpowers/specs/2026-08-24-phase-d1-wallet-observation-store-design.md`

No B/C Python trading implementation file should change.

## D1 completion claim

D1 may be called complete only when normalized wallet observations survive restart with deterministic, contradiction-safe replay and query semantics while no wallet-derived trade signal exists yet.