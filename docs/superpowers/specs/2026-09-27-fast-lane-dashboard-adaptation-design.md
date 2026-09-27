# Fast Lane Dashboard Adaptation — Design

**Date:** 2026-09-27  
**Base main SHA:** `a15258b54d8daf9c639826d7a0f12c05d5249fd0`

## Purpose

Implement FL10.5's first operator-dashboard adaptation without replacing the
existing authenticated G5/G7 dashboard or weakening its safety-control
boundary.

The dashboard currently shows legacy G4 PAPER campaign telemetry and trade
history. Fast Lane decision, execution, retry, and accounting telemetry now
exists as sealed read-only collectors, but the operator must run separate CLIs
to inspect it.

This slice adds one optional authenticated Fast Lane panel/API that composes
those already-sealed collectors over a bounded recent window.

It does not alter the legacy G4 telemetry schema, trading behavior, systemd
lifecycle, risk-control mutation paths, or LIVE authority.

## Configuration

Add exact optional dashboard configuration:

```python
DashboardFastLaneConfig(
    manifest_path,
    execution_policy_path,
    ledger_database_path,
    run_id,
    decision_evidence_directory,
    execution_source_directory,
    pending_buy_retry_source_directory,
    expected_release_sha,
    window_seconds,
)
```

Environment keys:

```text
SHREKS_DASHBOARD_FAST_LANE_MANIFEST_PATH
SHREKS_DASHBOARD_FAST_LANE_EXECUTION_POLICY_PATH
SHREKS_DASHBOARD_FAST_LANE_LEDGER_DATABASE_PATH
SHREKS_DASHBOARD_FAST_LANE_RUN_ID
SHREKS_DASHBOARD_FAST_LANE_DECISION_EVIDENCE_DIRECTORY
SHREKS_DASHBOARD_FAST_LANE_EXECUTION_SOURCE_DIRECTORY
SHREKS_DASHBOARD_FAST_LANE_PENDING_BUY_RETRY_SOURCE_DIRECTORY
SHREKS_DASHBOARD_FAST_LANE_EXPECTED_RELEASE_SHA
SHREKS_DASHBOARD_FAST_LANE_WINDOW_SECONDS
```

Rules:

- if none of these keys is present, `DashboardRuntimeConfig.fast_lane` is
  `None` and existing deployments behave exactly as before;
- if any is present, all are required;
- all paths must resolve to absolute paths without requiring existence during
  config parsing;
- run id must be non-empty;
- expected release SHA must be exactly 40 lowercase hex characters;
- window must be an integer in `1..86400` seconds;
- unknown `SHREKS_DASHBOARD_*` keys still fail closed.

The dashboard uses only its existing `/etc/shreks/shreks.env`; it does not
read or depend on the shadow service's private env file.

## Read-only Fast Lane source

Add:

```python
load_dashboard_fast_lane_snapshot(
    config,
    *,
    until_unix_ms,
) -> dict[str, object]
```

The helper computes:

```text
since = max(0, until - window_seconds * 1000)
```

and calls the existing sealed collectors:

1. `collect_fast_paper_shadow_decision_telemetry(...)`;
2. `collect_fast_paper_shadow_execution_telemetry(...)`;
3. `collect_fast_paper_shadow_outcome_telemetry(...)`.

It returns one JSON-ready document containing:

- requested window;
- expected release SHA;
- decision telemetry document;
- execution telemetry document;
- outcome telemetry document.

Before returning, require all three documents to agree on:

- expected release SHA;
- exact requested window.

When identities are populated, also require manifest/champion/action-policy
identity to agree between documents.

No metric is recomputed in the dashboard layer. The dashboard only composes
authoritative collector output.

## HTTP

Add authenticated GET:

```text
/api/v1/fast-lane
```

Rules:

- normal Basic authentication and security headers apply;
- if Fast Lane config is absent, return
  `503 {"error":"FAST_LANE_UNAVAILABLE"}`;
- collector/config/source failures return generic
  `503 {"error":"SOURCE_UNAVAILABLE"}`;
- exception text and paths are not returned;
- no POST/PUT/PATCH/DELETE Fast Lane route exists.

The existing injected dashboard clock supplies the window end, preserving
deterministic tests and avoiding a second clock.

## Page

Add a read-only wide panel:

`Fast Lane PAPER shadow`

Show server-authoritative fields only:

- source availability/window;
- champion version;
- decision evidence count/rate;
- BUY/SKIP/HOLD/REDUCE/SELL action counts;
- selected net value mean bps;
- event-to-evaluation p95;
- decision latency p95;
- decision-to-commit p95;
- decision-to-booked-entry p95;
- max-entry-price aborts;
- pending-BUY retry outcomes/abort count;
- expected selected price-cost mean bps;
- realized price-cost mean bps;
- realized explicit-cost mean bps;
- realized PnL delta;
- cash balance;
- rolling drawdown;
- open risk.

The page must not calculate expectancy, PnL, drawdown, action selection, proof,
or execution economics. It may format already-authoritative numbers.

If the endpoint is unavailable, the legacy dashboard remains functional and the
Fast Lane panel displays `SOURCE_UNAVAILABLE`.

## Attention integration

Fast Lane source unavailability must not replace legacy G4/G7 health.

When the Fast Lane endpoint is configured but unavailable, add one dashboard
attention item: `Fast Lane telemetry unavailable`.

Do not synthesize trade/risk alerts from telemetry values in this slice.

## Systemd and authority

No systemd unit change is required:

- dashboard already reads `/etc/shreks/shreks.env`;
- dashboard already has read-only access to `/var/lib/shreks` and
  `/etc/shreks`;
- its only write exception remains `/var/lib/shreks/risk` for existing G7
  safety controls;
- it remains loopback-only and independent of `shreks.target`.

No new write, execution, scoring, service-management, signing, submission, or
LIVE authority is added.

## RED acceptance

Tests require:

1. Fast Lane config is optional when all keys are absent;
2. partial Fast Lane config fails closed;
3. exact complete Fast Lane config parses safely;
4. unknown dashboard keys still fail closed;
5. Fast Lane source calls all three sealed collectors with the same bounded
   window and explicit release identity;
6. cross-document release/window/identity drift fails closed;
7. authenticated `/api/v1/fast-lane` returns composed evidence;
8. unconfigured route returns `FAST_LANE_UNAVAILABLE`;
9. source failures return generic 503 without sensitive details;
10. mutation methods cannot reach Fast Lane data;
11. page contains the Fast Lane panel and same-origin fetch;
12. page renders authoritative action/EV/latency/cost/outcome fields;
13. no profitability/action/execution formula is implemented in browser JS;
14. existing safety-control endpoints/behavior remain unchanged;
15. dashboard source contains no scoring, PAPER execution, checkpoint writes,
    systemd/subprocess/network-provider, signing/submission, or LIVE authority.

## Following slice

Proceed to FL10.3 restart reconstruction: prove Fast Lane rolling learned state,
pending BUY/open PAPER positions, execution cursor, and idempotency recover
across process/host restart without duplicate economic actions.

Then collect FL10.4 physical resource-headroom evidence under real event bursts.

LIVE remains disabled.
