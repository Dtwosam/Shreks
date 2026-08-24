# Shreks

Shreks is an autonomous Solana memecoin trading system under active development.

The target system will watch the market, reject unsafe or untradeable tokens, identify explicit setups, size risk, execute entries and exits automatically, record outcomes, and learn from a growing point-in-time dataset.

**Current phase:** Phase C — PAPER TRADE  
**Current live-money status:** Disabled

## Architecture

- **Rust — eyes + hands:** Solana-facing ingestion, normalized events, operational storage, and eventual transaction execution.
- **Python — brain:** safety analysis, feature engineering, strategies, risk, paper trading, research, and model evaluation.
- **SQLite WAL — operational state:** active from Phase A2.
- **Parquet — research datasets:** introduced after enough observation data exists.

Shreks is Solana-only for V1 and must not require paid market-data subscriptions or paid RPC plans.

## Runtime modes

The shared runtime vocabulary is:

- `observe` — collect and persist data; no trades.
- `paper` — autonomous simulated trading.
- `shadow` — challenger decisions run without controlling capital.
- `live` — autonomous real execution; unavailable until promotion gates are proven.
- `halted` — no new trading activity.

The default is `observe`.

## Repository layout

```text
crates/
  shreks-core/       Shared Rust domain primitives
  shreks-storage/    SQLite WAL database + migrations
python/
  src/shreks_brain/  Python trading/research brain
  tests/             Python tests
docs/
  superpowers/       Design and implementation plans
.github/workflows/   CI
```

## Operational database

`shreks-storage` owns the Phase A operational SQLite schema. Opening a database automatically:

1. creates missing parent directories,
2. enables WAL journal mode,
3. enables foreign keys,
4. configures normal synchronous behavior and a 5-second busy timeout,
5. applies unapplied migrations transactionally.

Migration 1 creates:

- `schema_migrations`
- `provider_health`
- `token_candidates`
- `market_snapshots`
- `raw_observations`
- `ingestion_checkpoints`

The default runtime path in `.env.example` is `data/shreks.db`. Runtime databases, WAL/SHM files, and Parquet datasets are ignored by Git.

## Future outcome checkpoints

Phase A9 schedules future learning checkpoints for every durable observed candidate at:

- 1 minute,
- 5 minutes,
- 15 minutes,
- 30 minutes,
- 1 hour,
- 4 hours,
- 24 hours.

Checkpoint rows are durable and idempotent. Pending checkpoints survive SQLite/process restart, repeated scheduling does not duplicate them, and a completed checkpoint keeps references to the actual baseline and checkpoint market snapshots used for its metrics.

Outcome sampling runs only as part of normal full observer cycles. Realtime Pump wake-ups between cycles remain durable-write-only. Multiple overdue horizons for one candidate share one market-observation pass, and due work is bounded to at most 16 candidates per cycle while reusing the existing provider pacing. A candidate revisited only for an outcome checkpoint does not trigger mint-state/chain enrichment solely because the checkpoint is due.

When sufficient point-in-time evidence exists, Shreks records return, MFE, MAE, liquidity change, 5-minute volume change, and signed 5-minute buy/sell-count changes. Metrics stay `NULL` when required values are missing or a percentage denominator is not positive. If there is no usable price-bearing snapshot at or after a due horizon, the checkpoint stays pending for a later cycle rather than being falsely completed. `rug_or_dead_pool` and `exitability` also stay `NULL` until an explicit detector or quote provides evidence; absence of a provider pair is not treated as proof.

Phase A9 is observation and dataset infrastructure only. It does not enable transaction signing, transaction submission, paper execution, or live trading.

## Deterministic safety assessment

Phase B1 introduces a dependency-free, point-in-time Python safety core under `shreks_brain.safety`. It consumes already-proven candidate facts and a versioned `SafetyPolicy`; it does not read SQLite or provider payloads directly.

The safety decision is one of:

- `PASS` — no hard blocker exists and all policy-required critical facts are usable;
- `REJECT` — at least one proven hard blocker exists;
- `INCOMPLETE` — no hard blocker is proven, but required critical evidence is missing, stale, future-dated, or contradictory.

Decision precedence is `REJECT > INCOMPLETE > PASS`. Only `PASS` is eligible for later entry consideration. Later strategy scoring is not allowed to reinterpret a hard rejection as a soft penalty, and incomplete critical evidence fails closed rather than being guessed.

Hard/soft thresholds live in explicit `SafetyPolicy` configuration. Findings use stable reason codes and deterministic ordering so later research can measure which rules help or hurt. Soft findings are recorded for later scoring/research but never independently turn a result into `REJECT` or `INCOMPLETE`.

B1 accepts no future outcome checkpoints, realized PnL, future returns, MFE, or MAE. A critical-data timestamp after the assessment time is treated as contradictory evidence rather than fresh data. B1 adds no wallet secrets, signer, swap execution, paper-fill engine, or live-trading path.

## Deterministic feature engine

Phase B2 adds a dependency-light, point-in-time feature engine under `shreks_brain.features`. It converts normalized market observations plus the same-timestamp B1 `SafetyAssessment` into a versioned `FeatureVector`.

B2 is deliberately **not** a trade score. It exposes reproducible raw/derived evidence so later setup logic can be calibrated against Shreks' own post-cost outcome dataset instead of baking assumptions into one opaque formula.

The first schema, `b2-v1`, includes:

- market quality: token age, price, liquidity, 5-minute liquidity change, exit price impact;
- participation: 5-minute/hourly volume, volume velocity, transaction counts;
- flow: buy fractions, buy/sell ratios, buy-pressure acceleration;
- momentum: 1m/5m/15m returns and short-vs-medium momentum acceleration;
- structure: distance from local high and position inside the observed local range;
- safety research flags copied from B1 soft findings.

Named return horizons use versioned timing bands, so a feature called `return_1m_pct` cannot silently use a much newer or older observation. The feature vector also records current source age.

Missing market evidence remains `None`; it is never converted to zero. Zero denominators also produce `None` rather than infinity or artificial extreme signals. Every vector carries a deterministic `missing_features` list so later strategies can require the evidence they actually need.

B1 remains the hard safety gate. B2 computes feature vectors for `PASS`, `REJECT`, and `INCOMPLETE` candidates because rejected candidates are still valuable research data and reduce selection bias; later entry logic must independently require safety `PASS`.

B2 accepts no future outcome checkpoint or realized trade-result fields and does not read SQLite or call providers directly. It adds no setup score, trade intent, paper fill, signer, swap submission, or live-trading path.

## Fresh Launch Continuation setup

Phase B3 introduces the first explicit setup family under `shreks_brain.setups`: `fresh_launch_continuation`.

Fresh Launch Continuation is designed for newly launched Solana memecoins and intentionally avoids first-second blind sniping. It waits for point-in-time evidence that the token has survived long enough to evaluate, still has fresh source data, remains executable, and shows continuation characteristics across participation, volume velocity, buy pressure, short-term momentum, liquidity improvement, and local price structure.

Every numerical setup threshold belongs to an explicit, versioned `FreshLaunchPolicy`. B3 ships **no production default trading thresholds**. Thresholds are research hypotheses that must be calibrated against Shreks' own unseen, post-cost outcome data before they can be treated as useful trading rules.

A setup assessment is one of:

- `BLOCKED` — a hard condition currently prevents entry consideration, including safety not passing, stale data, expired setup window, inadequate liquidity, excessive exit impact, or an already-overextended 5-minute move;
- `WATCH` — no hard blocker is proven, but the setup is too young, evidence is missing, or one or more continuation confirmations have not passed;
- `READY` — safety/executability/age gates pass and all nine continuation confirmations are satisfied.

`READY` is **not** an order or trade instruction. It only means the setup is eligible for later decision, risk, and paper-trading layers. B1 safety `PASS` is mandatory and cannot be overridden by setup strength.

The 5-minute return ceiling is an explicit anti-chase guard: a token can have strong confirmation evidence and still be `BLOCKED` if the move is already too extended under the active policy.

B3's `confirmation_score` is only checklist completeness: `confirmations_passed / 9 * 100`. It is not expected return, win probability, confidence, or a final trade score. Hard-blocked candidates still retain confirmation counts for research so Shreks can later measure the opportunity cost and value of its filters instead of hiding rejected opportunities from the dataset.

B3 adds no `TradeIntent`, position size, paper fill, wallet, signer, transaction construction, submission, or live execution path.

## Pump graduation lifecycle evidence

Phase B4a adds the protocol-evidence prerequisite for a later Graduation/Breakout setup. It does **not** decide whether a graduation is tradable.

The existing single Pump websocket now carries both creation and migration log signals. Realtime delivery remains durable-write-only: a migration wake-up records its signature, full-width Solana slot, and local detection time, but does not fetch the transaction or trigger a setup decision between normal observer cycles.

During a full observer cycle, creation and migration verification share the same hard budget of at most 32 Pump transaction fetches. When migration backlog exists, up to eight slots are serviced first, creation verification can use the remaining capacity, and any unused creation capacity returns to older migration work. This is one shared budget, not separate 32-call budgets.

A normalized `pump_graduation` event is created only from a fetched transaction containing a verified Pump `migrate` or `migrate_v2` instruction with the pinned protocol identities/account layout. A PumpSwap market pair by itself is never graduation evidence, and `MigrateBondingCurveCreator` is intentionally not classified as a token graduation.

The durable lifecycle event preserves the token mint, quote mint, Pump.fun bonding-curve -> PumpSwap venue transition, PumpSwap pool, transaction provider, signature, full `u64` slot, decision-safe `detected_at_unix_ms`, and optional chain `occurred_at_unix_ms`. Legacy migrations normalize the quote asset to wrapped SOL; v2 migrations preserve the instruction's explicit quote mint.

Migration inbox replay is restart-safe and deterministic. Verified lifecycle persistence and terminal inbox completion are atomic, and an already-verified signature cannot silently mutate its normalized lifecycle truth on replay.

B4a adds no Graduation/Breakout threshold, setup score, `TradeIntent`, paper fill, wallet, signer, transaction construction, submission, or live execution path.

## Graduation/Breakout setup

Phase B4b introduces the second explicit setup family under `shreks_brain.setups`: `graduation_breakout`.

Graduation/Breakout requires normalized, protocol-verified B4a `pump_graduation` evidence with the exact Pump.fun bonding-curve -> PumpSwap transition. A PumpSwap pair or generic momentum alone is not enough. The setup consumes that immutable `GraduationContext` beside the unchanged B2 `b2-v1` `FeatureVector`; B4b does not widen the shared B2 schema or read SQLite/provider payloads inside strategy logic.

The first locally observed B4a `detected_at_unix_ms` is the sole graduation decision clock. Optional on-chain `occurred_at_unix_ms` remains audit/research metadata and cannot make a historical setup eligible before Shreks actually observed the migration.

Every numerical threshold belongs to an explicit, versioned `GraduationBreakoutPolicy`. B4b ships **no production default trading thresholds**. The policy values are research hypotheses that must later be calibrated against unseen, point-in-time outcomes after realistic fees, slippage, and exitability constraints.

The setup remains `BLOCKED / WATCH / READY`. Hard blockers include B1 safety not passing, missing or invalid verified graduation evidence, future-dated local detection, an expired post-graduation window, stale market data, inadequate known liquidity, excessive known exit price impact, or an already-overextended one-minute move. A graduation that is still too recent, missing executability evidence, or incomplete confirmation evidence remains `WATCH` when no hard blocker exists.

B4b-v1 uses exactly eight equal-weight confirmations: five-minute transaction participation, volume velocity, five-minute buy fraction, buy-pressure acceleration, one-minute return, five-minute liquidity growth, distance from the local high, and local-range position. Positive five-minute return and 1m-vs-5m momentum acceleration are deliberately excluded because their anchors can straddle the pre/post-graduation regime boundary immediately after migration.

`confirmation_score` is checklist completeness: `confirmations_passed / 8 * 100`. It is not expected return, win probability, confidence, position size, or a final trade score. Blocked candidates still retain computable confirmation evidence so later research can measure the opportunity cost and value of filters rather than hiding rejected opportunities.

`READY` is **not** an order or trading instruction. B4b creates no `TradeIntent`, position size, paper fill, wallet, signer, Jupiter execution request, transaction construction, submission, or live-money path.

## First Pullback setup

Phase B5 introduces the third explicit setup family under `shreks_brain.setups`: `first_pullback`.

First Pullback is not inferred from a single momentum snapshot. It requires explicit point-in-time chronology for `impulse start -> peak -> trough`, then evaluates the current B2 `b2-v1` market observation as the recovery state. Structural evidence later than the current market source observation is rejected so a historical decision cannot borrow a newer trough.

The evaluator derives the initial impulse return, peak-to-trough pullback depth, recovery from the trough, current position versus the prior peak, liquidity retention through the retracement, and the improvement in five-minute buy fraction versus the trough. A current price below the recorded trough invalidates that pullback context instead of being relabeled as a bargain or recovery.

Every numerical threshold belongs to an explicit, versioned `FirstPullbackPolicy`; B5 ships **no production default trading thresholds**. Policy values remain research hypotheses for later unseen, point-in-time, post-cost calibration.

B5-v1 uses exactly nine equal-weight confirmations: recovery from the trough, current price versus the prior impulse peak, liquidity retention, five-minute transaction participation, volume velocity, current five-minute buy fraction, buy-fraction improvement versus the trough, buy-pressure acceleration, and one-minute return. Missing evidence never becomes zero and never passes a confirmation.

Seller absorption is represented only by the auditable proxy `current 5m buy fraction - trough 5m buy fraction`; B5 does not claim to observe hidden order-book absorption. If either side of that comparison is unavailable, the absorption evidence remains unknown.

`confirmation_score` is checklist completeness: `confirmations_passed / 9 * 100`. It is not win probability, confidence, expected return, position size, or a final trade score. Hard-blocked candidates keep all computable structural metrics and confirmation evidence so later research can measure the opportunity cost and value of filters rather than hiding rejected recoveries.

`READY` is **not** an order or trading instruction. B5 adds no `TradeIntent`, sizing, paper fill, wallet, signer, swap request, transaction construction/submission, or live-money path.

## Explainable market regime

Phase B6 repairs an ordering gap in the repository by adding the explainable market-regime layer required by the source-of-truth build sequence before deterministic scoring. The branch is called B6 only to preserve repository chronology; functionally this is the planned regime-engine capability.

The regime engine lives under `shreks_brain.regime` and leaves the shared feature schema exactly at `b2-v1`. It produces one timestamped, versioned global market assessment with the labels `HOT`, `NORMAL`, `WEAK`, or `DEAD`; it does not widen individual token features or call setup evaluators.

The base regime is intentionally transparent rather than a weighted black-box score. It uses four aggregate market dimensions: candidate opportunity rate, executable-candidate breadth, median liquidity, and median five-minute volume. A candidate rate or executable fraction at the configured DEAD ceiling makes the base regime `DEAD`; otherwise any dimension below its WEAK minimum makes the base regime `WEAK`; all four at or above HOT minima make it `HOT`; a healthy mixed market is `NORMAL`.

Critical evidence quality fails closed. Future-dated or stale market source data, an undersized/too-short market window, no candidates, or missing critical liquidity/volume medians classify the base regime as `DEAD` with stable reason codes. This means Shreks pauses entry eligibility rather than guessing that incomplete global evidence is healthy.

Optional recent strategy performance is deliberately asymmetric. Once there is a configured minimum sample of closed trades, poor **after-cost** expectancy may downgrade the market regime to `WEAK` or `DEAD`; strong recent performance can never upgrade a weaker base market into `HOT`. This prevents a recent winning streak from creating a self-reinforcing pro-risk label. Future-dated performance is also rejected fail-closed.

Every numerical threshold belongs to an explicit, versioned `RegimePolicy`; B6 ships **no production default regime thresholds**. Those values remain research hypotheses to be calibrated on unseen point-in-time data and later paper results after realistic costs.

A regime label is **not** a trade instruction, expected-return forecast, confidence score, or sizing command. B6 adds no wallet intelligence, deterministic trade score, `TradeDecision`, `TradeIntent`, position sizing, paper fill, signer, swap request, transaction submission, or live-money path.

## Deterministic candidate score

Phase B7 adds the source build-order deterministic-score capability under `shreks_brain.scoring`. The B7 label preserves repository chronology; the shared B2 feature schema remains exactly `b2-v1`.

Score-v1 combines four explicit `0..100` candidate families: safety quality, money flow, setup quality, and liquidity/executability. Safety quality applies only configured penalties for the current B2 soft-safety flags; money flow normalizes volume velocity, five-minute buy fraction, and buy-pressure acceleration; setup quality passes through the selected setup family's confirmation score; liquidity/executability combines normalized liquidity with inversely normalized exit price impact.

Every family weight, soft-safety penalty, and normalization endpoint belongs to a required versioned `ScorePolicy`. B7 ships **no production scoring policy, weights, or entry threshold**. The values are hypotheses to be calibrated later against unseen point-in-time outcomes and realistic paper-trading costs.

Missing evidence never becomes zero and never causes silent weight renormalization. If a family with positive configured weight cannot be computed, `total_score` remains `None`. A deliberately zero-weight family may be absent for controlled ablation research because the remaining configured weights already sum to one.

B1 safety and setup eligibility stay independent from scoring. `REJECT`/`INCOMPLETE` safety candidates and `BLOCKED`/`WATCH` setups may still receive a numeric research score when the underlying score evidence is complete, preserving rejected opportunities for filter-value and selection-bias research. Their original safety decision and setup state are carried into the score assessment and cannot be changed by a high score.

The B6 `HOT / NORMAL / WEAK / DEAD` regime is also carried into the score assessment but is not a weighted score-v1 component. This avoids double-counting global liquidity/volume conditions; the later Decision Engine owns regime-specific entry permission and score-threshold policy.

Wallet quality is intentionally absent from score-v1 rather than zero-filled. The repository does not yet have the Phase D wallet-history, confidence, and independence evidence needed to make a statistically defensible wallet score.

`total_score` is **not** win probability, expected return, confidence, position size, or trade permission. B7 adds no `TradeDecision`, `TradeIntent`, risk sizing, paper fill, wallet/signing, transaction construction/submission, or live-money path.

## Deterministic entry decision engine

Phase B8 adds the source build-order Decision Engine under `shreks_brain.decision`. It consumes one B7 `ScoreAssessment` and an explicit versioned `DecisionPolicy`; it does not recompute safety, setup, regime, or score evidence.

The public decision vocabulary is `REJECT / WATCH / ENTER / HOLD / REDUCE / EXIT`, but B8-v1 is intentionally pre-entry only and emits exactly `REJECT`, `WATCH`, or `ENTER`. `HOLD`, `REDUCE`, and `EXIT` are reserved for the later position/exit layer, where actual open-position evidence will exist.

Entry precedence is fail-closed and fixed: score-policy compatibility, B1 safety decision, setup state, exact setup rule, market regime, total-score availability, then the selected threshold. A high score cannot bypass a safety rejection, incomplete critical safety evidence, blocked setup, missing setup rule, disabled setup, or DEAD regime.

Each setup has its own optional HOT/NORMAL/WEAK threshold in `DecisionPolicy`. There is no global fallback rule. A `None` threshold explicitly disables entry for that setup/regime and returns `WATCH`; `DEAD` always returns `REJECT`. Threshold equality is eligible for `ENTER`.

B8 ships **no production decision policy or score thresholds**. Those values remain research hypotheses for calibration on unseen point-in-time and later realistic paper results.

`ENTER` is not an order. It means only that the candidate may be forwarded to the independent Risk Engine. B8 adds no requested notional, capital percentage, position size, slippage allowance, idempotency key, `TradeIntent`, paper fill, wallet/signing, transaction construction/submission, or live-money path.

## Fail-closed risk engine and stable TradeIntent

Phase B9 adds the source build-order Risk Engine under `shreks_brain.risk`. It accepts only a B8 `ENTER` decision plus an immutable point-in-time `RiskContext` and explicit versioned `RiskPolicy`; it performs no provider, storage, balance, or wall-clock reads itself.

The risk engine independently rechecks upstream decision-policy/schema compatibility, safety `PASS`, setup `READY`, non-DEAD regime, score availability, and timestamp alignment before evaluating portfolio risk. It then enforces runtime mode, global kill switch, data/execution health, trading capital, simultaneous-position count, aggregate open risk, daily realized loss, rolling drawdown, consecutive-loss cooldown, minimum liquidity, expected price impact, price-impact quote size, market-data freshness, and duplicate-active-intent protection. Any unknown critical guardrail fails closed rather than becoming zero or healthy by assumption.

Entry size is deterministic and independent of strategy score: it is the minimum of target position notional, maximum per-position notional, configured capital-per-position fraction, and remaining aggregate-risk capacity. Until Phase C has authoritative stop/position/exit state, the full requested entry notional counts as incremental aggregate risk; B9 does not pretend an unimplemented stop reduces capital at risk.

Price-impact evidence is explicitly size-aware. The context records the notional covered by the impact estimate, and that notional must be at least the final risk-sized entry. An impact quote for a smaller trade cannot authorize a larger `TradeIntent`, even if its percentage looks attractive.

Approved intents use deterministic SHA-256 idempotency over the entry identity. Re-evaluating the same entry idea under a changed risk-policy version does not create a second active idea, and an already-active key is rejected before intent construction.

`TradeIntent` is now the stable boundary that Phase C paper execution and future live execution are designed to share. It carries mint, BUY/SELL side vocabulary, requested notional, slippage ceiling, strategy/setup version, score/decision/risk policy versions, reason, idempotency key, execution mode, and point-in-time timestamp. It deliberately carries no route, quote, fill, transaction, signature, wallet secret, or realized outcome.

B9 may produce intents only for `paper` and `shadow`. `observe` and `halted` cannot produce intents, and `live` is hard-disabled regardless of policy. B9 ships **no production risk-policy defaults** and touches no money; it creates only a validated domain intent for the next paper-trading phase.

## Realistic paper execution

Phase C1+C2 adds the first paper-trading execution boundary under `shreks_brain.paper`. It consumes the exact B9 `TradeIntent` interface and immutable caller-supplied execution evidence; the simulator performs no storage, provider, balance, wall-clock, or random-number reads itself.

Paper execution is deterministic and point-in-time safe. An explicit latency delay defines when an intent first becomes executable, and a bounded quote window defines how long matching evidence remains acceptable. A quote observed after the evaluation timestamp is rejected as future evidence, quotes before the latency boundary are deferred while the window remains open, and quotes after the deadline fail rather than being silently backfilled.

The simulator never extrapolates a quote beyond the size it actually covers. Filled notional is the minimum of requested notional, quoted notional, and evidenced available notional. That same rule applies to BUY and SELL, so future exit logic cannot assume a perfect liquidation when the market only evidences capacity for a partial exit. Partial fills are policy-controlled and must meet an explicit minimum fraction.

Paper outcomes are `DEFERRED`, `FAILED`, `PARTIAL`, or `FILLED`. Route-unavailable evidence fails with no invented fill or cost. A supplied failed-after-submission state records no fill but still charges the configured network cost, preserving an expense that a toy simulator would otherwise hide.

Slippage is side-aware: higher execution prices are adverse for BUYs and lower execution prices are adverse for SELLs. Slippage is represented by the execution price plus signed audit fields; it is not charged again as a separate fee. Explicit costs are only the configured swap fee and network fee. BUY cash flow is filled notional plus explicit costs leaving the account; SELL cash flow is proceeds less explicit costs entering the account.

C1+C2 ships **no production paper-fill policy defaults**. The layer deliberately does not own positions, balances, weighted entry price, realized/unrealized PnL, exit rules, autonomous looping, persistence, wallet/signing, transaction construction/submission, or live execution. Those responsibilities begin with the later Phase C accounting and exit layers.

## Authoritative paper position ledger

Phase C3 adds the authoritative in-memory paper accounting layer under `shreks_brain.paper`. It is a pure, replayable reducer over C1 terminal execution results: every terminal booking appends an immutable journal entry and derives immutable position snapshots, while `DEFERRED` results remain true no-ops that neither consume idempotency nor move accounting time.

Position accounting is intentionally cost-aware. Execution-weighted entry price excludes explicit fees so price evidence stays interpretable, while `open_cost_basis_usd` includes filled BUY notional plus already-incurred BUY swap/network fees. On a SELL, realized PnL is the net sale cash flow minus the proportional all-in open cost basis. Entry and exit costs are therefore counted exactly once; `accumulated_costs_usd` is an audit total and must not be subtracted from PnL again.

Failed post-submission attempts remain economically visible even when no tokens move. Their network fee reduces simulated cash and realized PnL, and a failed exit attempt is linked to the current open lifecycle so strategy-level paper expectancy cannot silently ignore execution failures.

Open positions carry quantity, weighted entry, all-in open basis, realized PnL, accumulated costs, lifecycle timestamps, and fill counts. A partial exit releases basis proportionally. A full exit closes the lifecycle without erasing its historical entry evidence. If the same mint is bought again later, C3 appends a new deterministic lifecycle instead of mutating the closed one.

Point-in-time marks compute `quantity * mark_price - open_cost_basis`. This includes incurred entry costs but deliberately excludes hypothetical future SELL fees, slippage, price impact, and liquidity constraints because a mark is not an executable quote. Marked unrealized PnL is therefore accounting evidence, not guaranteed realizable PnL. If any open position lacks a current mark, aggregate unrealized PnL remains unknown rather than treating the missing position as zero.

Every ledger snapshot self-reconciles cash, realized PnL, accumulated costs, processed terminal keys, journal sequence, and per-position linked economics. C3 models no leverage: any terminal cash flow that would make simulated cash negative is rejected instead of creating impossible paper capital.

C3 supplies **no production starting capital**, persistence/restart wiring, stop loss, take profit, trailing stop, maximum hold, emergency exit rule, autonomous paper loop, wallet/signing, transaction construction/submission, or live-money path. Exit decisions begin in C4; realistic SELL execution continues to use the same C1 adapter and C3 books only what that adapter actually fills.

## Deterministic paper exit engine

Phase C4 adds the first position-aware exit decision layer under `shreks_brain.exits`. It reuses the unchanged B2 `b2-v1` `FeatureVector` for price, liquidity, flow, and momentum evidence and the C3 `PaperPosition` for authoritative entry price, quantity, lifecycle, and booked holdings. The exit evaluator itself performs no provider, storage, wall-clock, balance, or random-number reads.

C4 makes `HOLD`, `REDUCE`, and `EXIT` first-class deterministic decisions. Structural contradictions and unusable point-in-time evidence fail closed to `HOLD` rather than inventing an executable exit. Global halt and maximum-hold rules are the deliberate exceptions: once structurally coherent, they may demand a full `EXIT` even when current market/quote evidence is stale or the current price is unavailable. With usable evidence, liquidity emergencies outrank hard stops, trailing stops, explicit wallet-distribution evidence, flow/momentum deterioration, and staged take profits. Every assessment has exactly one primary reason while retaining simultaneously proven lower-priority triggers as supporting findings for research.

Every numerical threshold belongs to an explicit, versioned `ExitPolicy`; C4 ships **no production exit thresholds or default policy**. Equality at a configured boundary triggers deterministically using a fixed arithmetic tolerance. The thresholds are hypotheses that must be calibrated on unseen, point-in-time paper outcomes after actual costs and exitability constraints rather than treated as claims of profitability.

Exitability evidence is explicitly size-aware. `ExitExecutionContext` carries route state, available exit notional, expected price impact, and the notional covered by that impact estimate. Missing route/capacity/impact evidence stays unknown. The B2 size-unknown impact field and a C3 mark are not treated as proof that the full position can actually be liquidated at that price.

C4 maintains immutable high-water and take-profit state per position lifecycle and exit-policy version. High water can only increase on usable current evidence. The earliest incomplete take-profit level is the only profit-taking level eligible to fire on a decision. Crucially, a take-profit decision does **not** mark that level complete: `acknowledge_exit_fill` advances the level only after authoritative C3 before/after position quantities prove that at least the targeted reduction was actually booked. Failed, no-fill, or undersized partial exits leave the level incomplete so the strategy cannot claim profits it did not realize.

Wallet distribution remains an optional tri-state input. `None` means unknown and cannot trigger an exit; C4 does not fabricate the Phase D wallet-history, clustering, or independence evidence that has not yet been built.

C4 outputs an exact target reduction fraction and token quantity, but deliberately does **not** create a SELL `TradeIntent`. The existing shared intent boundary is USD-notional based; converting a quantity target into a fixed notional at decision-time price could oversell the C3 position if execution price moves before the fill. C5 owns safe quote-aware wiring from C4 quantity targets into the existing `TradeIntent -> C1 realistic execution -> C3 accounting` path. C4 adds no autonomous loop, persistence, signer, transaction construction/submission, or live-money path.

## Autonomous paper loop

Phase C5 adds deterministic repeated PAPER orchestration under `shreks_brain.paper_loop`. It does not replace any earlier trading logic: the loop composes the existing setup evaluators, B7 score, B8 decision, B9 risk, C1 realistic execution, C3 accounting, and C4 exits into one immutable cycle state machine.

C5 permits at most one approved new BUY attempt per cycle and carries at most one deferred BUY. This is a correctness rule, not a profitability claim: multiple B9 approvals from point-in-time risk snapshots captured before the first fill could reuse stale capital or aggregate-risk capacity. A mint already OPEN in C3 is not pyramided by C5-v1. A lifecycle opened during a cycle begins C4 monitoring only on the next cycle so pre-entry evidence cannot be reused as post-fill exit evidence.

C4 authorizes exits in token quantity while the stable `TradeIntent` boundary is USD-notional. C5 therefore persists an unexecuted C4 `ExitAssessment`/quantity target across latency, **not** a fixed SELL intent or stale USD notional. When execution becomes eligible, C5 computes `requested_notional_usd = authorized_target_quantity * current_quote_execution_price` using the exact quote C1 will consume. Because C1 caps filled notional by requested/quoted/available size and derives quantity from that same execution price, simulated filled quantity cannot exceed the C4-authorized token quantity.

Pending exit precedence is intentionally fail-safe. A newer full `EXIT` may supersede a pending `REDUCE`, but HOLD or a weaker reduction cannot cancel an already-authorized full exit. The newer stronger exit keeps its own timestamp; C5 never backdates later evidence merely to satisfy latency. A terminal SELL attempt clears the pending exit, and a still-open lifecycle needs a fresh C4 decision before another attempt.

Every SELL still follows exactly `TradeIntent -> C1 execute_paper_intent -> C3 apply_paper_execution`. C5 does not implement a second fill or PnL formula. Partial fills, route failures, quote-window expiry, adverse slippage, swap/network costs, and failed-after-submission costs therefore remain economically visible. Take-profit progress is advanced only by C4 `acknowledge_exit_fill` after authoritative C3 before/after quantities prove the target reduction was actually booked.

Every position OPEN at cycle start is independently monitored when evidence is supplied. Missing exit observations do not invent a C4 HOLD. Still-open positions are marked only when the fresh C4 assessment exposes usable current price evidence. The loop returns immutable per-cycle entry/exit results plus next state for audit/replay; C6 owns durable persistence and restart recovery.

C5 ships **no production thresholds, starting capital, fill assumptions, or strategy ordering defaults**. It adds no provider/RPC/storage reads, wallet intelligence, signer, Solana transaction construction/submission, or live execution. `live` remains disabled.

## Paper accounting validation and restart recovery

Phase C6 adds `shreks_brain.paper_validation` plus Rust-owned migration 0006 to prove that C5 paper state remains economically reconcilable and restart-safe. It does not change C1 fills, C3 accounting formulas, C4 exits, or C5 trading decisions.

The accounting validator independently recomputes cash, realized PnL, accumulated costs, lifecycle-linked realized/cost evidence, running quantities, marked open-position market value, equity, and net PnL from the immutable C3 journal and positions. It explicitly counts partial reductions, terminal execution failures, open/closed lifecycles, and winning/losing/flat closed lifecycles. If any OPEN position is unmarked, portfolio unrealized PnL/equity remains `INCOMPLETE` rather than treating missing evidence as zero. Contradictory accounting is `INVALID`; C6 never repairs the ledger behind the caller's back.

Durable checkpoints use the same WAL-mode operational SQLite database. Migration 0006 owns the append-only `paper_loop_checkpoints` table; Python does not create or migrate it. State payloads are canonical JSON over an explicit allow-list of C3/C4/C5/B9 immutable types, with exact hexadecimal finite floats, deterministic tuples/frozensets, and SHA-256 integrity. Pickle, eval, dynamic imports, arbitrary class paths, and executable deserialization are not used.

Checkpoint writes are deterministic and collision-safe. Re-saving the same run/sequence with identical state and metadata is idempotent; a different payload at the same sequence is rejected, and a new lower sequence cannot be inserted after a higher checkpoint. On load, checksum and row/envelope metadata must agree before restored state is accepted.

File-backed restart tests close and reopen SQLite through a fresh connection, restore the exact `PaperLoopState`, compare canonical state fingerprints and accounting reports, prove duplicate terminal C3 intents cannot be rebooked, and continue C5 afterward with multiple OPEN positions independently monitored and marked. This validates durable mechanics, not strategy profitability.

C6 ships **no production thresholds, starting capital, strategy-profitability claim, signer, transaction submission, or live-money authority**. Completing these mechanics permits extended realistic PAPER evaluation; promotion still requires positive unseen expectancy after realistic costs, acceptable drawdown, stable provider/restart behavior, reproducible evaluation, and no unresolved accounting or execution defects. `live` remains disabled.

## Wallet observation store

Phase D1 adds the first durable wallet-evidence layer in Rust without turning wallet activity into a trading signal. `WalletObservation` records provider, wallet, candidate mint, broad action class (`buy`, `sell`, `transfer`, `liquidity_event`, `creator_action`, or `other`), whether the classification is `direct` or `inferred`, transaction signature/event index, full-width Solana slot, decision-safe local observation time, optional chain time, optional signed raw token/counter-asset deltas, venue, and counterparty evidence.

Wallet amount evidence is stored as signed raw integer units rather than floating-point UI amounts. Full `u64` slots and signed `i128` deltas are persisted as canonical decimal text, so SQLite never narrows Solana-width values into signed 64-bit integers. Missing deltas remain missing, and an inferred classification remains distinguishable from direct evidence.

The durable event identity is provider + signature + event index + wallet + candidate mint. An identical replay is idempotent and may only move the stored local observation timestamp earlier. If a replay changes action, evidence class, slot, chain time, deltas, counter asset, venue, or counterparty, storage rejects the contradiction instead of rewriting wallet history. Writes are accepted only for mints already known in `token_candidates`.

Migration 0007 adds restart-safe `wallet_observations` storage and deterministic inclusive time-bounded queries by candidate mint or wallet. The local `observed_at_unix_ms` remains the point-in-time availability clock; optional on-chain occurrence time is audit metadata and cannot backdate what Shreks knew.

D1 adds **no provider/RPC ingestion wiring, historical wallet backfill, trade reconstruction, wallet PnL, wallet ranking, clustering, smart-wallet score, B2 feature, setup/decision/risk change, signer, transaction submission, or live-money authority**. Those intelligence steps remain D2–D5 so wallet behavior can be tested with real sample-size, confidence, and independence evidence before it is allowed to influence trading.

## Local setup

### Rust

Install a stable Rust toolchain, then run:

```bash
cargo metadata --no-deps --format-version 1
cargo test --workspace
```

### Python

Python 3.12 or newer is required.

```bash
python -m venv .venv
```

Activate the environment using the command appropriate for your shell, then:

```bash
python -m pip install -e './python[dev]'
python -m pytest python/tests -q
```

## Configuration

Copy `.env.example` to a local `.env` when runtime configuration is needed.

Never commit:

- private keys,
- seed phrases,
- wallet secrets,
- real `.env` files,
- production API secrets.

The repository intentionally does not contain a live-wallet secret variable during the current pre-live phases.

## Build discipline

The required progression is:

```text
OBSERVE -> UNDERSTAND -> PAPER TRADE -> EVALUATE -> LEARN -> PROVE -> LIVE TRADE
```

Live execution is not an early demo milestone. Paper and live modes will share the same decision and risk path; only the execution adapter changes.

See `docs/superpowers/specs/2026-08-23-shreks-master-design.md` for the approved architecture. Design and implementation plans are under `docs/superpowers/`.

## Wallet trade reconstruction

Phase D2 adds a pure Python point-in-time reconstruction layer under `shreks_brain.wallets`. It consumes caller-supplied normalized D1 `WalletObservation` evidence and performs no provider, RPC, or SQLite reads inside reconstruction.

`observed_at_unix_ms` is the availability clock. Future local observations are rejected even when their optional chain time is older, so reconstruction cannot borrow evidence Shreks had not yet observed.

D2 estimates a closed outcome only for a clean known-inventory BUY/SELL cycle that uses one counter asset and returns cumulative candidate-token inventory exactly to zero. Partial exits remain part of the same open episode until known inventory reaches zero; D2 does not invent proportional cost-basis allocations or realized PnL while inventory remains open.

Missing economics, sign contradictions, a SELL without known starting inventory, an oversell, a counter-asset change, or a non-trade inventory change makes the history explicitly `UNRESOLVED` and halts later reconstruction for that wallet/mint instead of manufacturing continuity or PnL. Direct and inferred evidence remain distinguishable as `DIRECT`, `MIXED`, or `INFERRED`.

D2 produces reconstruction evidence only. It adds **no wallet score, wallet profile, clustering/independence claim, smart-wallet feature, setup/decision/risk change, signer, transaction submission, or live-money authority**. D3 must build confidence-weighted wallet histories before wallet behavior can be evaluated as a trading signal.

## Confidence-weighted wallet profiles

Phase D3 adds a pure Python profile layer under `shreks_brain.wallets`. It consumes only caller-supplied D2 reconstructions at the exact profile `as_of_unix_ms` plus optional caller-supplied versioned episode research context; it performs no provider, RPC, SQLite, wall-clock, price, FX, or token-decimal lookup.

Only D2 `CLOSED` episodes contribute to return, win-rate, hold-time, raw-PnL, and optional context aggregates. `OPEN` and `UNRESOLVED` episodes stay explicit counts and never become zero-return trades. DIRECT, MIXED, and INFERRED closed evidence receive weights only from an explicit `WalletProfilePolicy`; effective sample size and `evidence_sample_confidence` measure evidence amount/quality only, not win probability, expected return, or wallet quality.

Raw realized PnL is aggregated only when every closed episode uses the same counter-asset mint. D3 performs no cross-asset conversion. Optional entry quality, candidate-discovery-to-entry delay, drawdown, rug exposure, and regime history require explicit context observed no earlier than the target episode close and no later than the profile as-of time. Context semantic versions cannot be mixed, and unknown optional values remain unknown rather than becoming zero or false.

D3 produces descriptive wallet-history evidence only. It adds **no wallet ranking, smart-wallet label, clustering/independence claim, D5 smart-wallet feature, setup/score/decision/risk change, signer, transaction submission, or live-money authority**. D4 must establish independence/clustering evidence before wallet-derived signals can be treated as multiple independent confirmations.

## Wallet independence and coordination evidence

Phase D4 adds a pure Python point-in-time relationship layer under `shreks_brain.wallets`. It consumes only caller-supplied relationship evidence and an explicit versioned `WalletRelationshipPolicy`; it performs no provider, RPC, SQLite, wall-clock, balance, transaction-history, graph-service, or external-attribution reads.

Every possible wallet pair remains explicitly `LINKED`, `INDEPENDENT`, `CONFLICTING`, or `UNKNOWN`. Missing linkage evidence is never converted into independence. Direct and inferred evidence are provenance-weighted, but potentially correlated clues are never summed: each direction uses only its strongest weighted evidence, with deterministic provenance and lexical tie-breaking.

Strong `LINKED` and `CONFLICTING` pairs form conservative connected components so coordinated wallets cannot be counted as multiple confirmations. `maximum_independent_group_count` is only the number of components after those strong edges are collapsed; it is an upper bound, not proof that the remaining groups are independent. `all_pairs_independent_under_evidence` is true only when every possible pair is explicitly independent under the active policy, or fewer than two wallets exist.

D4 preserves uncertainty and does not claim common ownership, control, identity, or profitability. It adds **no wallet ranking, smart-wallet label, D5 wallet feature, setup/score/decision/risk change, signer, transaction submission, or live-money authority**. D5 must decide whether wallet quality plus D4 independence evidence can become a useful research feature, and unseen post-cost evaluation must prove any value.

## Smart-wallet research features

Phase D5 adds a parallel pure Python wallet-feature contract under `shreks_brain.features` with schema `d5-wallet-v1`. The sealed market feature schema remains exactly `b2-v1`; D5 does not silently widen `FeatureVector` or change existing setup, score, decision, risk, paper, or exit behavior.

The D5 reducer consumes only caller-supplied D2 candidate trade chronology, D3 confidence-weighted wallet profiles, the exact-time D4 relationship assessment, and optional D1 creator/deployer observations. All D2/D3/D4 evidence must align to the same `as_of_unix_ms` and wallet set, future local observations fail closed, and the reducer performs no provider, RPC, SQLite, wall-clock, price, FX, or token-decimal reads.

Wallet history strength is explicit `STRONG`, `NOT_STRONG`, or `UNKNOWN` under a caller-supplied versioned `WalletFeaturePolicy`. Positive effective history and evidence confidence are required; configured missing rug/drawdown evidence remains `UNKNOWN` unless another known threshold failure already proves `NOT_STRONG`. D5 creates no global smart-wallet label or composite wallet score.

D5 exposes inclusive recent entry/exit wallet counts, confidence-weighted strong-entry/exit support, and deterministic entrant historical return/win-rate aggregates. An exact independently-strong entrant count exists only when every strong-entrant pair is explicitly `INDEPENDENT` under D4; `LINKED`/`CONFLICTING` evidence blocks the claim and `UNKNOWN` stays unknown. D4 components connected through non-entrant bridge wallets remain visible through coordination-cluster and maximum-independent-group upper-bound features.

Creator/deployer activity is the count of supplied D1 `CREATOR_ACTION` observations inside the configured local observation window. Zero means zero qualifying supplied observations, not proof that no such activity happened elsewhere.

D5 is research evidence only. It adds **no Smart Wallet Cluster entry eligibility, production wallet-strength thresholds, B7/B8/B9 policy change, `TradeIntent`, position size, signer, transaction submission, or live-money authority**. D6 must export point-in-time-safe research datasets, and later unseen post-cost evaluation must prove whether the D5 wallet features improve trading results.

## Point-in-time research dataset export

Phase D6 adds a pure Python research-export boundary under `shreks_brain.research` with schema `d6-research-v1`. Each logical record is one candidate decision snapshot identified by `(candidate_mint, as_of_unix_ms)`, and `REJECT`, `WATCH`, and `ENTER` candidates are all retained so rejected opportunities remain available for selection-bias and filter-opportunity-cost research.

Future labels are decision-anchored rather than silently reused from candidate discovery. Every row carries the seven approved 1m, 5m, 15m, 30m, 1h, 4h, and 24h horizons, and a label baseline must equal the row decision timestamp. A discovery-anchored A9 checkpoint can be reused only when its actual baseline matches that decision timestamp; otherwise later historical replay must derive a decision-anchored label.

The physical schema keeps decision-time features/provenance and future targets structurally separate: 93 feature columns contain no `label_` prefix, while all 98 future-label columns do. Pending future metrics remain null rather than becoming zero. D5 wallet-strength audit rows are preserved as canonical JSON and reason/missing-code collections remain list-valued research evidence.

Dataset rows are deterministically sorted and receive a logical SHA-256 fingerprint over the canonical row values, including exact finite-float encoding. The fingerprint is independent of output path and Parquet byte layout, so writer/library changes cannot silently redefine logical dataset identity.

Parquet output uses an explicit schema, Zstandard compression, and metadata carrying the D6/B2/D5 schema versions, horizon set, row count, and logical digest. PyArrow is lazy-loaded and isolated behind the optional `shreks-brain[research]` extra; importing or building logical D6 research rows does not require it.

D6 does **not** read SQLite, replay history, generate missing labels, train or promote a model, change strategy/score/decision/risk behavior, create a `TradeIntent`, size capital, sign or submit transactions, or enable live trading. Phase E must use chronological replay and unseen post-cost evaluation to determine whether the wallet/market research evidence actually improves expectancy.

## Historical decision replay

Phase E1 adds a pure Python historical replay boundary under `shreks_brain.backtest` with schema `e1-replay-v1`. It recomputes the existing Fresh Launch, Graduation/Breakout, and First Pullback setup assessments from point-in-time decision evidence, then reuses B7 scoring and B8 entry decision logic under explicit caller-supplied policies.

Future D6 outcome labels are not part of replay decision inputs. They enter through a separate identity-matched bundle and are attached only after setup, score, and decision have been recomputed for the exact `(candidate_mint, as_of_unix_ms)`. Rejected and watched candidates remain in the replay output alongside entries, and D5 wallet features are preserved for research segmentation without being injected into the current B7/B8 decision path.

E1 performs no SQLite, provider, filesystem, network, PyArrow, or wall-clock reads and computes no profitability metric. It adds no risk sizing, paper/live execution, model training or promotion, signer, transaction submission, or live-money authority. Later chronological splitting, baselines, model training, and post-cost evaluation remain separate Phase E work.
