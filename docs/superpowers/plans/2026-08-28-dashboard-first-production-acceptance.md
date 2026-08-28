# Dashboard-first production acceptance

Date: 2026-08-28

## Scope

This record captures physical VPS acceptance for the dashboard-first operator visibility release `cec44076eff86006911c29953ad44662b7d2e5b1`.

The release adds the read-side `Attention / Problems` summary to the existing private dashboard. Telegram delivery remains deliberately deferred and dormant. This acceptance does not claim remote browser access, TLS/private-overlay exposure, or LIVE trading enablement.

**LIVE TRADING: DISABLED.**

## Release provenance

Immutable GitHub release tag:

`shreks-cec44076eff86006911c29953ad44662b7d2e5b1`

Release workflow:

- run `33122684098`;
- job `98693232739`;
- conclusion `success`.

Release assets:

- `RELEASE_MANIFEST.json` SHA-256 `b1cb97e472f0c59c60abb61f89ff61199d628e90ad95977e7b5b986228616ba7`;
- `shreks-release-cec44076eff86006911c29953ad44662b7d2e5b1.tar.gz` SHA-256 `60bd9c454cea2854f578340d4ac6149b891c69c274572bb8dbf02cc004ba8420`;
- checksum asset SHA-256 `531f6dd3ebaf4640e5af80850d090bc36c6433e195eb0e87f3a6876af20feafc`.

Deploy workflow:

- run `33122902966`;
- job `98693973229`;
- conclusion `success`.

The production symlink resolved exactly to:

`/opt/shreks/releases/cec44076eff86006911c29953ad44662b7d2e5b1`

## Initial host check and isolated diagnosis

The first post-deploy dashboard check proved the new release symlink was active, but the page did not yet contain the new Attention panel.

The dashboard process still had working directory:

`/opt/shreks/releases/cb72f76b901bd170b565a53a7269a20247c27908`

This matched the sealed release-manager boundary: core release activation manages the three core PAPER child services plus `shreks.target`, while the independently supervised dashboard is not restarted by core activation.

No core runtime defect was inferred from the stale dashboard process.

## Dashboard-only refresh acceptance

Before dashboard refresh:

- dashboard PID `24621`;
- dashboard working directory `/opt/shreks/releases/cb72f76b901bd170b565a53a7269a20247c27908`;
- observer PID `33187`;
- paper-evidence PID `25486`;
- paper-campaign PID `34476`.

Only `shreks-dashboard.service` was restarted.

After refresh:

- dashboard state `active`;
- dashboard PID `37729`;
- dashboard working directory `/opt/shreks/releases/cec44076eff86006911c29953ad44662b7d2e5b1`;
- `DASHBOARD_PROCESS_REFRESHED=yes`;
- `DASHBOARD_RUNNING_NEW_RELEASE=yes`.

The restart emitted a systemd warning that unit files had changed on disk and `daemon-reload` should be run. This warning does not invalidate the page/runtime acceptance below; host unit-manager hygiene remains to be refreshed separately.

## Authentication and visibility

Dashboard behavior after the isolated refresh:

- unauthenticated `GET /` -> HTTP `401`;
- authenticated `GET /` -> HTTP `200`;
- rendered page contained `Attention / Problems`;
- rendered page contained `id="attention-layer"` and the sealed `renderAttention` implementation;
- rendered page contained `LIVE TRADING: DISABLED`.

Host conclusion fields:

- `ATTENTION_PANEL_DEPLOYED=yes`;
- `LIVE_DISABLED_BANNER=yes`.

## Network boundary

Socket inspection showed the dashboard listener at:

`127.0.0.1:8787`

No public/wildcard dashboard listener was accepted.

Host conclusion:

`LOOPBACK_LISTENER=yes`

## Core runtime isolation

After the dashboard-only restart, core process identities were unchanged:

- observer PID `33187`;
- paper-evidence PID `25486`;
- paper-campaign PID `34476`.

Host conclusion:

`CORE_RUNTIME_UNTOUCHED=yes`

Therefore refreshing dashboard code did not restart the continuously supervised PAPER runtime.

## Read-side safety

The authoritative operator risk-control file SHA-256 before and after the dashboard exercise was exactly:

`4e4b02f6756d420a3b98ef6c0d6d1463889199745a789e7a29b4f5a05fd01c15`

Host conclusion:

`RISK_STATE_UNCHANGED=yes`

## Telegram boundary

The preceding production check reported:

- `shreks-alerts.timer.active=inactive`;
- `shreks-alerts.timer.enabled=not-found`;
- `TELEGRAM_DEFERRED=yes`.

No Telegram bot token or chat ID is required for this dashboard-first operating path.

## Telemetry interpretation discovered during acceptance

The dashboard snapshot reported `candidate_count=40485`, but this is a cumulative database count over `token_candidates`, not the number of candidates currently in the Observer V2 active tracking registry and not the number discovered in the last 24 hours.

The same snapshot reported:

- mode `PAPER`;
- overall status `UNAVAILABLE`;
- unhealthy provider count `0`;
- accounting status `VALID`;
- open PAPER positions `0`;
- closed PAPER positions `0`;
- realized PnL `$0.00`;
- unrealized PnL `$0.00`;
- global risk halt `false`;
- LIVE state `DISABLED`.

The cumulative candidate label therefore requires a later dashboard clarification before being used as an operating-capacity metric. The absence of PAPER positions also warrants separate diagnosis rather than assuming profitability or strategy behavior.

## Conclusion

Physical host conclusion:

`DASHBOARD-FIRST PRODUCTION ACCEPTANCE PASSED`

The dashboard-first read-side release is production-proven locally on the VPS, preserves loopback/authentication boundaries, does not mutate operator risk state, and can be refreshed independently without touching core PAPER process identities.

Remote browser access remains intentionally unproven and port `8787` must not be exposed directly to the public internet.

**LIVE TRADING: DISABLED.**
