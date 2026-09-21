# G1C V2 Quote-Valuation Reference — Design

**Date:** 2026-09-21  
**Status:** read-only evidence capture only; no production candidate-value authority

## Purpose

The evidence-only G1C v2 entry-sizing proposal requires three externally reviewed target inputs:

- target quote decimals;
- target quote USD-per-token reference;
- a fingerprint/timestamp identifying the valuation evidence.

WSOL decimals are already canonical repository protocol knowledge: 9.

The remaining missing evidence is a bounded, attributable WSOL/USD reference.

The existing FL9 runtime quote-evidence diagnostic intentionally exposes only recent quote-mint identity/count/timestamp. It does not expose a USD rate or evidence fingerprint and must not be widened silently.

The existing sealed observer-market API already derives quote-token USD value from one exact persisted market row:

`quote_asset_usd_per_token = price_usd / price_native`

This slice wraps that existing read-only derivation in one canonical evidence artifact.

## Inputs

All market-selection inputs are explicit:

- observer SQLite database path;
- candidate id;
- `as_of_unix_ms`;
- source;
- venue;
- base mint;
- quote mint;
- maximum age in milliseconds;
- optional expected market row id;
- new artifact destination.

There are no production host defaults.

## Read-only evidence path

The implementation calls only:

`ObserverMarketStore.quote_asset_usd_evidence(...)`

The store opens SQLite through URI `mode=ro`.

Selection is deterministic:

- exact candidate id;
- exact source;
- exact venue;
- exact base mint;
- exact quote mint;
- bounded observation age;
- latest matching row by the existing sealed ordering.

When `expected_market_row_id` is supplied, any row mismatch fails closed.

The implementation does not query an external provider and does not substitute a current internet price.

## Artifact

The artifact is canonical JSON, mode `0600`, write-once, and self-fingerprinted.

It records:

- schema/status;
- valuation mode `exact_market_ratio`;
- selected market row id;
- candidate id;
- row observation timestamp;
- requested as-of/freshness boundary;
- source/venue/pair/base/quote identity;
- exact persisted base-price-in-quote text;
- canonical decimal base USD price;
- canonical decimal derived quote USD-per-token;
- explicit non-authority fields;
- `reference_fingerprint_sha256`.

The reference fingerprint is suitable as the `quote_evidence_fingerprint_sha256` input of the already-merged entry-sizing proposal.

## Authority boundary

Always:

- `status=REFERENCE_EVIDENCE_ONLY`;
- `candidate_value_authority=NOT_GRANTED`;
- `candidate_authoring_authority=NOT_GRANTED`;
- `rotation_authority=NOT_GRANTED`;
- `scoring_authority=NOT_GRANTED`;
- `paper_promotion_authority=BLOCKED`;
- `live_authority=DISABLED`.

This slice does not choose an entry size.

It does not call the sizing proposal automatically.

It does not create candidate authority, author a candidate, create a transition binding, execute readiness, rotate a manifest, score/fit, promote, sign, submit, or enable LIVE.

## Next boundary

After this implementation is merged, production use still requires a separate seal/deploy/presence slice before a trusted administrator may capture one protected reference from the live observer database.

A later review may feed that exact reference into the evidence-only sizing proposal. The resulting proposed raw amount remains non-authoritative until a separate production candidate-value decision explicitly accepts it.
