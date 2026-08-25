# Phase G4 Four-Layer Telemetry Design

## Goal

Build one deterministic, read-only local telemetry snapshot that answers two operator questions without granting monitoring any trading authority:

1. Is Shreks technically healthy enough to trust its current PAPER evidence?
2. Is the sealed PAPER/proof path showing financially useful results after realistic costs?

This phase is telemetry, not dashboard/control. G5 will render the snapshot; G6 may alert from it.

## Authority boundary

Telemetry may read existing operational SQLite, PAPER checkpoint/state, E11 paper evidence, sealed evaluation output, E12 proof assessments, promotion assessments, campaign manifest, and host/systemd status. It may write only a derived telemetry snapshot file.

Telemetry must not:
- create or mutate trade intents;
- execute, sign, or submit transactions;
- mutate registry/promotion/proof/evaluation evidence;
- alter strategy, score, decision, risk, position, exit, or economic thresholds;
- repair source state automatically;
- enable live mode;
- expose provider credentials, wallet material, environment contents, or arbitrary file contents.

**LIVE TRADING: DISABLED.**

## Primary design invariant: no second profitability engine

Money/proof metrics must come from the sealed evaluation/proof engines. Telemetry must never independently recompute net expectancy, profit factor, drawdown, or cost burden with alternate formulas.

For the current PAPER campaign, telemetry derives `EvaluatedTrade` values only through the sealed `PaperEvaluationEvidenceStore.evaluated_trades(...)` path and passes them to the sealed `evaluate_trading_performance(...)` function with the exact starting equity from the restored PAPER ledger. The returned `TradingPerformanceMetrics` is copied into telemetry unchanged.

If those authoritative inputs cannot be loaded or reconciled, the relevant source/layer is `UNAVAILABLE` rather than using a proxy.

## Snapshot contract

Schema version: `g4-telemetry-snapshot-v1`.

Top level:
- `schema_version`
- `generated_at_unix_ms`
- `mode` — exact runtime mode evidence; this slice is `PAPER` only
- `overall_status` — `HEALTHY`, `DEGRADED`, or `UNAVAILABLE`
- `system`
- `trading`
- `money`
- `proof_risk`

Every layer contains:
- `status`
- `observed_at_unix_ms` or `null`
- `source_errors` as stable non-secret reason codes, never exception text containing source payloads/secrets.

Canonical JSON uses sorted keys, compact separators, UTF-8, finite numbers only, and one trailing newline.

## Layer 1 — System

Authoritative SQLite read-only sources:
- `provider_health`: provider/status/observation time/latency/consecutive failures;
- `market_snapshots`: latest observed market time;
- `ingestion_checkpoints`: latest checkpoint update time;
- PAPER checkpoint load: latest campaign state timestamp and accounting validity.

Host/systemd values are intentionally not guessed in the pure snapshot model. A fixed-allowlist host collector can add service status/restart/uptime/CPU/RAM/disk in a later G4 task only if it can do so without shell interpolation or secret exposure. Missing host telemetry remains explicitly unavailable.

System fields for the initial slice:
- provider statuses;
- latest market observation time and age;
- latest ingestion checkpoint time;
- PAPER last-cycle/checkpoint time;
- accounting status;
- systemd/host metrics availability marker.

SQLite must be opened read-only (`mode=ro`) and must never create a missing database.

## Layer 2 — Trading

Authoritative sources:
- observer SQLite candidate/market/safety-evidence tables;
- restored PAPER state;
- E11 paper-evaluation evidence.

Initial fields:
- observed candidate count;
- latest market observation time;
- holder-distribution evidence count;
- paper quote evidence count;
- terminal PAPER ledger entry count;
- open PAPER position count;
- closed PAPER position count;
- pending-entry present;
- current candidate version/mint/paper run id from the fingerprinted campaign manifest.

The repository does not currently persist a complete historical stream of every setup score and reject/watch decision. G4 must not fabricate those counts. They remain `null`/unavailable until an authoritative durable source exists.

## Layer 3 — Money

Authoritative sources:
- restored `PaperLedger` for current balance/position-state values;
- sealed `evaluate_trading_performance` output for completed-trade profitability/proof metrics.

Ledger fields:
- starting cash;
- cash balance;
- realized PnL;
- unrealized PnL (`null` when any open position lacks a valid mark);
- accumulated explicit costs;
- open position exposure from stored open cost basis only;
- open position count.

Sealed evaluation fields are copied exactly:
- trade/win/loss/flat counts;
- gross/net PnL;
- net expectancy USD/%;
- profit factor;
- maximum drawdown USD/%;
- win rate;
- turnover;
- execution friction;
- explicit/total costs;
- cost burden %.

Daily loss is not invented unless an exact durable daily-loss source exists; initial value is `null` with availability metadata.

## Layer 4 — Proof/Risk

Authoritative sources:
- latest matching `CandidateProofAssessment` from `CandidateProofAssessmentStore.load()`;
- latest matching `PromotionAssessment` from `PromotionAssessmentStore.load()`;
- fingerprinted campaign manifest for `global_risk_halt`, candidate identity, run identity;
- restored PAPER accounting validation;
- explicit runtime mode.

Fields:
- E12 proof decision and every gate code/status/observed/threshold value when present;
- promotion decision and gate summary when present;
- PAPER trade count and distinct mint count from the proof assessment when those gates provide observed values;
- proof net expectancy/profit factor/drawdown/cost-burden observations from the persisted E12 gates, not recomputed;
- global risk halt;
- accounting integrity;
- runtime mode = PAPER;
- live state = `DISABLED` for this production PAPER runtime;
- kill-switch state only when backed by an explicit source; otherwise `null`/unavailable.

No proof/promotion store append/mutation is permitted.

## Failure semantics

A telemetry failure must never weaken trading safety.

- Missing optional proof/promotion files: source status `UNAVAILABLE`, snapshot still emitted with null fields.
- Corrupt proof/promotion/evidence/checkpoint/manifest or required operational schema: affected layer `UNAVAILABLE`; no fabricated values.
- Required PAPER recovery/accounting failure: overall status `UNAVAILABLE`.
- Stale provider/market evidence: represented by timestamps/ages and degraded source status; no freshness threshold is invented in G4 unless supplied explicitly by an existing policy.
- Secret/environment values are never serialized.

## Output

The first production-shaped artifact is local and private:
`/var/lib/shreks/telemetry/current.json`

Writing is atomic: create a sibling temporary file, flush/fsync, `os.replace`, and fsync parent directory where supported. Permissions are restrictive. Source files are never modified.

## Deliberately deferred

- private authenticated web dashboard (G5);
- Telegram/mobile alerts (G6);
- emergency controls (G7);
- backup/restore (G8);
- external Prometheus/Grafana/metrics SaaS;
- any monitoring-triggered trade/control action.

## Exit criterion

G4 is complete when tests prove one deterministic four-layer snapshot can be assembled from sealed read-only sources, emits authoritative financial/proof values without metric drift, degrades explicitly on missing/corrupt sources, writes only its derived output atomically, and contains no control/live/signing authority.