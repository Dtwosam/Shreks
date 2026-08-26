# Phase G7 Controlled Halt Controls Verification Record

**Base:** sealed G6 `a4423138b64c9a3f425f1b3e6ecd48be1d4f9532`  
**Branch:** `feat/phase-g7-controlled-halt-controls`  
**Design:** `docs/superpowers/specs/2026-08-26-phase-g7-controlled-halt-controls-design.md`

**LIVE TRADING: DISABLED.**

## Frozen behavior

- Frozen G7 behavior SHA: `a7295abca5be942f98d7e22101b95766e574f34b`.
- Frozen CI: `32968379925` (`CI` run 1783).
- Workflow status: completed / success.
- Python: `2531 passed`.
- Rust/workspace: GREEN.
- Repository safety: GREEN.

This SHA is the final all-green Task 6 behavior point. No behavior changes are permitted after it in the G7 seal geometry.

## Exact G6 -> frozen G7 geometry

Comparison:

`a4423138b64c9a3f425f1b3e6ecd48be1d4f9532...a7295abca5be942f98d7e22101b95766e574f34b`

- status: ahead
- ahead by: 43 commits
- behind by: 0 commits
- total commits: 43
- changed files: 30

Changed files audited:

1. `.env.example`
2. `crates/shreks-observer/tests/g5_dashboard_systemd.rs`
3. `crates/shreks-observer/tests/g7_control_systemd.rs`
4. `deploy/systemd/G7_OPERATOR_CONTROLS.md`
5. `deploy/systemd/shreks-dashboard.service`
6. `deploy/systemd/shreks-paper-campaign.service`
7. `docs/superpowers/plans/2026-08-26-phase-g7-controlled-halt-controls.md`
8. `docs/superpowers/specs/2026-08-26-phase-g7-controlled-halt-controls-design.md`
9. `python/src/shreks_brain/dashboard/http.py`
10. `python/src/shreks_brain/dashboard/page.py`
11. `python/src/shreks_brain/observer_campaign/runtime.py`
12. `python/src/shreks_brain/observer_campaign/runtime_config.py`
13. `python/src/shreks_brain/risk/engine.py`
14. `python/src/shreks_brain/risk/models.py`
15. `python/src/shreks_brain/risk_control/__init__.py`
16. `python/src/shreks_brain/risk_control/cli.py`
17. `python/src/shreks_brain/risk_control/integration.py`
18. `python/src/shreks_brain/risk_control/models.py`
19. `python/src/shreks_brain/risk_control/paper_runtime.py`
20. `python/src/shreks_brain/risk_control/state.py`
21. `python/tests/test_g5_dashboard_authority.py`
22. `python/tests/test_g5_dashboard_page.py`
23. `python/tests/test_g7_dashboard_controls_http.py`
24. `python/tests/test_g7_dashboard_controls_page.py`
25. `python/tests/test_g7_host_reset_cli.py`
26. `python/tests/test_g7_paper_runtime_controls.py`
27. `python/tests/test_g7_risk_control_integration.py`
28. `python/tests/test_g7_risk_control_state.py`
29. `python/tests/test_observer_campaign_public_api.py`
30. `python/tests/test_risk_models.py`

## Authority audit

The 30-file diff is confined to G7 operator risk-control state, its narrow integration into the existing PAPER risk/exit path, authenticated dashboard safety controls, host recovery/deployment boundaries, tests, and documentation.

No provider adapter changed. No SQLite/database schema or migration changed. No strategy setup, threshold, selection, scoring, sizing, slippage, profitability/proof formula, promotion policy, wallet, signing, transaction construction/submission, or live-enable implementation changed.

The sensitive existing-risk changes are deliberately minimal:

- `RiskContext` adds `operator_entry_halt_active: bool = False`, preserving legacy/default behavior.
- `RiskReasonCode` adds stable `OPERATOR_ENTRY_HALT_ACTIVE`.
- `assess_entry_risk` adds one fail-closed rejection when that flag is true. No numeric risk threshold or formula changed.
- Existing `KILL_SWITCH_ACTIVE` behavior remains intact.
- Operator kill is overlaid onto the existing global-halt/exit path; G7 does not introduce a new exit or liquidation formula.
- `HALT NEW ENTRIES` alone does not force an exit.

The PAPER runtime boundary is also narrow:

- `SHREKS_RISK_CONTROL_STATE_PATH` is operational state configuration, separate from immutable trading-policy configuration.
- The configured control file is re-read on every PAPER cycle, so a safety action propagates without process restart.
- Missing/corrupt/unreadable configured state fails closed for new entries by treating entry halt as active.
- Unavailable state does not fabricate an emergency kill/liquidation fact.
- The controlled coordinator overlays the already-read operator flags, then uses the existing `run_paper_cycle`, existing E11 evidence write, existing PAPER checkpoint save/reload, and existing restart-equivalence validation paths.
- G7 does not rewrite the immutable campaign manifest.

## Durable control-state authority

G7 introduces a dedicated canonical operator risk-control state under `python/src/shreks_brain/risk_control/` with:

- exact strict state/command models;
- invariant `kill_switch_active -> halt_new_entries`;
- canonical JSON validation;
- revision-checked command application;
- atomic private writes and serialization lock;
- explicit audit source/reason metadata;
- monotonic dashboard safety commands;
- explicit host-only authority-increasing reset/clear commands.

The browser cannot clear either latch. Reset/clear remains host-only through `python -m shreks_brain.risk_control.cli` and requires explicit expected revision plus exact confirmation/reason inputs.

## Dashboard safety-control boundary

The G5 dashboard remains authenticated and loopback/private. G7 adds exactly these control paths:

- `GET /api/v1/operator-controls`
- `POST /api/v1/operator-controls/halt-new-entries`
- `POST /api/v1/operator-controls/emergency-kill`

The POST boundary proves:

- Basic authentication is checked before route handling;
- all other POST targets return `405`;
- exact `X-Shreks-CSRF` is required;
- `Content-Type: application/json` is required;
- request bodies are bounded and exact-key JSON;
- expected revision is mandatory and stale revisions return conflict;
- halt can only latch new-entry halt on;
- emergency kill requires exact `EMERGENCY KILL SWITCH` confirmation and latches both kill + halt;
- fixed server-side audit reasons are used;
- no browser reset, resume, live-enable, trade, promotion, wallet, signing, submission, or systemd route exists;
- credentials are not logged or returned.

The static dashboard page exposes only `HALT NEW ENTRIES` and `EMERGENCY KILL SWITCH`, uses same-origin requests, authoritative returned revision/state, safe `textContent`, no external assets, and no client-side profitability/trading formulas.

## Deployment and host-recovery boundary

- `.env.example` declares `SHREKS_RISK_CONTROL_STATE_PATH=/var/lib/shreks/risk/operator-control.json` and keeps `SHREKS_MODE=observe`.
- `shreks-dashboard.service` can write only `/var/lib/shreks/risk`; `/var/lib/shreks` and `/etc/shreks` remain otherwise read-only to the dashboard sandbox.
- The dashboard remains loopback-constrained and independent of `shreks.target` / PAPER service lifecycle.
- `shreks-paper-campaign.service` requires the same control state to be readable before startup but has no dashboard dependency.
- No G7 systemd unit contains service-management, reboot/shutdown, wallet/signing/submission, or live-mode authority.
- `deploy/systemd/G7_OPERATOR_CONTROLS.md` documents initialization, private `0700` directory / `0600` state permissions, host-only resets, expected revision, exact confirmation phrases, rollback preservation, and the rule that rollback to pre-G7 disables browser controls rather than deleting G7 state.

## TDD / CI evidence retained

Later G7 gates include:

- Task 4 confirmation RED: CI `32966536637` failed only the intended emergency-kill confirmation contract after G7 authority assertions were aligned.
- Task 4 GREEN: CI `32966731402`, Python/Rust/repository safety GREEN.
- Task 5 GREEN: CI `32967226414`, `2526` Python tests plus Rust/workspace and repository safety GREEN.
- Task 6 RED: CI `32967546484`, intended missing standalone env/host CLI/deployment gaps only; repository safety GREEN.
- Frozen Task 6 GREEN: CI `32968379925`, `2531` Python tests plus Rust/workspace and repository safety GREEN.

## Seal geometry requirement

This verification record is the only file permitted to change after frozen behavior SHA `a7295abca5be942f98d7e22101b95766e574f34b`.

Post-commit proof must show:

1. frozen behavior -> seal is exactly one commit;
2. exactly this verification record changed;
3. exact-seal CI is completed / success;
4. exact-seal Python cardinality is exactly `2531 passed` again;
5. Rust/workspace is GREEN;
6. repository safety is GREEN;
7. PR #48 remains open, draft, and unmerged.

## Real-host gates retained for deployment proof

Repository CI cannot prove physical host control propagation. Before any future live promotion, host evidence must show:

- the risk-control state is on persistent storage with intended permissions;
- a dashboard POST changes the persisted revision/state and no other authoritative file;
- a running PAPER process observes a control change on the next cycle without restart;
- halt blocks a controlled PAPER entry while exits continue;
- emergency kill blocks entries and exercises the existing emergency-exit path for a controlled open PAPER position;
- stale/replayed control requests are rejected;
- dashboard compromise does not expose reset/live/trade authority;
- restart preserves operator risk state;
- alerts/dashboard reflect the resulting risk state;
- rollback preserves state and disables incompatible browser controls;
- live trading remains disabled unless all separate promotion gates are legitimately satisfied.

## Conclusion

G7 repository behavior is frozen at `a7295abca5be942f98d7e22101b95766e574f34b` with all repository gates green. The implementation adds durable, revision-checked, one-way browser safety controls and host-only recovery without widening strategy, profitability/proof, wallet, signing, submission, promotion, or live-trading authority.

**Profitability remains unproven until real PAPER evidence satisfies the sealed proof gates.**

**LIVE TRADING: DISABLED.**
