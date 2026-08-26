# Observer V2 Mint-State Backfill Hotfix — Verification Record

**Date:** 2026-08-26  
**Base:** DexScreener quote-side production seal `7cb0532789c786786a4461881e10e8ebaee5c865`  
**Draft PR:** #53  
**Frozen behavior SHA:** `138beae10f9cebafcfe2075b33f9008611e103f2`

## Production finding

During first-host PAPER commissioning, two recent Observer V2 candidates had complete Helius holder-distribution evidence and working purpose-attributed Jupiter ENTRY/EXIT routes, but both reported:

```text
DECIMALS: MISSING
```

The exact observed candidates were:

- candidate 54: `EtquDNisHSiFkD1xFoN2Wp9HgG1iNRS8u9NHNKxUpump`
- candidate 55: `8hbHUy1JhEKE6SK595ZNKAnNkoJ45gwkR2qskooupump`

Because paper evidence amounts are raw token units, an EXIT probe cannot be interpreted economically without the candidate mint decimals. Campaign commissioning therefore remained blocked rather than assuming decimals.

## Root cause

Observer V2 independently discovers DexScreener candidates, durably upserts them, and schedules outcome checkpoints. The legacy observer remains the owner of Helius chain/mint-state truth.

For candidates discovered directly by the legacy observer, `Observer::run_cycle()` already runs both market and chain observation. For candidates discovered only by Observer V2, the bounded due-outcome fallback revisited market data but did not call the existing Helius `observe_chain_data` path.

That ownership gap allowed a valid V2 candidate to accumulate market, holder-distribution, and quote evidence while never receiving a `token_mint_states` row containing decimals and mint/freeze authority state.

## RED 1 — production gap

Commit: `5f76ecc51663abbb9f99c413e5c33d21bbb9dfd0`

Added a regression test that directly seeds a candidate and outcome schedule in SQLite, matching the V2 ownership path, then runs the legacy observer with a deterministic Helius chain provider.

Required behavior: the due candidate receives a persisted mint-state row with the provider-supplied decimals.

CI run `33012060650` failed exactly on that missing behavior: the new test expected one persisted mint state but observed zero.

## First GREEN attempt and boundedness finding

Commit: `c2e98f9ba96547b655eaee167a339333f20794b8`

The first minimal implementation reused `observe_chain_data` for every due candidate. It fixed the missing-decimals regression, but CI run `33012498758` exposed an existing free-provider-budget invariant: a candidate whose durable mint state was already known must not spend another Helius chain request solely because an outcome checkpoint is due.

The new missing-state regression passed, while the existing no-redundant-chain-call test failed. This was treated as an implementation defect rather than weakening the invariant.

## RED 2 — skip existing durable evidence

Commit: `a3e1034d2457088dba6ee3cb23eaed9923dbddcf`

Strengthened the due-candidate test to seed an existing Helius mint-state row and require:

- the normal due market pass still occurs;
- no Helius chain request occurs when mint-state evidence already exists.

CI run `33012790151` failed exactly on that requirement: one chain call occurred where zero was required.

## GREEN

Frozen behavior commit: `138beae10f9cebafcfe2075b33f9008611e103f2`

Minimal final behavior:

1. storage exposes a validated `has_mint_state(candidate_id)` existence query;
2. current-cycle legacy discoveries keep their existing fresh chain observation behavior unchanged;
3. the bounded due-candidate fallback still performs its existing market pass;
4. only when that due candidate has no durable mint-state row does it enter the existing paced Helius `observe_chain_data` path;
5. successful Helius evidence persists real decimals/mint/freeze authority state through the existing storage API;
6. an unavailable/failing provider fabricates no mint state, leaving the candidate eligible for a later bounded retry.

CI run `33013253424` completed successfully:

- Repository safety: GREEN
- Python: GREEN
- Rust/workspace: GREEN
- native ARM64 release build: GREEN

The Rust log explicitly confirms both key contracts are GREEN:

- `due_candidate_discovered_outside_legacy_observer_backfills_missing_mint_state`
- `due_candidate_with_existing_mint_state_gets_one_market_pass_and_no_chain_call`

The existing due-candidate batch cap and Helius chain pacing remain authoritative, so this fix does not create an unbounded provider-request path.

## Scope audit

Frozen behavior differs from base only in:

- `crates/shreks-observer/src/lib.rs`
- `crates/shreks-observer/tests/cycle.rs`
- `crates/shreks-observer/tests/outcome_sampling.rs`
- `crates/shreks-storage/src/outcomes.rs`

No strategy, feature arithmetic, setup, scoring, decision, risk, paper-fill economics, evaluation, promotion, wallet, signing, transaction submission, live execution, deployment policy, or provider-credential behavior changed.

The production PAPER amount/slippage choices remain commissioning hypotheses; this fix supplies missing chain truth and does not bless or alter those economic values.

**LIVE TRADING remains disabled.**

## Seal rule

This verification record is the only permitted post-behavior change. The resulting seal commit must pass fresh full repository CI before a new ARM64 release is built and deployed to the VPS.
