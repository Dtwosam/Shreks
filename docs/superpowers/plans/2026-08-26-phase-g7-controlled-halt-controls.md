# Phase G7 Controlled Halt Controls Implementation Plan

**Base:** sealed G6 `a4423138b64c9a3f425f1b3e6ecd48be1d4f9532`  
**Branch:** `feat/phase-g7-controlled-halt-controls`  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g7-controlled-halt-controls-design.md`

**LIVE TRADING: DISABLED.**

## Task 1 — Durable operator risk-control authority

Create RED tests for:

- exact immutable state schema and command enum;
- invariant `kill_switch_active -> halt_new_entries`;
- canonical strict JSON codec;
- missing/corrupt/symlink state behavior;
- atomic private writes;
- stable lock-file serialization;
- expected-revision conflict handling;
- monotonic dashboard commands;
- explicit host reset commands;
- exact audit metadata.

Implement under `python/src/shreks_brain/risk_control/` with no trading, accounting, execution, wallet, signing, submission, or service-management imports.

GREEN gate: full Python/Rust/safety CI.

## Task 2 — Existing risk/exit path integration

Create RED tests proving:

- explicit operator entry halt rejects ENTER through `assess_entry_risk` with a stable risk reason;
- default/legacy risk context remains unchanged when entry halt is false;
- emergency kill still rejects through existing `KILL_SWITCH_ACTIVE`;
- operator kill is forwarded to the existing `global_halt_active` exit context rather than a new G7 exit formula;
- `HALT NEW ENTRIES` alone does not force an exit.

Implement the smallest backward-compatible additions to `RiskContext`, risk engine, observer risk-context assembly, and existing campaign assembler/coordinator plumbing.

GREEN gate: full CI and no changed risk thresholds/formulas.

## Task 3 — Per-cycle runtime control-state read

Create RED tests proving:

- configured operator state is re-read for every PAPER cycle;
- halt activation between two cycles blocks the later entry without process restart;
- emergency kill activation between cycles feeds both existing entry kill switch and global-halt exit behavior;
- configured missing/corrupt/unreadable state fails closed for **new entries**;
- unavailable state does not fabricate an emergency liquidation fact;
- no G7 path rewrites the immutable campaign manifest;
- no state read mutates PAPER evidence/accounting.

Add optional `SHREKS_RISK_CONTROL_STATE_PATH` operational config. Production G7 runbook will require it; legacy tests/older releases without the key preserve sealed behavior.

GREEN gate: full CI.

## Task 4 — Authenticated dashboard control API

Create RED tests for:

- Basic auth still runs before every route;
- authenticated GET `/api/v1/control` returns authoritative state + process-local CSRF token;
- POST body is bounded and exact JSON;
- `Content-Type: application/json` required;
- exact `X-Shreks-CSRF` required;
- expected revision required;
- stale revision -> conflict;
- halt route can only set entry halt on;
- kill route requires exact confirmation phrase and sets kill + halt;
- no browser route clears/resets state;
- no mutation route can reach execution/ledger/promotion/wallet/signing/submission/systemd authority;
- source/internal errors return stable generic codes.

Modify dashboard HTTP/handler minimally. The handler may read a bounded body only for exact control POST routes.

GREEN gate: full CI.

## Task 5 — Emergency dashboard UI

Create RED tests for a dependency-free static controls card that:

- keeps `LIVE TRADING: DISABLED` prominent;
- displays availability/revision/halt/kill/last command;
- provides `HALT NEW ENTRIES` and `EMERGENCY KILL SWITCH` only;
- fetches control context same-origin;
- sends CSRF header and expected revision;
- sends kill confirmation phrase;
- disables safer-state buttons when already active/unavailable;
- does not add buy/sell/live-enable/promotion/wallet/service controls;
- continues using `textContent`, no external scripts/assets.

GREEN gate: full CI.

## Task 6 — Host reset CLI, systemd boundary, authority firewall, runbook

Create RED tests proving:

- host-only CLI initializes state through authority path;
- CLI clear/reset commands require expected revision + explicit confirmation/reason;
- dashboard package cannot import CLI reset commands;
- dashboard service gains write access only to `/var/lib/shreks/risk`;
- no systemd control verbs are introduced;
- PAPER service reads the control state but does not depend on dashboard uptime;
- runbook creates `/var/lib/shreks/risk`, initializes state, documents protected permissions and reset procedure;
- rollback to pre-G7 disables browser controls / preserves state rather than deleting it;
- live trading remains disabled.

Implement CLI, `.env.example`, systemd/runbook changes, and authority tests.

GREEN gate: full CI.

## Task 7 — Freeze, audit, and seal

1. Freeze behavior at the final all-green Task 6 SHA.
2. Compare exact G6 seal -> frozen G7.
3. Audit every changed file for authority drift.
4. Confirm no strategy threshold, scoring, profitability/proof formula, wallet, signing, submission, promotion, or live-enable behavior changed.
5. Confirm G7 writes only operator risk-control state and uses existing PAPER ledger/accounting paths.
6. Confirm dashboard safety actions are one-way safer; reset remains host-only.
7. Replace this plan with a verification record in one docs-only commit.
8. Prove frozen behavior -> seal is exactly 1 commit / 1 file.
9. Run exact-seal CI and require identical Python test cardinality plus Rust/workspace and repository safety GREEN.
10. Update the stacked draft PR and keep it open/draft/unmerged.

## Real-host gates retained for later deployment proof

Repository CI cannot prove physical host control propagation. Before live promotion, host evidence must show:

- risk-control state is on persistent storage with intended permissions;
- dashboard POST changes the persisted revision/state and no other authoritative file;
- running PAPER process observes a control change on the next cycle without restart;
- halt blocks a controlled PAPER entry while exits continue;
- emergency kill blocks entries and exercises the existing emergency-exit path for a controlled open PAPER position;
- stale/replayed control request is rejected;
- dashboard compromise does not expose reset/live/trade authority;
- restart preserves the operator risk state;
- alerts/dashboard reflect the resulting risk state;
- live trading is still disabled unless all separate promotion gates are legitimately satisfied.
