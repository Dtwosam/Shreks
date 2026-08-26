# Phase G6 Alerts and Phone Notifications Design

Base: sealed G5 `a5961c293b4a22ce17ae1033f7d39cc014c7e59f`.
Branch: `feat/phase-g6-alerts-phone-notifications`.

**LIVE TRADING: DISABLED.**

## Goal

Add reliable outbound critical alerts so the operator does not need to watch the G5 dashboard continuously. G6 must notify the operator about meaningful runtime, provider, data-freshness, accounting, risk, proof, and PAPER position events while preserving every existing trading authority boundary.

G6 is an **observation and notification subsystem**. It must not create trades, change risk state, promote a strategy, mutate PAPER evidence, enable live trading, or accept commands from Telegram or any other notification transport.

## Source-of-truth requirements

The project build order requires alerts for at least:

- Shreks stopped running;
- stale market data;
- persistent Helius/Jupiter/required-provider failure;
- database/checkpoint problems;
- accounting reconciliation failure;
- kill-switch activation;
- daily-loss or drawdown halt activation;
- PAPER/live position open;
- position close with PnL;
- unusually bad fill/slippage behavior;
- paper proof becoming sufficient;
- challenger proof failure;
- eventually, live-money transactions.

Telegram is the first transport. This does **not** make Telegram a trading/control surface.

## Architecture choice

Use a standard-library-only Python alert package plus an independent systemd **oneshot service + timer**.

```text
                          read only
G4 telemetry snapshot -------------------+
PAPER runtime / ledger ------------------+|
provider_health SQLite -----------------+||
systemd core service state ------------+|||
                                        vvvv
                               +------------------+
                               | G6 alert source  |
                               +--------+---------+
                                        |
                               normalized facts
                                        |
                                        v
                               +------------------+
                               | alert detector   |
                               | transition logic |
                               +--------+---------+
                                        |
                                  pending events
                                        |
                                        v
                          +---------------------------+
                          | alert-only durable state  |
                          | /var/lib/shreks/alerts/   |
                          +-------------+-------------+
                                        |
                                  retry queue
                                        |
                                        v
                               +------------------+
                               | Telegram sender  |
                               | outbound HTTPS   |
                               +------------------+
```

A timer-driven oneshot process is preferred over a permanent bot daemon because:

1. it follows the existing G4 telemetry supervision pattern;
2. every run is bounded and easy to audit;
3. systemd owns retry/restart scheduling;
4. there is no inbound listener or command loop;
5. the service can remain independent from `shreks.target`, so it can report a core runtime outage.

## Telegram transport

The current Telegram Bot API remains an HTTPS API and supports `sendMessage` with a bot token and target `chat_id`. G6 uses only outbound `sendMessage` requests.

G6 must never call or implement:

- `getUpdates`;
- webhook setup;
- inbound command handlers;
- callback queries;
- inline control buttons;
- trade/risk/promotion commands.

The bot token is a host-only secret file. It is never placed in `.env.example`, GitHub, logs, alert state, exception text, or notification bodies.

### Telegram secret/config split

Host-only secret:

- `/etc/shreks/telegram-bot-token`

Non-secret operator target/config values may live in `/etc/shreks/shreks.env`:

- `SHREKS_ALERTS_TELEGRAM_CHAT_ID`
- `SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE`
- `SHREKS_ALERTS_STATE_PATH`
- `SHREKS_ALERTS_MARKET_STALE_MS`
- `SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE`
- `SHREKS_ALERTS_TELEMETRY_PATH`

Existing `SHREKS_PAPER_CAMPAIGN_*` values remain authoritative for the PAPER database/E11/manifest paths. G6 must reuse the existing runtime config instead of duplicating those paths under `SHREKS_ALERTS_*`.

## Read-only alert source

Create a G6 source layer that collects one immutable observation.

### Telemetry

Read the sealed G4/G5 telemetry file through `decode_telemetry_snapshot`. Corrupt, missing, non-canonical, or unsupported telemetry is a source failure, not something G6 repairs.

The telemetry snapshot provides authoritative states including:

- system/accounting status;
- market age;
- proof decision;
- promotion decision;
- global risk halt;
- kill-switch state when the authoritative runtime begins persisting it;
- live state;
- PAPER performance metrics.

G6 must not recompute proof or financial metrics.

### Provider health

Read `provider_health` directly from the existing observer SQLite database in `mode=ro` with `PRAGMA query_only=ON`.

For each provider, read only persisted fields already owned by the observer schema:

- provider name;
- status;
- observed timestamp;
- detail;
- consecutive failure count.

This lets G6 name Helius/Jupiter/other required providers without changing G4 telemetry schema or provider code.

The alert threshold uses `SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE` only to decide when a notification is worth sending. It does not change provider health, trading eligibility, or risk behavior.

### PAPER state and ledger

Use `bootstrap_observer_paper_campaign_runtime` as a restore/read path only. Do not run a PAPER cycle.

Read:

- restored ledger entries;
- positions;
- manifest/global risk halt;
- existing E11 evaluated trades when needed for a closed-trade summary.

No checkpoint, E11, manifest, database, proof, promotion, or ledger mutation is permitted.

### Core runtime health

The G6 service is independent from `shreks.target` and performs read-only systemd checks for:

- `shreks.target`;
- `shreks-observe.service`;
- `shreks-paper-evidence.service`;
- `shreks-paper-campaign.service`;
- `shreks-telemetry.timer`.

A unit is healthy only when `systemctl is-active` reports `active`. Command failure or an unknown response is treated as unavailable evidence and produces a safe operational alert rather than assuming health.

The alert service never starts, stops, restarts, enables, disables, or resets any unit.

## Alert event model

Use immutable events with stable codes and stable event IDs.

### Severity

- `INFO`
- `WARNING`
- `CRITICAL`

### G6 alert codes

Initial codes:

- `CORE_RUNTIME_STOPPED`
- `SYSTEMD_HEALTH_UNAVAILABLE`
- `TELEMETRY_SOURCE_UNAVAILABLE`
- `MARKET_DATA_STALE`
- `PROVIDER_FAILURE_PERSISTENT`
- `CHECKPOINT_UNAVAILABLE`
- `PAPER_SOURCE_UNAVAILABLE`
- `ACCOUNTING_NOT_RECONCILED`
- `GLOBAL_RISK_HALT_ACTIVE`
- `KILL_SWITCH_ACTIVE`
- `POSITION_OPENED`
- `POSITION_CLOSED`
- `EXECUTION_DEGRADED`
- `PAPER_PROOF_SUFFICIENT`
- `CHALLENGER_PROOF_FAILED`
- `ALERTING_STARTED`

Live-money transaction alerts are intentionally not fabricated in G6 because no sealed live execution path exists yet. The event code may be reserved only when a future live authority produces durable transaction evidence.

## Alert-condition rules

### Shreks stopped running

Emit `CORE_RUNTIME_STOPPED` when `shreks.target` or any required core PAPER child is not active.

The event body includes the inactive unit names only. It does not attempt remediation.

### Market data stale

Emit `MARKET_DATA_STALE` when authoritative telemetry has a finite `market_age_ms` greater than the explicit `SHREKS_ALERTS_MARKET_STALE_MS` notification threshold.

If the market observation is absent entirely, treat it as a source/data availability problem and alert rather than inventing an age.

This threshold is notification policy only. It does not authorize or block trades.

### Persistent provider failure

Emit `PROVIDER_FAILURE_PERSISTENT` for a provider whose persisted status is not `healthy` and whose persisted `consecutive_failures` is at least `SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE`.

The provider name and failure count may appear in the notification. Provider secret material and raw unbounded detail text must not be sent.

### Database/checkpoint problems

Emit:

- `PAPER_SOURCE_UNAVAILABLE` if the required read-only PAPER bootstrap cannot be trusted;
- `CHECKPOINT_UNAVAILABLE` when telemetry reports the ingestion checkpoint missing;
- `TELEMETRY_SOURCE_UNAVAILABLE` when the canonical telemetry file itself cannot be read/decoded.

The operator receives stable error codes, not internal exception text.

### Accounting reconciliation

Emit `ACCOUNTING_NOT_RECONCILED` when telemetry/accounting evidence says anything other than the sealed reconciled/valid state.

### Risk halt and kill switch

Emit `GLOBAL_RISK_HALT_ACTIVE` on the transition from inactive to active.

Emit `KILL_SWITCH_ACTIVE` when the authoritative telemetry field becomes `True`.

Current sealed PAPER evidence exposes a global risk-halt boolean but does not persist a cause-specific daily-loss/drawdown halt reason. G6 must not infer that cause from PnL. When a later sealed risk authority persists the cause, G6 may add cause-specific messages without changing risk logic.

### Position opened

Emit `POSITION_OPENED` for new persisted ledger entries whose ledger reason code is `POSITION_OPENED` or `POSITION_INCREASED`.

The notification may include:

- mode (`PAPER`);
- mint;
- position ID;
- side;
- filled notional;
- booked timestamp;
- strategy/candidate version.

### Position closed

Emit `POSITION_CLOSED` for new persisted ledger entries whose ledger reason code is `POSITION_CLOSED`.

Include the exact persisted `realized_pnl_delta_usd`. Do not recompute PnL in the alert layer.

### Bad fill/slippage behavior

G6 must not invent a second fill/slippage threshold.

Emit `EXECUTION_DEGRADED` for new terminal ledger evidence with authoritative execution degradation/failure states/codes, including:

- `SLIPPAGE_EXCEEDS_INTENT`;
- `FILL_PARTIAL` / terminal `PARTIAL` outcomes;
- failed execution outcomes such as route/submission/price/notional failures.

If future persisted fill evidence exposes exact signed slippage and a sealed policy exposes an abnormal-fill threshold, G6 may include those exact values. Until then it alerts on the existing execution verdict/code.

### Proof sufficient / challenger failed

Emit on proof decision transition:

- `PAPER_PROOF_SUFFICIENT` when `proof_decision` becomes `SUFFICIENT`;
- `CHALLENGER_PROOF_FAILED` when it becomes `FAILED`.

Do not alert repeatedly for unchanged decisions.

## Durable dedup and retry state

G6 needs durable alert-only state so restarts do not spam old PAPER events and transport failures do not lose notifications.

Schema: `g6-alert-state-v1`.

Persist under the configured `SHREKS_ALERTS_STATE_PATH`, expected in `/var/lib/shreks/alerts/`.

State contains only alert bookkeeping, for example:

- schema version;
- initialized flag;
- highest observed ledger sequence;
- last proof decision;
- last promotion decision if needed later;
- active condition keys;
- pending alert events in send order;
- last completed source observation timestamp.

It contains **no token, API secret, provider key, wallet key, private key, seed phrase, auth header, Telegram response body, or trading authority state**.

### Two-phase cycle

Every oneshot run follows:

1. load/validate config and host secret metadata;
2. load alert state;
3. collect read-only source facts;
4. detect new events and append them to the durable pending queue;
5. atomically persist the updated queue/cursors;
6. send pending events in order;
7. after each successful send, remove exactly that event and atomically persist state;
8. on send failure, stop and leave the failed event plus later events pending for the next timer run.

This prevents a successful earlier event from being re-sent merely because a later event failed.

### First-run behavior

When no state file exists:

- initialize the ledger cursor to the current highest ledger sequence so historical PAPER positions are not replayed as fresh phone alerts;
- initialize proof transition baselines from current telemetry;
- initialize active noncritical condition keys from current state;
- queue one `ALERTING_STARTED` event;
- still queue currently active **critical** conditions such as core runtime stopped, accounting invalid, global risk halt, or kill switch so first installation does not hide an emergency.

A corrupt existing state file fails closed. G6 must not silently replace it with a fresh state and replay/lose history.

## Event formatting

Messages are plain text, bounded to Telegram's supported text-message limit, with no HTML/Markdown parsing required.

Format begins with stable identity and severity, for example:

```text
SHREKS [CRITICAL] CORE_RUNTIME_STOPPED
PAPER runtime is not fully active.
Units: shreks-paper-campaign.service
LIVE TRADING: DISABLED
```

Rules:

- include `LIVE TRADING: DISABLED` in G6 PAPER notifications;
- no credentials or filesystem secret contents;
- no arbitrary exception text;
- no raw database rows;
- no Telegram control instructions;
- no investment/hype language;
- bounded lengths for provider detail and identifiers.

## Telegram sender safety

Implement with Python standard library `urllib.request`.

Requirements:

- HTTPS endpoint only;
- exact host `api.telegram.org`;
- JSON POST to `/bot<TOKEN>/sendMessage`;
- bounded timeout;
- `chat_id` and `text` only for v1;
- parse response JSON and require `ok == true`;
- generic failure errors that never include the token URL or response body;
- no redirects to arbitrary hosts;
- no retries inside the sender; durable retry belongs to the next G6 timer cycle.

Tests must mock the HTTP opener; CI must never call Telegram.

## Runtime configuration

`AlertRuntimeConfig` contains only operational values:

- `telemetry_path: Path`
- `state_path: Path`
- `telegram_chat_id: str`
- `telegram_bot_token_file: Path`
- `market_stale_ms: int`
- `provider_failure_min_consecutive: int`
- `paper_runtime_config: ObserverPaperCampaignRuntimeConfig`

Validation:

- unknown `SHREKS_ALERTS_*` keys fail closed;
- all paths resolve explicitly;
- state path must be under an existing/writable alerts directory at runtime;
- bot token file must be regular, non-symlink, non-empty, bounded, not world-readable, and not group/world writable;
- chat ID must be a bounded non-empty string and contain no control characters;
- market stale threshold must be a canonical positive integer;
- provider failure threshold must be a canonical positive integer;
- no token value is stored in `AlertRuntimeConfig`.

## Alert-state persistence

Use canonical JSON with exact-key decoding and atomic replacement:

- write temporary file in the same directory;
- file mode `0600`;
- `flush` + `fsync`;
- `os.replace`;
- fsync directory where supported.

Only `/var/lib/shreks/alerts` is writable to the G6 service.

## Systemd supervision

Add:

- `shreks-alerts.service` — oneshot cycle;
- `shreks-alerts.timer` — independent periodic schedule.

Service properties:

- `User=shreks`, `Group=shreks`;
- `WorkingDirectory=/opt/shreks/current`;
- `EnvironmentFile=/etc/shreks/shreks.env`;
- protected bot token preflight;
- writable path only `/var/lib/shreks/alerts`;
- read access to `/var/lib/shreks` and `/etc/shreks` as needed;
- `NoNewPrivileges=true`;
- `PrivateTmp=true`;
- `PrivateDevices=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- network families limited to UNIX/IPv4/IPv6;
- independent from `shreks.target` and the dashboard;
- no `PartOf=shreks.target` or `Requires=shreks.target`.

The timer should run at a modest cadence consistent with G4 telemetry, initially every 60 seconds, and be persistent across reboot.

G6 needs outbound HTTPS, so unlike the loopback-only G5 dashboard service it must not use a systemd IP deny rule that blocks Telegram.

## Authority firewall

Automated tests must prove the G6 package does not import or call:

- live executor;
- transaction construction;
- signer/submission;
- wallet secrets;
- strategy registry mutation;
- promotion mutation;
- risk mutation;
- PAPER cycle execution;
- trading database writes.

Filesystem writes are permitted **only** in the G6 alert-state module and only for the configured alert state path. Transport code writes only to its outbound HTTPS request stream through the standard library.

No incoming network server exists.

## Failure behavior

- missing/corrupt alert state: fail closed, send nothing, preserve file;
- missing/corrupt telemetry: queue/send a stable telemetry-source-unavailable event when state can be trusted;
- PAPER source failure: queue/send stable PAPER-source-unavailable event;
- systemd query failure: queue/send stable systemd-health-unavailable event;
- Telegram failure: retain pending event and exit non-zero so systemd records the failure;
- state write failure: send nothing new until durable queue state is written;
- one malformed event: fail closed rather than silently dropping it;
- G6 failure never stops or mutates the PAPER runtime.

## Testing

Required test families:

1. immutable event/state models and canonical state codec;
2. atomic alert-state persistence and corrupt-state refusal;
3. strict runtime config and protected token-file handling;
4. read-only source collection for telemetry, provider rows, PAPER ledger, and systemd health;
5. detector transition/dedup behavior for every currently supportable G6 condition;
6. first-run historical suppression plus current-critical alerts;
7. pending-queue retry semantics across partial Telegram failure;
8. Telegram request construction and secret-redaction behavior with mocked HTTP;
9. runtime cycle behavior with zero real network calls;
10. authority-firewall tests;
11. systemd service/timer contract tests;
12. full Python, Rust/workspace, and repository-safety gates.

## Explicit scope gaps carried forward

The source of truth asks for cause-specific daily-loss/drawdown halt alerts and eventual live-money transaction alerts.

At the sealed G5 base:

- the persisted/telemetry risk surface exposes `global_risk_halt` but not a durable cause-specific daily-loss/drawdown halt reason;
- `daily_loss_usd` and `kill_switch_active` may be unavailable in current PAPER telemetry;
- there is no legitimate sealed live executor/transaction evidence path.

G6 therefore alerts the authoritative global halt/kill-switch fields when available and does not invent the missing cause. Live transaction alerts remain explicitly deferred until live execution exists. These are evidence gaps, not permission to derive a parallel risk/live system.

## Seal criteria

Before sealing G6:

1. freeze behavior after all G6 tests are green;
2. compare sealed G5 -> frozen G6 file-by-file;
3. prove all trading/provider/storage/proof/risk/live authority paths are unchanged except read-only alert adapters;
4. prove Telegram is outbound-only and contains no command/control surface;
5. prove token values cannot enter repo, state, output, logs, or exception text;
6. prove alert state is the only G6 persistent write path;
7. prove partial-send failure preserves unsent events without duplicating already acknowledged events;
8. prove service/timer are independent of `shreks.target`;
9. replace the implementation plan with one verification record in a docs-only seal commit;
10. prove frozen behavior -> seal is exactly one commit / one file;
11. run exact-seal CI with unchanged test cardinality;
12. update the stacked draft PR and keep it open/draft/unmerged.

Real phone delivery remains physical deployment evidence and cannot be claimed from mocked repository CI.

**LIVE TRADING: DISABLED.**