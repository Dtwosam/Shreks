# FL4 Covered Event Population — Design

**Date:** 2026-09-05
**Base:** `4d1e90603a654374d5f87c13cbe923d81c59109f`

## Status

Follow-on slice after #215 added durable realtime coverage sessions.

Physical FL9 proof previously established that the production database had 11,172,394 canonical
FastEvents but no FL4 labels and therefore no FL8.1 training population. #215 repaired the missing
coverage truth prospectively.

FL9 remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Goal

Add one bounded, deterministic, coverage-authenticated FL4 population writer that can turn canonical
FastEvents into genuine decision opportunities and persist the sealed FL4 v1 multi-horizon labels
without inventing coverage, strategy selection, execution economics, or capital authority.

The population is event-driven: every canonical FastEvent inside the explicit covered decision
window is a decision opportunity.

## Why event population

The project source of truth requires:

- `EVENT -> UPDATE STATE -> ... -> CHOOSE ACTION`;
- reevaluation whenever meaningful events arrive;
- learning from all observed opportunities and SKIPs;
- no future-outcome filtering of the decision population.

Therefore the population writer must not select only events that later won, only baseline BUYs, or
only historical PAPER actions.

## Explicit immutable coverage session

The caller supplies one durable `coverage_session_id`.

The requested session must be historical/immutable:

`coverage_session_id < MAX(fast_realtime_coverage_sessions.session_id)`

The current latest session is rejected because it may still extend and change
`coverage_complete_through_unix_ms` after labels are written.

Process restart/reconnect/provider switch already creates a new session under #215, so the prior
session becomes immutable naturally.

## Explicit decision window

The caller supplies:

- `from_observed_at_unix_ms` inclusive;
- `through_observed_at_unix_ms` inclusive;
- `maximum_decisions` positive integer.

The full requested window must lie inside the chosen immutable coverage session:

`session.first <= from <= through <= session.last`.

The writer counts canonical FastEvents in the window before any label write.

It fails before writing if:

- count is zero;
- count exceeds `maximum_decisions`;
- the coverage session is missing, latest/mutable, or ambiguous;
- bounds are invalid.

This is the operational guard against accidentally launching an 11M-event labeling job.

## Horizons

Use the sealed:

`DEFAULT_FUTURE_PATH_HORIZONS_MS`

exactly:

`250ms, 500ms, 1s, 3s, 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h`.

The caller does not adapt horizons after seeing outcomes.

The coverage supplied to FL4 is:

- `complete_through_unix_ms = selected_session.last_notification_observed_at_unix_ms`;
- `contiguous = true`.

Therefore short horizons can be complete while longer horizons near the end of the session remain
truthfully incomplete.

## Decision identity

For every canonical event in the window:

- market = exact FastEvent market;
- event id = exact signature + ordinal;
- sequence = exact canonical durable sequence;
- observed timestamp = exact canonical observation time;
- executable entry price = exact canonical FastEvent price;
- optional entry total quote = **None** in this slice.

The observed market participant's trade size is not treated as Shreks' hypothetical decision size.

## Execution economics

This slice does not fabricate historical execution assumptions.

Future observations therefore preserve:

- canonical price/path events;
- route availability = unknown;
- exit capacity = unknown;
- executable net exit quote = unknown.

As a result:

- raw endpoint/path/MFE/MAE/reversal targets can become available;
- route/capacity/cost-adjusted targets remain unavailable unless a later source-backed economics
  annotation slice supplies them.

This limitation is explicit and preferable to contaminating training with current constants or
another trader's size.

## Efficient market replay

Do not call `fast_events_for_market` once per decision.

The writer:

1. preflights event count;
2. finds distinct markets in the decision window;
3. loads each canonical market replay once through the existing conflict-quarantine-aware API;
4. selects decision events from that replay;
5. uses deterministic bounds within the already-loaded replay for future observations.

This avoids quadratic whole-market database replay.

## Atomicity and idempotency

The population write runs inside one SQLite savepoint.

Any error rolls back every FL4 row from that invocation.

Existing exact rows remain idempotent through `record_future_path_label`.

A rerun against the same immutable session/window must produce no conflicting mutation.

## Report

Return/print a machine-readable report containing at least:

- schema name/version;
- FL4 label version;
- coverage session id;
- coverage provider;
- decision window;
- coverage complete-through timestamp;
- decision count;
- inserted label count;
- already-existing label count;
- minimum/maximum decision sequence;
- exact sealed horizon list.

No wall-clock selection or outcome-derived field is added to the population identity.

## CLI

Add a Rust binary:

`shreks-fast-populate-future-path-labels`

Arguments:

- `--database`
- `--coverage-session-id`
- `--from-observed-at-unix-ms`
- `--through-observed-at-unix-ms`
- `--maximum-decisions`

The command writes only FL4 derived evidence into the supplied database.

## Authority boundary

No:

- strategy threshold;
- baseline BUY filter;
- future-outcome population filter;
- PAPER fill/ledger mutation;
- risk or sizing authority;
- model training;
- champion promotion;
- signing;
- transaction submission;
- LIVE authority.

## Following work

After this slice is sealed and deployed:

1. let the VPS accumulate at least two coverage sessions so the first is immutable;
2. choose one explicit covered chronological window;
3. populate genuine FL4 labels;
4. inspect label counts/completeness;
5. add source-backed cost/capacity annotations for the targets that remain unknown;
6. rerun the sealed FL8.1 proof workspace only when enough mature evidence exists.

LIVE remains disabled.
