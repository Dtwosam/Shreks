# Phase G4 Four-Layer Telemetry Implementation Plan

Base: sealed G3 `9ad51e8bd0af1630694468ba0423ca222ff8e4ea`.
Branch: `feat/phase-g4-telemetry-snapshot`.

**LIVE TRADING: DISABLED.**

## Task 1 — schema, canonical encoding, authority firewall

RED first in `python/tests/test_g4_telemetry_models.py`.

Require:
- exact `g4-telemetry-snapshot-v1` schema;
- exactly four named layers;
- HEALTHY/DEGRADED/UNAVAILABLE source/layer status;
- canonical deterministic JSON with finite values and trailing newline;
- strict dataclass/type validation;
- no secret/control/live-signing fields or mutation API.

Implement `python/src/shreks_brain/telemetry/{__init__,models,codec}.py`.

GREEN gate: full Python + Rust/workspace + repository safety.

## Task 2 — read-only operational/PAPER source collector

RED first in `python/tests/test_g4_telemetry_sources.py`.

Implement a collector that:
- opens observer SQLite read-only and validates required tables/columns;
- reads provider health, candidate/market/safety evidence counts, latest market/checkpoint timestamps;
- decodes the fingerprinted campaign manifest;
- restores the campaign through the existing read-only bootstrap/load-state path;
- validates accounting;
- loads E11 evidence through the sealed store;
- never writes source DB/files and never creates missing inputs;
- returns stable source-error codes on unavailable optional sources.

GREEN gate required.

## Task 3 — authoritative Money and Proof/Risk composition

RED first in `python/tests/test_g4_telemetry_financial.py`.

Implement composition that:
- gets evaluated trades only from `PaperEvaluationEvidenceStore.evaluated_trades`;
- invokes sealed `evaluate_trading_performance` rather than reimplementing metrics;
- copies `TradingPerformanceMetrics` exactly;
- reads latest matching E12 proof assessment and promotion assessment with `.load()` only;
- copies persisted gate values/statuses exactly;
- reports manifest global-risk-halt and PAPER/live-disabled state;
- leaves daily-loss/kill-switch values unavailable when no exact source exists.

Include monkeypatch tests proving telemetry calls the sealed evaluator and does not contain alternate expectancy/PF/drawdown formulas.

GREEN gate required.

## Task 4 — deterministic assembler and atomic local snapshot writer

RED first in `python/tests/test_g4_telemetry_snapshot.py`.

Implement:
- complete four-layer snapshot assembly;
- overall status precedence;
- deterministic generated timestamp injection;
- atomic write to caller-provided path;
- restrictive file permissions;
- no source mutation;
- fail-closed handling for corrupt required PAPER state;
- optional missing proof/promotion represented explicitly, not fatal.

Add a CLI/runtime entry point only if it takes explicit paths and output destination and contains no control authority.

GREEN gate required.

## Task 5 — production systemd telemetry service/runbook

RED first against systemd contract only after Task 4 is independently GREEN.

If the snapshot CLI is stable, add an unprivileged telemetry service/timer or long-running read-only daemon writing `/var/lib/shreks/telemetry/current.json`. It must:
- be part of `shreks.target` only if failure semantics will not accidentally stop the core PAPER runtime;
- read protected sources without changing them;
- write only telemetry output;
- restart safely;
- never contain provider/wallet secrets or live authority.

If coupling telemetry failure to the required target would reduce trading-runtime availability, keep telemetry as a separately supervised non-required service and document that choice.

GREEN gate required.

## Final audit/seal

1. Freeze final G4 behavior SHA after all task GREEN gates.
2. Compare sealed G3 -> frozen G4 behavior file-by-file.
3. Confirm no strategy/scoring/risk thresholds, provider behavior, storage migrations, execution, ledger/accounting core, checkpoint core, promotion mutation, transaction signing/submission, wallet, or live-enable authority changed.
4. Confirm all telemetry source accesses are read-only and the only write target is derived telemetry output.
5. Replace this plan with a verification record in one docs-only commit.
6. Prove behavior -> seal is exactly 1 commit / 1 file.
7. Run exact-seal CI and require unchanged full test cardinality, Rust/workspace GREEN, repository safety GREEN.
8. Update G4 PR; keep draft and unmerged.

Real-host telemetry values cannot be claimed until the VPS is actually connected/deployed.