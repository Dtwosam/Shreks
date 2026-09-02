# FL3 Execution Economics Design

**Status:** Approved by standing project instruction for autonomous implementation  
**Date:** 2026-09-02  
**Phase:** FL3 — Execution economics and maximum acceptable entry price

## Goal

Make Shreks able to answer, in deterministic Rust and before any learned strategy or live execution authority, whether a specific trade at a specific executable price and size is economically worthwhile after realistic costs, exit capacity, and a caller-supplied edge/risk requirement.

This phase does **not** create `TradeIntent`s, sign or submit transactions, change PAPER authority, or enable LIVE.

## Build-order contract

`SHREKS_BUILD_ORDER.md` requires FL3 to implement:

1. a versioned/configurable round-trip cost model covering protocol/platform/swap fees, buy and sell impact/slippage, network and priority fees, failed-fill cost where meaningful, and decision-to-landing latency impact;
2. exit-capacity estimation under active curve/pool conditions;
3. break-even future executable price/move;
4. maximum acceptable entry price for a required edge/risk margin; and
5. a final reprice/abort invariant that refuses to chase an entry whose executable economics have crossed the approved boundary.

The FL3 exit criterion is the ability to answer “is this specific trade at this specific price/size economically worthwhile?” without substituting token-quality scoring for execution economics.

## Evidence and current protocol facts

Protocol fee values are not embedded as production constants in the core economics math. Current protocol evidence was re-checked on 2026-09-02 against official Pump documentation and public IDLs:

- `https://pump.fun/docs/fees` publishes current Pump bonding-curve and PumpSwap fee schedules and explicitly notes that smart-contract fee values can change.
- `pump-fun/pump-public-docs` `docs/FEE_PROGRAM_README.md` documents the dynamic fee program and market-cap/canonical-pool inputs.
- `pump-fun/pump-public-docs` `idl/pump.json` emits Pump trade fee basis points and raw fee amounts, including creator-related and newer fee fields.
- `pump-fun/pump-public-docs` `idl/pump_amm.json` emits PumpSwap LP/protocol/creator fee evidence plus newer cashback/buyback fields.
- PumpSwap public documentation specifies constant-product pricing and an effective quote reserve that includes `virtual_quote_reserves` when present.

The repository already decodes part of this authoritative evidence but currently discards several fee fields. FL3 should retain the evidence needed to validate or derive cost schedules rather than replacing it with guessed constants.

## Design principles

### 1. Quote-asset units are canonical

All Fast Lane execution economics stay in the market’s quote asset. SOL/WSOL markets therefore use SOL-denominated economics; USDC markets use USDC-denominated economics. FL3 must not label native quote values as USD without an explicit later FX conversion.

### 2. Pure core math, explicit inputs

`shreks-core` owns provider-neutral deterministic execution math. It accepts an explicit, versioned cost model and executable trade inputs. It has no provider calls, database writes, strategy scoring, transaction construction, signing, submission, or runtime authority.

No production fee, slippage, latency, or risk-margin default is hidden inside the core. A caller must supply the cost/economic assumptions used for the assessment.

### 3. Effective fee rate avoids double counting

Provider evidence may contain protocol, LP, creator, cashback, buyback, or future fee fields whose economic relationships can change. The core cost model therefore consumes one caller-derived **effective charged fee rate per leg**, not a naïve sum of every named field.

Detailed provider fee evidence is preserved separately for audit and schedule derivation. A rebate reduces the effective rate only when it is actually guaranteed/realizable for the modeled execution path. Unknown fee semantics fail closed at the provider-to-cost-model boundary; they are not silently treated as zero.

### 4. Cost components remain separately inspectable

For each entry/exit leg, the core keeps these independent inputs:

- effective fee basis points;
- expected price impact basis points;
- expected additional slippage basis points;
- expected adverse decision-to-landing movement basis points;
- network fee in quote units;
- priority fee/tip in quote units; and
- expected failed/partial-fill cost in quote units.

Variable basis-point costs apply to the gross executable quote notional for that leg. Fixed quote costs are added/subtracted separately. This makes small-notional economics correctly pay a larger percentage burden from fixed network costs.

### 5. One explicit round-trip algebra

For intended base quantity `Q`, entry executable price `P_entry`, and entry variable cost rate `r_entry`:

`entry_total = Q * P_entry * (1 + r_entry) + entry_fixed_quote`

For future/forecast executable exit price `P_exit` and exit variable cost rate `r_exit`:

`exit_net = Q * P_exit * (1 - r_exit) - exit_fixed_quote`

`net_pnl = exit_net - entry_total`

The implementation validates that `r_exit < 1` so the exit leg cannot mathematically produce a non-positive variable multiplier.

The break-even exit price solves `exit_net == entry_total` exactly:

`P_break_even = (entry_total + exit_fixed_quote) / (Q * (1 - r_exit))`

The break-even move is expressed relative to `P_entry` in basis points.

### 6. Maximum acceptable entry price is solved, not guessed

The caller supplies a forecast executable exit price and a required net-return requirement in basis points. Required edge and risk margin remain separately named inputs but are added into one required return rate for the algebra.

The maximum acceptable entry price is the highest `P_entry` satisfying:

`exit_net >= entry_total * (1 + required_return_rate)`

Solving for entry price produces a deterministic ceiling. If fixed costs or the required return consume all expected exit value, there is no acceptable positive entry price and the assessment fails closed.

This boundary is an **execution boundary**, not a token-quality score.

### 7. Reprice/abort is a first-class invariant

The assessment exposes a predicate that accepts an immediately re-quoted executable entry only when:

- exit capacity still covers the intended base quantity; and
- current executable entry price is finite, positive, and `<= maximum_acceptable_entry_price_quote`.

A price above the approved ceiling is an abort. The core never converts that abort into a chase or a higher price automatically.

### 8. Capacity is boundary-driven, not threshold-invented

There is no arbitrary “safe liquidity percentage” in FL3. Venue-specific capacity answers how much base can be exited while respecting an explicit caller-provided minimum executable exit-price/economic boundary and the venue’s real reserve constraints.

For constant-product contexts, capacity math uses authoritative reserve context and checked arithmetic. Pump bonding-curve calculations must respect real reserve constraints. PumpSwap pricing must incorporate effective quote reserves, including the documented virtual quote reserve when source evidence supplies it.

If source evidence is insufficient to prove the required reserve/capacity state, capacity is unknown and the trade is not approved by FL3.

### 9. Historical evidence remains truthful

Older stored raw events may predate newer appended Pump/PumpSwap event fields. When a historical source row does not carry the newer fee/virtual-reserve evidence, Shreks must represent that field as unknown rather than fabricating current values into the past.

Storage replay remains source-derived. No duplicate canonical fee table is introduced merely to copy immutable raw event truth.

## Core domain surface

Create `crates/shreks-core/src/fast_lane/economics.rs` with a small public surface:

```rust
pub const EXECUTION_ECONOMICS_VERSION: u16 = 1;

pub struct ExecutionLegCostInput {
    pub effective_fee_bps: u32,
    pub expected_impact_bps: u32,
    pub expected_slippage_bps: u32,
    pub expected_latency_bps: u32,
    pub network_fee_quote: f64,
    pub priority_fee_quote: f64,
    pub expected_failure_cost_quote: f64,
}

pub struct ExecutionCostModel {
    pub version: u16,
    pub entry: ExecutionLegCostInput,
    pub exit: ExecutionLegCostInput,
}

pub struct ExecutionTradeInput {
    pub base_quantity: f64,
    pub executable_entry_price_quote: f64,
    pub forecast_exit_price_quote: f64,
    pub exit_capacity_base: f64,
    pub required_edge_bps: u32,
    pub risk_margin_bps: u32,
}

pub struct ExecutionEconomics {
    pub version: u16,
    pub entry_total_quote: f64,
    pub forecast_exit_net_quote: f64,
    pub forecast_net_pnl_quote: f64,
    pub break_even_exit_price_quote: f64,
    pub break_even_move_bps: f64,
    pub maximum_acceptable_entry_price_quote: f64,
    pub exit_capacity_base: f64,
}
```

Exact internal helper names may differ, but the public responsibilities and semantics above are fixed. `ExecutionEconomics::assess(...)` validates inputs, capacity, and algebra. `ExecutionEconomics::entry_price_is_acceptable(...)` implements the reprice boundary.

Basis-point component inputs that directly represent a cost are individually bounded to `<= 10_000`; summed entry variable cost may exceed 100% only if explicit inputs genuinely imply it, but exit total variable cost must remain `< 100%` because otherwise no positive net-exit multiplier exists. Required edge/risk margin are non-negative `u32` values and are not capped by an arbitrary strategy threshold.

## Provider fee-evidence surface

Provider parsers should retain authoritative onchain fee evidence needed for research/config verification.

Pump evidence should preserve fee basis points/raw amounts that are actually present in the decoded trade event. PumpSwap evidence should preserve the current LP/protocol/creator/newer fee fields when present and retain `virtual_quote_reserves` as optional source evidence.

The Fast Lane source-normalization path may derive an `ExecutionLegCostInput` only when fee semantics for that exact source/event/config are known. Otherwise it returns unknown/not-assessable rather than guessing.

## PumpSwap reserve correction

The current FL2 `FastReserveContext::PumpSwapPool` stores physical pool base/quote reserves. FL3 must extend this context only if needed to represent the documented virtual quote reserve without losing historical truth. The preferred shape is an optional signed virtual quote reserve because the current IDL exposes it as `i128` and older stored events may not contain the appended field.

Pricing helpers use:

`effective_quote_reserve = physical_quote_reserve + virtual_quote_reserve`

with checked signed-to-unsigned validation. A missing virtual-reserve field remains unknown for calculations that require it; it is not silently assumed from today’s protocol configuration.

## Error handling

Fail closed on:

- zero/non-finite/negative quantity or price;
- non-finite/negative fixed quote cost;
- per-component cost basis points above 10,000;
- exit variable cost rate `>= 100%`;
- insufficient/unknown exit capacity;
- arithmetic overflow/non-finite result;
- forecast economics that yield no positive acceptable entry price;
- missing source evidence required by a venue-specific capacity calculation.

Errors are explicit domain errors, not booleans that erase the reason an assessment failed.

## TDD and verification

Every production behavior is introduced test-first:

1. RED core economics contract tests;
2. GREEN minimal core algebra;
3. RED provider fee/virtual-reserve evidence tests;
4. GREEN parsers/source-derived replay;
5. RED capacity tests for Pump and PumpSwap reserve contexts;
6. GREEN venue-specific capacity math;
7. end-to-end deterministic economics/reprice tests.

Each RED must fail for the intended missing behavior. Each GREEN head must pass all four repository gates: repository safety, Rust workspace, Python suite, and native ARM64 release build/verification.

## Authority and release boundary

FL3 remains pure decision/economic infrastructure. It does not:

- create or execute `TradeIntent`s;
- alter the existing PAPER fill ledger or risk authority;
- add signer/wallet access;
- submit Solana transactions;
- enable `RuntimeMode::Live`;
- weaken release verification or deployment controls.

A later FL7 PAPER action engine may consume this economics contract. A later live-capital phase must independently pass shadow/profitability/risk/operations promotion gates.

**LIVE remains disabled.**