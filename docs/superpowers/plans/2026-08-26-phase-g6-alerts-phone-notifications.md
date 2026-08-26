# Phase G6 Alerts and Phone Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reliable outbound phone alerts over sealed telemetry/PAPER evidence with durable dedup/retry state and no trading/control authority.

**Architecture:** Add a standard-library-only `shreks_brain.alerts` package. An independent systemd oneshot+timer cycle collects read-only telemetry, provider, PAPER-ledger, and core-service health facts; derives stable alert events; durably queues them in alert-only state; and sends pending events through an outbound-only Telegram `sendMessage` adapter. No inbound Telegram updates or trading/risk mutations exist.

**Tech Stack:** Python 3.12 standard library (`json`, `sqlite3`, `subprocess`, `urllib.request`, filesystem primitives), existing Shreks telemetry/PAPER modules, pytest, Rust systemd contract tests, systemd.

**Spec:** `docs/superpowers/specs/2026-08-26-phase-g6-alerts-phone-notifications-design.md`

## Global Constraints

- Base exactly on sealed G5 `a5961c293b4a22ce17ae1033f7d39cc014c7e59f`.
- LIVE TRADING remains disabled.
- No new production Python dependency.
- Telegram is outbound `sendMessage` only; no incoming updates/webhooks/commands/buttons.
- No transaction, signing, wallet, live, promotion, registry, risk, or PAPER-cycle authority.
- No invented financial/proof/risk calculations.
- Provider names/failure counts come from the existing read-only `provider_health` table.
- Alert state under `/var/lib/shreks/alerts` is the only G6 persistent write path.
- Existing `SHREKS_PAPER_CAMPAIGN_*` paths remain authoritative and are reused.
- Secrets never enter GitHub, alert state, messages, logs, or exception text.
- G6 service/timer remain independent of `shreks.target`.

---

## File map

Create:

- `python/src/shreks_brain/alerts/__init__.py` — narrow public event/config interfaces only.
- `python/src/shreks_brain/alerts/models.py` — immutable alert/event/source/state models and enums.
- `python/src/shreks_brain/alerts/state.py` — strict canonical state codec + atomic alert-state persistence.
- `python/src/shreks_brain/alerts/config.py` — strict runtime config and protected Telegram token-file loader.
- `python/src/shreks_brain/alerts/source.py` — read-only telemetry/provider/PAPER/systemd fact collection.
- `python/src/shreks_brain/alerts/detector.py` — transition/dedup event derivation only.
- `python/src/shreks_brain/alerts/telegram.py` — outbound HTTPS `sendMessage` adapter only.
- `python/src/shreks_brain/alerts/runtime.py` — one bounded G6 cycle + CLI.
- `python/tests/test_g6_alert_models_state.py`
- `python/tests/test_g6_alert_config.py`
- `python/tests/test_g6_alert_source.py`
- `python/tests/test_g6_alert_detector.py`
- `python/tests/test_g6_telegram.py`
- `python/tests/test_g6_alert_runtime.py`
- `python/tests/test_g6_alert_authority.py`
- `crates/shreks-observer/tests/g6_alerts_systemd.rs`
- `deploy/systemd/shreks-alerts.service`
- `deploy/systemd/shreks-alerts.timer`

Modify:

- `.env.example` — add G6 non-secret operational keys only.
- `deploy/systemd/README.md` — G6 Telegram secret, enablement, retry, and no-control runbook.
- `docs/superpowers/plans/2026-08-26-phase-g6-alerts-phone-notifications.md` — replaced by final verification record at seal.

---

### Task 1: Immutable alert models and durable state codec

**Files:**
- Create: `python/src/shreks_brain/alerts/models.py`
- Create: `python/src/shreks_brain/alerts/state.py`
- Create: `python/src/shreks_brain/alerts/__init__.py`
- Create: `python/tests/test_g6_alert_models_state.py`

**Interfaces:**

Produce:

```python
class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class AlertCode(StrEnum):
    CORE_RUNTIME_STOPPED = "CORE_RUNTIME_STOPPED"
    SYSTEMD_HEALTH_UNAVAILABLE = "SYSTEMD_HEALTH_UNAVAILABLE"
    TELEMETRY_SOURCE_UNAVAILABLE = "TELEMETRY_SOURCE_UNAVAILABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    PROVIDER_FAILURE_PERSISTENT = "PROVIDER_FAILURE_PERSISTENT"
    CHECKPOINT_UNAVAILABLE = "CHECKPOINT_UNAVAILABLE"
    PAPER_SOURCE_UNAVAILABLE = "PAPER_SOURCE_UNAVAILABLE"
    ACCOUNTING_NOT_RECONCILED = "ACCOUNTING_NOT_RECONCILED"
    GLOBAL_RISK_HALT_ACTIVE = "GLOBAL_RISK_HALT_ACTIVE"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXECUTION_DEGRADED = "EXECUTION_DEGRADED"
    PAPER_PROOF_SUFFICIENT = "PAPER_PROOF_SUFFICIENT"
    CHALLENGER_PROOF_FAILED = "CHALLENGER_PROOF_FAILED"
    ALERTING_STARTED = "ALERTING_STARTED"

@dataclass(frozen=True, slots=True)
class AlertEvent:
    event_id: str
    code: AlertCode
    severity: AlertSeverity
    observed_at_unix_ms: int
    title: str
    lines: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class AlertState:
    schema_version: str
    initialized: bool
    highest_ledger_sequence: int
    last_proof_decision: str | None
    active_condition_keys: tuple[str, ...]
    pending_events: tuple[AlertEvent, ...]
    last_observed_at_unix_ms: int | None
```

State schema constant: `G6_ALERT_STATE_SCHEMA_VERSION = "g6-alert-state-v1"`.

State functions:

```python
def encode_alert_state(state: AlertState) -> bytes: ...
def decode_alert_state(payload: bytes | str) -> AlertState: ...
def load_alert_state(path: Path) -> AlertState | None: ...
def write_alert_state(path: Path, state: AlertState) -> None: ...
```

- [ ] **Step 1: Write RED model/codec tests**

Require exact enum values, frozen/slot dataclasses, non-empty bounded strings, unique pending `event_id` values, sorted/unique `active_condition_keys`, non-negative timestamps/sequences, exact schema version, canonical UTF-8 JSON with trailing newline, exact-key rejection, unknown enum rejection, non-canonical whitespace rejection, non-finite rejection, and state round trip.

Also require `load_alert_state(missing_path) is None`, corrupt existing state raises a stable state error, and no decoder silently repairs invalid state.

- [ ] **Step 2: Write RED atomic-persistence tests**

Patch `os.replace`/`os.fsync` where needed and require:

- same-directory temporary file;
- mode `0600`;
- flush/fsync before replace;
- no final-file mutation if encode/write fails;
- temporary cleanup on failure;
- state payload contains no token-like field names.

- [ ] **Step 3: Run RED**

Run:

```sh
python -m pytest python/tests/test_g6_alert_models_state.py -q
```

Expected: missing `shreks_brain.alerts`.

- [ ] **Step 4: Implement minimal models/state layer**

Keep validation helpers private. The state module is the only G6 package module allowed to perform filesystem writes.

- [ ] **Step 5: Run Task 1 + full Python gates**

```sh
python -m pytest python/tests/test_g6_alert_models_state.py -q
python -m pytest python/tests -q
```

- [ ] **Step 6: Commit Task 1 GREEN**

Commit message: `feat: add durable G6 alert state`.

---

### Task 2: Strict G6 runtime config and protected Telegram secret

**Files:**
- Create: `python/src/shreks_brain/alerts/config.py`
- Create: `python/tests/test_g6_alert_config.py`
- Modify: `python/src/shreks_brain/alerts/__init__.py`
- Modify: `.env.example`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class AlertRuntimeConfig:
    telemetry_path: Path
    state_path: Path
    telegram_chat_id: str
    telegram_bot_token_file: Path
    market_stale_ms: int
    provider_failure_min_consecutive: int
    paper_runtime_config: ObserverPaperCampaignRuntimeConfig

class AlertRuntimeConfigError(ValueError): ...

def load_alert_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    base_directory: str | os.PathLike[str] | None = None,
) -> AlertRuntimeConfig: ...

def load_telegram_bot_token(config: AlertRuntimeConfig) -> bytes: ...
```

Allowed G6 keys exactly:

```text
SHREKS_ALERTS_TELEGRAM_CHAT_ID
SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE
SHREKS_ALERTS_STATE_PATH
SHREKS_ALERTS_MARKET_STALE_MS
SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE
SHREKS_ALERTS_TELEMETRY_PATH
```

- [ ] **Step 1: Write RED config tests**

Require:

- unknown `SHREKS_ALERTS_*` key rejection;
- telemetry/state/token paths resolve deterministically;
- state path names a file and parent path is explicit;
- chat ID non-empty, bounded, no ASCII control characters;
- stale threshold canonical integer `>= 1`;
- provider consecutive threshold canonical integer `>= 1`;
- token file missing/symlink/directory/empty/oversized/world-readable/group-or-world-writable rejection;
- one optional trailing CRLF stripped from token;
- embedded newline rejected;
- config dataclass has no token value/provider API keys/wallet secrets;
- existing PAPER runtime config is reused.

- [ ] **Step 2: Run RED**

```sh
python -m pytest python/tests/test_g6_alert_config.py -q
```

Expected: missing `alerts.config`.

- [ ] **Step 3: Implement minimal config/token loader**

Token maximum size: `4096` bytes. Require exact file permissions no weaker than the G5 protected-secret rules.

`.env.example` adds non-secret G6 keys and only the token-file path, never a token value.

- [ ] **Step 4: Run Task 2 + full Python gates**

- [ ] **Step 5: Commit Task 2 GREEN**

Commit message: `feat: add G6 alert runtime configuration`.

---

### Task 3: Read-only telemetry/provider/PAPER/systemd source

**Files:**
- Create: `python/src/shreks_brain/alerts/source.py`
- Create: `python/tests/test_g6_alert_source.py`
- Modify: `python/src/shreks_brain/alerts/models.py`
- Modify: `python/src/shreks_brain/alerts/__init__.py`

**Interfaces:**

Add immutable source models:

```python
@dataclass(frozen=True, slots=True)
class AlertProviderHealth:
    provider: str
    status: str
    observed_at_unix_ms: int
    consecutive_failures: int

@dataclass(frozen=True, slots=True)
class AlertSystemdHealth:
    active_units: tuple[str, ...]
    inactive_units: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class AlertSourceSnapshot:
    observed_at_unix_ms: int
    telemetry: TelemetrySnapshot | None
    telemetry_error_code: str | None
    providers: tuple[AlertProviderHealth, ...]
    paper_ledger_entries: tuple[PaperLedgerEntry, ...] | None
    paper_error_code: str | None
    systemd: AlertSystemdHealth | None
    systemd_error_code: str | None
```

Source function:

```python
def collect_alert_source(
    config: AlertRuntimeConfig,
    *,
    observed_at_unix_ms: int,
    systemctl_runner: Callable[[tuple[str, ...]], tuple[int, str]] | None = None,
) -> AlertSourceSnapshot: ...
```

Required core units:

```text
shreks.target
shreks-observe.service
shreks-paper-evidence.service
shreks-paper-campaign.service
shreks-telemetry.timer
```

- [ ] **Step 1: Write RED telemetry/PAPER tests**

Require canonical telemetry decode, read-only PAPER bootstrap, ledger tuple copied without mutation, source failure represented only by stable error code, and source collection never calls `run_cycle` or a store write API.

- [ ] **Step 2: Write RED provider-SQL tests**

Seed `provider_health(provider,status,observed_at_unix_ms,latency_ms,detail,consecutive_failures)` and require lexical provider ordering, exact persisted status/failure count, `mode=ro`, `PRAGMA query_only=ON`, and unchanged DB bytes/mtime after collection.

- [ ] **Step 3: Write RED systemd tests**

Inject a fake runner. Require exact `systemctl is-active <unit>` reads only, active/inactive classification, and stable unavailable code on command/response failure. Assert no `start`, `stop`, `restart`, `enable`, `disable`, `reset-failed`, or `daemon-reload` argument can be generated.

- [ ] **Step 4: Run RED**

```sh
python -m pytest python/tests/test_g6_alert_source.py -q
```

- [ ] **Step 5: Implement minimal read-only source layer**

Use SQLite URI `?mode=ro` + query-only. Default systemd runner uses `subprocess.run(..., check=False, capture_output=True, text=True, timeout=5)` with absolute `/usr/bin/systemctl` and no shell.

- [ ] **Step 6: Run Task 3 + full gates**

- [ ] **Step 7: Commit Task 3 GREEN**

Commit message: `feat: collect read-only G6 alert sources`.

---

### Task 4: Alert detector, transition rules, and first-run suppression

**Files:**
- Create: `python/src/shreks_brain/alerts/detector.py`
- Create: `python/tests/test_g6_alert_detector.py`
- Modify: `python/src/shreks_brain/alerts/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class AlertDetectionResult:
    state: AlertState
    queued_event_ids: tuple[str, ...]


def detect_alert_events(
    config: AlertRuntimeConfig,
    previous: AlertState | None,
    source: AlertSourceSnapshot,
) -> AlertDetectionResult: ...
```

Stable condition keys are strings such as:

```text
CORE_RUNTIME_STOPPED
SYSTEMD_HEALTH_UNAVAILABLE
TELEMETRY_SOURCE_UNAVAILABLE
MARKET_DATA_STALE
PROVIDER_FAILURE_PERSISTENT:<provider>
CHECKPOINT_UNAVAILABLE
PAPER_SOURCE_UNAVAILABLE
ACCOUNTING_NOT_RECONCILED
GLOBAL_RISK_HALT_ACTIVE
KILL_SWITCH_ACTIVE
```

Ledger event IDs use persisted sequence, for example `ledger:42:POSITION_CLOSED`.
Proof transition IDs include the authoritative telemetry generation timestamp and decision, for example `proof:1712345678901:SUFFICIENT`.

- [ ] **Step 1: Write RED first-run tests**

When `previous is None`:

- set highest ledger sequence to current maximum;
- do not queue historical position/execution events;
- baseline current proof decision;
- queue `ALERTING_STARTED`;
- still queue current CRITICAL conditions (core stopped, accounting unreconciled, global risk halt, kill switch);
- do not mark a queued critical condition active until it exists durably in the returned state/pending queue.

- [ ] **Step 2: Write RED condition-transition tests**

Require one event on inactive→active transition and no repeat while active for:

- stopped core unit(s);
- telemetry unavailable;
- stale market age `> market_stale_ms`;
- provider `status != healthy` with `consecutive_failures >= threshold`;
- checkpoint missing;
- PAPER source unavailable;
- accounting not reconciled;
- global risk halt true;
- kill switch true.

When a condition clears, remove its active key so a later reactivation can alert again. Recovery messages are not required.

- [ ] **Step 3: Write RED ledger-event tests**

For ledger sequences above `highest_ledger_sequence`:

- `POSITION_OPENED` / `POSITION_INCREASED` -> `POSITION_OPENED` INFO;
- `POSITION_CLOSED` -> `POSITION_CLOSED` INFO with exact `realized_pnl_delta_usd` text;
- `SLIPPAGE_EXCEEDS_INTENT`, terminal `PARTIAL`, or terminal failed execution -> `EXECUTION_DEGRADED` WARNING;
- no alternate PnL/slippage formula appears.

Advance the cursor to the highest observed sequence while queuing each stable event exactly once.

- [ ] **Step 4: Write RED proof-transition tests**

Require:

- non-`SUFFICIENT` -> `SUFFICIENT` queues `PAPER_PROOF_SUFFICIENT`;
- non-`FAILED` -> `FAILED` queues `CHALLENGER_PROOF_FAILED`;
- unchanged decision queues nothing;
- missing proof decision does not invent one.

- [ ] **Step 5: Run RED**

```sh
python -m pytest python/tests/test_g6_alert_detector.py -q
```

- [ ] **Step 6: Implement minimal detector**

All event text must be bounded, plain, and include `LIVE TRADING: DISABLED`. Internal exception text never enters events.

- [ ] **Step 7: Run Task 4 + full gates**

- [ ] **Step 8: Commit Task 4 GREEN**

Commit message: `feat: detect G6 critical alert transitions`.

---

### Task 5: Outbound-only Telegram sender and durable runtime queue

**Files:**
- Create: `python/src/shreks_brain/alerts/telegram.py`
- Create: `python/src/shreks_brain/alerts/runtime.py`
- Create: `python/tests/test_g6_telegram.py`
- Create: `python/tests/test_g6_alert_runtime.py`

**Interfaces:**

```python
class TelegramAlertError(RuntimeError): ...

def format_alert_message(event: AlertEvent) -> str: ...

def send_telegram_alert(
    *,
    chat_id: str,
    bot_token: bytes,
    event: AlertEvent,
    opener: Callable[..., object] | None = None,
    timeout_seconds: float = 10.0,
) -> None: ...

class AlertRuntimeError(RuntimeError): ...

def run_alert_cycle(
    config: AlertRuntimeConfig,
    *,
    observed_at_unix_ms: int | None = None,
    source_loader=collect_alert_source,
    sender=send_telegram_alert,
) -> int: ...
```

CLI: `python -m shreks_brain.alerts.runtime`.

- [ ] **Step 1: Write RED Telegram request tests**

With a mocked opener require:

- HTTPS URL host is exactly `api.telegram.org`;
- path is `/bot<TOKEN>/sendMessage`;
- POST JSON contains exactly `chat_id` and `text`;
- `Content-Type: application/json`;
- bounded timeout;
- response must be JSON object with exact boolean `ok` true;
- HTTP/network/JSON/`ok=false` errors raise generic `TelegramAlertError`;
- exception string never contains token, full token URL, chat ID, or response body;
- no `getUpdates`, webhook, callback, reply markup, or command path exists.

- [ ] **Step 2: Write RED message-format tests**

Require deterministic plain text beginning `SHREKS [SEVERITY] CODE`, bounded below Telegram's text limit, no parse mode, and `LIVE TRADING: DISABLED` present.

- [ ] **Step 3: Write RED runtime queue/retry tests**

Cycle order must be:

1. load state;
2. collect source;
3. detect/queue;
4. write updated state **before any send**;
5. send first pending event;
6. on success remove only that event and write state;
7. continue;
8. on failure retain failed + later events and return/raise non-zero failure.

Use a sender that succeeds for event 1 and fails event 2; reload the state and prove event 1 is absent while event 2+ remain. Next successful cycle must not resend event 1.

- [ ] **Step 4: Run RED**

```sh
python -m pytest python/tests/test_g6_telegram.py python/tests/test_g6_alert_runtime.py -q
```

- [ ] **Step 5: Implement minimal sender/runtime**

Do not implement internal network retries. Timer cycles own retry cadence.

- [ ] **Step 6: Run Task 5 + full gates**

- [ ] **Step 7: Commit Task 5 GREEN**

Commit message: `feat: send durable Telegram alert queue`.

---

### Task 6: Authority firewall, systemd production units, and runbook

**Files:**
- Create: `python/tests/test_g6_alert_authority.py`
- Create: `crates/shreks-observer/tests/g6_alerts_systemd.rs`
- Create: `deploy/systemd/shreks-alerts.service`
- Create: `deploy/systemd/shreks-alerts.timer`
- Modify: `deploy/systemd/README.md`

**Interfaces:**
- No new trading authority interface.
- systemd service runs `python -m shreks_brain.alerts.runtime`.

- [ ] **Step 1: Write RED Python authority tests**

AST/source checks require:

- package exports contain no trade/control mutation verbs;
- no import of live executor, transaction builder, signer/submission, wallet secret, registry mutation, promotion mutation, or risk mutation APIs;
- no `run_cycle` call under alerts;
- no incoming HTTP server/socket listener;
- no Telegram `getUpdates`, webhook, callback-query, or command handler;
- filesystem write calls under alerts appear only in `state.py`;
- `subprocess` use appears only in `source.py` and generated command is read-only systemctl inspection.

- [ ] **Step 2: Write RED Rust systemd tests**

Require `shreks-alerts.service`:

```text
Description=Shreks outbound alert notifications
After=network-online.target
Wants=network-online.target
User=shreks
Group=shreks
WorkingDirectory=/opt/shreks/current
EnvironmentFile=/etc/shreks/shreks.env
Environment=PYTHONDONTWRITEBYTECODE=1
RequiresMountsFor=/var/lib/shreks /etc/shreks /opt/shreks/current
ExecStartPre=/usr/bin/test -r /etc/shreks/telegram-bot-token
ExecStartPre=/usr/bin/test -d /var/lib/shreks/alerts
ExecStartPre=/usr/bin/test -w /var/lib/shreks/alerts
ExecStart=/opt/shreks/current/.venv/bin/python -m shreks_brain.alerts.runtime
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/shreks/alerts
UMask=0077
```

Forbid:

```text
PartOf=shreks.target
WantedBy=shreks.target
Requires=shreks.target
SHREKS_MODE=live
--live
submit_transaction
sign_transaction
wallet-command
getUpdates
setWebhook
```

Require `shreks-alerts.timer`:

```text
Unit=shreks-alerts.service
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=5s
Persistent=true
WantedBy=timers.target
```

Also prove `shreks.target` does not mention alert units.

- [ ] **Step 3: Write RED runbook assertions**

Require documentation for:

- separate `/etc/shreks/telegram-bot-token` installation as `root:shreks 0640`;
- bot token never stored in env/GitHub;
- Telegram is outbound notifications only;
- no commands/trading control through Telegram;
- install/enable timer independently of `shreks.target`;
- alert-state path and retry behavior;
- `systemctl status shreks-alerts.timer` / `journalctl -u shreks-alerts.service`;
- alert failure cannot stop PAPER runtime;
- `LIVE TRADING: DISABLED`.

- [ ] **Step 4: Run RED**

Run authority test and targeted Rust test; expected Rust failure is only absent G6 units/runbook entries.

- [ ] **Step 5: Implement units/runbook**

Do not add alert units to `shreks.target` or the G2 core release health contract.

- [ ] **Step 6: Run Task 6 + full gates**

```sh
python -m pytest python/tests -q
cargo test --workspace
```

Repository safety must remain GREEN in CI.

- [ ] **Step 7: Commit Task 6 GREEN / freeze behavior**

This commit becomes the frozen G6 behavior SHA if the final audit finds no defect.

---

## Final audit and seal

- [ ] Compare sealed G5 `a5961c293b4a22ce17ae1033f7d39cc014c7e59f` -> frozen G6 behavior.
- [ ] Record commit/file geometry and inspect every changed file.
- [ ] Confirm no provider mutation, storage/schema migration, strategy/scoring/risk/execution/ledger/accounting/checkpoint/proof/promotion/live mutation drift.
- [ ] Confirm alerts read provider/PAPER/systemd evidence only and write only alert state.
- [ ] Confirm Telegram is outbound-only and has no command/control path.
- [ ] Confirm secret token values cannot enter state, repo, messages, logs, or exception text.
- [ ] Confirm partial-send retry semantics do not lose or duplicate acknowledged events.
- [ ] Confirm alert units remain independent of `shreks.target`.
- [ ] Replace this plan with a verification record in one docs-only commit.
- [ ] Prove behavior -> seal is exactly 1 commit / 1 file.
- [ ] Run exact-seal CI and require identical full Python cardinality to frozen behavior plus Rust/workspace and repository safety GREEN.
- [ ] Update stacked draft PR with base/frozen/seal SHAs, CI IDs, scope proof, known evidence gaps, and remaining real-host Telegram delivery proof.
- [ ] Keep PR draft/open/unmerged.

Real phone delivery is not proven until a host-owned bot token/chat target are configured and a message is observed on the operator's phone.

Profitability remains unproven until real PAPER campaign evidence satisfies sealed proof gates.

**LIVE TRADING: DISABLED.**