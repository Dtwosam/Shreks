# Fast PAPER Shadow Initial BUY Authority Source — Design

**Date:** 2026-09-27  
**Base main SHA:** `871d5fa2de379f41e4ff9dd4d84369774bbf8d30`

## Purpose

Add the durable authenticated handoff required for the first learned Fast PAPER
shadow BUY.

The learned decision already says BUY and seals the point-in-time market
decision evidence. The existing shadow execution contract deliberately refuses
to infer token quantity, maximum acceptable entry price, risk state, or market
regime. This slice supplies those values only as explicit upstream authority and
binds them to the exact isolated PAPER checkpoint/runtime state.

This slice does not publish an execution-input source and does not execute a
trade.

## Record contract

Add schema:

`shreks.fast_paper_shadow_buy_authority_source` version `1`.

Add public:

- `FastPaperShadowBuyAuthoritySourceRecord`;
- `build_fast_paper_shadow_buy_authority_source_record(...)`;
- `write_fast_paper_shadow_buy_authority_source_record(...)`;
- `read_fast_paper_shadow_buy_authority_source_record(...)`.

Each record binds:

- runtime manifest fingerprint;
- isolated ledger-binding fingerprint;
- execution-policy fingerprint;
- exact PAPER checkpoint sequence and payload SHA-256;
- exact learned runtime-state fingerprint;
- exact BUY decision-evidence fingerprint;
- source-event id and market key;
- exact mint and quote mint;
- evaluation timestamp;
- explicit risk-day start;
- explicit source-observation timestamp;
- exact `FastCampaignPaperEntryAuthority`;
- exact `RiskContext`;
- exact `MarketRegime`;
- non-empty upstream source version;
- upstream source fingerprint;
- deterministic record fingerprint.

## Build validation

Building a source record must:

1. require the exact latest checkpoint/runtime pair;
2. require the execution-policy fingerprint already sealed into runtime state;
3. require the decision to be exact learned `BUY` from FLAT posture;
4. require that posture to match the current durable shadow state;
5. require no unresolved canonical or learned pending BUY;
6. require the decision to be at/after durable PAPER state;
7. require entry authority market identity to match the decision;
8. require entry authority decision executable price to match the decision's
   sealed entry reference price;
9. require `RiskContext.as_of_unix_ms` to equal the decision evaluation time;
10. require risk trading capital to equal isolated-ledger starting cash;
11. recompute ledger accounting with
    `derive_paper_risk_accounting_facts(...)` and require exact equality for
    open-position count/risk, realized PnL, drawdown, loss streak, and
    last-loss time;
12. reject external active-intent claims;
13. require risk-day start at/before evaluation;
14. require source observation at/after the sealed entry quote observation and
    at/before evaluation;
15. require exact `MarketRegime`;
16. validate upstream source identity and fingerprint.

Liquidity, price-impact, market-age, health, kill-switch, and operator-halt
values already present in the exact supplied `RiskContext` remain explicit
upstream facts. This slice does not derive or invent them.

## Persistence

The record is canonical JSON with one trailing newline and mode `0600`.

Publication is write-once into an existing regular non-symlink directory. The
filename is deterministic from the exact decision-evidence fingerprint.

The reader must rebuild the expected record against the current exact latest
checkpoint/runtime pair. Any state advance, decision drift, policy drift,
malformed payload, unknown field, duplicate key, symlink, non-canonical float,
or fingerprint mismatch fails closed.

## Authority boundary

```text
INITIAL_BUY_AUTHORITY_SOURCE=WRITE_ONCE_AUTHENTICATED
BUY_SIZE_AND_MAX_ENTRY=EXPLICIT_ONLY
BUY_RISK_EXTERNAL_FACTS=EXPLICIT_ONLY
BUY_LEDGER_RISK_ACCOUNTING=RECOMPUTED
MARKET_REGIME=EXPLICIT_ONLY
QUOTE_USD_SOURCE=SEPARATE_EXISTING_AUTHORITY
EXECUTION_INPUT_PUBLICATION=NOT_GRANTED
BUY_EXECUTION=NOT_GRANTED
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
LIVE=DISABLED
```

The module must not import or invoke scoring, legacy decision authority,
provider/network clients, SQLite, execution functions, signing/submission,
future labels, counterfactuals, or LIVE mode.

## RED acceptance

The intentional RED contract requires:

- stable public schema/model/build/read/write API;
- exact latest checkpoint/runtime binding;
- exact BUY decision and FLAT posture binding;
- explicit entry/risk/regime authority;
- ledger-backed risk-accounting validation;
- truthful source chronology;
- private write-once canonical round trip;
- stale-state/tamper refusal;
- no execution, scoring, provider/network, signing/submission, or LIVE
  authority.

Current main is expected to fail during Python collection because the new public
API does not exist.

## Following slice

A separately reviewed BUY source publisher may combine this exact authenticated
record with the already-sealed quote/USD source for the same decision, construct
one `FastPaperShadowExecutionInput`, and delegate publication to the existing
state-bound execution-source producer.
