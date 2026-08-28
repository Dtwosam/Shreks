# Verified Pump launch market-evidence production fix

Date: 2026-08-28

## Production evidence before fix

Read-only VPS diagnostics on sealed release `330ace280067905b6502ba3846f73b2b461be125` proved:

- `PUMP_VERIFIED_5M=135`
- `PUMP_WITH_MARKET_SNAPSHOT_5M=0`
- `PUMP_VERIFIED_30M=665`
- `PUMP_WITH_MARKET_SNAPSHOT_30M=0`
- `PUMP_VERIFIED_24H=41191`
- `PUMP_WITH_MARKET_SNAPSHOT_24H=0`
- `NEW_CANONICAL_ELIGIBLE=0`
- aggregate PAPER cycle assembly succeeded but contained zero entry candidates and zero quotes
- LIVE trading remained disabled

The canonical-pair selector correction was therefore valid but not the active production blocker.

## Root cause

The lifecycle observer verifies Pump Create/CreateV2 transactions, persists the normalized token candidate, ensures outcome checkpoints, and links the verified Pump signal to the candidate. `Observer::run_cycle` then sends newly verified candidates through market observation.

Production `build_lifecycle_observer` attached Helius chain and transaction providers but no market provider. Therefore the verified Pump candidate path had no market adapter to call. Observer V2 separately owned DEX Screener profile/boost discovery and dense public-market sampling, but it did not import the verified Pump candidate identity.

This produced the measured state: verified Pump candidates existed durably, but none had market snapshots, so the Fresh Launch PAPER selector had no current market evidence to evaluate.

## Safety-preserving fix

PR #70 adds a dedicated optional Pump-only market provider to the observe-only `Observer`.

- The provider is invoked immediately after a Pump launch is verified and linked to its candidate ID.
- The same existing provider pacing, health accounting, snapshot identity validation, and SQLite persistence are reused.
- Production wires DEX Screener to this Pump-only lane when DEX Screener is enabled.
- The lifecycle observer still has no public discovery provider.
- The lifecycle observer still has no general market provider, so it does not duplicate Observer V2 discovery or due-outcome market sampling.
- No strategy, setup, score, decision, risk, sizing, slippage, exit, execution, or LIVE authority changed.

## TDD / CI evidence

Branch: `fix/pump-launch-market-evidence`

RED contract commits:

- `ce395c921af5c74a7ce060a3c836349f1de90726`
- tightened safe-boundary RED: `b54b15ec5fe73046bfa2cb01ca7ab1c196081a80`

RED CI:

- `33165004649`: Rust failed on the new missing Pump market-evidence contract; Python and repository safety remained green.
- `33165115344`: tightened Rust contract failed because `with_pump_market_provider` did not yet exist; Python and repository safety remained green.

GREEN implementation/test head:

- `00506940b832b2cc98f243b69d088d7e26833977`
- CI `33165532353`: Python GREEN, Rust GREEN, repository safety GREEN, ARM64 release build GREEN.
- Rust coverage includes an end-to-end regression that verifies a Pump creation, persists its candidate, invokes the Pump-only market provider, and proves a DEX Screener row exists in `market_snapshots` for that candidate.

PR #70 merged at:

- `6e85952e1893dfef57d5209860381b925a756015`

Merged-main CI:

- `33165659950`: Python GREEN, Rust GREEN, repository safety GREEN, ARM64 release build GREEN.

## Production acceptance required after deployment

The code fix is sealed but is not considered production-proven until an exact release is deployed and the VPS demonstrates new verified Pump candidates receiving market snapshots.

Acceptance must prove at minimum:

1. `/opt/shreks/current` resolves to the exact sealed release SHA.
2. Observer, PAPER evidence, PAPER campaign, and target are active.
3. Verified Pump launches continue increasing.
4. `PUMP_WITH_MARKET_SNAPSHOT_5M` and/or a bounded post-deploy cohort becomes greater than zero.
5. Market rows are linked to verified Pump candidate IDs and use the expected DEX provider.
6. Core risk state remains unchanged by read-only acceptance checks.
7. LIVE trading remains disabled.
8. PAPER selector/evaluation is then re-measured without lowering any safety or trading thresholds.
