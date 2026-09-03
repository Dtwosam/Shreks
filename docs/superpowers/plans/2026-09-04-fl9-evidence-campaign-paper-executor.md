# FL9 Evidence Campaign PAPER Executor — Implementation Plan

**Date:** 2026-09-04

Base: SEALED FL9 campaign decision seam merge `2c16b293815e0f62082f3956633613b911fb8227`.

Design: `docs/superpowers/specs/2026-09-04-fl9-evidence-campaign-paper-executor-design.md`.

## Goal

Build one deterministic Python PAPER campaign executor:

```text
FastCampaignDecisionResults
        + explicit per-event quote/risk/entry evidence
        + caller-supplied SEALED policies
        + starting PaperLedger
                    ↓
            FL7.1 event journal
                    ↓
       FL7.2 BUY / FL7.4 HOLD-REDUCE-SELL
                    ↓
            SEALED ledger evidence
                    ↓
                 E11
                    ↓
                  E5
                    ↓
        FastPolicyRunEvidence
```

No network, provider, persistence, promotion, signer, or LIVE authority.

## Task 1 — RED public models and identity contracts

Create:

`python/tests/test_fast_campaign_paper_models.py`

Lock package:

`shreks_brain.fast_campaign_paper`

Public names:

- `FAST_CAMPAIGN_PAPER_EXECUTOR_VERSION`
- `FastCampaignPaperCandidateIdentity`
- `FastCampaignPaperEntryAuthority`
- `FastCampaignPaperQuoteEvidence`
- `FastCampaignPaperDecisionEvidence`
- `FastCampaignPaperRunResult`
- `run_fast_campaign_paper_candidate`

RED assertions:

1. executor version is `fl9-campaign-paper-v1`;
2. candidate SHA must be lowercase 64-char hex;
3. identity strings are non-empty;
4. quote evidence validates exact PaperQuoteState semantics;
5. BUY entry authority requires positive finite sizing/economic fields;
6. decision evidence timestamps cannot precede decision when bound to a run;
7. duplicate/misaligned event IDs fail closed;
8. run result carries exact sealed result types.

Expected RED: package missing.

## Task 2 — RED SKIP-only deterministic event population

Create:

`python/tests/test_fast_campaign_paper_executor.py`

Fixture:

- one canonical Rust campaign result with SKIP;
- one matching decision evidence row;
- exact caller policies;
- exact starting ledger.

Assert:

- one FL7.1 material event record;
- no BUY/position execution results;
- final ledger unchanged;
- E11 capture empty;
- E5 trade tuple empty;
- FastPolicyRunEvidence exists;
- repeated identical input returns equal run result and same fingerprints.

## Task 3 — RED BUY → HOLD → SELL closed trade

Use sealed FL7 fixture values:

- starting cash: 20,000 USD;
- BUY decision price 10.0;
- BUY max price 10.5;
- actual BUY executable quote 10.1;
- SELL executable quote 10.9;
- quote-to-USD 1.0;
- fill policy 50 bps + 0.05 USD network fee;
- risk policy aligned to assessment/state versions.

Decisions:

1. BUY at T0+100, current exposure 0.0, target 1.0;
2. HOLD at T0+300, current exposure 1.0, target 1.0;
3. SELL at T0+500, current exposure 1.0, target 0.0.

Assert:

- event loop records all 3 decisions;
- BUY opens one position;
- HOLD marks only;
- SELL closes exact authoritative quantity;
- final ledger has one CLOSED position;
- E11 capture has one entry, two executions, one closure;
- E5 has one evaluated trade;
- trade net PnL equals sealed closure realized PnL;
- execution costs equal sealed accumulated costs;
- FastPolicyRunEvidence decision_count == 3.

## Task 4 — RED REDUCE quantity derivation

Campaign:

- BUY exact 10 base units;
- REDUCE from current exposure 1.0 to target 0.4.

Expected FL7.4 exit authority:

`10 * (1 - 0.4 / 1.0) = 6`

Assert resulting PAPER execution quantity is 6 base units within existing tolerances and the remaining OPEN position is 4.

Reject:

- target >= current for REDUCE;
- current <= 0;
- target <= 0;
- non-finite exposure values.

No caller-provided base exit quantity API exists. A zero remaining exposure is represented by SELL, not REDUCE.

## Task 5 — RED explicit quote-only behavior

Assert:

- BUY with explicit `UNAVAILABLE` quote does not fill;
- BUY with no quote evidence is rejected by executor input contract;
- HOLD/REDUCE/SELL with no quote evidence is rejected by executor input contract;
- future quote fails through sealed FL7 validation;
- risk rejection leaves ledger flat and remains run evidence;
- quote/provider fields are never inferred from decision features.

## Task 6 — RED posture/ledger reconciliation

Reject:

- BUY with tracked OPEN position;
- SKIP with tracked OPEN position;
- HOLD/REDUCE/SELL while flat;
- decision current exposure 0 while ledger is open;
- decision current exposure >0 while ledger is flat;
- SELL target exposure != 0;
- REDUCE target exposure >= current.

These are structural campaign errors, not execution outcomes.

## Task 7 — Implement models

Create:

```text
python/src/shreks_brain/fast_campaign_paper/models.py
python/src/shreks_brain/fast_campaign_paper/__init__.py
```

Models are frozen/slotted and strictly validate:

- candidate identity;
- entry authority;
- quote evidence;
- decision evidence;
- run result.

Do not add filesystem/network/process helpers.

## Task 8 — Implement executor

Create:

`python/src/shreks_brain/fast_campaign_paper/engine.py`

Implementation order per decision:

1. positional evidence identity validation;
2. translate Rust result via SEALED `fast_campaign_result_to_paper_assessment`;
3. write exact material update through SEALED `run_fast_paper_event`;
4. reconcile flat/open tracked position;
5. dispatch:
   - SKIP: no execution;
   - BUY: SEALED FL7.2;
   - HOLD/REDUCE/SELL: SEALED FL7.4;
6. collect only actually returned execution + ledger updates;
7. collect entry regime context only when position was actually opened.

At end:

8. SEALED E11 extraction;
9. SEALED `build_evaluated_trades`;
10. SEALED E5 evaluation;
11. construct exact `TradingEvaluationEvidence`;
12. SEALED `build_fast_policy_run_evidence`.

No custom economic formulas except REDUCE base quantity conversion from exposure fractions.

## Task 9 — Position tracking

Internal only:

- map market_key → position_id;
- map position_id → `FastPaperPositionActionState`.

On BUY FILLED:
- obtain exact position_id from applied ledger update;
- create SEALED position-action state.

On SELL SOLD:
- remove market tracking.

On REDUCE:
- retain updated state and OPEN position.

On failed/deferred exit:
- preserve returned pending state exactly.

## Task 10 — Authority firewall

Create:

`python/tests/test_fast_campaign_paper_authority.py`

Forbidden in new package:

- `requests`
- `httpx`
- `urllib`
- `socket`
- `sqlite3`
- `subprocess`
- provider modules
- signer/submission
- registry mutation/promotion
- `RuntimeMode.LIVE`
- future/counterfactual labels
- custom `net_pnl`, `profit_factor`, `expectancy`, `drawdown` calculations.

Allowed:

- SEALED Fast PAPER functions;
- SEALED risk models;
- SEALED E11/E5;
- SEALED FL9 run-evidence builder.

## Task 11 — Full verification

Require:

- targeted executor tests GREEN;
- full Python suite GREEN;
- Rust workspace unchanged and GREEN;
- repository safety GREEN;
- native ARM64 release GREEN.

Scope must contain only:

- design/plan;
- new `fast_campaign_paper` package;
- new executor tests.

No Rust/provider/storage/runtime-deployment changes.

## Task 12 — Clean history and seal

After final candidate 4/4 GREEN:

1. freeze final tree;
2. reconstruct design → plan → consolidated RED → implementation;
3. verify exact final tree identity;
4. force-move only `build/fl9-evidence-campaign-executor`;
5. clean-head 4/4 GREEN;
6. update PR evidence;
7. guarded merge by expected head SHA;
8. merged-main 4/4 GREEN;
9. mark **FL9 learned-candidate PAPER campaign executor — SEALED**.

## Next slice

Build Rust FL6 baseline decision replay over the exact same event/evidence population, then execute each required baseline through this same PAPER executor and compare with the SEALED superiority proof.

No profitability claim until real non-fixture evidence returns `SUPERIOR`.

LIVE remains disabled.
