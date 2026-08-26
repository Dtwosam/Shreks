# Phase G5 Private Operator Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private authenticated read-only operator dashboard that presents sealed G4 telemetry and persisted PAPER/E11 trade evidence without introducing trading/control authority.

**Architecture:** Add a standard-library-only `shreks_brain.dashboard` package. The dashboard strictly decodes the G4 snapshot, restores existing PAPER state read-only for trade drill-down, authenticates every HTTP route with host-only Basic credentials, and serves a dependency-free responsive HTML/JS UI. It has no mutation routes and runs as an independent loopback-only systemd service.

**Tech Stack:** Python 3.12 standard library, existing Shreks Python domain/store modules, pytest, Rust systemd contract tests, systemd.

**Spec:** `docs/superpowers/specs/2026-08-26-phase-g5-private-operator-dashboard-design.md`

## Global Constraints

- Base exactly on sealed G4 `e59ff10028f966f690c7f766004f30d1862e3360`.
- LIVE TRADING remains disabled.
- No new production Python dependency.
- No dashboard-side profitability formulas.
- No database/E11/checkpoint/proof/promotion writes.
- No POST/PUT/PATCH/DELETE control surface.
- No promotion/risk/live/signing/submission/wallet authority.
- Unknown/missing/corrupt required evidence fails closed.
- Browser output never includes auth secret material.
- Dashboard binds only to explicit loopback.
- Dashboard service is independent of `shreks.target`.

---

## File map

Create:

- `python/src/shreks_brain/dashboard/__init__.py` — narrow public read-only dashboard API.
- `python/src/shreks_brain/dashboard/models.py` — immutable source/trade/auth-safe view models.
- `python/src/shreks_brain/dashboard/source.py` — G4 snapshot + E11/PAPER ledger read-only source joins.
- `python/src/shreks_brain/dashboard/config.py` — strict dashboard operational configuration and secret-file validation.
- `python/src/shreks_brain/dashboard/http.py` — authentication, routing, safe JSON/HTML responses and security headers.
- `python/src/shreks_brain/dashboard/page.py` — static dependency-free HTML/CSS/JS shell.
- `python/src/shreks_brain/dashboard/runtime.py` — HTTP server bootstrap/CLI only.
- `python/tests/test_g5_telemetry_decoder.py`
- `python/tests/test_g5_dashboard_source.py`
- `python/tests/test_g5_dashboard_config.py`
- `python/tests/test_g5_dashboard_http.py`
- `python/tests/test_g5_dashboard_page.py`
- `python/tests/test_g5_dashboard_authority.py`
- `crates/shreks-observer/tests/g5_dashboard_systemd.rs`
- `deploy/systemd/shreks-dashboard.service`

Modify:

- `python/src/shreks_brain/telemetry/codec.py` — add strict decoder only.
- `python/src/shreks_brain/telemetry/__init__.py` — expose decoder.
- `.env.example` — add dashboard operational keys only.
- `deploy/systemd/README.md` — G5 auth/private-access/systemd runbook.
- `docs/superpowers/plans/2026-08-26-phase-g5-private-operator-dashboard.md` — final verification record at seal.

---

### Task 1: Strict G4 telemetry decoder

**Files:**
- Modify: `python/src/shreks_brain/telemetry/codec.py`
- Modify: `python/src/shreks_brain/telemetry/__init__.py`
- Create: `python/tests/test_g5_telemetry_decoder.py`

**Interfaces:**
- Consumes: `TelemetrySnapshot` and nested G4 telemetry dataclasses.
- Produces: `decode_telemetry_snapshot(payload: str | bytes) -> TelemetrySnapshot`.

- [ ] **Step 1: Write RED tests**

Tests must construct a valid `TelemetrySnapshot`, encode it with `encode_telemetry_snapshot`, then require decoder round-trip equality. Mutations must reject:

```python
@pytest.mark.parametrize(
    "mutator",
    [
        lambda obj: {**obj, "extra": True},
        lambda obj: {**obj, "schema_version": "g4-telemetry-snapshot-v999"},
        lambda obj: {**obj, "mode": "LIVE"},
        lambda obj: {**obj, "system": {**obj["system"], "extra": True}},
    ],
)
def test_decode_rejects_unknown_or_unsupported_shapes(mutator): ...
```

Also require rejection of non-UTF8 bytes, non-finite numeric JSON constants, missing trailing newline/non-canonical whitespace, wrong nested types, and invalid status values.

- [ ] **Step 2: Run the new test file and prove RED**

Run: `python -m pytest python/tests/test_g5_telemetry_decoder.py -q`

Expected: import/attribute failure because `decode_telemetry_snapshot` does not exist.

- [ ] **Step 3: Implement the minimal strict decoder**

Implementation requirements:

```python
def decode_telemetry_snapshot(payload: str | bytes) -> TelemetrySnapshot:
    # normalize bytes through strict UTF-8
    # json.loads with parse_constant rejecting NaN/Infinity
    # exact-key validation at snapshot + nested structures
    # explicit LayerStatus reconstruction
    # exact dataclass reconstruction
    # re-encode and require byte/string canonical equality
    return snapshot
```

Do not use arbitrary object hooks/deserialization. Keep helpers private to `telemetry.codec`.

- [ ] **Step 4: Run Task 1 tests, then full gates**

Run:

```sh
python -m pytest python/tests/test_g5_telemetry_decoder.py -q
python -m pytest python/tests -q
cargo test --workspace
```

Repository safety must also remain GREEN in CI.

- [ ] **Step 5: Commit Task 1 GREEN**

Commit message: `feat: add strict telemetry snapshot decoder`.

---

### Task 2: Read-only dashboard source and trade drill-down

**Files:**
- Create: `python/src/shreks_brain/dashboard/models.py`
- Create: `python/src/shreks_brain/dashboard/source.py`
- Create: `python/src/shreks_brain/dashboard/__init__.py`
- Create: `python/tests/test_g5_dashboard_source.py`

**Interfaces:**
- Consumes: `decode_telemetry_snapshot`, `ObserverPaperCampaignRuntimeConfig`, `bootstrap_observer_paper_campaign_runtime`, `EvaluatedTrade`, `PaperLedgerEntry`.
- Produces:
  - `DashboardEvidenceAvailability(StrEnum)` with `AVAILABLE`, `NOT_PERSISTED`.
  - `DashboardTradeSummary`.
  - `DashboardLedgerEvent`.
  - `DashboardTradeDetail`.
  - `DashboardSnapshotSource`.
  - `DashboardSourceConfig`.
  - `load_dashboard_snapshot(config, *, max_trades: int) -> DashboardSnapshotSource`.
  - `load_dashboard_trade(config, position_id: str) -> DashboardTradeDetail | None`.

- [ ] **Step 1: Write RED source tests**

Use existing real test fixtures/helpers for a seeded PAPER runtime. Require:

- canonical G4 snapshot file is read and decoded;
- E11 evaluated trades are ordered newest-close first;
- ledger entries join only by exact `position_id`;
- ledger event sequence remains original ledger sequence order;
- exact E11 economics are copied without recomputation;
- full safety/features/score/decision/risk/raw-quote/strategic-exit fields carry `NOT_PERSISTED` when absent;
- missing/corrupt required telemetry fails closed;
- source reads do not mutate telemetry, DB, manifest, checkpoint, or E11 mtimes/bytes.

- [ ] **Step 2: Run RED**

Run: `python -m pytest python/tests/test_g5_dashboard_source.py -q`

Expected: missing `shreks_brain.dashboard`.

- [ ] **Step 3: Implement immutable view models and source loader**

Important behavior:

```python
@dataclass(frozen=True, slots=True)
class DashboardSourceConfig:
    telemetry_path: Path
    paper_runtime_config: ObserverPaperCampaignRuntimeConfig


def load_dashboard_snapshot(config: DashboardSourceConfig, *, max_trades: int) -> DashboardSnapshotSource:
    telemetry = decode_telemetry_snapshot(config.telemetry_path.read_bytes())
    bootstrap = bootstrap_observer_paper_campaign_runtime(config.paper_runtime_config)
    trades = tuple(bootstrap.runner.evaluated_trades())
    # copy evidence only; no cycle execution
    ...
```

`load_dashboard_trade` joins E11 trade to `bootstrap.restored_state.ledger.entries`. It must not call `run_cycle` or any store append/save method.

- [ ] **Step 4: Run Task 2 tests and full gates**

Run new test file, full Python, and Rust workspace.

- [ ] **Step 5: Commit Task 2 GREEN**

Commit message: `feat: add read-only dashboard evidence source`.

---

### Task 3: Dashboard config and authentication boundary

**Files:**
- Create: `python/src/shreks_brain/dashboard/config.py`
- Create: `python/tests/test_g5_dashboard_config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces:
  - `DashboardRuntimeConfigError`.
  - `DashboardRuntimeConfig` with exact fields:
    - `bind_host: str`
    - `port: int`
    - `username: str`
    - `password_file: Path`
    - `telemetry_path: Path`
    - `max_trades: int`
    - `paper_runtime_config: ObserverPaperCampaignRuntimeConfig`
  - `load_dashboard_runtime_config(env: Mapping[str, str] | None = None) -> DashboardRuntimeConfig`.
  - `load_dashboard_password(config: DashboardRuntimeConfig) -> bytes`.

- [ ] **Step 1: Write RED config tests**

Require exact accepted dashboard keys and rejection of:

- unknown `SHREKS_DASHBOARD_*` keys;
- non-loopback bind hosts;
- ports outside `1024..65535`;
- blank/colon-containing username;
- missing/symlink/directory/empty/oversized password file;
- world-readable password file;
- group/world writable password file;
- missing telemetry path;
- max trades outside `1..500`.

Also prove the dataclass contains no password value and no provider/wallet credentials.

- [ ] **Step 2: Run RED**

Expected: missing `dashboard.config`.

- [ ] **Step 3: Implement config loader and password-file validation**

Reuse `load_observer_paper_campaign_runtime_config(env)` for the existing G1C paths. Do not duplicate those operational keys under the dashboard namespace.

`.env.example` receives blank placeholders for the six dashboard keys only and comments that the password value belongs in the host-only file.

- [ ] **Step 4: Run Task 3 tests + full gates**

- [ ] **Step 5: Commit Task 3 GREEN**

Commit message: `feat: add dashboard runtime configuration`.

---

### Task 4: Authenticated read-only HTTP JSON API

**Files:**
- Create: `python/src/shreks_brain/dashboard/http.py`
- Create: `python/src/shreks_brain/dashboard/runtime.py`
- Create: `python/tests/test_g5_dashboard_http.py`

**Interfaces:**
- Consumes: `DashboardRuntimeConfig`, dashboard source functions, protected password bytes.
- Produces:
  - `DashboardApplication` request dispatcher independent of socket server for tests.
  - `DashboardHTTPResponse(status: int, headers: tuple[tuple[str, str], ...], body: bytes)`.
  - `run_dashboard_server(config: DashboardRuntimeConfig) -> None`.
  - module CLI `python -m shreks_brain.dashboard.runtime`.

- [ ] **Step 1: Write RED HTTP tests**

Drive the request dispatcher directly; no flaky network port tests are needed for route behavior.

Require:

```text
GET / without auth                 -> 401
GET /api/v1/snapshot with auth     -> 200 JSON
GET /api/v1/trades with auth       -> 200 JSON
GET /api/v1/trades/<known>         -> 200 JSON
GET /api/v1/trades/<unknown>       -> 404
POST/PUT/PATCH/DELETE any route    -> 405
corrupt source                     -> 503 without exception text
```

Every response requires security headers. Auth must accept exact Basic credentials and reject near-matches. Tests monkeypatch `hmac.compare_digest` to prove the implementation uses it.

JSON output must not contain password-file path contents, password value, provider credentials, or arbitrary exception text.

- [ ] **Step 2: Run RED**

Expected: missing `dashboard.http` / runtime.

- [ ] **Step 3: Implement dispatcher and server adapter**

Use `BaseHTTPRequestHandler` + `ThreadingHTTPServer` only in the socket adapter. Override request logging so Authorization values are never printed. Request dispatcher owns auth/routing/source-failure mapping.

All source data is serialized with `json.dumps(..., allow_nan=False)` and content type `application/json; charset=utf-8`.

- [ ] **Step 4: Run Task 4 tests + full gates**

- [ ] **Step 5: Commit Task 4 GREEN**

Commit message: `feat: serve authenticated read-only dashboard API`.

---

### Task 5: Responsive operator page

**Files:**
- Create: `python/src/shreks_brain/dashboard/page.py`
- Create: `python/tests/test_g5_dashboard_page.py`
- Modify: `python/src/shreks_brain/dashboard/http.py`

**Interfaces:**
- Produces: `DASHBOARD_HTML: bytes` or `render_dashboard_page() -> bytes` with no dynamic source interpolation.

- [ ] **Step 1: Write RED page tests**

Require static page source to contain:

- title/branding `Shreks Operator Dashboard`;
- prominent `LIVE TRADING: DISABLED`;
- section IDs/labels for System, Trading, Money, Proof/Risk;
- recent-trades table and trade-detail region;
- viewport meta for phone use;
- authenticated same-origin fetches to `/api/v1/snapshot` and `/api/v1/trades`;
- source values written with `textContent` rather than `innerHTML`;
- no `http://`, `https://`, CDN, analytics, external fonts/scripts/images;
- no `HALT`, `KILL`, `POST`, `PUT`, `PATCH`, `DELETE` control code.

- [ ] **Step 2: Run RED**

- [ ] **Step 3: Implement the dependency-free page**

Use inline CSS for responsive cards/table/detail drawer and inline same-origin JS polling. Display explicit `UNAVAILABLE`/source-error codes. Presentation helpers may format timestamps/currency/percentages but must not calculate expectancy, PF, drawdown, costs, or proof gates.

- [ ] **Step 4: Run Task 5 tests + full gates**

- [ ] **Step 5: Commit Task 5 GREEN**

Commit message: `feat: add responsive operator dashboard page`.

---

### Task 6: Authority firewall and systemd production service

**Files:**
- Create: `python/tests/test_g5_dashboard_authority.py`
- Create: `crates/shreks-observer/tests/g5_dashboard_systemd.rs`
- Create: `deploy/systemd/shreks-dashboard.service`
- Modify: `deploy/systemd/README.md`

**Interfaces:**
- No new Python authority interface.
- Systemd unit runs `python -m shreks_brain.dashboard.runtime` independently.

- [ ] **Step 1: Write combined RED tests**

Python authority test must prove:

- dashboard package exports contain no mutation/control functions;
- source tree does not import live executor, transaction construction, signer/submission, wallet-secret modules, registry mutation, promotion mutation, or risk mutation APIs;
- no HTTP mutation route exists;
- no filesystem write call exists under `shreks_brain/dashboard`.

Rust systemd test must require:

- `deploy/systemd/shreks-dashboard.service` exists;
- `User=shreks`, `Group=shreks`;
- `EnvironmentFile=/etc/shreks/shreks.env`;
- loopback-safe hardening and no writable runtime path;
- `Restart=on-failure` and bounded restart settings;
- service is **not** wanted/required by `shreks.target`;
- service command is exact dashboard module runtime;
- no live/wallet/signing/submission/control command appears.

- [ ] **Step 2: Run RED**

Run Python authority test and Rust systemd test. Expected failures are only the missing G5 service/authority implementation assertions.

- [ ] **Step 3: Implement service and runbook**

Runbook must document:

- install `/etc/shreks/dashboard-password` separately as protected host secret (example `root:shreks 0640`);
- dashboard listener is loopback only;
- do not expose its plain HTTP port to the public Internet;
- use a same-host TLS reverse proxy or authenticated private overlay/tunnel for phone/remote access;
- enable dashboard separately from `shreks.target`;
- dashboard failure cannot stop PAPER runtime;
- no controls until G7;
- `LIVE TRADING: DISABLED` remains explicit.

- [ ] **Step 4: Run Task 6 tests + full gates**

Require full Python, Rust/workspace, repository safety GREEN.

- [ ] **Step 5: Commit Task 6 GREEN / freeze behavior**

This commit becomes the frozen G5 behavior SHA if the final audit finds no defect.

---

## Final audit and seal

- [ ] Compare sealed G4 `e59ff100...` -> frozen G5 behavior.
- [ ] Record commit/file geometry and inspect every changed file.
- [ ] Confirm no provider/storage schema/strategy/scoring/risk/execution/ledger/accounting/checkpoint/proof/promotion/live mutation drift.
- [ ] Confirm dashboard package performs no persistent write.
- [ ] Confirm all HTTP application routes require auth and all mutation verbs return `405`.
- [ ] Confirm password values cannot enter output/logs and repository safety is GREEN.
- [ ] Confirm dashboard remains independent of `shreks.target`.
- [ ] Replace this plan with a verification record in one docs-only commit.
- [ ] Prove behavior -> seal is exactly 1 commit / 1 file.
- [ ] Run exact-seal CI and require the same full Python cardinality as frozen behavior plus Rust/workspace and repository safety GREEN.
- [ ] Update draft PR with base/frozen/seal SHAs, CI IDs, scope proof, and remaining real-host gates.
- [ ] Keep PR draft/open/unmerged.

Profitability remains unproven until real PAPER campaign evidence satisfies sealed proof gates.

**LIVE TRADING: DISABLED.**
