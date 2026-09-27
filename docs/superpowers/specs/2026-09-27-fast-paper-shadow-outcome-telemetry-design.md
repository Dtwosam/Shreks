# Fast PAPER Shadow Outcome Telemetry — Design

**Date:** 2026-09-27  
**Base main SHA:** `ac5eb43ca0e2ab6afe48a62ebb99f73afef88e04`

## Purpose

Add the accounting/outcome half of FL10.2 telemetry over the isolated Fast PAPER
shadow ledger.

This slice is read-only. It authenticates the exact release-bound shadow ledger
and selects the latest canonical Fast PAPER checkpoint whose
`state_as_of_unix_ms` is inside the requested bounded window.

It reports terminal PAPER execution/accounting outcomes and cumulative ledger
health without changing decision, execution, checkpoint, systemd, PAPER
authority, or LIVE authority.

This slice intentionally does **not** yet claim:

- action-to-execution latency;
- expected-vs-realized slippage;
- pre-ledger abort attribution;
- raw observer events/sec.

Those require the following execution-source join slice.

## New read primitive

Add a read-only public checkpoint loader:

```python
load_fast_paper_checkpoint_at_or_before(
    database_path,
    run_id,
    as_of_unix_ms,
) -> FastPaperCheckpointRecord | None
```

It must:

- reuse the same table/schema namespace checks as the existing latest loader;
- select the highest checkpoint with
  `state_as_of_unix_ms <= as_of_unix_ms`;
- canonical-decode and checksum-verify the payload;
- require stored row metadata to match the decoded record;
- perform no writes.

Add the manifest/binding-aware shadow wrapper:

```python
load_fast_paper_shadow_ledger_checkpoint_at_or_before(
    manifest,
    binding,
    *,
    as_of_unix_ms,
) -> FastPaperCheckpointRecord | None
```

It must authenticate the persisted shadow binding and the returned state-policy
versions exactly as the existing latest loader does.

## CLI

Add:

```text
shreks-fast-paper-shadow-outcome-telemetry summarize \
  --manifest-path <path> \
  --ledger-database-path <path> \
  --run-id <id> \
  --expected-release-sha <40-hex> \
  --since-unix-ms <inclusive> \
  --until-unix-ms <exclusive>
```

Window rules:

- exact non-negative integer milliseconds;
- `since < until`;
- maximum 24 hours.

The selected checkpoint is the latest state with:

```text
state_as_of_unix_ms <= until_unix_ms - 1
```

If no such checkpoint exists, return a canonical empty telemetry document.

## Authentication

Before summarizing:

1. read the canonical runtime manifest;
2. verify all manifest artifact bindings;
3. require `manifest.release_source_sha == expected_release_sha`;
4. build the exact shadow ledger binding from explicit `run_id` and database
   path;
5. load/authenticate the selected checkpoint through the new shadow wrapper.

No direct unverified ledger object is accepted by the production CLI.

## Window entries

From the selected checkpoint's authoritative `PaperLedger.entries`, include
only entries satisfying:

```text
since_unix_ms <= booked_at_unix_ms < until_unix_ms
```

The checkpoint is cumulative, so the window selection is deterministic and does
not require a second database mutation or replay pass.

## Metrics

### Terminal execution/accounting counts

Expose exact counts for:

- `FAILED`;
- `PARTIAL`;
- `FILLED`;
- BUY;
- SELL;
- paper execution reason code;
- ledger reason code.

Expose:

- terminal ledger-entry count;
- fill count;
- failed execution count.

### Window economics

Expose totals for:

- filled notional USD;
- explicit cost USD;
- realized PnL delta USD;
- cash-flow USD.

For PARTIAL/FILLED entries with positive filled notional, expose deterministic
mean/p50/p95 of:

```text
explicit_cost_bps =
    explicit_cost_usd / filled_notional_usd * 10_000
```

This is realized **explicit** fee/network cost burden only. It does not claim
slippage.

### Cumulative ledger snapshot

Expose the selected checkpoint's:

- starting cash USD;
- cash balance USD;
- realized PnL USD;
- unrealized PnL USD or `null`;
- accumulated costs USD;
- open-position count;
- total-position count;
- total ledger-entry count;
- processed intent count.

Reuse `derive_paper_risk_accounting_facts(...)` to expose:

- rolling drawdown percent or `null`;
- consecutive losses;
- last-loss timestamp;
- aggregate open risk USD.

The day start supplied to that helper is the telemetry window start, so
`daily_realized_pnl_usd` is also emitted as an independently derived
cross-check of window-realized PnL when the selected checkpoint does not extend
past the requested window.

## Provenance

Expose exact:

- release SHA;
- manifest fingerprint;
- champion version/fingerprint;
- action-policy version;
- shadow ledger run id;
- binding fingerprint;
- selected checkpoint sequence/payload SHA;
- selected checkpoint state/creation timestamps;
- telemetry fingerprint.

## Empty result

If no checkpoint exists at or before the window end:

- counts/totals are zero;
- percentile fields are `null`;
- ledger snapshot fields are `null`;
- expected release SHA and requested window remain present;
- no profitability conclusion is emitted.

## Authority firewall

The implementation must not:

- import scoring;
- invoke score logic;
- execute PAPER actions;
- write checkpoints/ledger/runtime state;
- mutate systemd;
- use subprocess/network clients;
- sign/submit;
- enable LIVE.

## RED acceptance

Tests prove:

1. exact historical checkpoint selection works and is checksum/canonical safe;
2. shadow wrapper preserves persisted-binding and policy authentication;
3. explicit release identity is required;
4. window execution-state/side/reason counts are exact;
5. window notional/cost/PnL/cash-flow totals are exact;
6. realized explicit-cost bps summary is deterministic;
7. cumulative ledger PnL/cost/cash/position fields are exact;
8. rolling drawdown/loss/open-risk facts are reused, not reimplemented;
9. entries outside the requested window are excluded;
10. empty historical windows are canonical and safe;
11. output fingerprint covers the whole document;
12. CLI is packaged in the immutable release;
13. source contains no scoring, execution, write, systemd, network, signing,
    submission, or LIVE authority.

## Following slice

Join authenticated execution-source records to their exact pre-state and
successor checkpoint to expose:

- decision/action -> commit latency;
- decision/action -> booked fill latency;
- expected selected execution cost vs realized explicit cost + slippage;
- max-entry-price aborts;
- other pre-ledger abort/rejection evidence where the sealed executor/state
  makes attribution unambiguous;
- pending-BUY retry execution attribution.

Then adapt operator dashboard views toward Fast Lane action/EV/latency/economic
evidence.

Physical VPS activation/restart receipts are still required before FL10 can be
claimed physically accepted.
