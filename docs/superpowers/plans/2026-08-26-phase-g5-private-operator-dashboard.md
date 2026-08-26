# Phase G5 Private Operator Dashboard Verification Record

**Phase:** G5 — Private operator dashboard  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-g5-private-operator-dashboard`  
**Stacked PR:** `#46`  
**Base:** sealed G4 `e59ff10028f966f690c7f766004f30d1862e3360`  
**Frozen G5 behavior:** `3b78016cbeebf896ddbfb6cbc1b530dbe853c520`  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g5-private-operator-dashboard-design.md`

**LIVE TRADING: DISABLED.**

## Verification result

G5 repository behavior is **VERIFIED** for the scoped read-only dashboard implementation.

The implementation adds a private authenticated read-only operator view over sealed G4 telemetry and already-persisted PAPER/E11 evidence. It does not add trading/control authority, live execution, promotion mutation, risk mutation, transaction construction/signing/submission, wallet handling, paid infrastructure, or a second profitability/proof engine.

This record seals repository behavior only. Real-host deployment, browser access, TLS/private-overlay exposure, and operator-login checks remain physical deployment evidence and are explicitly not claimed by repository CI.

## Base proof

G5 is stacked directly on the sealed G4 commit:

- G4 seal: `e59ff10028f966f690c7f766004f30d1862e3360`
- G4 exact-seal CI: `32918757080`
- G4 exact-seal jobs: Python GREEN, Rust/workspace GREEN, repository safety GREEN

No G4 behavior was rewritten or rebased into G5.

## Frozen behavior proof

Frozen G5 behavior:

- SHA: `3b78016cbeebf896ddbfb6cbc1b530dbe853c520`
- CI: `32954921213`
- Python tests: **2406 passed**
- Rust/workspace: GREEN
- Repository safety: GREEN

The frozen behavior SHA is the final behavior-bearing commit. Any later seal commit is documentation-only.

## G4 -> frozen G5 geometry

GitHub compare from sealed G4 to frozen G5 reported:

- status: ahead
- commits: **22**
- changed files: **21**
- behind: **0**

Changed files inspected during the final audit:

1. `.env.example`
2. `crates/shreks-observer/tests/g5_dashboard_systemd.rs`
3. `deploy/systemd/README.md`
4. `deploy/systemd/shreks-dashboard.service`
5. `docs/superpowers/plans/2026-08-26-phase-g5-private-operator-dashboard.md`
6. `docs/superpowers/specs/2026-08-26-phase-g5-private-operator-dashboard-design.md`
7. `python/src/shreks_brain/dashboard/__init__.py`
8. `python/src/shreks_brain/dashboard/config.py`
9. `python/src/shreks_brain/dashboard/http.py`
10. `python/src/shreks_brain/dashboard/models.py`
11. `python/src/shreks_brain/dashboard/page.py`
12. `python/src/shreks_brain/dashboard/runtime.py`
13. `python/src/shreks_brain/dashboard/source.py`
14. `python/src/shreks_brain/telemetry/__init__.py`
15. `python/src/shreks_brain/telemetry/codec.py`
16. `python/tests/test_g5_dashboard_authority.py`
17. `python/tests/test_g5_dashboard_config.py`
18. `python/tests/test_g5_dashboard_http.py`
19. `python/tests/test_g5_dashboard_page.py`
20. `python/tests/test_g5_dashboard_source.py`
21. `python/tests/test_g5_telemetry_decoder.py`

No provider adapter, database migration/schema, strategy, setup, scoring, risk-engine, execution, ledger, accounting, checkpoint, proof, promotion, registry, wallet, signing, submission, or live-execution file changed.

## Verified behavior

### 1. Strict sealed-G4 decoder

G5 adds only a read-side decoder to the existing telemetry codec.

Verified properties:

- accepts exact canonical G4 telemetry only;
- requires UTF-8 JSON and canonical encoding/trailing newline;
- rejects unknown fields and schema drift;
- rejects unsupported status/live values and wrong nested types;
- rejects NaN/Infinity/non-finite JSON constants;
- reconstructs the existing G4 dataclasses rather than creating alternate monitoring formulas;
- does not modify G4 snapshot generation or trading metrics.

### 2. Read-only evidence source

The dashboard source:

- decodes the persisted G4 snapshot;
- bootstraps/restores the existing PAPER runtime state without executing a cycle;
- reads persisted `EvaluatedTrade` and `PaperLedgerEntry` evidence;
- orders and joins trades deterministically by exact persisted identifiers;
- copies E11 economics rather than recomputing them;
- marks unavailable historical explanation evidence as `NOT_PERSISTED` rather than inventing it;
- fails closed on missing/corrupt/incoherent required evidence.

The real-runtime source test proves the read operation leaves the operational database, manifest, E11 evidence, and telemetry bytes unchanged.

### 3. Runtime configuration and secret boundary

Dashboard-specific configuration is limited to:

- `SHREKS_DASHBOARD_BIND_HOST`
- `SHREKS_DASHBOARD_PORT`
- `SHREKS_DASHBOARD_USERNAME`
- `SHREKS_DASHBOARD_PASSWORD_FILE`
- `SHREKS_DASHBOARD_TELEMETRY_PATH`
- `SHREKS_DASHBOARD_MAX_TRADES`

Verified properties:

- unknown dashboard keys fail closed;
- bind host must be exact loopback (`127.0.0.1` or `::1`);
- port and trade bound are canonical bounded integers;
- username is exact printable ASCII without colon/whitespace ambiguity;
- password is loaded only from a protected host file;
- symlink, missing, directory, empty, oversized, world-readable, or group/world-writable password files are rejected;
- password value is not part of `DashboardRuntimeConfig`;
- existing PAPER runtime paths remain authoritative rather than being duplicated into a second dashboard policy channel.

No populated secret was committed. Repository safety is GREEN.

### 4. Authenticated read-only HTTP boundary

All application routing is behind authentication.

Verified routes:

- `GET /`
- `GET /api/v1/snapshot`
- `GET /api/v1/trades`
- `GET /api/v1/trades/<position_id>`

Verified boundary behavior:

- absent/malformed/incorrect Basic credentials -> `401`;
- credentials use `hmac.compare_digest`;
- unknown trade -> `404`;
- source failure -> generic `503` without exception or password leakage;
- mutation methods (`POST`, `PUT`, `PATCH`, `DELETE`) -> `405` before application routing;
- no mutation/control route exists;
- standard request logging is suppressed so Authorization values are not printed;
- JSON uses finite serialization (`allow_nan=False`);
- responses include no-store, CSP, nosniff, frame denial, no-referrer and restrictive permission headers.

### 5. Responsive operator page

The page is dependency-free HTML/CSS/JS served from the same authenticated process.

Verified properties:

- prominent `LIVE TRADING: DISABLED` banner;
- System, Trading, Money and Proof/Risk layers;
- bounded recent-trade list and persisted trade drill-down;
- phone/desktop responsive viewport/layout;
- same-origin authenticated GET polling only;
- source-derived values are written with `textContent`, never `innerHTML`;
- no external URLs, scripts, fonts, images, CDN or analytics dependency;
- no halt, kill-switch, POST, PUT, PATCH or DELETE UI control;
- browser formatting is limited to presentation such as timestamp/currency/percentage rendering;
- expectancy, profit factor, drawdown, total cost burden and proof decisions come from authoritative server evidence rather than browser-side formulas.

### 6. Authority firewall

The G5 authority tests verify that the dashboard package:

- exports no mutation/control API;
- imports no live executor, signer/submission, transaction-construction, wallet-secret, promotion-mutation, registry-mutation, or risk-mutation module;
- contains no filesystem write calls;
- routes GET only before application-route dispatch.

This is in addition to the file-level final audit showing that no pre-existing trading-authority file changed.

### 7. Independent systemd service

`deploy/systemd/shreks-dashboard.service` is verified to:

- run as `shreks:shreks`;
- use `/opt/shreks/current/.venv/bin/python -m shreks_brain.dashboard.runtime`;
- read `/etc/shreks/shreks.env` and `/etc/shreks/dashboard-password`;
- have no writable Shreks runtime path;
- use `ProtectSystem=strict` plus additional process/kernel hardening;
- restrict address families and deny non-loopback networking;
- restart on failure with bounded restart settings;
- remain independent of `shreks.target`;
- contain no live/wallet/signing/submission/control command.

`shreks.target` was not modified and does not require or want the dashboard service. Dashboard failure therefore cannot stop the core PAPER target.

The runbook requires the password file to be protected as `root:shreks 0640`, keeps the application listener loopback-only, rejects public exposure of the plain HTTP port, and requires a same-host TLS reverse proxy or authenticated private overlay/tunnel for remote/phone access.

## TDD / CI evidence retained

The implementation was built through explicit RED -> GREEN gates. Later-stage evidence retained in GitHub includes:

- Task 3 defect fix: `af1c91e4db7ef86025f8cdff7ed83735791a7e09`; CI `32953401893` GREEN.
- Task 4 RED: `e937b767cb5a5919f56e4972f12027dc3858bb70`; CI `32953604824` failed only because `shreks_brain.dashboard.http` did not yet exist.
- Task 4 GREEN: `86fa9d399da68c287b2988db9ebaa4b5640ff1a6`; CI `32953827675` GREEN.
- Task 5 RED: `e648eba0da7b833e90c075a8df78111f4d89daea`; CI `32953986957` failed only because `shreks_brain.dashboard.page` did not yet exist.
- Task 5 final GREEN behavior before Task 6: `2b2aa2c1e796b26c970769532c7f395972ac181e`; CI `32954445449` GREEN.
- Task 6 RED: `be0eba5867e4c6f1c6f5149d6353af3b0c4fe76d`; CI `32954637114`; Python authority + repository safety GREEN and Rust failed only on the intentionally absent G5 service/runbook contract.
- Task 6/frozen behavior GREEN: `3b78016cbeebf896ddbfb6cbc1b530dbe853c520`; CI `32954921213`; **2406 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.

Earlier Task 1/Task 2 commits/tests remain in the branch history and are re-exercised by the frozen full-suite gate.

## Scope-drift audit

Final file-by-file inspection found no G5 mutation drift in:

- providers or free-source policy;
- database/storage schemas or migrations;
- observer/write cadence;
- strategy/setup logic;
- scoring or feature formulas;
- risk decisions or limits;
- paper/live execution;
- position ledger or accounting;
- restart/checkpoint state;
- E11 proof calculations or proof gates;
- champion/challenger registry or promotion;
- wallet/signing/submission paths;
- live enablement.

G5 is a presentation/read-side layer only.

## Seal geometry requirement

This file replaces the implementation plan in the **single documentation-only seal commit** after frozen behavior.

Required post-commit proof before the PR may be considered G5-sealed:

1. compare frozen behavior `3b78016cbeebf896ddbfb6cbc1b530dbe853c520` to the seal commit;
2. require exactly **1 commit / 1 changed file**;
3. require the sole file to be this verification record;
4. run exact-seal CI;
5. require **2406 Python tests passed** again, plus Rust/workspace GREEN and repository safety GREEN;
6. record the seal SHA and exact-seal CI in draft PR #46;
7. keep PR #46 open, draft, and unmerged.

No behavior change is permitted after the frozen SHA without invalidating this seal and repeating the audit.

## Remaining real-host / later-phase gates

Repository CI does **not** prove:

- actual host user/group/file ownership and permissions;
- real systemd startup/restart behavior on the selected VPS;
- actual loopback socket exposure under host networking;
- real reverse-proxy/TLS or private-overlay configuration;
- successful operator login from phone/browser;
- browser usability against live PAPER telemetry on the production host;
- G6 alert delivery;
- G7 controlled halt/kill-switch operator controls;
- G8 backup/restore proof.

Those remain later operational/deployment evidence. They do not grant live-money permission.

Profitability remains unproven until the autonomous PAPER campaign satisfies the sealed proof gates with real accumulated evidence.

**LIVE TRADING: DISABLED.**
