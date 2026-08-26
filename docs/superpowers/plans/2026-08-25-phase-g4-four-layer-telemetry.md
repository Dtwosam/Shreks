# Phase G4 Four-Layer Telemetry Verification Record

Base: sealed G3 `9ad51e8bd0af1630694468ba0423ca222ff8e4ea`.
Branch: `feat/phase-g4-telemetry-snapshot`.
Frozen behavior: `717c0b474a9f9742b770ae2246f258434a2c81f1`.
Frozen-behavior CI: `32918559990`.

**LIVE TRADING: DISABLED.**

## Result

G4 adds one deterministic, local, private, read-only telemetry artifact with exactly four canonical monitoring layers:

1. System
2. Trading
3. Money
4. Proof/Risk

The implementation is reporting-only. It does not create a second profitability engine, does not mutate proof/promotion state, does not create trading intents, and has no signing, submission, wallet, live-enable, alerting, dashboard, or auto-remediation authority.

Frozen-behavior verification on `717c0b474a9f9742b770ae2246f258434a2c81f1`:

- Python: **2336 passed in 10.68s**
- Rust/workspace: GREEN
- Repository safety: GREEN

## Task 1 — schema, canonical encoding, authority firewall

RED:
- SHA `85b6a4624b0ca02b12f8e926237b7fd74bc06c6b`
- CI `32908594722`
- Python failed because the telemetry package did not yet exist; unchanged Rust/workspace and repository-safety lanes remained clean.

GREEN:
- SHA `15f043a57bdb12c45edddc87cfd2988b533d172b`
- CI `32908753871`
- Python, Rust/workspace, and repository safety GREEN.

Implemented:
- exact schema version `g4-telemetry-snapshot-v1`;
- exact four-layer dataclass contract;
- `HEALTHY` / `DEGRADED` / `UNAVAILABLE` statuses;
- strict finite-number and reconciliation validation;
- deterministic canonical JSON with trailing newline;
- deliberately narrow package `__all__` with no control/secret/live authority.

## Task 2 — read-only operational/PAPER source collector

RED:
- SHA `e9d5f0f3d68e2be4d657aa08740a9d1688db0386`
- CI `32908903870`
- Python failed on the intentionally missing source collector; Rust/workspace and repository safety remained GREEN.

Fixture corrections were made after RED exposed that a reused campaign-only SQLite test fixture lacked the two operational tables G4 deliberately requires and that one nested temporary directory was not created. Production schema requirements were not weakened.

GREEN:
- SHA `fcaf6758842c4d0a09df3c3f60eb9326ac5e3132`
- CI `32914365416`
- Python, Rust/workspace, and repository safety GREEN.

Read-only proof:
- observer SQLite is opened through a URI with `mode=ro`;
- `PRAGMA query_only=ON` is enabled;
- a missing database is rejected rather than created;
- required table/column shapes are validated before reporting;
- PAPER campaign state is restored through the existing bootstrap/load-state path;
- accounting is validated before reporting;
- E11 evaluated trades come from the sealed runner/evidence path;
- proof and promotion assessment stores use `.load()` only;
- source bytes/mtimes are covered by tests and remain unchanged.

## Task 3 — authoritative Money and Proof/Risk composition

RED:
- SHA `699c0b96bdc305dd33bc2924b46a37b57ec0f909`
- CI `32914747036`
- Python failed on the missing financial composition module; unchanged Rust/workspace and repository safety remained clean.

GREEN:
- SHA `b0d73ca8e63e1ac02603ee92b538ac0a595041a9`
- CI `32914976605`
- Python **2327 passed**; Rust/workspace and repository safety GREEN.

Financial authority proof:
- telemetry invokes sealed `evaluate_trading_performance` rather than duplicating expectancy, profit-factor, drawdown, turnover, friction, or cost formulas;
- evaluator starting equity must exactly match restored PAPER starting cash;
- Money metrics are copied from sealed evaluator output;
- Proof/Risk values come from the latest matching persisted E12 proof and promotion assessments;
- candidate fingerprint, paper run, and point-in-time matching are enforced;
- manifest `global_risk_halt` and PAPER/live-disabled state are reported directly;
- unsupported daily-loss and kill-switch values remain `None` rather than using invented proxies.

A later integration correction tightened the designed failure semantics: missing/corrupt proof or promotion evidence makes Proof/Risk `UNAVAILABLE`; accounting-only incompleteness remains `DEGRADED`.

## Task 4 — deterministic snapshot assembler and atomic writer

RED:
- SHA `33a87e34db85b38185d98e0fc4de69de161c74a5`
- CI `32915134366`
- Python failed on the intentionally missing snapshot module; Rust/workspace and repository safety remained GREEN.

Initial GREEN candidate:
- SHA `aaaba3d2ab1c4bbf42e1665935bf06070c22e13a`
- CI `32915259393`

Integration tests then exposed two real contract issues before freeze:
- proof/promotion absence had to be `UNAVAILABLE`, not `DEGRADED`;
- canonical telemetry encoding is a UTF-8 string, so the atomic binary writer must explicitly encode it before writing.

Final integrated Task 4 GREEN:
- SHA `b1f4ff2ab03f9d28926bd571d8224efd52e312bf`
- CI `32915610414`
- Python **2332 passed**; Rust/workspace and repository safety GREEN.

Writer proof:
- caller-provided timestamp is deterministic;
- overall status precedence is deterministic;
- only the derived telemetry destination is written;
- sibling temporary file is flushed/fsynced;
- exactly one `os.replace` performs activation;
- final snapshot mode is `0600`;
- parent-directory fsync is attempted where supported;
- operational database, campaign manifest, and E11 evidence remain unchanged.

Production-shaped destination is `/var/lib/shreks/telemetry/current.json`.

## Task 5 — isolated production telemetry runtime and systemd supervision

Combined RED:
- runtime RED originated at SHA `a79546a3840341da94154b247e4c2ccd5aeebb66`;
- combined runtime/systemd RED SHA `4fa9a1f88036ee30160aff434a9e0b9b27b71346`;
- CI `32917638619`;
- Python failed only because `shreks_brain.telemetry.runtime` did not exist;
- Rust failed only because the telemetry service/timer did not exist;
- repository safety remained GREEN.

Implemented runtime:
- explicit operational telemetry configuration only;
- exact allowlist of `SHREKS_TELEMETRY_*` reporting keys;
- sealed G1C PAPER runtime configuration reused for source paths;
- explicit evaluator reporting policy version and calibration bucket count;
- `--preflight` performs read-only source/recovery validation and writes no snapshot;
- no-argument execution performs one snapshot generation and atomic write;
- unknown CLI arguments fail with exit code 2;
- runtime failures fail nonzero;
- live state remains `DISABLED`.

Implemented systemd isolation:
- `shreks-telemetry.service` is unprivileged `Type=oneshot`;
- it preflights before snapshot generation;
- `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, `NoNewPrivileges=true`;
- its only production writable path is `/var/lib/shreks/telemetry`;
- `shreks-telemetry.timer` runs the service once per minute and is persistent across reboot;
- telemetry is deliberately **not** `PartOf=` or `WantedBy=` `shreks.target`;
- `shreks.target` remains unchanged and has no telemetry dependency;
- telemetry failure therefore cannot stop the observer, paper-evidence, or PAPER campaign runtime.

Final Task 5 / frozen-behavior GREEN:
- SHA `717c0b474a9f9742b770ae2246f258434a2c81f1`
- CI `32918559990`
- Python **2336 passed in 10.68s**
- Rust/workspace GREEN
- Repository safety GREEN.

### G2 rollback compatibility decision

During Task 5, an experimental test/implementation path briefly explored adding telemetry units to the sealed G2 v1 release-bundle allowlist. Audit identified that changing the old manifest contract would make pre-G4 verified releases unsafe or impossible to validate as rollback points under the new verifier.

That experiment was fully reverted before the behavior freeze. Final G3→G4 comparison contains **no `deploy/release/*` change and no G2 test-fixture change**.

The final G4 operational contract is therefore:
- G2 verified core release/rollback semantics stay sealed and backward compatible;
- G4 telemetry service/timer are separate first-host bootstrap artifacts installed from the exact sealed G4 source;
- telemetry remains outside core deployment health gating;
- rolling back to a pre-G4 code release requires disabling the telemetry timer because that older Python release does not contain the telemetry module;
- this monitoring transition never substitutes for or weakens the G2 core rollback path.

## Frozen-behavior scope audit

Compare:
- base `9ad51e8bd0af1630694468ba0423ca222ff8e4ea`
- behavior `717c0b474a9f9742b770ae2246f258434a2c81f1`
- **30 commits ahead**
- **0 behind**
- exactly **19 changed files**.

Changed files:

1. `.env.example`
2. `crates/shreks-observer/tests/g4_telemetry_systemd.rs`
3. `deploy/systemd/README.md`
4. `deploy/systemd/shreks-telemetry.service`
5. `deploy/systemd/shreks-telemetry.timer`
6. `docs/superpowers/plans/2026-08-25-phase-g4-four-layer-telemetry.md`
7. `docs/superpowers/specs/2026-08-25-phase-g4-four-layer-telemetry-design.md`
8. `python/src/shreks_brain/telemetry/__init__.py`
9. `python/src/shreks_brain/telemetry/codec.py`
10. `python/src/shreks_brain/telemetry/financial.py`
11. `python/src/shreks_brain/telemetry/models.py`
12. `python/src/shreks_brain/telemetry/runtime.py`
13. `python/src/shreks_brain/telemetry/snapshot.py`
14. `python/src/shreks_brain/telemetry/sources.py`
15. `python/tests/test_g4_telemetry_financial.py`
16. `python/tests/test_g4_telemetry_models.py`
17. `python/tests/test_g4_telemetry_runtime.py`
18. `python/tests/test_g4_telemetry_snapshot.py`
19. `python/tests/test_g4_telemetry_sources.py`

The only pre-existing files changed are `.env.example` and the systemd operator runbook. All executable Python production code is new under `shreks_brain.telemetry`; both new systemd units are telemetry-only.

Confirmed absent from the frozen diff:
- strategy/setup/scoring implementation changes;
- risk-engine implementation changes;
- provider behavior changes;
- storage schemas or migrations;
- paper execution, ledger/accounting-core, checkpoint-core, or evaluation-core changes;
- registry mutation or challenger promotion authority;
- transaction construction, signing, or submission;
- wallet/private-key authority;
- live-enable paths;
- dashboard, alerting, or auto-remediation control.

Source-level audit also found no wallet, execution, or submission imports in `python/src/shreks_brain/telemetry`.

## Remaining real-host gate

Repository/CI behavior is proven. No claim is made that the telemetry timer has run on the production VPS, that `/var/lib/shreks/telemetry/current.json` contains real campaign values, or that host permissions/systemd behavior have been physically exercised in this chat.

Before G4 can be treated as physically deployed, the dedicated VPS must:
- install the two telemetry units from the exact sealed G4 source;
- create the private telemetry directory;
- populate the reporting-only host configuration;
- enable the independent timer;
- prove repeated snapshot generation, source immutability, permissions, and failure isolation on the actual host.

This real-host gate does not weaken the repository seal and does not authorize live capital.

## Seal rule

This verification record is the only file permitted to change after frozen behavior. The seal candidate must therefore compare to `717c0b474a9f9742b770ae2246f258434a2c81f1` as exactly one commit ahead, zero behind, with this verification record as the only changed file. Exact-seal CI must preserve **2336 Python tests** plus Rust/workspace and repository safety GREEN.

Profitability remains unproven until real PAPER campaign evidence satisfies the sealed proof gates.

**LIVE TRADING: DISABLED.**
