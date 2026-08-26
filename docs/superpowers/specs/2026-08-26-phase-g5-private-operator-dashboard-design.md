# Phase G5 Private Operator Dashboard Design

Base: sealed G4 `e59ff10028f966f690c7f766004f30d1862e3360`.
Branch: `feat/phase-g5-private-operator-dashboard`.

**LIVE TRADING: DISABLED.**

## Goal

Build the smallest private authenticated operator dashboard that lets an operator inspect Shreks without SSH/log reading while preserving the existing authority boundaries.

The dashboard is a **read-only presentation surface** over sealed G4 telemetry plus already-persisted PAPER/E11 evidence. It does not calculate a second set of trading/profitability metrics, mutate authoritative state, promote strategies, change risk state, create intents, sign or submit transactions, or enable live trading.

## Canonical constraints

- Solana V1 only.
- Rust/Python architecture remains unchanged.
- No paid service or paid data dependency.
- G4 remains the authoritative four-layer monitoring snapshot.
- E11 / sealed PAPER evidence remains authoritative for trade economics.
- Missing historical explanation evidence is shown as unavailable; the dashboard never invents a reason.
- Secrets never enter GitHub or dashboard output.
- Dashboard failure must not stop `shreks.target`, observer, paper evidence, paper campaign, or telemetry generation.
- No emergency controls are introduced in G5; controlled halt/kill-switch mutation belongs to G7.

## Architecture choice

Use a standard-library-only Python HTTP service under `shreks_brain.dashboard`.

Reasons:

1. The repository currently has zero production Python dependencies. A small read-only dashboard does not justify FastAPI/Flask/Node or a frontend build chain.
2. Standard-library HTTP keeps the deploy/runtime surface small and auditable.
3. The UI can be a single local HTML/CSS/JS asset that polls authenticated JSON endpoints and never executes source-derived HTML.
4. Authentication can be handled with HTTP Basic credentials read from a protected host-only password file, while the service itself is restricted to loopback. Remote operator access must therefore pass through a same-host TLS reverse proxy or a private authenticated overlay/tunnel.

G5 deliberately does **not** select/provision a public DNS provider, TLS certificate service, or VPN vendor. Those are host/network deployment choices and must remain free/private-compatible. Repository behavior proves the application auth and loopback boundary; real-host exposure remains physical deployment evidence.

## Data flow

```text
G4 telemetry JSON (read-only) -----------+
                                         |
G1C PAPER runtime config/state (read-only)|
E11 evaluated trades (read-only) --------+--> dashboard source --> authenticated HTTP --> operator browser
PAPER ledger entries (read-only) --------+

Only write: none.
```

The dashboard does not regenerate the G4 snapshot. It consumes the sealed snapshot file produced by `shreks-telemetry.service`.

## Strict telemetry decoding

G4 currently has canonical encoding only. G5 adds `decode_telemetry_snapshot(payload: str | bytes) -> TelemetrySnapshot` to the existing telemetry codec.

Decoder rules:

- UTF-8 JSON only;
- exact schema version `g4-telemetry-snapshot-v1`;
- exact object keys at every level;
- exact enum/status values;
- finite numeric values only;
- typed reconstruction through existing telemetry dataclasses;
- canonical round-trip equality against `encode_telemetry_snapshot`;
- trailing newline required through canonical equality;
- no permissive unknown fields.

This is a read-only compatibility addition; no G4 metric formula or source collection behavior changes.

## Dashboard source model

Create immutable dashboard view objects that distinguish source evidence from availability state.

### Summary source

`DashboardSnapshotSource` contains:

- exact decoded `TelemetrySnapshot`;
- source file mtime/age metadata used only to label dashboard freshness;
- recent `DashboardTradeSummary` values.

No profitability metrics are derived here. The UI copies values already present in G4 telemetry.

### Trade summary

A trade summary is built from sealed `EvaluatedTrade` evidence:

- position ID;
- mint;
- candidate/strategy version;
- setup name;
- market regime;
- open/close timestamps;
- entry notional;
- turnover;
- gross PnL;
- execution friction;
- explicit cost;
- net PnL.

Canonical order is newest closed trade first, then opened time, position ID, mint.

### Trade detail

A trade detail joins one `EvaluatedTrade.position_id` to matching `PaperLedgerEntry` records from the restored PAPER state.

Persisted evidence shown where available:

- token/mint;
- setup name;
- regime;
- candidate version;
- position ID and timestamps;
- entry notional / turnover;
- gross and net PnL;
- execution friction / explicit costs;
- exact terminal ledger events including side, fill state, fill reason code, ledger reason code, quantities, notionals, costs, realized PnL deltas, and strategy/policy versions.

The following historical closed-trade evidence is **not currently guaranteed to be persisted in E11/ledger state** and therefore must be represented with explicit availability codes instead of reconstructed guesses:

- full safety assessment;
- feature vector;
- numeric score assessment;
- full entry decision object/reasons;
- full risk assessment/sizing reasons;
- raw entry quote;
- strategic exit-assessment reasons when not present in persistent ledger evidence.

`DashboardEvidenceAvailability` uses stable values such as `AVAILABLE` and `NOT_PERSISTED` so the UI can say why a field is absent.

## Source access rules

The dashboard source reuses the existing G1C runtime configuration and read-only bootstrap/load-state path.

- operational SQLite remains opened by existing read-only collectors with `mode=ro` / query-only semantics;
- E11 is loaded through existing evidence store reads;
- manifest/checkpoint are decoded/loaded only;
- ledger/evaluated trades are read from restored state;
- dashboard never runs a PAPER cycle;
- dashboard never writes a checkpoint, E11 record, database row, proof record, promotion record, or telemetry snapshot.

Required-source corruption fails the request closed with a stable unavailable response; exception text is not sent to the browser.

## Runtime configuration

Dashboard-specific environment keys are exactly:

- `SHREKS_DASHBOARD_BIND_HOST`
- `SHREKS_DASHBOARD_PORT`
- `SHREKS_DASHBOARD_USERNAME`
- `SHREKS_DASHBOARD_PASSWORD_FILE`
- `SHREKS_DASHBOARD_TELEMETRY_PATH`
- `SHREKS_DASHBOARD_MAX_TRADES`

Rules:

- unknown `SHREKS_DASHBOARD_*` keys fail closed;
- bind host must be explicit loopback: `127.0.0.1` or `::1`;
- port must be an integer within `1024..65535`;
- username is non-empty printable ASCII without `:`;
- password file must be an existing regular non-symlink file, non-empty, bounded in size, not world-readable, and not group/world-writable;
- password value is never stored in a public status object or emitted to logs;
- telemetry path must name the G4 snapshot file;
- max trades must be an explicit positive integer within `1..500`.

The existing G1C PAPER runtime environment values remain the source of observer DB, E11, and manifest paths. G5 does not create a second copy of those paths under dashboard-specific names.

## Authentication

Use HTTP Basic authentication because the service is loopback-only.

- credentials are checked on every protected request;
- username/password comparison uses `hmac.compare_digest`;
- password is loaded from the protected file at service bootstrap;
- malformed/absent credentials return `401` with `WWW-Authenticate`;
- auth failures never echo supplied credentials;
- no cookies or server-side sessions are required;
- no auth token/password appears in dashboard JSON or HTML.

Remote access must terminate TLS or an authenticated private tunnel/overlay before reaching loopback. The runbook must explicitly reject exposing the dashboard's plain HTTP listener directly to the public Internet.

## HTTP surface

All application routes require authentication.

### `GET /`

Returns the operator dashboard HTML shell.

### `GET /api/v1/snapshot`

Returns canonical JSON for the current decoded G4 snapshot plus only safe dashboard source metadata (for example source-file age). It does not add alternate financial calculations.

### `GET /api/v1/trades`

Returns the bounded recent trade summary list.

### `GET /api/v1/trades/<position_id>`

Returns one trade detail joined from persisted E11 + ledger evidence. Unknown IDs return `404`.

### Method boundary

`POST`, `PUT`, `PATCH`, and `DELETE` are not implemented and return `405`.

There are no mutation/control endpoints in G5.

## HTTP security headers

Responses include:

- `Cache-Control: no-store`;
- `Content-Security-Policy` limiting scripts/styles to same document and disallowing frames/objects;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- `X-Frame-Options: DENY`.

Source-derived values are inserted into the DOM with `textContent`, never `innerHTML`.

## UI

Single-page, dependency-free UI with:

- prominent `LIVE TRADING: DISABLED` banner;
- overall status and snapshot timestamp;
- four cards/sections: System, Trading, Money, Proof/Risk;
- explicit unavailable/degraded source codes;
- recent trades table;
- click/tap trade drill-down panel;
- automatic polling of authenticated APIs at a modest fixed UI cadence;
- responsive CSS for phone/desktop;
- no external fonts, scripts, analytics, CDN, or third-party requests.

The main layer values are copied from the G4 snapshot. Formatting (currency, percentages, timestamps) is presentation-only.

## Systemd supervision

Add `shreks-dashboard.service` as an independent service.

- user/group `shreks`;
- working directory `/opt/shreks/current`;
- Python `/opt/shreks/current/.venv/bin/python -m shreks_brain.dashboard.runtime`;
- environment file `/etc/shreks/shreks.env`;
- restart on failure with bounded restart behavior consistent with G3;
- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- no writable runtime path required;
- loopback network only;
- independent of `shreks.target` so dashboard failure cannot stop PAPER runtime;
- enabled explicitly by operator/host setup.

The password file is installed separately under `/etc/shreks/` with protected permissions and is never committed.

## Failure behavior

- missing/corrupt telemetry -> authenticated request returns `503` safe JSON/HTML state;
- corrupt required PAPER/E11 state for trade endpoints -> `503`;
- missing trade -> `404`;
- auth failure -> `401`;
- unsupported method -> `405`;
- internal exception text is not returned;
- dashboard failure does not change PAPER/risk/live state.

## Testing

Required tests:

1. strict G4 decoder accepts canonical payload and rejects malformed/non-canonical/unknown-field payloads;
2. dashboard source is read-only and joins E11 trades to ledger events deterministically;
3. unavailable historical explanation fields are explicitly `NOT_PERSISTED`;
4. config rejects unsupported dashboard env keys and unsafe bind/secret-file settings;
5. authentication accepts only exact credentials using no mutation/session state;
6. route tests cover `401`, `404`, `405`, `503`, safe headers, and JSON shapes;
7. HTML contains all four layers, live-disabled banner, responsive metadata, and no external URLs/scripts;
8. authority-firewall tests reject mutation/control/live/signing/wallet surface;
9. systemd contract proves dashboard is independent of `shreks.target` and has no write authority;
10. full Python, Rust/workspace, and repository safety gates remain GREEN.

## Scope exclusions

G5 does not add:

- emergency halt/kill-switch controls (G7);
- alert delivery (G6);
- backup/restore jobs (G8);
- live executor/signer/submission paths;
- wallet secrets;
- strategy/promotion mutation;
- paid hosting/data dependencies;
- public Internet exposure configuration;
- alternate trading/evaluation metrics.

## Seal criteria

Before sealing G5:

1. freeze behavior after all G5 tests are GREEN;
2. compare sealed G4 -> frozen G5 file-by-file;
3. verify no strategy/scoring/risk/provider/storage/execution/accounting/checkpoint/promotion/live authority drift;
4. verify dashboard source reads only and no control HTTP methods exist;
5. verify no secrets are committed or emitted;
6. replace the implementation plan with a verification record in one docs-only commit;
7. prove behavior -> seal is exactly one commit / one verification file;
8. run exact-seal CI with unchanged test cardinality;
9. update the stacked draft PR and keep it open/draft/unmerged.

Real-host browser access, TLS/private-overlay exposure, and actual operator login remain physical deployment proof and are not claimed from repository CI alone.
