# Phase G7 Controlled Halt Controls Design

**Phase:** G7 — Emergency operator controls  
**Base:** sealed G6 `a4423138b64c9a3f425f1b3e6ecd48be1d4f9532`  
**Primary requirement:** emergency dashboard actions must write through the controlled risk/runtime authority path; the dashboard must never create trades or mutate accounting directly.

**LIVE TRADING: DISABLED.**

## Goal

Add two operator safety controls without turning the dashboard into a trading bot:

- `HALT NEW ENTRIES`
- `EMERGENCY KILL SWITCH`

The controls must affect the same risk/exit path used by autonomous PAPER operation now and future live execution later. G7 does not enable live trading.

## Safety model

G7 introduces one small durable authority object: **operator risk-control state**.

It contains only safety state and audit metadata:

- schema version;
- monotonically increasing revision;
- `halt_new_entries` boolean;
- `kill_switch_active` boolean;
- update timestamp;
- last command/source.

Invariant: `kill_switch_active == true` always implies `halt_new_entries == true`.

The dashboard is not the authority. It is an authenticated client of the risk-control authority.

## Semantics

### HALT NEW ENTRIES

`HALT NEW ENTRIES` blocks autonomous entry approval while leaving existing-position exit management active.

It must not be implemented by reusing `global_risk_halt`, because the sealed exit engine treats global halt as an emergency exit trigger. Instead G7 adds an explicit entry-halt fact to the existing `RiskContext`; the existing risk engine rejects an ENTER decision through a stable G7 risk reason.

### EMERGENCY KILL SWITCH

`EMERGENCY KILL SWITCH` is stronger:

- sets `halt_new_entries = true`;
- sets `kill_switch_active = true`;
- feeds the existing `RiskContext.kill_switch_active` entry rejection;
- also feeds the existing global-halt exit context, so managed open positions follow the sealed emergency-exit path rather than a new G7 exit formula.

G7 does not create a second risk or exit engine.

## Persistence and concurrency

Default production path:

`/var/lib/shreks/risk/operator-control.json`

Configuration key:

`SHREKS_RISK_CONTROL_STATE_PATH`

State requirements:

- canonical exact-key JSON;
- finite/bounded values only;
- atomic temporary-file + replace + fsync writes;
- private file mode;
- symlink rejection;
- corrupt existing state fails closed;
- mutation serialized with a stable adjacent lock file and `flock`;
- every mutation requires an exact expected revision;
- stale/replayed browser requests fail with a conflict rather than overwriting newer safety state.

A configured-but-missing/corrupt/unreadable control state must never silently grant entry authority. PAPER runtime interpretation is fail-closed for new entries: unavailable operator-control state means entry halt is active. It does **not** invent an emergency liquidation intent unless the persisted kill-switch fact is actually true.

Legacy/unit-test paths with no G7 state path configured preserve prior behavior; the production G7 runbook requires the path.

## Commands

Authority commands:

- `HALT_NEW_ENTRIES`
- `EMERGENCY_KILL_SWITCH`
- host-only `CLEAR_ENTRY_HALT`
- host-only `RESET_KILL_SWITCH`

Dashboard routes expose only the first two safety-increasing commands.

Host reset commands exist so a tested PAPER halt can be recovered without hand-editing/deleting the state file. They must use the same revision-checked authority and explicit confirmation/reason input. They are not exposed through the dashboard.

## Dashboard security boundary

Existing Basic authentication remains required before every route.

G7 adds an authenticated control-context GET route containing:

- current risk-control state;
- a process-local high-entropy CSRF token.

Safety POST requests must require all of:

- valid Basic authentication;
- exact known control route;
- `Content-Type: application/json`;
- bounded request body;
- exact CSRF header value;
- exact JSON keys;
- expected state revision;
- for kill switch, exact confirmation phrase `EMERGENCY KILL SWITCH`.

No CORS headers are added. The static page continues to use same-origin requests and no external scripts/resources.

The HTTP application may call the risk-control authority only. It must not import or call execution, ledger, registry promotion, wallet, signing, submission, or service-management mutation APIs.

## Dashboard UX

The page retains a prominent:

`LIVE TRADING: DISABLED`

It gains a dedicated **Emergency controls** card showing:

- operator-control availability;
- revision;
- entry-halt state;
- kill-switch state;
- last update/command;
- `HALT NEW ENTRIES` button;
- `EMERGENCY KILL SWITCH` button.

Buttons are disabled when the corresponding safer state is already active or control state is unavailable.

The kill-switch action requires an explicit browser confirmation and the backend confirmation phrase. The page never exposes trade-entry, buy/sell, position-size, wallet, promotion, or live-enable controls.

## Runtime integration

The PAPER campaign runtime reads operator-control state at the start of every cycle.

Effective facts:

- `entry_halt_active = operator.halt_new_entries OR operator_state_unavailable`;
- `effective_kill_switch = manifest.risk_environment.kill_switch_active OR operator.kill_switch_active`;
- `effective_global_halt_for_exit = manifest.global_risk_halt OR operator.kill_switch_active`.

The immutable manifest is not rewritten. Operator controls are operational safety state, not strategy policy.

The runner/assembler/risk-context path receives only the effective booleans required to apply existing risk/exit gates. Accounting and PAPER ledger mutation continue to happen only through the sealed PAPER loop.

## Telemetry and alerts

G7 should surface the persisted operator state in the read-side evidence path so the dashboard can show the authoritative value immediately. Where existing G4 telemetry remains constrained to its sealed PAPER schema, G7 control-context data is read directly from the risk-control store rather than rewriting historical telemetry formulas.

G6 alerts already understand authoritative kill-switch/global-halt telemetry. G7 may extend alert sourcing to operator-control state only where needed to make the newly persisted control activation observable without inventing duplicate risk logic.

## Systemd / host authority

The G5 dashboard service intentionally had no writable runtime path. G7 changes that narrowly:

- dashboard receives write access only to `/var/lib/shreks/risk`;
- the rest of `/var/lib/shreks` remains read-only to the dashboard;
- campaign runtime reads the same state path each cycle;
- no dashboard systemd start/stop/restart authority is added.

The runbook must initialize the risk directory/state through the controlled CLI before enabling G7 production controls.

## Non-goals

G7 does **not** add:

- live trading enablement;
- buy/sell buttons;
- Telegram control commands;
- wallet/private-key access;
- transaction construction/signing/submission;
- promotion controls;
- strategy/risk threshold editing;
- direct ledger/accounting mutation;
- service restart buttons;
- a browser reset/resume action;
- automatic risk-state clearing.

## Test strategy

Build through explicit RED -> GREEN gates:

1. strict operator risk-control model/codec/store and concurrent revision semantics;
2. risk-engine entry-halt integration and emergency-kill reuse of sealed exit path;
3. PAPER runtime reads control state every cycle and fails closed for entries on unavailable state;
4. authenticated CSRF/revision-protected dashboard control API;
5. static control UI with no external/control-surface drift;
6. host-only reset CLI, authority firewall, systemd/write-path/runbook verification;
7. final G6->G7 scope audit, behavior freeze, docs-only seal, exact-seal CI.

## Acceptance boundary

Repository G7 is complete when tests prove:

- dashboard safety commands mutate only canonical operator risk-control state;
- entry halt blocks new entries through the risk engine, not dashboard logic;
- emergency kill blocks entries and uses the existing global-halt exit path;
- stale/replayed requests cannot overwrite newer safety state;
- corrupt/unavailable configured state fails closed for new entries;
- browser routes cannot clear safety state or create trades;
- host-only reset goes through the same revisioned authority;
- dashboard write access is limited to the risk-control directory;
- LIVE remains disabled throughout;
- frozen and exact-seal CI are fully green with identical test cardinality.
