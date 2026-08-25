# Phase E15 Observer Paper Campaign Design

**Status:** Approved under the standing autonomous-build instruction  
**Date:** 2026-08-25  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-e15-observer-paper-campaign`

## 1. Purpose

E12 can evaluate whether reconstructed paper evidence is sufficient, E13 can replay point-in-time observer market history, and E14 can reconstruct point-in-time B1 safety. The remaining gap is a trustworthy bridge from real observer history into the sealed C5 paper loop and then into the existing E11/E12 evidence path.

E15 builds that bridge without enabling Phase F. It must make paper/shadow proof reproducible from persisted observer data, while refusing to manufacture missing execution evidence.

The key discovery that shapes this phase is that E14 intentionally persists only token->stable **exit** quotes. Reusing those sell quotes as buy fills would bias paper results. E15 therefore adds explicit, purpose-attributed bidirectional quote evidence before constructing paper cycles.

## 2. Scope

E15 adds three isolated capabilities:

1. **Bidirectional paper quote evidence**
   - preserve exact `ENTRY` and `EXIT` Jupiter quote requests/results;
   - retain raw amounts and exact mint attribution;
   - retain token mint decimals required to convert raw amounts into token quantities;
   - never persist transaction instructions, signed transactions, or credentials.

2. **Point-in-time observer campaign assembly**
   - derive aggregate B6 `RegimeMarketWindow` from persisted observer history;
   - evaluate each candidate with sealed E14 B1 safety;
   - build sealed B2 features;
   - build exact `PaperQuote`, `PaperEntryCandidate`, `PaperExitObservation`, and `PaperCycleInput` values only when the required evidence exists;
   - derive dynamic risk context from the current sealed paper-loop state plus explicit caller health/capital state.

3. **Restart-safe paper campaign orchestration**
   - run sealed C5 `run_paper_cycle` only in `RuntimeMode.PAPER`;
   - persist C6 paper-loop checkpoints after applied cycles;
   - record every cycle into the sealed E11 paper-evaluation evidence store;
   - expose evaluation/proof inputs, but do not call promotion or live execution.

## 3. Non-goals and authority boundary

E15 does not:

- change B1 safety thresholds, precedence, or reason ordering;
- change B2 feature arithmetic;
- change B6 regime thresholds or classification logic;
- change setup, score, decision, risk, exit, paper-fill, accounting, E11, E12, registry, or promotion rules;
- invent numeric trading thresholds;
- attach Jupiter or the campaign runner to the default Phase-A observer;
- sign or submit transactions;
- mutate the champion/challenger registry;
- promote a challenger;
- enable `RuntimeMode.LIVE`;
- claim profitability or sufficient proof.

Phase F remains disabled.

## 4. Quote purpose contract

Add a provider-neutral Rust enum:

```rust
pub enum QuotePurpose {
    Entry,
    Exit,
}
```

Persist purpose with each paper quote observation. Existing E14 exit quote persistence remains semantically `Exit`; E15 adds a generic insertion method used for both purposes. The database migration is additive and preserves existing rows as `exit`.

The explicit collector probe becomes:

```rust
pub struct SafetyEvidenceProbe {
    pub probe_policy_version: String,
    pub distribution_request: TokenDistributionRequest,
    pub exit_quote_request: QuoteRequest,
    pub entry_quote_request: Option<QuoteRequest>,
}
```

Rules:

- exit request input mint must equal the candidate mint;
- optional entry request output mint must equal the candidate mint;
- entry input mint must equal exit output mint so both directions refer to one quote asset;
- both quote requests must use the same taker and slippage bps;
- provider failures remain unknown evidence and do not synthesize rows;
- a successful normalized no-route response is explicit unavailable evidence for that purpose.

The default observer remains unchanged; this collector is still opt-in.

## 5. Persistence

Migration `0009_paper_quote_purpose.sql` adds a new append-only table rather than rewriting E14 rows:

```text
paper_quote_snapshots
```

Required fields:

- `candidate_id`
- `purpose` (`entry` / `exit`)
- `provider`
- `probe_policy_version`
- `input_mint`
- `output_mint`
- `taker`
- `input_amount` as canonical decimal text
- `output_amount` as canonical decimal text
- `minimum_output_amount` as canonical decimal text
- `slippage_bps`
- `route_available`
- `price_impact_pct`
- canonical route-label JSON
- `quoted_at_unix_ms`

Semantic uniqueness includes candidate, purpose, provider, probe policy, exact request identity, and quote timestamp. Exact replay is idempotent; same semantic identity with contradictory content fails closed.

Existing `exit_quote_snapshots` is not removed. E14 readers remain unchanged.

## 6. Python paper-quote reconstruction

Create `shreks_brain.observer_campaign` as an isolated Python package.

The read-only store validates additive schema compatibility and exposes exact point-in-time reads. It also reads `token_mint_states.decimals` for the candidate token and requires an explicit caller-supplied quote-asset decimal count and USD value per whole quote token.

No stablecoin is assumed by name. The caller supplies:

```python
@dataclass(frozen=True, slots=True)
class ObserverPaperQuoteAsset:
    mint: str
    decimals: int
    usd_per_token: float
```

For an `ENTRY` quote (`quote_asset -> candidate`):

```text
reference token price = current observer price_usd
input quote-asset USD = input_amount / 10^quote_decimals * usd_per_token
quoted token quantity = output_amount / 10^token_decimals
execution token price = input quote-asset USD / quoted token quantity
quoted_notional_usd = input quote-asset USD
available_notional_usd = input quote-asset USD when route is available
```

For an `EXIT` quote (`candidate -> quote_asset`):

```text
input token quantity = input_amount / 10^token_decimals
output quote-asset USD = output_amount / 10^quote_decimals * usd_per_token
execution token price = output quote-asset USD / input token quantity
quoted_notional_usd = input token quantity * reference token price
available_notional_usd = quoted_notional_usd when route is available
```

No route produces `PaperQuoteState.UNAVAILABLE` with no fabricated execution price. Malformed or zero-denominator raw evidence fails closed.

## 7. Aggregate regime replay

E15 builds B6 aggregate market evidence from the observer SQLite database without changing B6.

`ObserverRegimeReadPolicy` is versioned and caller-supplied:

- `window_ms`
- `max_snapshot_age_ms`
- ordered market source priority
- exact paper quote probe identity used to decide contemporaneous executable breadth.

At `as_of_unix_ms`:

- include candidates discovered on or before `as_of`;
- for each candidate choose one latest allowed market snapshot not later than `as_of` and not older than `max_snapshot_age_ms`;
- `candidate_count` is the count of candidates with a selected market snapshot inside the aggregate window;
- `median_liquidity_usd` and `median_volume_m5_usd` are medians across selected rows and become `None` if any selected candidate lacks the required field, preserving B6 fail-closed semantics;
- `executable_candidate_count` counts candidates with contemporaneous B1 `PASS` plus an exact matching `ENTRY` route-available quote at or before `as_of`;
- source timestamp is the oldest selected market/safety/entry-quote timestamp consumed, never a newer convenient row;
- no later evidence is visible.

Recent strategy performance is caller-supplied or `None`; E15 never fabricates it.

## 8. Dynamic risk context

`build_observer_risk_context` derives risk facts from the current `PaperLoopState` and explicit health/capital inputs.

Caller supplies only facts that cannot be derived from the paper ledger:

```python
@dataclass(frozen=True, slots=True)
class ObserverPaperRiskEnvironment:
    trading_capital_usd: float
    day_started_at_unix_ms: int
    data_healthy: bool
    execution_healthy: bool
    kill_switch_active: bool
```

Derived values:

- open position count from OPEN ledger positions;
- aggregate open risk from current open cost basis;
- daily realized PnL from journal realized deltas booked on/after `day_started_at_unix_ms`;
- rolling drawdown from the chronological equity path reconstructable from starting cash, journal cash flows, and current marks; if a required mark is missing, drawdown is `None` and sealed C4 rejects;
- consecutive losses and last-loss timestamp from chronologically closed positions;
- liquidity, price impact, price-impact notional, and market-data age from current observer/ENTRY quote evidence;
- active intent keys from the paper loop pending entry plus current processed/intended state.

No health value defaults to `True`.

## 9. Cycle assembly

`assemble_observer_paper_cycle(...)` consumes exact sealed policy objects and produces one `PaperCycleInput` plus an audit record.

V1 supports the **Fresh Launch** setup only because its setup input is fully constructible from the observer feature vector and a versioned `FreshLaunchPolicy`. Graduation-breakout and first-pullback require additional lifecycle/context adapters and are intentionally deferred rather than guessed.

Assembly order:

1. load E13 market window;
2. load E15 entry/exit quote evidence;
3. assess E14/B1 safety using the existing exit probe identity;
4. build B2 `FeatureInputs`/`FeatureVector`;
5. build aggregate B6 `RegimeMarketWindow` and call sealed `assess_regime`;
6. build dynamic C4 `RiskContext` from current paper state;
7. build `PaperEntryCandidate` with caller-supplied sealed Fresh Launch, score, decision, risk, and exit policies;
8. build exit observations for currently managed positions from the same point-in-time feature vector and exact position state;
9. reconstruct purpose-correct C3 `PaperQuote` values;
10. create `PaperCycleInput`.

Safety `REJECT` or `INCOMPLETE` is not filtered away; the candidate remains auditable and the sealed score/decision/risk path performs the rejection. Missing execution quote evidence remains `None`, causing sealed C3/C5 defer/reject behavior rather than a synthetic fill.

## 10. Campaign runner

`ObserverPaperCampaignRunner` is an explicit object; no default runtime constructs it.

Public write methods:

- `run_cycle(as_of_unix_ms, created_at_unix_ms)`
- `load_state()`
- `evaluated_trades()`

The runner:

- resolves one exact observer candidate and one exact E6 `RegistryCandidate` attribution;
- restores the latest C6 checkpoint for its `paper_run_id`, or uses a caller-supplied initial `PaperLoopState`;
- assembles a cycle from read-only observer evidence;
- calls sealed `run_paper_cycle`;
- records E11 evidence from the actual `PaperCycleResult`;
- saves the resulting C6 checkpoint with monotonically increasing sequence;
- validates accounting after each applied state;
- fails closed on checkpoint collision, attribution mismatch, invalid accounting, or evidence contradiction.

The runner does not call E12 automatically because E12 thresholds and E8 promotion assessment are independent caller-supplied proof inputs. `evaluated_trades()` exposes the exact E11-normalized trades for downstream E10/E12 evaluation.

## 11. Restart and idempotency

Running the same campaign cycle twice with identical inputs must not create duplicate economic evidence.

- C5 intent keys remain the sealed idempotency mechanism.
- E11 evidence store performs semantic append-only merge.
- C6 checkpoint `(run_id, sequence)` collision with different state fails closed.
- exact repeated cycle at the already-checkpointed `as_of` is treated as an idempotent no-op only when restored state/evidence fingerprints match.
- restart from the latest checkpoint and replaying later cycles must produce the same final `PaperLoopState`, E11 ledger, accounting report, and evaluated trades as uninterrupted execution.

## 12. Testing strategy

TDD must prove:

- migration/additive persistence and restart;
- entry/exit quote purpose attribution;
- bidirectional collector identity validation and failure counting;
- exact quote raw->USD reconstruction using token/quote decimals;
- no-route and malformed evidence fail closed;
- no future rows are selected;
- aggregate regime uses an oldest-consumed timestamp and no look-ahead;
- executable breadth requires B1 `PASS` plus exact entry quote;
- risk context derives ledger facts and refuses unknown drawdown/marks;
- only Fresh Launch is constructible in V1;
- campaign restart equivalence and cycle idempotence;
- E11 evidence equals the actual C5 result;
- public API contains no registry mutation, promotion, signing, submission, or live authority;
- fresh imports do not eagerly load live execution packages.

## 13. Profitability and Phase-F boundary

E15 makes the proof campaign **possible and reproducible**. It does not make a challenger profitable and does not satisfy the live gate by itself.

Live remains disabled until real paper evidence demonstrates the source-of-truth requirements, including sufficient independent sample size, positive expectancy after realistic costs, acceptable drawdown, stable provider/restart behavior, accounting/execution integrity, paper/live parity, reliable risk halts, realistic fill simulation, and reproducible evaluation.
