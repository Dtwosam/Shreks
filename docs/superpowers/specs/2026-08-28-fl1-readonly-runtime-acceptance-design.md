# FL1.5 Read-Only Runtime Acceptance Design

## Purpose

Provide a deterministic, read-only way to measure whether the merged FL1 Pump/PumpSwap ingestion path is producing timely, replayable production evidence on the real Shreks host before FL2 begins.

CI can prove software behavior. It cannot prove real provider event rate, real host latency, storage growth, CPU/RAM headroom, or reconnect behavior. FL1.5 therefore separates database-derived evidence from host/operator evidence and refuses to treat either one as the other.

## Safety boundary

The acceptance path must:

- open the existing SQLite database with `SQLITE_OPEN_READ_ONLY | SQLITE_OPEN_NO_MUTEX`;
- never create a missing database;
- never execute migrations;
- never write rows, checkpoints, controls, or telemetry state;
- make no network/provider calls;
- have no wallet, signing, transaction-construction, submission, PAPER, risk, strategy, or LIVE authority;
- fail closed on missing required FL1 schema or invalid timing evidence.

FL2 remains blocked until the real production host has produced and retained FL1.5 evidence.

## Database acceptance report

A standalone `shreks-fast-lane-acceptance` binary reads an explicit inclusive/exclusive observation window `[window_start_unix_ms, as_of_unix_ms)` and emits stable `key=value` output suitable for operator capture and diffing.

The report includes:

- window start/end and duration;
- database file size and WAL file size observed from filesystem metadata;
- raw Pump events observed in the window;
- raw PumpSwap events observed in the window;
- canonical FastEvents accepted in the window;
- current pending Pump raw rows;
- current pending PumpSwap raw rows;
- canonical journal sequence-integrity violations;
- source latency summary for raw direct events: chain occurrence -> first local source observation;
- normalization latency summary for canonical events: source observation -> canonical acceptance;
- end-to-end latency summary for canonical events: chain occurrence -> canonical acceptance.

Each latency summary records sample count plus exact nearest-rank p50/p95/p99 and maximum milliseconds. Empty samples remain explicitly absent rather than fabricated as zero latency.

## Window semantics

Raw event counts and raw source-latency samples are selected by each raw row's `observed_at_unix_ms`.

Canonical counts and canonical latency samples are selected by `fast_events.observed_at_unix_ms` because that is the information-usable acceptance clock.

The report rejects:

- negative window timestamps;
- `as_of_unix_ms <= window_start_unix_ms`;
- source observations that precede their chain occurrence time;
- canonical acceptance that precedes either source observation or chain occurrence;
- malformed required integer fields;
- missing/invalid required tables or columns.

## Pending semantics

Pending counts are current backlog counts across the whole database, not only the requested report window. A pending raw row is one whose `(signature, ordinal)` has no canonical `fast_events` row.

The first acceptance slice reports backlog count only. It does not invent a reason for a pending row when the durable schema cannot prove whether the cause is missing decimals, missing PumpSwap lifecycle mapping, or another unresolved prerequisite.

## Sequence integrity

The reporter validates that canonical sequence starts at 1 and is contiguous in ascending order. Any gap or invalid first sequence is an acceptance integrity violation.

Duplicate raw deliveries discarded by the immutable `INSERT OR IGNORE` boundary are not preserved as durable rows, so the database reporter cannot truthfully count attempted reconnect duplicates. Reconnect/duplicate-delivery behavior must be captured separately from runtime logs/host observation while confirming that durable identities remain deduplicated.

## Filesystem evidence

The reporter reads metadata for the database path and `<db>-wal` path when present. This provides a point-in-time storage-size observation without modifying SQLite state.

It does not claim CPU, RAM, or network headroom from database evidence.

## Verified release availability

Production acceptance must use the reporter from the same immutable verified release mechanism as the running Shreks services.

New FL1.5 release bundles build and stage `target/release/shreks-fast-lane-acceptance`, include it in the sealed manifest, and therefore subject it to the existing archive/hash/tree verification path. The reporter is an allowed optional payload at the manifest-schema level so older already-sealed releases remain valid rollback points; the current FL1.5 build script is what makes it mandatory for newly built acceptance-capable releases.

A production evidence set is invalid if the reporter is locally compiled, copied outside the verified release, absent from `RELEASE_MANIFEST.json`, or comes from a different source SHA than `/opt/shreks/current`.

## Host acceptance evidence

The production runbook requires operators to capture, alongside the database report:

- service status and restart count;
- process CPU and RSS during normal flow and an observed burst;
- host memory/storage headroom;
- database/WAL growth across a measured interval;
- provider/reconnect log evidence;
- start/end timestamps for the acceptance observation period;
- immutable current-release path, manifest, and source SHA.

Those measurements must come from the actual production host. CI fixtures are not substitutes.

## Output contract

The binary emits stable plain-text `key=value` lines and exits non-zero on invalid arguments, missing database/schema, SQL failure, or integrity/timing violations.

The output contains no API keys, wallet secrets, signing material, or full raw event payloads.

## Exit gate

FL1.5 is complete only when:

1. the reporter, verified-release packaging, and runbook are merged with full Rust/Python/safety/ARM64 CI green;
2. the reporter is present in the exact production `RELEASE_MANIFEST.json` and run from that immutable release against the real production FL1 database in read-only mode;
3. host CPU/RAM/storage/reconnect evidence is captured for the same observation period;
4. event-rate and latency evidence is reviewed for enough capacity/headroom to proceed;
5. no unexplained canonical gaps or invalid timing rows exist.

Until then, FL2 must not begin and LIVE remains disabled.
