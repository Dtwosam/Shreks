# FL9 Learned Continuous Action Policy — Implementation Plan

**Goal:** Add a pure deterministic Rust action policy that consumes point-in-time learned forecasts plus explicit current execution/risk evidence and selects `BUY`, `SKIP`, `HOLD`, `REDUCE`, or `SELL` with dynamic horizon/exposure and auditable cost/risk-adjusted values.

**Base:** SEALED FL8.6 merged-main `ffcc87a38ae9484e4cc050a105ab4068801f0c34`, merged-main four-gate GREEN CI `33808678017`.

**Spec:** `docs/superpowers/specs/2026-09-03-fl9-continuous-action-policy-design.md`

## Global constraints

- Reuse existing `FastLaneAction`.
- Runtime inputs are point-in-time forecasts plus caller-supplied current constraints only.
- FL4 future labels / FL5 counterfactual outcomes are forbidden runtime inputs.
- No provider/network/storage/filesystem/wall-clock/randomness/environment/training/PAPER execution/`TradeIntent`/signer/submission/promotion/LIVE authority.
- No new Rust dependency.
- Hard execution/risk constraints dominate learned action value.
- Missing forecast/execution evidence never becomes zero.
- Every assessment carries exact champion and policy provenance.
- New-entry and already-open economics must remain separate: BUY uses `endpoint_cost_adjusted_return_bps`; open continuation uses raw `endpoint_return_bps` minus current future-exit cost, because the historical entry leg is sunk.
- The code merge does not itself prove FL9 economic superiority.

---

### Task 1: RED public/input contracts

**Create:** `crates/shreks-core/tests/fast_continuous_action_policy.rs`

Future crate-root API:

```text
CONTINUOUS_ACTION_POLICY_VERSION
FastActionForecastSet
FastContinuousActionPolicy
FastReduceExecutionCost
FastActionConstraints
FastActionPositionState
FastHorizonActionEvidence
FastActionCandidateAssessment
FastContinuousActionAssessment
FastContinuousActionReason
FastContinuousActionError
assess_continuous_action
```

Tests import these names before implementation exists, intentionally producing Rust unresolved-import RED.

Lock validation failures for:

- invalid/non-lowercase SHA champion fingerprint;
- empty champion/model version;
- duplicate `(target,horizon)` forecast;
- non-finite forecast;
- binary probability outside `[0,1]`;
- policy version mismatch;
- zero/unsorted/duplicate horizons;
- invalid/unsorted/duplicate entry exposure candidates;
- invalid reduction target candidates;
- non-finite/negative weights or thresholds;
- missing-forecast action other than REDUCE/SELL;
- missing reduction targets when fallback action is REDUCE;
- invalid max/current exposure;
- invalid/unsorted/duplicate `FastReduceExecutionCost` targets;
- negative/non-finite future exit, reduction, or sell cost.

### Task 2: RED complete-horizon forecast contract

Each complete configured horizon requires exact predictions for:

- `endpoint_cost_adjusted_return_bps`;
- `endpoint_return_bps`;
- `mae_bps`;
- `reversal_occurred`;
- `route_unavailability_observed`.

Tests prove:

- exact horizon grouping/no nearest fallback;
- partial horizons are excluded, not zero-filled;
- duplicate target/horizon fails;
- complete horizon evidence is sorted canonically.

### Task 3: RED flat BUY/SKIP behavior

Lock:

```text
adverse_bps = max(0, -mae_bps)
base_risk_bps = adverse_weight*adverse_bps
              + reversal_penalty_bps*reversal_probability
              + route_penalty_bps*route_unavailability_probability

disagreement_bps = max(raw endpoint_return_bps) - min(raw endpoint_return_bps)
risk_bps = base_risk_bps + disagreement_weight*disagreement_bps
buy_value_bps(h,e) = e*endpoint_cost_adjusted_return_bps(h) - e^2*risk_bps(h)
skip_value_bps = 0
```

Behavior tests:

- strong all-in reward/low risk => BUY with high exposure;
- downside/probability/disagreement risk can make smaller BUY exposure optimal;
- economics veto => SKIP regardless of reward;
- max exposure zero => SKIP;
- buy below threshold => SKIP;
- no complete configured horizon => SKIP with `ForecastEvidenceIncomplete`;
- nearby unconfigured horizons do not qualify.

### Task 4: RED open HOLD/REDUCE/SELL economics

For current exposure `c` and configured horizon `h`:

```text
open_reward_bps(h) = endpoint_return_bps(h) - expected_future_exit_cost_bps
retained_value_bps(h,e) = e*open_reward_bps(h) - e^2*risk_bps(h)
hold_value_bps(h) = retained_value_bps(h,c)
reduce_value_bps(h,r) = retained_value_bps(h,r)
                        - (c-r)*reduce_execution_cost_bps(r)
sell_value_bps = -c*sell_now_cost_bps
```

Tests prove:

- strong continuation => HOLD;
- high downside/risk can make exact executable REDUCE target optimal;
- weak/negative continuation => SELL when executable;
- reduction costs are exact per target exposure and absence means not executable;
- sell cost is explicitly charged;
- sunk historical entry cost does not enter open comparison;
- current exposure above hard max cannot HOLD;
- force-sell overrides learned value;
- force-sell with unavailable sell => fail-closed error;
- non-executable SELL is excluded unless hard safety requires it.

### Task 5: RED dynamic horizon and missing-evidence behavior

- every call compares all complete configured horizons;
- changing forecast values can change selected horizon/action without mutating policy;
- no fixed hold horizon persists between calls;
- missing complete forecasts while flat => SKIP;
- missing complete forecasts while open + REDUCE fallback => choose largest configured/executable target below current and within hard max;
- missing complete forecasts while open + SELL fallback => require executable sell;
- unavailable configured safe action => fail-closed error.

### Task 6: RED deterministic audit surface

Lock public output fields so tests can reconcile:

`FastHorizonActionEvidence`:
- horizon;
- five model versions;
- entry cost-adjusted reward;
- raw endpoint return;
- MAE/adverse magnitude;
- reversal/route probabilities;
- disagreement/risk.

`FastActionCandidateAssessment`:
- action;
- optional horizon;
- target exposure;
- reward;
- risk;
- immediate execution-cost penalty;
- comparison value;
- eligibility.

`FastContinuousActionAssessment`:
- policy version;
- champion version/fingerprint;
- position state;
- selected action/reason/horizon;
- current/target exposure;
- selected reward/risk/execution-cost/value;
- canonical horizon evidence;
- canonical candidates.

Tie-break: higher value -> lower exposure -> shorter horizon -> lexical action. Repeated identical calls must compare exactly equal.

### Task 7: Minimal production implementation

**Create/modify:**
- `crates/shreks-core/src/fast_lane/action_policy.rs`
- `crates/shreks-core/src/fast_lane/mod.rs`
- `crates/shreks-core/src/lib.rs`

Implement exact validation, complete-horizon grouping, risk/disagreement math, flat/open cost formulas, candidate generation, eligibility, fail-closed fallback, deterministic sorting/selection, and provenance output.

### Task 8: Authority firewall

**Create after production module exists:** `python/tests/test_fast_continuous_action_policy_authority.py`

Reject source tokens/imports for providers/network/storage/filesystem/time/random/env, FL4/FL5 future evidence, training, PAPER executor/ledger writes, `TradeIntent`, signer/submission, promotion/registry, runtime-mode/LIVE control. Assert no new `shreks-core` dependency beyond already-sealed `serde`, `serde_json`, `sha2`.

### Task 9: TDD/CI/history seal

- Open draft PR only after RED test commit.
- Capture intentional Rust unresolved-import RED; safety must remain GREEN.
- Implement only after RED evidence.
- Require candidate repository safety + Python + Rust + ARM64 GREEN.
- Audit exact scope vs SEALED FL8.6.
- Collapse to exact four commits `design -> plan -> RED -> implementation`, preserving the verified final tree.
- Fresh clean-head four-gate GREEN.
- Update PR, mark ready, guarded merge with exact head SHA.
- Fresh merged-main four-gate GREEN.

### Task 10: Economic exit proof

After merge, inspect actual PAPER/shadow/evaluation evidence for a leakage-safe comparison of champion+FL9 policy against the best deterministic baseline under realistic costs/risk.

If adequate independent evidence exists, build/run the evaluation. If it does not, record **FL9 policy implementation SEALED; economic exit pending**, keep FL10/LIVE progression blocked by the unresolved proof gate, and do not infer profitability from fixtures.

LIVE remains disabled.