# G2 production seal — Fresh Launch PAPER mint-state backfill

Date: 2026-08-27

## Purpose

Seal the production behavior that closes the missing token-decimals dependency in the Fresh Launch PAPER evidence path without weakening strategy, safety, risk, or execution rules.

## Production evidence that motivated the change

Read-only historical replay of the commissioned PAPER run after the Fresh Launch selector alignment reproduced persisted checkpoint states exactly and showed selected Fresh Launch candidates reaching setup/decision evaluation with no reconstructed PAPER quote (`QUOTE_MINTS=()`). At least the first selected candidates already had persisted Jupiter ENTRY/EXIT quote snapshots from the evidence collector. The E15 assembler reconstructs executable PAPER quotes only when matching quote evidence and durable Helius token decimals are both available.

The standalone `shreks-paper-evidence` path collected holder distributions and Jupiter quotes but did not own mint-state/decimals backfill. The legacy observer had a bounded due-outcome mint-state backfill, but that later lifecycle can arrive after the 60-second-to-30-minute Fresh Launch entry window.

The production PAPER evidence interval has separately been set operationally to 60 seconds, retaining the max-2 candidate bound. This seal does not encode or loosen trading thresholds.

## Sealed behavior

PR #65, `fix: backfill Fresh Launch mint state in PAPER evidence`, merged as:

- merge commit: `2274c93e46713ae80204de74f8675aa4ccf0e22c`
- final PR head: `9f3277f984da415b622346d95dc2c09ff32b88a1`

Behavior:

1. `SafetyEvidenceCollector` may receive an optional read-only `ChainDataProvider`.
2. For each already-selected PAPER evidence candidate, it checks durable `has_mint_state(candidate_id)` first.
3. If mint state is absent, it performs a bounded Helius `token_mint_state` lookup.
4. Only correctly attributed provider+mint evidence is persisted through the existing `insert_mint_state` storage path.
5. Once durable mint state exists, subsequent evidence cycles make no repeat chain lookup for that candidate.
6. Chain-provider failure or misattribution leaves mint state unknown and is counted; no evidence is fabricated.
7. The production PAPER evidence daemon reuses the existing Helius client for chain and holder evidence and retains Jupiter for ENTRY/EXIT quote evidence.
8. Runtime evidence logs expose `mint_states_stored` and include chain failures in the aggregate provider-failure count without exposing credentials.

## TDD evidence

RED began at `7fe37d110fd7c442385e37d3b6f8aa63c5d67273` and was hardened through `806e987ccd01955e6f75fad2cb83e21a64048354`.

RED CI:

- run `33109162560`
- Python GREEN
- repository safety GREEN
- Rust failed as expected because the production collector did not yet provide the required mint-state backfill contract

GREEN PR head:

- `9f3277f984da415b622346d95dc2c09ff32b88a1`
- CI run `33109605573`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN
- native ARM64 release build GREEN

Merged-main verification:

- `2274c93e46713ae80204de74f8675aa4ccf0e22c`
- CI run `33109928288`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN
- native ARM64 release build GREEN

## Scope audit

The behavior change is limited to:

- `crates/shreks-observer/src/safety_evidence.rs`
- `crates/shreks-observer/src/bin/shreks-paper-evidence/cycle.rs`
- `crates/shreks-observer/src/bin/shreks-paper-evidence/main.rs`
- focused PAPER evidence tests

Unchanged:

- Fresh Launch strategy thresholds
- safety hard vetoes
- scoring/decision thresholds
- risk sizing and loss/drawdown controls
- paper-fill economics
- max PAPER evidence candidate count
- wallet/signing/submission authority
- LIVE enablement

## Promotion boundary

This seal removes an evidence-completeness blocker. It is not evidence of profitability and does not authorize LIVE trading. After deployment, physical VPS proof must demonstrate that selected Fresh Launch candidates receive mint state plus matching Jupiter quote evidence and that the PAPER campaign can reconstruct executable quotes. Strategy expectancy remains evidence-gated.

**LIVE TRADING: DISABLED.**
