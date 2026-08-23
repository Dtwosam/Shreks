# Phase B9 Risk Engine — Verification Record

**Goal:** Add the source build-order Risk Engine capability as a pure fail-closed layer that accepts a B8 `ENTER`, risk-sizes it from explicit point-in-time portfolio/health/executability evidence, and either rejects it or returns the stable `TradeIntent` interface for Phase C paper execution.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b9-risk-engine-design.md`

**Base:** verified B8 head `38f1d1b1f7de80a7504d92904c0314df22ce94f7`.

## Implemented contract

- `shreks_brain.risk` is pure and performs no SQLite, provider, balance, or wall-clock I/O.
- Risk independently rechecks decision-policy/schema compatibility, `ENTER`, safety `PASS`, setup `READY`, non-DEAD regime, score availability, and point-in-time timestamp alignment.
- PAPER and SHADOW may produce intents; OBSERVE, HALTED, and LIVE cannot.
- LIVE is hard-disabled in B9 regardless of supplied policy.
- Global kill switch, data health, and execution health fail closed before portfolio sizing.
- Trading capital, simultaneous-position count, aggregate open risk, daily realized loss, rolling drawdown, and consecutive-loss cooldown are explicit required guardrails.
- Minimum liquidity, expected entry price impact, impact-estimate notional coverage, and market-data age are explicit required executability guardrails.
- Missing critical evidence is never converted to zero, healthy, or permissive.
- Entry size is deterministic and independent of strategy score: minimum of target position notional, per-position notional cap, capital-fraction cap, and remaining aggregate-risk capacity.
- Until authoritative Phase C stop/position/exit state exists, the full requested entry notional is treated as incremental aggregate open risk.
- Price-impact evidence must cover at least the final risk-sized entry notional; a smaller quote cannot authorize a larger intent.
- SHA-256 idempotency is deterministic over entry identity and intentionally excludes risk-policy version so a changed risk policy cannot duplicate the same active entry idea.
- Duplicate active intent keys reject before intent construction.
- No production `RiskPolicy` instance or thresholds exist.
- B9 creates no paper fill, position ledger, exit engine, route request, signer, transaction, transaction submission, or live-money path.

## Stable public API

`shreks_brain.risk` exports exactly:

```text
RiskAssessment
RiskContext
RiskFinding
RiskPolicy
RiskReasonCode
RiskState
TradeIntent
TradeSide
assess_entry_risk
```

`TradeIntent` fields are:

```text
mint
side
requested_notional_usd
max_slippage_bps
strategy_name
strategy_version
score_policy_version
decision_policy_version
risk_policy_version
reason
idempotency_key
execution_mode
as_of_unix_ms
```

It contains no route, quote, fill, transaction, signature, private key, wallet secret, realized PnL, or unrealized PnL.

## Design refinement before implementation

The initial B9 spec correctly required expected price impact but did not explicitly bind that estimate to a trade size. Self-review fixed this before TDD production code:

- added `RiskContext.price_impact_notional_usd`;
- required the impact estimate notional to be at least the final risk-sized notional;
- added stable unknown/undersized reason codes;
- removed an unreachable synthetic `NO_ENTRY_CAPACITY` state because preceding validated portfolio gates mathematically guarantee a positive minimum sizing result.

Corrected normative spec commit: `6e5d10492f0cab6afe230ea28242318dd6c9fea5`.

## TDD evidence

### Task 1 — immutable risk models and stable intent domain

RED:
- commit `bea8f55ae1a7e7c9a80bc0f4d35b2e56fe80a354`
- CI `32669847526`
- Python failed exactly because `shreks_brain.risk` did not exist.
- Repository safety remained green; workspace metadata remained green once Rust setup reached it.

GREEN:
- commit `70530637c0cd19c2e92929a03504a4b82cdf6633`
- CI `32669903174`
- Rust tests, Python tests, workspace metadata, and repository safety all passed.

### Task 2 — pure fail-closed evaluator

RED:
- commit `6003a1b2bbcdb776d1e5d204a69298c95e98fdd5`
- CI `32670000249`
- Python failed exactly because `shreks_brain.risk.engine` did not exist.
- Repository safety and workspace metadata remained green.

GREEN:
- commit `96cf377924f9613d9cb0f602180278f234e8fa22`
- CI `32670055983`
- Rust tests, Python tests, workspace metadata, and repository safety all passed.

The GREEN suite pins:
- every upstream/runtime/kill-switch/health/portfolio/loss/cooldown/executability reason;
- exact boundary behavior for position count, aggregate risk, daily loss, drawdown, cooldown, liquidity, price impact, impact-notional coverage, and market-data age;
- all four independent sizing caps;
- score-independent risk sizing;
- deterministic SHA-256 idempotency and duplicate rejection;
- PAPER/SHADOW stable intent construction;
- OBSERVE/HALTED/LIVE no-intent behavior;
- one-terminal-reason precedence and repeated-input determinism.

### Task 3 — stable package API

RED:
- commit `89004df65273e900bd07b28314e48cb3ea710085`
- CI `32670120110`
- Python failed exactly because package-level risk exports were absent.
- Repository safety and workspace metadata remained green.

Package GREEN:
- commit `2f8540ec282f2d73377a481309a0d7a8aa171cf7`
- CI `32670155157`
- Rust tests, Python tests, workspace metadata, and repository safety all passed.

README risk semantics:
- commit `4d9ab2ec84694ae81fabf3702cc58f4367f8db91`.

## Phase-B exit criterion represented

The source build order requires Phase B to be able to reproducibly decide whether a candidate is safe, identify a setup, score it, and create or reject a trade intent without touching money.

B1/B2/B3/B4b/B5/B6/B7/B8/B9 now provide that deterministic chain in repository code:

```text
Safety -> Features -> Setup -> Regime -> Score -> Decision -> Risk -> TradeIntent or rejection
```

B9 does not claim positive expectancy or paper/live readiness. It establishes the stable risk-approved intent boundary required before Phase C can simulate realistic fills and complete positions.

## Immutable-seal procedure

This verification-record commit is the last tracked B9 mutation before final verification.

After it:

1. run a fresh full CI on the exact head;
2. audit verified B8 -> B9 file diff;
3. record final branch SHA and final CI only in draft PR #12 metadata;
4. do not mutate the verified B9 branch afterward;
5. leave PR #12 draft and unmerged.
