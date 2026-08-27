# Dashboard-First Operator Attention Seal

**Date:** 2026-08-27  
**Repository:** `Dtwosam/Shreks`  
**Merged behavior SHA:** `429f093cb78bbc1bb44484dc62cd4ba4860f06e1`  
**PR:** `#68` — `feat: add dashboard attention summary`  

**LIVE TRADING: DISABLED.**

## Decision

Operator visibility is dashboard-first. Physical G6 Telegram provisioning and phone-notification deployment are deferred. No Telegram bot token or chat ID is required for this release, and no Telegram transport is activated.

The existing private dashboard remains the operator surface. This change adds an at-a-glance `Attention / Problems` section so important degraded state is visible without a separate notification channel.

## Scope

Behavior-bearing changes are limited to:

- `python/src/shreks_brain/dashboard/page.py`
- `python/tests/test_g5_dashboard_attention.py`

The Attention panel uses only data already fetched by the authenticated dashboard:

- canonical G4 telemetry from `/api/v1/snapshot`;
- authoritative operator-control state from `/api/v1/operator-controls`.

It surfaces degraded/unavailable telemetry layers, unhealthy-provider count, unavailable ingestion checkpoint, invalid accounting state, telemetry source errors, global risk halt, kill-switch state, and operator entry-halt/kill state.

The page continues to use safe DOM text writes. It does not calculate profitability, risk, proof, accounting, provider thresholds, or trading decisions.

## Authority boundary

This change does **not**:

- add an alerts API endpoint;
- activate Telegram or any other outbound notification transport;
- add inbound commands;
- add live trading;
- add transaction construction, signing, or submission;
- change strategy, scoring, risk, execution, ledger, proof, or promotion behavior;
- expand operator-control authority beyond the already-sealed G7 safety controls;
- expose the dashboard beyond its loopback-only systemd/network boundary.

The dashboard remains bound to the existing private authenticated service contract. Secure remote access must continue through a private tunnel rather than exposing port `8787` publicly.

## TDD proof

### RED

- Commit: `1d27fecb9841aecfeb2e5e0f952baf05b85211e4`
- CI: `33121566308`
- Expected result: Python failed because the required Attention panel did not yet exist.
- Rust and repository safety remained green.

### GREEN branch

- Commit: `d4a7e6bf630726c49555195b2bc19f02e23b96ef`
- CI: `33121741856`
- Python: GREEN
- Rust: GREEN
- Repository safety: GREEN
- Native ARM64 release build: GREEN

### Merged main

- Merge SHA: `429f093cb78bbc1bb44484dc62cd4ba4860f06e1`
- CI: `33121892911`
- Python: GREEN
- Rust: GREEN
- Repository safety: GREEN
- Native ARM64 release build: GREEN

## Production boundary

This seal records repository verification only. Production completion still requires:

1. immutable ARM64 release from this seal commit;
2. verified deployment to the VPS;
3. authenticated local dashboard acceptance showing the new Attention panel;
4. confirmation that the dashboard remains loopback-only and the core PAPER runtime remains active.

Telegram remains intentionally deferred after production deployment.
