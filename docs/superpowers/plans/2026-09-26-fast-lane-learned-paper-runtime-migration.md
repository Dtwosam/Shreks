# Fast Lane Learned PAPER Runtime Migration — Implementation Plan

**Date:** 2026-09-26  
**Required base main SHA:** `680fe3ff4208af9d7d5241f2f42d20714a814867`  
**Production PAPER release at planning time:** `816e7c6591d216369b60f893cc5dfe5785e88652`

## Goal

Replace the active score-gated PAPER decision path with the learned Fast Lane
forecast/action path while preserving the existing authoritative PAPER ledger,
execution accounting, risk guardrails, release discipline, restart/recovery
behavior, and LIVE-disable boundary.

The target production loop is:

```text
market event/state
-> exact Fast Lane feature state
-> approved forecast champion
-> execution economics
-> BUY/SKIP/HOLD/REDUCE/SELL comparison
-> score-free Fast Lane risk
-> PAPER execution
-> authoritative PaperLedger update
-> evaluation/counterfactual evidence
-> later challenger training
```

This migration must not create a new score, score authority, score threshold,
or score-to-trade compatibility layer.

---

## Verified current-state facts

### Active production PAPER authority is still legacy

The deployed service is:

```text
shreks-paper-campaign.service
-> python -m shreks_brain.observer_campaign.runtime
-> observer campaign coordinator / paper loop
-> score_candidate(...)
-> decide_entry(...)
-> legacy entry-risk path
-> PAPER execution/accounting
```

The legacy decision engine still gates entry on a deterministic total score and
configured score threshold. This path is now architecture debt and may not be
extended or retuned.

### The correct Fast Lane decision path already exists

The repository already contains the replacement foundations:

- Rust `shreks-fast-campaign-decision`;
- `FastCampaignContinuousActionPolicy`;
- direct `BUY/SKIP/HOLD/REDUCE/SELL` action comparison;
- immutable Fast Lane champion artifacts;
- `run_fast_learned_chronological_campaign(...)`;
- `run_fast_campaign_paper_candidate(...)`;
- `execute_fast_paper_buy(...)`;
- score-free `assess_fast_entry_risk(...)`;
- the existing authoritative `PaperLedger` type and PAPER execution/accounting
  primitives.

The Fast Lane PAPER executor therefore does not require migration to a new
accounting model.

### Self-training is not yet a continuously operating production loop

Training and chronological validation code exist, but there is no production
service/timer that repeatedly:

```text
fresh evidence -> train challenger -> replay -> PAPER/shadow -> promotion evidence
```

That automation is a later migration stage after the learned PAPER runtime is
stable.

---

## Non-negotiable migration invariants

1. **No scoring control path.**
   New production runtime code must not import or invoke:
   - `shreks_brain.scoring`;
   - `score_candidate`;
   - legacy `decide_entry`;
   - legacy total-score thresholds.

2. **Preserve authoritative accounting.**
   `PaperLedger`, fill accounting, processed-intent idempotency, PnL, fees,
   slippage evidence, and reconciliation remain authoritative.

3. **Use Fast Lane risk.**
   Fast Lane BUYs route through `assess_fast_entry_risk(...)`, not through a
   synthetic legacy `TradeDecision`.

4. **No ledger reinterpretation.**
   Cutover occurs only after the legacy authoritative ledger is reconciled and
   has no open position, pending entry, deferred execution, or ambiguous active
   intent.

5. **No silent champion replacement.**
   Runtime uses one exact approved champion artifact and one exact action-policy
   version. Challenger training cannot silently modify the active champion.

6. **No LIVE authority.**
   Every migration PR remains PAPER/shadow only. LIVE stays disabled.

7. **Economic floors are not token scores.**
   A direct action-value floor such as `minimum_buy_value_bps` is permitted
   only when it is explicitly derived from executable expected value/risk/cost.
   It must not become an aggregate token-quality score or approval proxy.

8. **Legacy scoring becomes historical compatibility only.**
   Existing historical codecs/tests may remain until a separately reviewed
   compatibility cleanup removes them. No new runtime may depend on them.

---

# Migration sequence

## PR 1 — Score-free runtime contract and authority firewall

### Purpose

Create the production-facing learned PAPER runtime contract without changing
the active service.

### Add

Suggested package:

```text
python/src/shreks_brain/fast_paper_runtime/
```

Initial files:

- `models.py` — exact runtime manifest/config/state contracts;
- `codec.py` — canonical deterministic manifest/checkpoint codec;
- `__init__.py` — intentionally small public API;
- focused tests under `python/tests/`.

The runtime manifest must bind:

- exact release source SHA;
- exact champion path/fingerprint/version;
- exact Rust decision binary path/SHA;
- exact Fast Lane continuous-action policy;
- exact Fast Lane state/feature schema;
- exact risk/fill/position-action policy versions;
- observer database path;
- authoritative PAPER evidence path;
- durable runtime checkpoint path;
- quote asset/route evidence identity;
- PAPER mode only.

### RED contracts

Tests must prove:

- source contains no scoring or legacy decision imports;
- unknown manifest fields fail closed;
- champion/binary fingerprint mismatch fails closed;
- LIVE mode is unrepresentable;
- manifest cannot contain score thresholds, `ScorePolicy`, or
  `DecisionPolicy`;
- state/checkpoint writes are canonical, write-once/atomic where applicable,
  and deterministic.

### Boundary

No service, ledger, observer DB, or runtime behavior changes in PR 1.

---

## PR 2 — Incremental canonical Fast Lane decision feed

### Purpose

Feed fresh production observations into the learned action engine without
duplicating feature semantics or using future information.

### Required behavior

Add a bounded read-only decision-feed adapter that reuses the exact canonical
Fast Lane feature construction already used by the sealed training/export path.

The adapter must:

- read only the authoritative observer SQLite/WAL source;
- resume from an exact persisted decision-sequence/event cursor;
- emit only unseen point-in-time-safe `FastTrainingFeatureRecord` rows;
- preserve strict source/event ordering;
- reject duplicate/conflicting identities;
- never read future-path labels or counterfactual outcomes for runtime action
  selection;
- bind every emitted row to the exact feature schema/version;
- support restart without re-executing an economic action.

If the current exporter cannot safely provide bounded incremental rows, factor
the shared feature construction into a reusable library boundary rather than
reimplementing it.

### Required tests

- same source DB + same cursor => same emitted records;
- exact replay is idempotent;
- cursor regression fails closed;
- future labels/counterfactual modules are not imported;
- runtime records match canonical exporter records for the same decisions;
- database mutation during a bounded snapshot is detected or safely retried.

### Boundary

Still shadow/read-only. No authoritative PAPER ledger mutation.

---

## PR 3 — Learned shadow runtime

### Purpose

Run the actual learned champion continuously against production observation and
execution evidence before replacing the legacy PAPER service.

### Runtime path

For each new material decision row:

1. load/reuse exact approved champion;
2. build `FastCampaignDecisionRequest`;
3. construct current execution/action constraints from point-in-time quote and
   route evidence;
4. call the release-local `shreks-fast-campaign-decision` binary;
5. validate champion/version/result identity;
6. record:
   - action;
   - selected horizon;
   - selected expected value;
   - forecast/risk evidence;
   - decision latency;
   - quote/executability state;
7. optionally run realistic PAPER execution in an **isolated shadow ledger**
   that cannot mutate the authoritative PAPER ledger.

### Service topology

Add a separate shadow unit, for example:

```text
shreks-fast-paper-shadow.service
```

It must not be a replacement for `shreks-paper-campaign.service` yet.

### Proof

Compare learned shadow evidence against the legacy deterministic PAPER baseline
on the same chronological market windows.

Required metrics include:

- net expectancy after costs;
- profit factor;
- maximum drawdown/tail loss;
- fee/slippage burden;
- expected-vs-realized EV;
- entry-price efficiency;
- exit-timing efficiency;
- missed-opportunity cost;
- action distribution;
- event-to-decision latency.

No score metric may determine the winner or promotion.

---

## PR 4 — Durable Fast Lane PAPER runner on the existing PaperLedger

### Purpose

Make the learned path restart-safe and capable of authoritative PAPER execution
without changing the accounting model.

### Reuse directly

- `PaperLedger`;
- `execute_fast_paper_buy(...)`;
- `apply_fast_paper_position_action(...)`;
- `assess_fast_entry_risk(...)`;
- PAPER fill/execution primitives;
- existing accounting/evaluation records where schemas remain compatible.

### New durable state

Add a Fast Lane PAPER runtime checkpoint that binds:

- exact `PaperLedger` state/fingerprint;
- Fast PAPER event-loop cursor/state;
- per-market open-position/exposure mapping;
- position-action state;
- last processed decision identity;
- champion fingerprint;
- action-policy version;
- release SHA;
- risk/fill policy versions.

The checkpoint must not contain or synthesize:

- total score;
- score policy version as active policy;
- score threshold;
- setup-ready approval as a trade gate.

Historical `TradeIntent.score_policy_version` compatibility fields may carry
the already existing Fast Lane sentinel only until the legacy schema is
separately migrated.

### Restart proof

Tests must prove:

- crash/restart yields the same next ledger/action as uninterrupted replay;
- no duplicate BUY/REDUCE/SELL after restart;
- active intent/idempotency keys reconcile;
- pending/deferred execution is not replayed twice;
- accounting validation remains exact.

---

## PR 5 — Controlled production PAPER cutover

### Pre-cutover conditions

Do not switch authority until all are true:

```text
legacy_ledger_accounting=VALID
legacy_open_positions=0
legacy_pending_entries=0
legacy_deferred_executions=0
legacy_active_intents=0
learned_shadow_champion=EXACT_AND_PROVEN
fast_runtime_restart_equivalence=PASS
fast_runtime_paper_accounting=PASS
fast_runtime_score_imports=NONE
live_authority=DISABLED
```

If the legacy ledger is not flat, remain in shadow mode. Do not force-close a
position merely to enable cutover.

### Cutover behavior

1. stop the legacy PAPER campaign service;
2. capture and verify the final authoritative legacy checkpoint/ledger;
3. initialize the Fast Lane checkpoint from the **unchanged authoritative
   PaperLedger** plus fresh Fast Lane runtime state;
4. keep the same durable accounting/evidence roots;
5. switch `shreks-paper-campaign.service` (or atomically switch target
   membership) to the Fast Lane runtime;
6. start with PAPER only;
7. run protected verification.

### Protected production verification

Must prove:

- active service process belongs to exact immutable release;
- runtime module/binary is the Fast Lane path;
- exact champion fingerprint/version;
- exact action-policy version;
- `SCORING_CONTROL_PATH=FORBIDDEN`;
- no legacy scoring/decision module loaded by the PAPER runtime;
- authoritative ledger path is unchanged;
- opening cash / realized PnL / processed intents reconcile across cutover;
- action telemetry emits `BUY/SKIP/HOLD/REDUCE/SELL`;
- restart counter and checkpoint recovery are healthy;
- LIVE remains disabled.

### Rollback rule

After cutover, **do not restore score-gated PAPER trading authority**.

Rollback choices are:

1. previous known-good Fast Lane PAPER release; or
2. halt/observe-only while preserving the authoritative ledger.

The legacy score runtime may remain available only for historical replay and
comparison.

---

## PR 6 — Remove score authority from active runtime/config surfaces

Only after the Fast Lane PAPER cutover is physically proven:

- remove `ScorePolicy` and legacy `DecisionPolicy` from active PAPER runtime
  manifests;
- remove score ranking from active candidate selection;
- remove score/pass telemetry from active operator views;
- change stale active `scoring_authority=NOT_GRANTED` runtime fields to the
  canonical no-scoring control representation in new schema versions;
- preserve old decoders only for immutable historical artifacts;
- prevent legacy `paper_loop` / `observer_campaign` from being selected as a
  production trading authority.

Do not mass-rewrite historical seals or immutable evidence documents.

---

# Continuous self-improvement sequence

Begin only after the learned PAPER runtime is stable and physically accepted.

## PR 7 — Automatic challenger production

Add a bounded trainer service/timer or equivalent scheduled worker that:

1. snapshots new point-in-time-safe observation/PAPER evidence;
2. materializes fresh labels/counterfactual outcomes only for training;
3. builds a new immutable training bundle;
4. trains challenger forecast members;
5. performs chronological validation;
6. packages a challenger artifact;
7. records exact provenance/fingerprints.

Training may happen automatically. It must not mutate the active champion.

## PR 8 — Automatic challenger shadow evaluation

Every newly produced challenger must automatically enter read-only/PAPER-shadow
evaluation against the active champion.

Compare:

- net expectancy;
- drawdown/tail loss;
- cost burden;
- latency;
- calibration;
- capacity;
- missed-opportunity cost;
- performance stability across regime/strategy/horizon.

A classification metric or statistical score may be recorded as diagnostic
evidence but cannot independently authorize promotion.

## PR 9 — Proof-gated promotion boundary

Use the existing champion/challenger registry and promotion evidence model, but
adapt any remaining legacy assumptions to the Fast Lane runtime.

Initial version remains:

```text
challenger_training=AUTOMATIC
challenger_shadow_evaluation=AUTOMATIC
production_champion_replacement=EXPLICIT_PROOF_GATE
```

A later separately reviewed FL11 slice may authorize fully automatic promotion
only if the promotion action is itself exact, versioned, auditable, reversible,
and driven by the complete economic/risk proof—not by a score threshold.

LIVE remains disabled until FL12.

---

# What must remain untouched during the first migration slices

Until a specific slice says otherwise, do not change:

- observer chain ingestion semantics;
- authoritative SQLite/WAL evidence history;
- `PaperLedger` accounting rules;
- PAPER fill model;
- backup/recovery;
- operator kill switch / entry halt;
- capital/risk limits;
- release/deploy manager;
- signing/submission;
- LIVE configuration.

---

# Required regression guard

Before the production cutover PR can merge, repository tests must prove the new
Fast Lane PAPER runtime production source tree contains no imports/references to:

```text
shreks_brain.scoring
score_candidate
shreks_brain.decision.decide_entry
TOTAL_SCORE_BELOW_THRESHOLD
required_score_threshold
```

Historical baseline/replay packages may still contain those names.

The test must target only the active Fast Lane production runtime package and
service entrypoint so immutable historical compatibility code remains readable.

---

# Migration completion statement

The score-gated PAPER architecture is retired only when protected physical
verification proves:

```text
production_paper_runtime=FAST_LANE_LEARNED
approved_champion=EXACT_VERSIONED_ARTIFACT
decision_actions=BUY_SKIP_HOLD_REDUCE_SELL
score_control_imports=NONE
entry_risk=FAST_LANE_SCORE_FREE
authoritative_paper_ledger=PRESERVED_AND_RECONCILED
restart_equivalence=PASS
paper_accounting=PASS
continuous_challenger_training=AVAILABLE
silent_champion_self_promotion=FORBIDDEN
SCORING_CONTROL_PATH=FORBIDDEN
LIVE=DISABLED
```

At that point the old score pipeline is historical regression machinery only,
not a trading authority.
