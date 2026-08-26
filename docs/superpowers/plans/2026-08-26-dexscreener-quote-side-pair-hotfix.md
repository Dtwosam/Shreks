# DexScreener Quote-Side Pair Hotfix — Verification Record

**Date:** 2026-08-26  
**Base:** ARM64 production seal `66178ffc391181e02dcff1efa0c12314e845d9ff`  
**Draft PR:** #52  
**Frozen behavior SHA:** `12e7154973f19fa6dea5d77946753820b30e3bef`

## Production finding

During first-host commissioning, the sealed observer created the operational SQLite database successfully, then Observer V2 stopped with:

```text
InvalidData("market provider dexscreener returned mint A8KKLxi2Qyg4jZyK1M8aVEPWYc13HhgPMgxwXPFNpump while sampling 7nLukVng5teXze14rum9v57juXLjUp7JJnCveko1pump")
```

A direct read-only query of the exact DexScreener token-pairs endpoint returned 15 Solana pairs for the sampled mint: 13 had the sampled mint as `baseToken`, while 2 had it as `quoteToken`.

## Root cause

`DexScreenerProvider::token_pairs()` parsed every Solana pair returned by `/token-pairs/v1/solana/{mint}`. Observer V2 deliberately requires each market snapshot for a tracked candidate to have `snapshot.base_mint == candidate.mint` and fails closed on a mismatch.

The provider therefore passed legitimate quote-side relationship pairs into a base-mint sampling boundary, causing the sampler to terminate even though valid base-side pairs were also present.

The existing DexScreener fixture covered only a response where the requested mint was the base token, so this production response shape was not test-pinned.

## RED

Commit: `1f1522680ab3e7599c2c210324b6f27a13519553`

Added a regression fixture containing both:

- a pair whose `baseToken.address` equals the requested mint;
- a pair whose `quoteToken.address` equals the requested mint.

The required normalized result contains only the base-side pair.

CI run `33007910304` behaved as intended:

- Repository safety: GREEN
- Python: GREEN
- ARM64 release build: GREEN
- Rust: RED only because `parse_token_pairs_json_for_mint` did not yet exist (`E0432 unresolved import`)

## GREEN

Commit: `12e7154973f19fa6dea5d77946753820b30e3bef`

Minimal fix:

1. preserve the existing generic JSON parser;
2. add `parse_token_pairs_json_for_mint(...)` which filters parsed pairs to `pair.base_mint == requested_mint`;
3. make the production `DexScreenerProvider::token_pairs()` path use that requested-mint normalization.

No pair is inverted and no price/liquidity/transaction statistic is fabricated. Quote-side relationship pairs are simply excluded from the candidate-base sampling result.

CI run `33008129440` completed successfully:

- Repository safety: GREEN
- Python: GREEN
- Rust/workspace: GREEN
- native ARM64 release build: GREEN

## Scope audit

Frozen behavior differs from the production base only in:

- `crates/shreks-providers/src/dexscreener.rs`
- `crates/shreks-providers/tests/dexscreener.rs`

No strategy, feature arithmetic, setup, scoring, decision, risk, paper accounting, evaluation, promotion, wallet, signing, submission, live execution, deployment policy, or provider credential behavior changed.

**LIVE TRADING remains disabled.**

## Seal rule

This verification record is the only permitted post-behavior change. The resulting seal commit must pass fresh full repository CI before a new ARM64 release is built and deployed to the VPS.
