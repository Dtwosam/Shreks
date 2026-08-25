# Phase G1 Production Paper Evidence Runtime — Final Verification Record

**Phase:** G1 — Dedicated Linux production runtime, first bounded slice  
**Sealed base:** E15 `b8daa24bbaaa1369e91c9735aaad0d990fd6ba53`  
**Frozen behavior SHA:** `711d4b68a4bc41f17ba133163bf4f41615a7835b`  
**Behavior CI:** GitHub Actions run `32891299275` — SUCCESS on the exact frozen behavior SHA  
**Design:** `docs/superpowers/specs/2026-08-25-phase-g1-production-paper-evidence-runtime-design.md`  
**Stacked PR:** #40 — `Phase G1: Production paper evidence runtime`  
**Date:** 2026-08-25

## Result

Phase G1 adds a continuously runnable, restart-supervised, paper-only evidence runtime on top of sealed E15 without adding trading, signing, submission, promotion, registry-mutation, or live-money authority.

The frozen behavior can:

- select a deterministic bounded set of recently active observer candidates from the operational SQLite database using a separate read-only connection;
- require every operational/economic paper-evidence input explicitly at runtime;
- require Helius and Jupiter before daemon startup;
- collect real read-only Helius holder-distribution evidence;
- collect purpose-correct Jupiter EXIT and ENTRY quote evidence through the sealed E15 `SafetyEvidenceCollector` and storage path;
- aggregate provider degradation without fabricating evidence;
- fail closed on candidate-store, schema, configuration, probe, or storage-integrity failures;
- run continuously as `shreks-paper-evidence` with clean Ctrl-C/SIGINT handling;
- supervise both `shreks-observe` and `shreks-paper-evidence` under systemd on one Linux host with durable state outside the release checkout.

**LIVE TRADING REMAINS DISABLED.**

## TDD evidence ledger

### Task 1 — bounded read-only candidate selection

The first RED at `45e4d85a4c962e61cecfb948feb09932b482641d` intentionally exposed the absence of a proposed storage read API. Before production implementation, the design was tightened so operational candidate enumeration would not widen sealed E15 storage. The abandoned RED remains immutable history.

The corrected runtime-local RED was `8872540329ba58d19cca5deb113bf29b4ee4d686`. Production implementation landed through `520e7e8a3b3bdfd7d38a278d33d3310daf039c43` plus the runtime dependency move at `1ac8f33991ae9bad6830b1bd20da9e91d0012d16`. Exact-head CI run `32888846383` was GREEN.

Verified properties include point-in-time windowing, future-row exclusion, deterministic ordering, duplicate collapse, hard limiting, zero-limit behavior, invalid-window rejection, schema validation, malformed-row rejection, and non-creation of a missing database by the read-only store.

### Task 2 — explicit runtime/economic configuration

RED: `89a7eafd51d55c1ab68d0e35f31a5b9b6f258dd7`.

GREEN behavior: `b628cdf02c6e278fc877f4156a389a36ab0d8629`, with blank variable declarations at `a9a5d72f29ce894821177ce4666b7b69dd985cfd`. Exact-head CI run `32889181098` was GREEN.

Verified properties include explicit required interval/lookback/batch settings, explicit probe version, quote asset, taker, entry/exit amounts, slippage, distribution page size/max pages, separate Helius/Jupiter provider gates, purpose-correct bidirectional probes, and no provider-key contents in debug/error output. No economic production default was copied from a test fixture.

### Task 3 — one bounded evidence cycle

RED: `41e0defdd054e3d842b20c49a3d254a7b67ae8d2`.

GREEN: `d28dddd1fc8880eb6467f223b13cd4db8fac66a4`. Exact-head CI run `32889508928` was GREEN.

Verified properties include probing only the selected point-in-time candidate set, exact ENTRY/EXIT direction and amount identity, persistence through the sealed E15 collector, zero provider calls for an empty candidate set, provider-failure accounting without synthetic success, and propagation of probe/storage/integrity failures.

### Task 4 — long-running paper-evidence daemon

RED: `7e1fba5a7e2f102519865b00bf0fdbde71b7e556`.

The RED review found a contradictory test assertion: the daemon was required to construct Helius/Jupiter providers while the test also prohibited the safe credential accessors needed to do so. The contract was corrected at `6693660e14be11f41e2691a103f6ce93c9f50519` before production implementation. The correct rule is that runtime credentials may be consumed only to construct provider clients and must never be logged or persisted as evidence.

GREEN: `36fe821719200adf7b272bcc81057e59e6cbd0f2`. Exact-head CI run `32889856333` was GREEN.

Verified properties include startup provider gates, the shared configured database, read-only candidate enumeration, one sealed evidence collector, continuous bounded cycles, aggregate non-secret logging, clean Ctrl-C handling, and a source-level authority firewall against trading/promotion/signing/submission paths.

### Task 5 — Linux systemd supervision

Initial RED: `43216cbdf7e2c02632faa2ceef9719d36aee4707`.

That RED correctly failed Rust because the four deployment artifacts were absent, but repository safety also rejected literal private-key/seed-phrase assignment patterns inside the test source itself. The assertions were rewritten without weakening their semantics at `d02b7b653af6138254b27c452e9dc2a848411794`; the corrected RED then had repository safety and Python GREEN while Rust failed only because the deployment files were absent.

GREEN/frozen behavior: `711d4b68a4bc41f17ba133163bf4f41615a7835b`. Exact-head push CI run `32891299275` completed SUCCESS with Rust/workspace, Python, and repository-safety jobs all GREEN.

Verified properties include a dedicated non-root `shreks` identity, `/opt/shreks/current`, `/etc/shreks/shreks.env`, `Restart=on-failure`, SIGINT shutdown, grouped `shreks.target`, no embedded provider/wallet secrets, no live enablement, and a runbook that keeps the SQLite WAL database/evidence on durable host storage across release changes and rollbacks.

## Sealed E15 -> frozen G1 behavior audit

The exact compare from sealed E15 `b8daa24bbaaa1369e91c9735aaad0d990fd6ba53` to frozen behavior `711d4b68a4bc41f17ba133163bf4f41615a7835b` is ahead by 20 commits, behind by 0, and changes exactly 17 files.

| File | Audit result |
| --- | --- |
| `.env.example` | Adds blank provider/paper-evidence variable declarations only; no populated secret or economic default. |
| `crates/shreks-observer/Cargo.toml` | Moves already-used `rusqlite` from dev-only to runtime dependency; no unrelated dependency widening. |
| `crates/shreks-observer/src/bin/shreks-paper-evidence/candidate_store.rs` | New runtime-local read-only, schema-validated, deterministic bounded candidate selector; no write/migration authority. |
| `crates/shreks-observer/src/bin/shreks-paper-evidence/config.rs` | New strict explicit config and probe construction; provider credentials are consumed through existing `ProviderConfig`; no hidden economic defaults. |
| `crates/shreks-observer/src/bin/shreks-paper-evidence/cycle.rs` | New bounded collector aggregator using sealed E15 evidence APIs only; no trading/promotion/signing/submission authority. |
| `crates/shreks-observer/src/bin/shreks-paper-evidence/main.rs` | New long-running paper evidence daemon; read-only provider calls plus sealed evidence writes only. |
| `crates/shreks-observer/tests/paper_evidence_binary.rs` | Structural daemon authority/logging firewall tests only. |
| `crates/shreks-observer/tests/paper_evidence_candidate_store.rs` | Point-in-time/read-only/schema/bounds regression tests only. |
| `crates/shreks-observer/tests/paper_evidence_cycle.rs` | Real temp-SQLite + static-provider cycle tests, including no-fabrication provider-failure behavior and authority firewall. |
| `crates/shreks-observer/tests/paper_evidence_runtime_config.rs` | Explicit-config, exact-probe, provider-gate, and secret-redaction regression tests only. |
| `crates/shreks-observer/tests/systemd_units.rs` | Static deployment-contract and no-live/no-secret assertions only. |
| `deploy/systemd/README.md` | Single-host operator runbook; durable state, protected runtime env, supervision, upgrade/rollback, live disabled. |
| `deploy/systemd/shreks-observe.service` | Non-root supervision for existing observer; no new authority. |
| `deploy/systemd/shreks-paper-evidence.service` | Non-root supervision for the new paper-evidence daemon; no new authority. |
| `deploy/systemd/shreks.target` | Groups the two paper/observe services only. |
| `docs/superpowers/plans/2026-08-25-phase-g1-production-paper-evidence-runtime.md` | G1 implementation/proof record. |
| `docs/superpowers/specs/2026-08-25-phase-g1-production-paper-evidence-runtime-design.md` | G1 approved design boundary. |

## Negative authority audit

The frozen behavior diff does **not** modify any sealed `shreks-storage` source file and does not widen the sealed storage public API.

It does **not** modify strategy, risk, E11/E12 evaluation/promotion, live execution, signing, or transaction-submission implementation.

The new runtime does **not** create trade intents, mutate champion/challenger state, promote candidates, construct/sign/submit transactions, enable live mode, or contain wallet/private signing material.

Provider credentials remain runtime-only configuration. The committed `.env.example`, unit files, tests, docs, and runtime logging contain no real secret values.

Synthetic/static provider fixtures remain test mechanics only and are not evidence of profitability.

## Seal protocol

`711d4b68a4bc41f17ba133163bf4f41615a7835b` is the frozen behavior SHA. The commit containing this verification document is the G1 seal commit and must modify only this file relative to the frozen behavior SHA.

After this document is committed, verification is performed externally against Git history and GitHub Actions:

1. behavior -> seal must be exactly one commit ahead and zero behind;
2. the only behavior -> seal changed file must be this verification document;
3. a fresh exact-seal CI run must be GREEN for Rust/workspace, Python, and repository safety.

The seal commit SHA and exact-seal CI run are therefore recorded in PR #40 / GitHub history rather than self-referentially editing this immutable record again.

## Next proof phase

The next implementation slice is the **Python multi-candidate paper campaign coordinator**, followed by actual independent paper evidence collection on real point-in-time observer data.

That evidence must be evaluated through the existing E10/E11/E12 proof stack for at least:

- expectancy after measured costs;
- drawdown;
- independent trade/sample count, distinct mints, and elapsed time;
- cost burden and winner concentration;
- reproducible accounting and evaluation inputs.

No threshold may be invented merely to pass a gate. Synthetic fixtures prove mechanics, not profitability.

**Live money remains disabled until the required real-paper, reliability, fill, risk-halt, accounting, restart/reconciliation, and paper/live-parity evidence is actually demonstrated.**
