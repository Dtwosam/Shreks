# Phase G1 Production Paper Evidence Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a continuously runnable, restart-safe, paper-only evidence daemon that collects real Helius holder evidence and purpose-correct Jupiter ENTRY/EXIT quote evidence for bounded recent observer candidates.

**Architecture:** Reuse the sealed E15 `SafetyEvidenceCollector` and existing provider adapters. Add one bounded point-in-time candidate-read API in storage, an environment-derived runtime config that requires all economic probe parameters explicitly, a thin long-running Rust binary, and systemd supervision files. No strategy, registry, promotion, execution, or live authority is introduced.

**Tech Stack:** Rust 2021, Tokio, SQLite/rusqlite, existing Helius/Jupiter adapters, GitHub Actions, systemd unit files.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-g1-production-paper-evidence-runtime-design.md`

## Global Constraints

- Base exactly on sealed E15 `b8daa24bbaaa1369e91c9735aaad0d990fd6ba53`.
- Do not modify sealed B1/B2/B6/C5/C6/E11/E12 strategy/risk/evaluation/promotion semantics.
- Do not create trade intents, transactions, signatures, submissions, or live-money authority.
- No wallet/private signing credentials in code, GitHub, logs, docs examples, or tests.
- Use only existing free/public provider adapters; Helius and Jupiter credentials are runtime environment values.
- Economic probe values must be explicit configuration, never copied from permissive test fixtures.
- TDD RED -> inspect -> minimal GREEN for every behavior change.

---

### Task 1: Bounded point-in-time evidence candidate selection

**Files:**
- Modify: `crates/shreks-storage/src/lib.rs`
- Create: `crates/shreks-storage/tests/evidence_probe_candidates.rs`

**Interfaces:**
- Produces:
  - `pub struct EvidenceProbeCandidate { pub candidate_id: i64, pub mint: String, pub latest_market_observed_at_unix_ms: i64 }`
  - `ShreksDb::recent_evidence_probe_candidates(&self, as_of_unix_ms: i64, lookback_ms: i64, limit: usize) -> Result<Vec<EvidenceProbeCandidate>, StorageError>`

- [ ] **Step 1: Write RED tests**

Cover all of these behaviors in `evidence_probe_candidates.rs`:

1. only candidates with market evidence inside `[as_of - lookback, as_of]` are returned;
2. future market snapshots are excluded;
3. duplicate snapshots collapse to one candidate using the latest eligible timestamp;
4. order is latest timestamp descending then candidate id ascending;
5. result count is capped by `limit`;
6. `limit == 0` returns empty;
7. negative `as_of_unix_ms` fails with `StorageError::InvalidData`;
8. `lookback_ms <= 0` fails with `StorageError::InvalidData`.

- [ ] **Step 2: Run repository CI and verify RED**

Expected Rust failure: missing `EvidenceProbeCandidate` / `recent_evidence_probe_candidates`. Python and repository-safety jobs must remain GREEN.

- [ ] **Step 3: Implement minimal storage API**

Use one SQL query equivalent to:

```sql
SELECT tc.id, tc.mint, MAX(ms.observed_at_unix_ms) AS latest_market_observed_at_unix_ms
FROM token_candidates AS tc
JOIN market_snapshots AS ms ON ms.candidate_id = tc.id
WHERE ms.observed_at_unix_ms BETWEEN ?1 AND ?2
GROUP BY tc.id, tc.mint
ORDER BY latest_market_observed_at_unix_ms DESC, tc.id ASC
LIMIT ?3
```

Compute lower bound with saturating/clamped arithmetic so timestamp zero is valid. Validate returned ids/timestamps/mints before constructing the public read model.

- [ ] **Step 4: Run full CI to GREEN and commit**

Commit message: `feat: select bounded paper evidence candidates`

---

### Task 2: Explicit paper-evidence runtime configuration

**Files:**
- Create: `crates/shreks-observer/src/paper_evidence_runtime.rs`
- Modify: `crates/shreks-observer/src/lib.rs`
- Create: `crates/shreks-observer/tests/paper_evidence_runtime.rs`
- Modify: `.env.example`

**Interfaces:**
- Produces:
  - `PaperEvidenceRuntimeConfig`
  - `PaperEvidenceRuntimeConfigError`
  - `PaperEvidenceRuntimeConfig::from_lookup<F>(lookup: F)`
  - `PaperEvidenceRuntimeConfig::from_env()`
  - `PaperEvidenceRuntimeConfig::probe_for(&self, candidate_mint: &str) -> Result<SafetyEvidenceProbe, PaperEvidenceRuntimeConfigError>`
  - `PaperEvidenceRuntimeConfig::require_providers(&self) -> Result<(), PaperEvidenceRuntimeConfigError>`

Configuration fields:

```text
db_path: PathBuf
cycle_interval: Duration
candidate_lookback_ms: i64
max_candidates: usize
probe_policy_version: String
quote_asset_mint: String
quote_taker: String
entry_input_amount: u64
exit_input_amount: u64
slippage_bps: u16
distribution_page_size: usize
distribution_max_pages: usize
providers: ProviderConfig
```

- [ ] **Step 1: Write RED tests**

Tests must prove:

1. every required economic input is rejected when blank/missing;
2. zero amounts, zero page sizes/pages, invalid slippage, zero/invalid cycle interval/lookback/max-candidate values fail closed;
3. Helius and Jupiter are both required by `require_providers`;
4. `probe_for("MintX")` creates holder, EXIT and ENTRY requests with exact candidate/quote-asset/taker/slippage/version attribution;
5. no API-key contents appear in `Debug` output;
6. `.env.example` contains variable names only and no real secrets.

- [ ] **Step 2: Run CI and verify RED**

Expected Rust failure: module/types absent.

- [ ] **Step 3: Implement minimal config/parser**

Use existing `ProviderConfig::from_lookup`. Parse all integers with explicit positive/range validation. Do not introduce economic defaults. `probe_for` must use validated `TokenDistributionRequest::new` and `QuoteRequest::new` constructors.

- [ ] **Step 4: Run full CI to GREEN and commit**

Commit message: `feat: add paper evidence runtime config`

---

### Task 3: One bounded paper-evidence runtime cycle

**Files:**
- Modify: `crates/shreks-observer/src/paper_evidence_runtime.rs`
- Create: `crates/shreks-observer/tests/paper_evidence_cycle.rs`

**Interfaces:**
- Produces:
  - `PaperEvidenceRuntimeCycleReport`
  - `PaperEvidenceRuntimeError`
  - `run_paper_evidence_cycle(...)`

The cycle function consumes an already-open `ShreksDb`, an already-built `SafetyEvidenceCollector`, the validated runtime config, and one explicit `as_of_unix_ms`. It selects bounded candidates through Task 1 and calls the sealed collector once per selected candidate.

- [ ] **Step 1: Write RED tests**

Use static test providers and a real temporary SQLite database. Prove:

1. only selected recent candidates are probed;
2. exact candidate-specific ENTRY/EXIT identities are used;
3. collector provider failures are accumulated in the cycle report and do not fabricate stored evidence;
4. storage/probe integrity errors fail the cycle;
5. no candidate selected means zero provider calls and a zero report;
6. no trade-intent, registry mutation, promotion, signing, submission, or live module is referenced by the runtime source.

- [ ] **Step 2: Run CI and verify RED**

Expected failure: cycle interface absent.

- [ ] **Step 3: Implement minimal bounded cycle**

Keep provider transport failures nonfatal only when the sealed collector already represents them as report counts. Do not catch and suppress `SafetyEvidenceError::Storage` or `InvalidProbe`.

- [ ] **Step 4: Run full CI to GREEN and commit**

Commit message: `feat: run bounded paper evidence cycles`

---

### Task 4: Long-running `shreks-paper-evidence` binary

**Files:**
- Create: `crates/shreks-observer/src/bin/shreks-paper-evidence.rs`
- Create: `crates/shreks-observer/tests/paper_evidence_binary.rs`

**Interfaces:**
- Binary name: `shreks-paper-evidence`
- External authority: read-only Helius/Jupiter calls plus evidence writes through sealed storage only.

- [ ] **Step 1: Write RED structural/runtime tests**

Prove the binary source:

1. constructs `PaperEvidenceRuntimeConfig` from environment;
2. requires Helius/Jupiter before loop start;
3. opens the configured shared SQLite path;
4. constructs `HeliusProvider`, `JupiterProvider`, and `SafetyEvidenceCollector` only;
5. repeatedly calls the bounded cycle on a configured interval;
6. exits cleanly on Ctrl-C;
7. never imports execution, live, promotion, registry mutation, signing, or transaction-submission paths;
8. never logs provider key contents.

- [ ] **Step 2: Run CI and verify RED**

Expected failure: binary absent.

- [ ] **Step 3: Implement minimal daemon**

Log startup and per-cycle aggregate counts only. Treat configuration/storage/integrity errors as process-fatal. Keep provider failures visible through report counts.

- [ ] **Step 4: Run full CI to GREEN and commit**

Commit message: `feat: add paper evidence daemon`

---

### Task 5: Linux systemd supervision

**Files:**
- Create: `deploy/systemd/shreks-observe.service`
- Create: `deploy/systemd/shreks-paper-evidence.service`
- Create: `deploy/systemd/shreks.target`
- Create: `deploy/systemd/README.md`
- Create: `crates/shreks-observer/tests/systemd_units.rs`

**Interfaces:**
- Runtime root: `/opt/shreks/current`
- Environment file: `/etc/shreks/shreks.env`
- Service user/group: `shreks`

- [ ] **Step 1: Write RED repository tests**

Tests read the unit files as text and require:

- `User=shreks`, `Group=shreks`;
- `WorkingDirectory=/opt/shreks/current`;
- `EnvironmentFile=/etc/shreks/shreks.env`;
- `Restart=on-failure`;
- observe service executes `shreks-observe`;
- evidence service executes `shreks-paper-evidence`;
- no `JUPITER_API_KEY=`, `HELIUS_API_KEY=`, seed phrase, private key, live enable, or transaction-submit command appears;
- target groups both services.

- [ ] **Step 2: Run CI and verify RED**

Expected failure: deployment files absent.

- [ ] **Step 3: Add minimal systemd units and operator README**

README covers dedicated-user creation, persistent data directory ownership, runtime environment-file permissions (`0600`), build/install paths, `daemon-reload`, enable/start/stop/status/journal commands, reboot behavior, and explicit statement that this slice has no signing/live authority.

- [ ] **Step 4: Run full CI to GREEN and commit**

Commit message: `ops: supervise observer paper evidence runtime`

---

### Task 6: Scope audit and seal

**Files:**
- Modify only this plan file for the final verification record.

- [ ] **Step 1: Freeze behavior SHA after Task 5 full CI is GREEN**

Record exact behavior SHA and CI run.

- [ ] **Step 2: Audit sealed E15 -> G1 behavior diff file by file**

Reject the seal if any strategy threshold, paper accounting semantics, E11/E12 behavior, registry mutation/promotion, live execution, signing, or transaction submission changed.

- [ ] **Step 3: Replace this plan with the final verification record in one docs-only commit**

Include RED/GREEN commit anchors and exact CI runs for Tasks 1-5.

- [ ] **Step 4: Prove behavior -> seal is exactly one commit / one verification-document file**

- [ ] **Step 5: Run fresh exact-seal CI**

Require Python, Rust/workspace, and repository-safety GREEN at the exact seal SHA.

- [ ] **Step 6: Update the stacked draft PR**

State clearly that the next step is the Python multi-candidate paper campaign coordinator and actual independent paper evidence collection. Live trading remains disabled.