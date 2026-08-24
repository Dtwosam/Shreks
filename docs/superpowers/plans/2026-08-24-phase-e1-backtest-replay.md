# Phase E1 Historical Decision Replay Verification Record

**Base:** sealed D6 head `d7ea5fbcd2eab893b540c940eab8d24ff40a3903`.

**Design:** `docs/superpowers/specs/2026-08-24-phase-e1-backtest-replay-design.md`, committed as `73cc3f2286338978af0f114782942a61a9c7a0f0`.

**Implementation plan:** originally committed as `5992fab80f2e8ecafa585846a2f5c9d9aa80322b`; this file now replaces that plan with the verification record required by the E1 seal.

## Implemented scope

E1 adds a pure, deterministic historical entry-decision replay boundary under `shreks_brain.backtest` with schema `e1-replay-v1`.

For each historical `(candidate_mint, as_of_unix_ms)` identity, E1 consumes only caller-supplied decision-time evidence and explicit replay policies. It dispatches to the existing Fresh Launch Continuation, Graduation/Breakout, or First Pullback evaluator, then reuses the sealed B7 `score_candidate` and B8 `decide_entry` path. D5 wallet features are carried unchanged into the resulting D6-compatible research snapshot but are not injected into the current B7/B8 score or decision logic.

Future D6 outcome labels use a separate `ReplayOutcomeBundle`. The exact decision/outcome identity sets must match, and the engine retrieves the outcome bundle only after setup assessment, scoring, and entry decision are complete. This preserves the structural rule that future outcome evidence cannot influence the historical decision being replayed.

E1 performs no SQLite, provider, filesystem, PyArrow, network, or current-time reads. It computes no profitability, expectancy, drawdown, execution-cost, or model metric. It does not size risk, create a `TradeIntent`, simulate execution, train/promote a model, sign or submit transactions, or enable live-money authority.

## TDD evidence

### Model/public-contract RED

Model/public API RED commit `3e6cc65f7f4f643918c55d574aa3a0d35aebb9b0` added only:

- `python/tests/test_backtest_models.py`,
- `python/tests/test_backtest_public_api.py`.

CI `32756075534` behaved as intended: repository safety was GREEN and Python stopped during collection only because `shreks_brain.backtest` did not yet exist.

### Model/public-contract GREEN

Initial model implementation commit `f7d0b62b150fe0ff89c910fbd024ffb26404a35b` added only:

- `python/src/shreks_brain/backtest/models.py`,
- `python/src/shreks_brain/backtest/engine.py` with an intentional behavior stub,
- `python/src/shreks_brain/backtest/__init__.py`.

Two subsequent failures demonstrated invalid test construction rather than production defects:

- `faff3cec8d7da88cfb3bbf17a9876b2b354d1c68` repaired a test-only regime fixture whose window started before Unix epoch;
- `05f00263aa54d08590f6a08ab043bfac3e8b98d7` aligned a test-only invalid D5 schema assertion with the sealed D5 model, which correctly rejects such a vector before E1 can receive it.

No E1 production change was required for either repair. CI `32757274538` then passed repository safety, Python (`1677 passed`), Rust tests, and workspace metadata validation.

### Replay-behavior RED

Behavior RED commit `e601c56b691218a95faad8fc51960a6bb216b78f` added only `python/tests/test_backtest_replay.py`.

CI `32757587658` produced exactly the intended signal: `13 failed, 1678 passed`. Every failure was the intentional `NotImplementedError` from the replay stub; all predecessor and E1 model/public-contract tests passed.

### Replay-behavior GREEN

Behavior implementation commit `db978ee938b91e08c01f5eedf2d53115fd639e36` replaced only `python/src/shreks_brain/backtest/engine.py`.

CI `32757775099` is GREEN across repository safety, Python (`1691 passed`), Rust tests, and workspace metadata validation.

## Replay integrity properties proven

- replay decision inputs are immutable and contain no future outcome field;
- B2 market features, D5 wallet features, regime evidence, and setup context must reconcile to the exact historical timestamp/candidate identity;
- future-dated graduation evidence and pullback structure newer than the market observation fail closed before replay;
- decision and outcome inputs must use unique identities and their identity sets must match exactly;
- input order cannot change replay output; snapshots sort by `(as_of_unix_ms, candidate_mint)`;
- each used setup kind requires an explicitly supplied setup policy;
- Fresh Launch replay reuses `assess_fresh_launch`;
- Graduation/Breakout replay reuses `assess_graduation_breakout`;
- First Pullback replay reuses `assess_first_pullback`;
- all three setup paths then reuse the supplied B7 `ScorePolicy` and B8 `DecisionPolicy` through the existing engines;
- `REJECT`, `WATCH`, and `ENTER` candidates are all retained;
- D5 wallet features are preserved unchanged for downstream research segmentation without altering B7/B8 behavior;
- changing only a future outcome from a severe loss to a large gain cannot change the replayed score or decision;
- outcome lookup occurs only after the replayed decision exists and attaches only to the exact matching identity;
- resulting snapshots are accepted directly by the sealed D6 `build_research_dataset` contract;
- replay action counts and timestamp bounds reconcile exactly to the emitted snapshots;
- repeated identical inputs/policies produce identical replay runs;
- importing/running the replay core does not require PyArrow or SQLite and the engine has no filesystem, provider, network, or wall-clock dependency.

## Exact D6 -> E1 implementation diff

Before the documentation seal, the audited diff from sealed D6 to E1 behavior GREEN contains exactly:

```text
docs/superpowers/plans/2026-08-24-phase-e1-backtest-replay.md
docs/superpowers/specs/2026-08-24-phase-e1-backtest-replay-design.md
python/src/shreks_brain/backtest/__init__.py
python/src/shreks_brain/backtest/engine.py
python/src/shreks_brain/backtest/models.py
python/tests/test_backtest_models.py
python/tests/test_backtest_public_api.py
python/tests/test_backtest_replay.py
```

No predecessor production file, dependency configuration, Rust source, migration, or README line was changed before the seal.

## Scope boundaries

E1 establishes point-in-time historical decision replay only. It does not claim that any setup, score threshold, wallet feature, or replayed `ENTER` action is profitable. Chronological train/validation/test splitting, baselines, model training, realistic after-cost backtest metrics, statistical significance, promotion gates, and shadow-vs-production comparison remain later Phase E work.

Live execution remains disabled.

## Final seal procedure

The seal commit may touch only `README.md` and this verification record, with README additions only. After the detached seal diff is proven exact, the E1 branch is moved to that seal commit and fresh exact-head repository safety, Python, Rust, and workspace-metadata CI must all pass. The eventual final frozen E1 SHA and exact-head CI run are recorded in draft PR metadata only so no tracked-file write occurs after final verification.
