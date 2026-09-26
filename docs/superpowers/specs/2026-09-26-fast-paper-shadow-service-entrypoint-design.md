# Fast PAPER Learned Shadow Service Entrypoint — Design

**Date:** 2026-09-26  
**Base main SHA:** `a6d06607ed3d2ae975c5cc427b13fe83384bc173`  
**Parent plan:** `docs/superpowers/plans/2026-09-26-fast-lane-learned-paper-runtime-migration.md`

## Goal

Add the first separately supervised learned Fast PAPER shadow service entrypoint on top of the already merged canonical feature feed, restart-safe shadow decision orchestration, and persisted quote resolver.

This slice remains decision-shadow only. It does not mutate the authoritative PAPER ledger, execute a shadow ledger, replace the legacy PAPER campaign, join `shreks.target`, fetch providers, sign, submit, or enable LIVE.

## Exact runtime path

For each bounded cycle the service must:

1. authenticate the exact `FastPaperRuntimeManifest` and current runtime state;
2. fetch unseen canonical `FastTrainingFeatureRecord` rows with `fetch_fast_paper_runtime_feature_batch(...)`;
3. resolve the exact observer candidate id from persisted ENTRY quote evidence matching the record mint/quote mint, manifest provider, service quote identity, decision chronology, and freshness window using read-only/query-only SQLite; reject missing or ambiguous attribution;
4. construct a `FastPaperShadowQuoteReadPolicy` from one canonical service policy;
5. call `resolve_fast_paper_shadow_cycle_input(...)` so ENTRY/EXIT economics come only from persisted observer quote evidence;
6. evaluate each row as a FLAT entry-opportunity shadow posture in this slice;
7. commit each row through `run_fast_paper_shadow_batch(...)` before advancing to the next row;
8. preserve the existing per-record evidence-before-cursor restart ordering;
9. stop the cycle on the first unresolved row without advancing that row's cursor.

The service must not rebuild quote economics, action constraints, forecasts, or champion inference itself.

## Service policy

Add one canonical private JSON policy with schema:

`shreks.fast_paper_shadow_service_policy` version `1`.

It contains only:

- `route_evidence_version`;
- `probe_policy_version`;
- `taker`;
- `slippage_bps`;
- `entry_input_amount_raw`;
- `exit_input_amount_raw`;
- `max_quote_age_ms`;
- `max_exposure_fraction`.

The route-evidence version must equal the runtime manifest. No price, score, forecast, result, position, prebuilt action constraint, future label, counterfactual, wallet, signing, submission, or LIVE field is permitted.

Reduction reads are empty because this first supervised service slice evaluates only FLAT entry opportunities. OPEN/HOLD/REDUCE/SELL posture continuity remains deferred until an isolated shadow position/ledger authority is explicitly designed.

## Configuration

The service reads only:

- `SHREKS_FAST_PAPER_RUNTIME_MANIFEST_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_SERVICE_POLICY_PATH`;
- `SHREKS_FAST_PAPER_SHADOW_EVIDENCE_DIRECTORY`;
- optional bounded cadence and batch-size settings.

The manifest remains the authority for champion/binary identity, observer DB, runtime checkpoint, provider, quote mint/decimals, and route-evidence version.

## Preflight

`python -m shreks_brain.fast_paper_runtime.shadow_service --preflight` must authenticate:

- manifest and bound release artifacts;
- existing checkpoint when present;
- service policy;
- observer database readability;
- shadow evidence directory separation from authoritative PAPER evidence.

Preflight must not fetch a feature batch, run inference, resolve quote rows, or write runtime state/evidence.

## systemd boundary

Package `deploy/systemd/shreks-fast-paper-shadow.service`.

It must:

- run as `shreks:shreks`;
- use the immutable release Python;
- use a dedicated `/etc/shreks/fast-paper-shadow.env`;
- write only under `/var/lib/shreks/fast-paper-shadow`;
- depend only on observation/evidence availability, never on the legacy campaign lifecycle;
- contain no `PartOf=shreks.target`, `WantedBy=shreks.target`, or legacy paper-campaign lifecycle directive;
- not be added to `deploy/systemd/shreks.target`.

The unit is packaged but not auto-enabled by this slice.

## Authority boundary

```text
SCORING_CONTROL_PATH=FORBIDDEN
PROVIDER_NETWORK_ACCESS=FORBIDDEN
OBSERVER_DATABASE=READ_ONLY
SHADOW_POSTURE=FLAT_ENTRY_OPPORTUNITY_ONLY
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
AUTHORITATIVE_PAPER_EXECUTION=NOT_GRANTED
SHADOW_LEDGER_EXECUTION=NOT_GRANTED
SYSTEMD_CUTOVER=NOT_GRANTED
LIVE=DISABLED
```

## RED acceptance

The RED contract requires:

- the new `shadow_service` module and public service API;
- direct composition of the merged feature-feed, persisted-quote resolver, and restart-safe shadow batch APIs;
- no raw/prebuilt execution economics or action constraints in the service policy;
- read-only exact candidate attribution;
- fail-closed per-record processing with no failed-row cursor advance;
- preflight with no decision-side effects;
- a separate hardened systemd unit;
- no membership in `shreks.target`;
- no scoring, legacy decision, PAPER ledger mutation, provider-network, transaction, signing, submission, or LIVE authority.

Current main is expected to fail because the service module and systemd unit do not exist.
