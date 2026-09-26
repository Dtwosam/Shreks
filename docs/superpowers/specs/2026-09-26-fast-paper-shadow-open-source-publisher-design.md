# Fast PAPER Shadow OPEN Source Publisher — Design

**Date:** 2026-09-26  
**Base main SHA:** `d7e17835282bb763cba61b56e29774da585dc673`

## Purpose

Add the smallest safe supervised execution-source publisher for learned OPEN
posture actions.

The runtime already has:
- authenticated learned decision evidence;
- authenticated write-once quote/USD source records;
- a state-bound execution-source producer;
- restart-safe execution-source persistence.

For `HOLD`, `REDUCE`, and `SELL`, the sealed execution-input contract
requires no BUY sizing, RiskContext, or MarketRegime. It requires only the exact
decision evidence and explicit quote/USD evidence. This slice composes those
existing authorities without deriving a new fact.

## Contract

Add public:

`run_fast_paper_shadow_open_source_publisher_cycle(...)`

Inputs:
- exact runtime manifest;
- exact authenticated execution bootstrap;
- decision-evidence directory;
- quote/USD source directory.

One invocation must:

1. validate both source directories as existing regular non-symlink directories;
2. select deterministically only the oldest unexecuted learned decision;
3. return zero if none exists;
4. return zero without touching quote/USD authority when the oldest action is
   `BUY` or `SKIP`;
5. require `HOLD`, `REDUCE`, or `SELL` evidence to carry OPEN posture;
6. locate only the exact quote/USD source file for that decision fingerprint;
7. if the exact quote/USD file is absent, return zero backpressure;
8. if present, read it only through
   `read_fast_paper_shadow_quote_usd_source_record(...)`;
9. construct exactly one `FastPaperShadowExecutionInput` with:
   - exact decision evidence;
   - `entry_authority=None`;
   - `risk_context=None`;
   - `market_regime=None`;
   - authenticated `quote_usd_evidence`;
10. delegate exact latest checkpoint/runtime/policy validation to
    `produce_fast_paper_shadow_execution_input_source_record(...)`;
11. use the decision evaluation timestamp as source-observation time;
12. use `risk_day_started_at_unix_ms=None`;
13. write only through the canonical write-once execution-source writer;
14. on a write collision, strictly read back the exact execution source and
    require semantic equality;
15. publish at most one source per invocation;
16. never leapfrog an older BUY/SKIP decision.

## Authority boundary

```text
AUTO_SOURCE_ACTIONS=HOLD_REDUCE_SELL_ONLY
QUOTE_USD_AUTHORITY=PREPUBLISHED_AUTHENTICATED_ONLY
BUY_SOURCE_PUBLICATION=NOT_GRANTED
QUOTE_USD_DERIVATION=FORBIDDEN
RISK_REGIME_SIZING_DERIVATION=FORBIDDEN
OBSERVER_DATABASE_ACCESS=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SHADOW_EXECUTION=NOT_GRANTED
SHADOW_TRANSITION_PERSISTENCE=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
PRODUCTION_PAPER_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:
- public OPEN-source publisher API;
- deterministic oldest-unexecuted selection;
- BUY/SKIP no-leapfrog backpressure;
- exact quote/USD source consumption;
- exact HOLD/REDUCE/SELL execution-input construction;
- state-bound producer composition;
- write-once persistence and strict collision readback;
- no observer/provider/USD derivation, BUY authority, execution, scoring,
  signing/submission, authoritative PAPER, or LIVE authority.
