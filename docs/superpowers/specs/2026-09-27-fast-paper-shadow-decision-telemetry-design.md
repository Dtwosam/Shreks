# Fast PAPER Shadow Decision Telemetry Rollup — Design

**Date:** 2026-09-27  
**Base main SHA:** `bcb55885c7c97b09dfde9b661d8c64262f2a9751`

## Purpose

Add the first durable FL10.2 Fast Lane telemetry surface over already-authenticated
shadow decision evidence.

The shadow runtime already writes one canonical
`FastPaperShadowDecisionEvidence` record per processed decision. Those records
contain the exact release/champion/action-policy identity plus:

- source/evaluation timestamps;
- measured Rust decision latency;
- selected action and reason;
- selected horizon;
- selected reward/risk/execution-cost/value;
- immutable evidence fingerprints.

This slice adds a read-only rollup CLI over those existing records. It does not
change decision/execution behavior, does not write trading state, does not alter
systemd, and does not grant PAPER cutover or LIVE authority.

This is intentionally only the **decision-evidence** portion of FL10.2. It does
not call its rate raw observer events/sec and does not claim state-update,
fill-latency, realized-slippage, or full FL10 telemetry complete.

## CLI

Add:

```text
shreks-fast-paper-shadow-decision-telemetry \
  summarize \
  --evidence-directory <path> \
  --expected-release-sha <40-hex> \
  --since-unix-ms <inclusive> \
  --until-unix-ms <exclusive>
```

The time window is required and bounded:

- exact non-negative integer millisecond timestamps;
- `since < until`;
- maximum window 24 hours.

The command is read-only.

## Evidence discovery

The evidence directory must be a regular non-symlink directory.

Decision evidence is selected only from regular non-symlink files named:

```text
shadow-<20 digit source sequence>-<16 lowercase hex>.json
```

The dedicated decision directory also contains the runtime checkpoint by
design, so other regular non-symlink files are ignored rather than mistaken for
decision evidence. Hidden members are likewise ignored because the existing
writer may temporarily create same-directory dot-prefixed staging files before
atomic publication.

Any directory member or symlink fails closed. A matching decision filename is
never ignored: it must decode successfully and its embedded source sequence
must match the filename.

Each selected file is decoded with the existing
`read_fast_paper_shadow_decision_evidence(...)` reader so canonical JSON,
schema, nested model validation, and evidence fingerprint checks are reused.

## Identity contract

Every selected record must agree on:

- `release_source_sha` equal to the explicit expected release SHA;
- manifest fingerprint;
- champion version;
- champion fingerprint;
- action-policy version.

Source sequences must be unique and strictly increasing after canonical sort.
Source event IDs and evidence fingerprints must also be unique.

A source-sequence gap is telemetry, not silently treated as an error, because a
window can begin/end between decisions or upstream evidence can legitimately
contain unselected sequence ranges. The rollup records:

- gap count;
- total missing sequence numbers between adjacent selected decision records.

Duplicates/conflicts fail closed.

## Metrics

The canonical rollup includes:

### Window/rate

- since/until timestamps;
- duration milliseconds;
- decision evidence count;
- decision evidence rate per second.

The rate is explicitly named `decision_evidence_rate_per_second`. It is not
raw event-ingestion throughput.

### Lag/latency

For each record:

```text
event_to_evaluation_lag_ms =
    evaluated_at_unix_ms - as_of_unix_ms

decision_latency_ms =
    decision_latency_ns / 1_000_000
```

Expose p50/p95/p99/max for both using deterministic nearest-rank percentiles.

### Actions

Expose exact counts for all five actions:

- BUY;
- SKIP;
- HOLD;
- REDUCE;
- SELL.

Also expose deterministic reason counts and selected-horizon counts.

### Decision economics

Expose mean/p50/p95 for:

- selected reward bps;
- selected risk bps;
- selected execution cost bps;
- selected value bps.

These are decision-model economics, not realized fill economics.

### Executability evidence

Expose counts for:

- entry quote unavailable;
- exit quote unavailable;
- BUY economically disallowed;
- SELL non-executable;
- force-sell constraint.

### Provenance

Expose exact:

- release SHA;
- manifest fingerprint;
- champion version/fingerprint;
- action-policy version;
- first/last source sequence;
- first/last as-of timestamp;
- source-sequence gap count/total;
- rollup fingerprint.

## Empty windows

An empty valid time window returns a canonical telemetry document with:

- count/rate zero;
- zero action/executability counts;
- empty reason/horizon maps;
- latency/economic percentile fields `null`;
- provenance fields that require evidence set to `null`.

The explicit expected release SHA is still retained.

This makes periodic collection safe even when no decision occurs during a
window.

## Output

Schema:

```text
schema_name = shreks.fast_paper_shadow_decision_telemetry
schema_version = 1
```

The CLI prints exactly one canonical JSON document with a self-fingerprint.

No output contains score/pass authority fields.

## Authority firewall

The source must not:

- import legacy scoring;
- invoke `score_candidate`;
- mutate PAPER ledgers/checkpoints/evidence;
- create/delete/rename decision evidence;
- call systemctl/subprocess/network clients;
- sign/submit;
- enable LIVE.

## RED acceptance

Tests prove:

1. canonical decision filename selection plus directory/symlink rejection;
2. canonical reader is reused;
3. explicit release identity is required;
4. mixed manifest/champion/action-policy identity fails closed;
5. duplicate source sequence/event/fingerprint fails closed;
6. deterministic source-sequence gaps are reported;
7. p50/p95/p99/max lag and inference latency are deterministic;
8. BUY/SKIP/HOLD/REDUCE/SELL counts are exact;
9. reason/horizon/economic/executability metrics are exact;
10. empty windows are canonical and safe;
11. output fingerprint authenticates the complete rollup;
12. CLI is packaged in the release;
13. source has no score, trading-state mutation, systemd, signing, submission,
    network, or LIVE authority.

## Following slice

After this decision telemetry is sealed, add execution/outcome telemetry over
the isolated shadow ledger and execution evidence:

- action-to-execution latency;
- max-entry-price/risk aborts where evidence supports it;
- expected-vs-realized fill/slippage/cost;
- position/action latency;
- PAPER PnL/drawdown/cost accumulation.

Then adapt the operator dashboard from legacy score/pass emphasis toward Fast
Lane action/EV/latency evidence.

Physical VPS acceptance remains pending until the trusted-admin activation and
restart receipts are produced on the real production-paper host.
