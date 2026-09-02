# FL4 Multi-Horizon Future-Path Labels Design

**Base proof:** `c63cf234989bea3b14474af88af9277a5d5b25fc` (FL3 merged-main four-gate GREEN)

## Goal

Create deterministic, point-in-time-safe future-path labels from the canonical FastEvent journal so Shreks can train and evaluate microstructure decisions without leaking future information or confusing missing capture with a genuine flat/no-trade future.

## Non-goals

FL4 does not create trading authority, strategy scores, learned models, PAPER orders, signers, transaction submission, provider fallback changes, release/deploy changes, or LIVE authorization.

## Decision clock and leakage rule

A decision is anchored to canonical `observed_at_unix_ms`, not transaction occurrence time. Future observations used by a label must satisfy:

- same canonical market identity,
- sequence strictly greater than the decision sequence,
- `observed_at_unix_ms` strictly greater than the decision timestamp,
- `observed_at_unix_ms <= decision_at + horizon_ms`.

An event that occurred earlier on-chain but was observed after the decision is future information for that decision and is therefore eligible only after its canonical observation time. No FL4 label is allowed to mutate or enter `FastMarketState`; labels remain a separate derived research surface.

## Horizons

Version 1 exposes these evidence-supported millisecond horizons:

`250, 500, 1_000, 3_000, 5_000, 10_000, 30_000, 60_000, 300_000, 900_000, 1_800_000, 3_600_000`.

They are labeling horizons, never action timers. Callers may request a validated subset/order, but duplicate, zero, or unsorted horizons fail closed.

## Coverage and completeness

Label completeness is explicit. The caller supplies a canonical coverage watermark and whether the source interval is known contiguous.

A horizon is `Complete` only when:

- canonical coverage is declared contiguous, and
- `complete_through_unix_ms >= decision_at_unix_ms + horizon_ms`.

Otherwise it is `Incomplete`. Incomplete horizons expose no path/return metrics.

A complete horizon with zero future events is distinct from an incomplete horizon:

- status = complete,
- `event_count = 0`,
- `no_trade_events = true`,
- endpoint/excursion/reversal/economic metrics remain `None` because no executable future trade observation exists.

This preserves the difference between “the stream was complete and no trade event occurred” and “we do not know what happened.”

## Label metrics

For a complete horizon with at least one future event, FL4 derives from canonical observed prices:

- endpoint executable-observation return in basis points from the decision price to the last future event in the horizon,
- MFE and MAE in basis points over all future events in the horizon,
- time from decision to local peak and local trough,
- decision-price-cross reversal occurrence and first reversal timing,
- event count and endpoint event identity.

Reversal is threshold-free and deterministic: the first future price establishes the initial side of the decision price; reversal occurs at the first later future event that reaches or crosses the decision price in the opposite direction. If the first future price exactly equals the decision price, reversal direction remains undefined until a later event moves away from the decision price.

## Route, capacity, and cost-adjusted annotations

FL4 can consume optional, source-backed annotations aligned to a future FastEvent identity:

- `route_available: Option<bool>`,
- `exit_capacity_base: Option<f64>`,
- `executable_exit_net_quote: Option<f64>`.

These values are never guessed. Missing evidence remains `None`.

For each complete horizon FL4 may derive:

- minimum and endpoint observed exit capacity,
- whether route unavailability was observed,
- best and endpoint cost-adjusted net return in basis points when both decision `entry_total_quote` and future executable exit-net evidence exist.

Cost-adjusted return is `(exit_net_quote / entry_total_quote - 1) * 10_000`. FL4 does not recompute fees from current protocol constants and does not backfill historical missing economics.

## Core API

Add a focused `fast_lane/future_path.rs` module with versioned types:

- `FUTURE_PATH_LABEL_VERSION: u16 = 1`
- `DEFAULT_FUTURE_PATH_HORIZONS_MS`
- `FuturePathDecision`
- `FuturePathObservation`
- `FuturePathCoverage`
- `FuturePathCompleteness`
- `FuturePathLabel`
- `FuturePathLabelError`
- `label_future_paths(...)`

`FuturePathObservation::from_event` copies immutable FastEvent identity/time/price and starts with all optional route/economic annotations unknown. Builder-style annotation methods validate finite/non-negative economics.

## Determinism and ordering

Input observations must be strictly increasing in canonical sequence and non-decreasing in canonical observation time. Duplicate identities, duplicate/non-monotonic sequence, market mismatch, observations at/before the decision sequence/timestamp, invalid numeric annotations, or malformed horizons fail closed.

The same decision, ordered observations, coverage, and horizons must produce byte-for-byte-equivalent serializable field values apart from normal floating-point representation already used by Fast Lane domain types.

## Durable derived labels

Migration 16 adds `fast_future_path_labels`, a derived research table keyed by:

`(decision_signature, decision_ordinal, horizon_ms, label_version)`.

Rows retain:

- decision canonical identity/sequence/market/timestamp/price,
- coverage watermark/contiguity,
- completeness,
- event count/no-trade flag,
- endpoint identity/time/price/return,
- MFE/MAE and peak/trough timings,
- reversal fields,
- capacity/route fields,
- cost-adjusted fields.

The table references the canonical decision FastEvent identity. Values are derived and reproducible; they do not replace raw/canonical evidence.

Writes are exact and idempotent. An exact duplicate returns unchanged; the same primary identity with different label contents fails closed rather than overwriting training evidence. Historical rows are never silently relabeled under a new version.

## Label generation from storage

Storage exposes bounded reads of canonical future events for one market after a decision sequence and up to a caller-provided observation-time boundary. Existing raw-conflict quarantine rules remain authoritative: ambiguous canonical markets fail closed through the existing replay path.

A storage helper persists a complete set of labels for one decision only after core validation succeeds. It does not claim completeness itself; the caller must provide a truthful coverage watermark/continuity assertion from the ingestion/replay boundary.

## TDD/proof requirements

Required RED/GREEN coverage includes:

1. exact horizon-boundary inclusion and post-boundary exclusion,
2. canonical observation clock defeating late-arrival leakage,
3. complete no-trade horizon vs incomplete horizon,
4. endpoint return, MFE, MAE, peak/trough timing,
5. deterministic reversal timing,
6. optional route/capacity/economic annotations without guessed defaults,
7. invalid ordering/market/horizon/numeric inputs fail closed,
8. migration 16 schema and exact/idempotent/conflicting label writes,
9. deterministic storage round-trip,
10. no changes to PAPER/signing/submission/LIVE authority.

Final FL4 completion requires the established four gates on the exact PR head and again on the merged-main commit:

- Repository safety,
- Rust workspace,
- Python suite,
- native ARM64 release build + bundle verification.

## Exit criterion

FL4 is complete when Shreks can generate and durably retain deterministic multi-horizon future-path labels from canonical FastEvents with explicit completeness, point-in-time-safe clocks, path excursions/reversal timing, and optional source-backed execution/capacity economics—without granting any capital authority.
