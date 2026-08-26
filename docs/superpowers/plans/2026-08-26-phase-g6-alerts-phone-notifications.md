# Phase G6 Alerts and Phone Notifications Verification Record

**Phase:** G6 — Alerts and phone notifications  
**Repository:** `Dtwosam/Shreks`  
**Branch:** `feat/phase-g6-alerts-phone-notifications`  
**Stacked PR:** `#47`  
**Base:** sealed G5 `a5961c293b4a22ce17ae1033f7d39cc014c7e59f`  
**Frozen G6 behavior:** `1f9caf3e56000f0fb80612b0b2ee801f03e118a8`  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g6-alerts-phone-notifications-design.md`

**LIVE TRADING: DISABLED.**

## Verification result

G6 repository behavior is **VERIFIED** for the scoped outbound alert and phone-notification subsystem.

The implementation adds durable outbound alerts over sealed telemetry, persisted provider/PAPER evidence, and read-only systemd health. It does not add inbound Telegram commands, trading/control authority, auto-remediation, live execution, promotion mutation, risk mutation, transaction construction/signing/submission, wallet handling, or a second profitability/risk/proof engine.

This record seals repository behavior only. Real-host installation, Telegram credential provisioning, external connectivity, and receipt of an actual notification on the intended phone remain physical deployment evidence and are explicitly not claimed by repository CI.

## Base proof

G6 is stacked directly on the sealed G5 commit:

- G5 seal: `a5961c293b4a22ce17ae1033f7d39cc014c7e59f`
- G5 exact-seal CI: `32955319338`
- G5 exact-seal Python tests: **2406 passed**
- G5 exact-seal Rust/workspace: GREEN
- G5 exact-seal repository safety: GREEN

No G5 behavior was rewritten or rebased into G6.

## Frozen behavior proof

Frozen G6 behavior:

- SHA: `1f9caf3e56000f0fb80612b0b2ee801f03e118a8`
- CI: `32960623418`
- CI status: completed / success
- Python tests: **2477 passed**
- Rust/workspace: GREEN
- Repository safety: GREEN

The frozen behavior SHA is the final behavior-bearing commit. The seal commit containing this record is documentation-only.

## G5 -> frozen G6 geometry

GitHub compare from sealed G5 to frozen G6 reported:

- status: ahead
- commits: **28**
- changed files: **22**
- behind: **0**
- PR additions at freeze: **4620**
- PR deletions at freeze: **6**

Changed files inspected during the final audit:

1. `.env.example`
2. `crates/shreks-observer/tests/g6_alerts_systemd.rs`
3. `deploy/systemd/README.md`
4. `deploy/systemd/shreks-alerts.service`
5. `deploy/systemd/shreks-alerts.timer`
6. `docs/superpowers/plans/2026-08-26-phase-g6-alerts-phone-notifications.md`
7. `docs/superpowers/specs/2026-08-26-phase-g6-alerts-phone-notifications-design.md`
8. `python/src/shreks_brain/alerts/__init__.py`
9. `python/src/shreks_brain/alerts/config.py`
10. `python/src/shreks_brain/alerts/detector.py`
11. `python/src/shreks_brain/alerts/models.py`
12. `python/src/shreks_brain/alerts/runtime.py`
13. `python/src/shreks_brain/alerts/source.py`
14. `python/src/shreks_brain/alerts/state.py`
15. `python/src/shreks_brain/alerts/telegram.py`
16. `python/tests/test_g6_alert_authority.py`
17. `python/tests/test_g6_alert_config.py`
18. `python/tests/test_g6_alert_detector.py`
19. `python/tests/test_g6_alert_models_state.py`
20. `python/tests/test_g6_alert_runtime.py`
21. `python/tests/test_g6_alert_source.py`
22. `python/tests/test_g6_telegram.py`

No existing provider adapter, database/storage schema or migration, strategy, setup, scoring, risk-engine, execution, ledger, accounting, checkpoint, proof, promotion, registry, wallet, signing, submission, live-execution, or core `shreks.target` file changed.

## Verified behavior

### 1. Durable alert event/state model

G6 introduces immutable alert-only models and a strict canonical state codec.

Verified properties:

- stable `AlertCode` and `AlertSeverity` vocabularies;
- bounded printable event identifiers/titles/lines;
- canonical finite JSON with exact keys and stable ordering;
- unknown schema/fields, malformed values, non-canonical encoding, and non-finite JSON fail closed;
- missing state is treated only as first installation;
- corrupt existing state fails closed rather than silently resetting history;
- state files are written atomically through a temporary file plus replace/fsync;
- state file mode is private (`0600`);
- failed atomic replacement preserves the previous state.

The only persistent write authority added by G6 is its own alert queue/state under the configured alert-state path.

### 2. Strict operational config and secret boundary

G6-specific environment configuration is limited to:

- `SHREKS_ALERTS_TELEGRAM_CHAT_ID`
- `SHREKS_ALERTS_TELEGRAM_BOT_TOKEN_FILE`
- `SHREKS_ALERTS_STATE_PATH`
- `SHREKS_ALERTS_MARKET_STALE_MS`
- `SHREKS_ALERTS_PROVIDER_FAILURE_MIN_CONSECUTIVE`
- `SHREKS_ALERTS_TELEMETRY_PATH`

Existing `SHREKS_PAPER_CAMPAIGN_*` paths remain authoritative for PAPER evidence restore/read access.

Verified properties:

- unknown alert keys fail closed;
- integer thresholds require canonical positive values;
- configured paths resolve safely;
- Telegram chat ID is operational configuration, not a control channel;
- bot token value is never part of `AlertRuntimeConfig`;
- token is loaded only from the protected host-only file;
- token-file symlinks, directories, missing/empty/oversized/non-printable content, world-readable permissions, and unsafe group/world write permissions are rejected;
- repository `.env.example` contains only the token-file path, never a populated token.

Repository safety is GREEN.

### 3. Read-only observation sources

The G6 collector reads four independent evidence surfaces:

1. canonical G4 telemetry;
2. persisted provider health from the observer SQLite database opened read-only/query-only;
3. restored PAPER ledger entries through the existing campaign runtime bootstrap without executing a cycle;
4. core systemd health through exact `/usr/bin/systemctl is-active <unit>` calls.

Verified properties:

- telemetry is decoded through the strict canonical decoder;
- provider queries use read-only SQLite and do not repair/mutate the table;
- PAPER restore reads existing ledger state and never calls `run_cycle`;
- systemd observation never invokes start/stop/restart/enable/disable/reset-failed/daemon-reload;
- independent source failures become stable unavailable error codes rather than leaking internal exceptions or being treated as healthy;
- missing/broken provider health cannot silently become a healthy provider verdict;
- source collection does not mutate authoritative database, PAPER, telemetry, or service state.

### 4. Transition/dedup detector

G6 derives alert transitions only from authoritative persisted/read-side facts and configured notification thresholds.

Verified current condition alerts include:

- core PAPER runtime not fully active;
- systemd-health source unavailable;
- telemetry unavailable;
- market data stale relative to the explicit G6 notification threshold;
- named provider persistent failure at the explicit consecutive-failure threshold;
- ingestion/checkpoint unavailable;
- PAPER evidence unavailable;
- accounting not reconciled/valid;
- authoritative global risk halt active;
- authoritative kill-switch state active.

Verified persisted event alerts include:

- PAPER position opened/increased;
- PAPER position closed with exact persisted realized-PnL delta;
- terminal partial/failed execution and persisted `SLIPPAGE_EXCEEDS_INTENT` degradation evidence;
- PAPER proof transition to `SUFFICIENT`;
- challenger/proof transition to `FAILED`.

Important non-authority properties:

- first install baselines existing ledger/proof history rather than spamming historical events;
- current critical conditions may still be surfaced on first install;
- recurring conditions re-fire only after clear/re-entry rather than every timer tick;
- event identifiers/order are deterministic;
- existing pending events remain durable until the runtime acknowledges delivery;
- G6 does not compute a second PnL, drawdown, slippage threshold, daily-loss policy, risk verdict, profitability verdict, or proof formula;
- future live-money transaction alerts remain dormant because no sealed live execution path exists.

Every alert message retains `LIVE TRADING: DISABLED`.

### 5. Outbound-only Telegram transport

The first notification transport is a dependency-free HTTPS Telegram `sendMessage` adapter.

Verified properties:

- destination host is exactly `api.telegram.org`;
- method is HTTPS `POST` to `/bot<TOKEN>/sendMessage`;
- request body is bounded JSON containing only `chat_id` and deterministic plain-text `text`;
- no `parse_mode`, buttons, callback markup, incoming update polling, webhook registration, or command parser exists;
- timeout is finite, positive, and bounded;
- success requires a JSON object with exact boolean `ok: true`;
- transport/HTTP/response failures become the generic `TelegramAlertError("telegram alert delivery failed")`;
- token, token-bearing URL, chat ID, and response/error body are not included in the public exception text;
- runtime main catches alert failures and exits nonzero without printing a secret-bearing traceback.

No external production Python dependency was added.

### 6. Durable send/acknowledgement semantics

The one-shot runtime uses write-before-send ordering:

1. load previous alert state;
2. collect read-only source snapshot;
3. detect transitions/events;
4. persist the complete updated pending queue;
5. load the protected bot token only if a send is required;
6. send the first pending event;
7. after successful send only, remove that one event and persist the acknowledgement;
8. continue in queue order;
9. on the first delivery failure, stop and leave that failed event plus every later event queued.

Verified consequences:

- acknowledged events are not resent on the next successful cycle;
- a crash/failure before acknowledgement cannot silently lose an unsent event;
- no in-process exponential retry storm exists;
- retry cadence is delegated to the independent systemd timer;
- deleting/resetting authoritative PAPER evidence is never used to repair alert delivery.

### 7. Authority firewall

The G6 authority tests verify that the alert package:

- exports no trading/control mutation API;
- imports no live executor, transaction builder, signer, submission, wallet, registry-mutation, promotion-mutation, or risk-mutation subsystem;
- never calls a trading/PAPER `run_cycle`;
- creates no HTTP/TCP listener;
- contains no Telegram `getUpdates`, `setWebhook`, callback-query, command-handler, or reply-markup path;
- confines direct filesystem-write primitives to `state.py`;
- confines `subprocess` use to `source.py`;
- confines systemd subprocess generation to `systemctl is-active`.

This is in addition to the final changed-file audit showing that no pre-existing trading-authority file changed.

### 8. Independent hardened systemd supervision

`deploy/systemd/shreks-alerts.service` is verified to:

- run as `shreks:shreks`;
- run as `Type=oneshot`;
- use `/opt/shreks/current/.venv/bin/python -m shreks_brain.alerts.runtime`;
- read `/etc/shreks/shreks.env` and protected `/etc/shreks/telegram-bot-token`;
- require the dedicated `/var/lib/shreks/alerts` directory;
- keep the release tree and Shreks state read-only except `ReadWritePaths=/var/lib/shreks/alerts`;
- use `ProtectSystem=strict` and additional process/kernel hardening;
- allow only AF_UNIX/AF_INET/AF_INET6 for required outbound HTTPS/system interaction;
- remain independent of `shreks.target`;
- contain no live/wallet/signing/submission/control command.

`deploy/systemd/shreks-alerts.timer` is verified to:

- schedule the alert service after boot;
- retry once per minute through `OnUnitActiveSec=60s`;
- use a bounded `AccuracySec=5s`;
- persist timer scheduling across reboot;
- enable independently under `timers.target`.

`shreks.target` was not modified and does not require or want the alert service/timer. Alert failure therefore cannot stop the core PAPER target.

### 9. Deployment/runbook boundary

The systemd runbook now documents:

- `/var/lib/shreks/alerts` as the only G6 writable runtime directory;
- `/var/lib/shreks/alerts/state.json` as the durable queue/state;
- `/etc/shreks/telegram-bot-token` as a protected `root:shreks 0640` host secret;
- that the token is never stored in the environment file or GitHub;
- exact G6 non-secret environment keys;
- independent installation/enablement via `systemctl enable --now shreks-alerts.timer`;
- service/timer status and journal inspection commands;
- queue-preservation behavior after failed delivery;
- rollback rules for pre-G6 releases;
- that alert failure cannot stop the PAPER runtime;
- that Telegram has no command/trading-control authority;
- that real phone delivery remains unproven until an actual host message is observed.

## TDD / CI evidence retained

The implementation was built through explicit RED -> GREEN gates:

- Task 1 RED: `9b89dc4c82467b3bce9356eb2ffa7b02ae64a3ad`; CI `32957675293` failed only because `shreks_brain.alerts` did not yet exist.
- Task 1 GREEN/fix: `b0fafe9573e064083b3d67ffd953c37038b50c97`; CI `32958014706`; **2422 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.
- Task 2 RED: `7f6f1889baf95a6888eb67fb7a9eb89851fcb091`; CI `32958186684` failed only because `shreks_brain.alerts.config` did not yet exist.
- Task 2 GREEN: `e6ffb12a6aa97dfacfbaae0ecfe87e5b821d65a5`; CI `32958343842`; **2451 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.
- Task 3 RED: `861b6a6ac6e4c8560207cfe57ff6b2e497484913`; CI `32958525820` failed only because `shreks_brain.alerts.source` did not yet exist.
- Task 3 GREEN: `2f29fcdfeb343e11f8861cbb871b5d333cf6267e`; CI `32958717827`; **2459 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.
- Task 4 RED: `0220f91ddfe164d80e4e94b22bc2cffc76bb3123`; CI `32958982377` failed only because `shreks_brain.alerts.detector` did not yet exist.
- Task 4 GREEN: `e23c5c615223dae107366fced34f7288a9729913`; CI `32959191156`; **2464 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.
- Task 5 RED: through `5d22cb9c4c15968fe6648bc984efee27005fe135`; CI `32959877078` failed only because `shreks_brain.alerts.telegram` and `shreks_brain.alerts.runtime` did not yet exist.
- Task 5 first GREEN candidate: `18cb5badc92bebf7a2dc44d2c16bad9831fba73f`; CI `32960008535`; implementation tests exposed only an invalid test fixture (`AlertSourceSnapshot` violated its own invariant), not a runtime behavior defect.
- Task 5 corrected GREEN: `a652300d759f62a1861fcbb0b12bf3914b16c11a`; CI `32960134368`; **2472 Python tests passed**, Rust/workspace GREEN, repository safety GREEN. The runtime implementation itself was unchanged by the fixture fix.
- Task 6 RED: through `7e180154307fe8b795155267e2f592a8a20e075c`; CI `32960321780`; Python authority tests GREEN, repository safety GREEN, Rust failed only because the intentionally absent G6 service/timer/runbook contract had not yet been implemented. The independent PAPER-target assertion already passed.
- Task 6/frozen GREEN: `1f9caf3e56000f0fb80612b0b2ee801f03e118a8`; CI `32960623418`; **2477 Python tests passed**, Rust/workspace GREEN, repository safety GREEN.

## Scope-drift audit

Final file-by-file and compare inspection found no G6 mutation drift in:

- provider adapters or provider policy;
- database/storage schemas or migrations;
- strategy/setup/scoring logic;
- risk engine or risk policy;
- PAPER/live execution logic;
- ledger/accounting/checkpoint implementation;
- proof or promotion policy/mutation;
- registry mutation;
- wallet/private-key handling;
- transaction construction, signing, or submission;
- live execution;
- core `shreks.target` membership or release health gating.

The only existing non-document/config file modified outside tests is `.env.example`, and it adds only G6 alert operational keys. Every production Python module is new under `python/src/shreks_brain/alerts/`. The two systemd production files are new independent G6 units.

## Known deployment/evidence gates not claimed by repository CI

Before treating G6 phone notification delivery as physically proven on a host, capture real deployment evidence that:

1. `/var/lib/shreks/alerts` exists with the intended ownership/permissions;
2. `/etc/shreks/telegram-bot-token` is installed as `root:shreks 0640` and contains the intended bot token;
3. the configured Telegram chat ID points to the intended private operator destination;
4. `shreks-alerts.timer` is enabled and active independently from `shreks.target`;
5. a controlled test alert is received on the intended phone;
6. service/journal output contains no token-bearing URL or secret material;
7. a simulated delivery failure leaves the failed/later event(s) in `/var/lib/shreks/alerts/state.json` and a later successful timer cycle drains them in order;
8. PAPER runtime health remains independent if alert delivery is unavailable.

These are host/integration checks, not missing repository behavior.

## Profitability / live-state statement

G6 adds observability delivery, not profitability evidence. The existence or success of alerts does not prove the strategy is profitable. Profitability remains unproven until real PAPER evidence passes the sealed proof gates.

G6 does not enable live execution, transaction signing/submission, wallet handling, or Telegram control authority.

**LIVE TRADING: DISABLED.**

## Seal post-commit requirements

After committing this verification record:

1. compare frozen behavior `1f9caf3e56000f0fb80612b0b2ee801f03e118a8` to the seal commit;
2. require exactly **1 commit / 1 changed file**, this verification record only;
3. run exact-seal CI on the seal SHA;
4. require exact-seal Python cardinality to remain **2477 passed**;
5. require Rust/workspace GREEN and repository safety GREEN;
6. update draft PR #47 with frozen/seal evidence and retained real-host gates;
7. keep PR #47 **open, draft, and unmerged**.
