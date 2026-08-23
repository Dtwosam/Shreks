# Phase A3-A6 Provider Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Shreks stable, testable provider contracts and read-only adapters for DEX Screener, Solana/Helius, and Jupiter without leaking provider JSON into the rest of the system.

**Architecture:** `shreks-core` owns provider-neutral value objects used across adapters. A new `shreks-providers` crate owns async provider traits, HTTP/RPC clients, error classification, and provider-specific response parsing. Provider adapters return Shreks-owned DTOs only. No strategy, scoring, paper trading, signing, or live execution is introduced in this slice.

**Tech Stack:** Rust stable, serde/serde_json, reqwest with rustls, async-trait, tokio for tests, existing SQLite operational storage.

**Spec:** `docs/superpowers/specs/2026-08-23-shreks-master-design.md`

## Global Constraints

- Solana only for V1.
- Free external data/API/RPC sources only.
- No private keys or seed phrases in source control or ChatGPT.
- Paper trading precedes live trading.
- External provider JSON must not become the Shreks domain model.
- Missing, stale, malformed, rate-limited, or contradictory critical data must be represented explicitly; later decision logic will fail closed.
- Jupiter integration uses current Swap API V2, not deprecated Swap V1.
- This plan is read-only: it must not sign or submit transactions.

---

### Task 1: Provider-neutral contracts

**Files:**
- Modify: `Cargo.toml`
- Modify: `crates/shreks-core/src/lib.rs`
- Create: `crates/shreks-providers/Cargo.toml`
- Create: `crates/shreks-providers/src/lib.rs`
- Create: `crates/shreks-providers/tests/contracts.rs`

**Interfaces:**
- Produces `ProviderId`, `ProviderErrorKind`, `ProviderError`, `ProviderHealthState`, `DiscoveredToken`, `PairMarketData`, `TokenMintState`, `QuoteRequest`, and `QuoteSnapshot`.
- Produces async traits `DiscoveryProvider`, `MarketDataProvider`, `ChainDataProvider`, and `QuoteProvider`.

- [ ] Write failing tests for stable provider identifiers, retryability classification, quote-request validation, and trait usability.
- [ ] Run `cargo test --workspace` and confirm failure because provider contracts do not exist.
- [ ] Add the minimal provider-neutral types and async traits.
- [ ] Run `cargo test --workspace` and confirm green.
- [ ] Commit the verified contract layer.

### Task 2: Shared HTTP/error handling

**Files:**
- Create: `crates/shreks-providers/src/http.rs`
- Modify: `crates/shreks-providers/src/lib.rs`
- Create: `crates/shreks-providers/tests/http_errors.rs`

**Interfaces:**
- Produces HTTP status classification into `ProviderErrorKind`.
- Preserves `Retry-After` information when rate-limited.
- Rejects oversized/malformed responses through structured provider errors.

- [ ] Write failing tests for 401/403, 404, 429, 5xx and malformed-body classification.
- [ ] Verify tests fail for missing implementation.
- [ ] Implement minimal status/error classification.
- [ ] Verify full Rust suite passes.

### Task 3: DEX Screener read-only adapter

**Files:**
- Create: `crates/shreks-providers/src/dexscreener.rs`
- Create: `crates/shreks-providers/tests/dexscreener.rs`

**Interfaces:**
- Implements `DiscoveryProvider` using public latest-profile/latest-boost sources as opportunistic discovery only.
- Implements `MarketDataProvider::token_pairs` using `/token-pairs/v1/solana/{tokenAddress}`.
- Normalizes pair identity, DEX, base/quote token identity, price, liquidity, volume, transactions, FDV/market cap, and pair creation time into `PairMarketData`.

- [ ] Write fixture-driven failing parsing tests without calling the public API.
- [ ] Verify expected failure.
- [ ] Implement response parsing and URL construction.
- [ ] Add network client method behind the trait.
- [ ] Verify full Rust suite passes.

### Task 4: Solana/Helius read-only adapter

**Files:**
- Create: `crates/shreks-providers/src/helius.rs`
- Create: `crates/shreks-providers/tests/helius.rs`

**Interfaces:**
- Implements `ChainDataProvider::token_mint_state` through Helius Solana JSON-RPC `getAccountInfo` with parsed SPL-token mint data.
- Captures mint authority, freeze authority, supply, decimals, owner program, slot, and observation time.
- Classifies JSON-RPC errors and HTTP rate limits without guessing.

- [ ] Write fixture-driven failing tests for a parsed token mint, missing account, JSON-RPC error, and malformed data.
- [ ] Verify expected failure.
- [ ] Implement JSON-RPC request/response parsing.
- [ ] Verify full Rust suite passes.

### Task 5: Jupiter Swap V2 read-only quote/build adapter

**Files:**
- Create: `crates/shreks-providers/src/jupiter.rs`
- Create: `crates/shreks-providers/tests/jupiter.rs`

**Interfaces:**
- Implements `QuoteProvider` with `GET https://api.jup.ag/swap/v2/build`.
- Sends `inputMint`, `outputMint`, `amount`, `taker`, and configured `slippageBps`.
- Returns `QuoteSnapshot` containing input/output amounts, minimum output, price impact, route labels, quote timestamp, and route availability.
- Does not sign, execute, submit, or expose raw transaction instructions to the trading brain.

- [ ] Write fixture-driven failing tests for a successful build response, empty route, API error, and quote-request validation.
- [ ] Verify expected failure.
- [ ] Implement V2 URL/query construction and response parsing.
- [ ] Verify full Rust suite passes.

### Task 6: Provider health and free-tier-aware configuration

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Create: `crates/shreks-providers/src/config.rs`
- Create: `crates/shreks-providers/tests/config.rs`

**Interfaces:**
- Reads optional Helius/Jupiter API-key environment variables at runtime without requiring secrets in tests.
- Provides conservative default request-rate budgets below documented free-tier limits.
- Never contains a paid fallback endpoint.

- [ ] Write failing configuration tests for safe defaults and missing-key behavior.
- [ ] Verify expected failure.
- [ ] Implement configuration values and documentation.
- [ ] Verify repository safety, Python tests, Rust metadata and Rust workspace tests all pass in CI.

## Self-Review

- Spec coverage: A3 interfaces, A4 DEX Screener, A5 initial Helius token-state slice, and A6 Jupiter read-only quote/build are covered.
- Deliberately deferred from A5: broad live wallet activity streaming and comprehensive pool-program discovery. Those depend on A8 continuous observer design and direct Solana program subscriptions; they will not be faked inside this adapter slice.
- No live execution or signing is introduced.
- No paid provider dependency is introduced.
- All provider responses terminate at adapter-owned parsers and return Shreks-owned types.
