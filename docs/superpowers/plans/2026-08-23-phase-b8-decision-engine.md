# Phase B8 Deterministic Decision Engine — Verification Record

**Goal:** Add a pure, versioned entry Decision Engine that converts one B7 score into `REJECT`, `WATCH`, or `ENTER` using hard safety/setup precedence plus explicit setup-specific and regime-specific score thresholds.

**Spec:** `docs/superpowers/specs/2026-08-23-phase-b8-decision-engine-design.md`

**Base:** verified B7 head `26367ddf64aab9aae724afce4843219770b9feae`.

## Implemented contract

- `shreks_brain.decision` is dependency-light and pure.
- Public action vocabulary is exactly `REJECT / WATCH / ENTER / HOLD / REDUCE / EXIT`.
- B8-v1 `decide_entry()` emits only `REJECT / WATCH / ENTER`; open-position actions await real position/exit evidence.
- Fixed precedence is score-policy compatibility -> safety -> setup state -> exact setup rule -> regime -> total-score availability -> threshold.
- Safety rejection cannot be bypassed by score.
- Safety incomplete returns `WATCH` fail-closed.
- Setup `BLOCKED` returns `REJECT`; setup `WATCH` returns `WATCH`.
- Missing or disabled setup rules cannot fall through to another setup's configuration.
- `DEAD` always rejects new entries.
- HOT/NORMAL/WEAK thresholds are setup-specific and optional; `None` disables entry for that exact setup/regime and returns `WATCH`.
- Threshold equality passes.
- `ENTER` only forwards the candidate to the independent Risk Engine.
- No production default `DecisionPolicy` or thresholds exist.
- No sizing, portfolio accounting, slippage policy, idempotency key, `TradeIntent`, paper fill, signing, transaction submission, or live-money path exists in B8.

## Stable public API

`shreks_brain.decision` exports:

```text
DecisionAction
DecisionFinding
DecisionPolicy
DecisionReasonCode
SetupDecisionRule
TradeDecision
decide_entry
```

`TradeDecision` carries only point-in-time decision context and the terminal decision finding. It carries no side, requested size/notional, capital percentage, slippage, idempotency, wallet, signer, order, fill, transaction, realized PnL, or position quantity.

## TDD evidence

### Task 1 — domain and policy

- RED: `71eafac3b5a5640f07e4171926a5ef61a72e6b16`
  - CI `32668898912`
  - Python failed exactly because `shreks_brain.decision` did not exist.
  - Repository safety remained green.
- GREEN: `d724582f0b46085bff0f0d1970d6e7a6b4111f2a`
  - CI `32668933524`
  - Rust tests, Python tests, workspace metadata, and repository safety all passed.

### Task 2 — pre-entry evaluator

- RED: `8add018d76b0e1dae5d33d93cf1427b983a60110`
  - CI `32668982634`
  - Python failed exactly because `shreks_brain.decision.engine` did not exist.
  - Repository safety and workspace metadata remained green.
- GREEN: `1f7e6691830791095ea6a7fe5c58d316c19591f1`
  - CI `32669029235`
  - Rust tests, Python tests, workspace metadata, and repository safety all passed.

### Task 3 — stable package API

- RED: `22099f0655eb0e01e231bc702142ba63e49825f3`
  - CI `32669073054`
  - Python failed exactly because package-level decision exports were absent.
  - Repository safety and workspace metadata remained green.
- Package GREEN: `86a5d2752db28a410835a87fb25ebc4430bcf9c4`
  - CI `32669107406`
  - Rust tests, Python tests, workspace metadata, and repository safety all passed.

## Documentation seal

- README decision semantics were added in commit `184d18f9ea5e10ea3e8bfadbf8f5a67eed86d850`.
- This verification-record commit is the last tracked B8 mutation before immutable final verification.
- The final branch SHA and final CI run are intentionally recorded only in draft PR metadata after the fresh exact-head run, so the verified tree is not mutated afterward.

## Scope audit requirements

The final diff against verified B7 must contain only:

- this B8 design/spec and verification plan;
- `python/src/shreks_brain/decision/{models.py,engine.py,__init__.py}`;
- the three B8 decision test files;
- the focused README documentation update.

No safety, feature, setup, regime, scoring, Rust, storage, provider, wallet, risk, paper, or execution implementation file may change in B8.
