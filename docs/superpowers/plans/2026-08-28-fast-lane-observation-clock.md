# Fast Lane Observation Clock Correction Plan

**Goal:** Make rolling Fast Lane state reflect the time information became available to Shreks, so sub-second windows remain meaningful for sources such as Pump whose onchain event timestamp is only second-resolution.

**Root cause:** `FastMarketState` currently prunes, windows, and validates ordering with `occurred_at_unix_ms`. Pump `tradeEvent.timestamp` is second-resolution, while Shreks records a higher-resolution `observed_at_unix_ms`. Using occurrence time collapses many real trades onto the same timestamp and also rejects valid late-arriving events.

**Correct invariant:**

- `sequence` controls deterministic ingestion order.
- `observed_at_unix_ms` controls point-in-time rolling windows and snapshot availability because that is when Shreks could actually act on the information.
- `occurred_at_unix_ms` remains immutable audit/chain evidence and may be older than a previously observed event.
- Replay remains deterministic because recorded observation timestamps are replayed unchanged.

**Scope:** `shreks-core` FastMarketState and its tests only. No provider, storage, observer, PAPER, risk, executor, deployment, or LIVE behavior changes.

## RED

Add tests proving:

1. two events with the same coarse occurrence timestamp are separated correctly by their observation timestamps in 100/250/500ms windows;
2. a late chain event with an older occurrence timestamp is accepted when sequence and observation order are monotonic;
3. observation time moving backward is rejected;
4. snapshots are rejected only when they precede the latest observation, not merely the latest chain occurrence.

Run `cargo test -p shreks-core --test fast_lane_state` and prove failure under current occurrence-clock behavior.

## GREEN

Change `FastMarketState` to:

- track `last_observed_at_unix_ms`;
- validate monotonic observation time;
- prune by observation time;
- build windows by observation time;
- interpret snapshot `as_of_unix_ms` on the observation clock;
- rename error variants/messages to observation-clock semantics.

Run focused tests, then full workspace CI including Rust, Python, repository safety, and ARM64.

## Merge gate

Diff must remain limited to this plan, `crates/shreks-core/src/fast_lane/state.rs`, and `crates/shreks-core/tests/fast_lane_state.rs`. Merge only after GREEN evidence. LIVE remains disabled.
