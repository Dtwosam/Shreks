# Fast Lane PAPER Shadow FL10.4 Resource Headroom — Design

**Date:** 2026-09-27  
**Base main SHA:** `51f2f253934e38972e5b343fb930a217903819d9`

## Purpose

Close the repository side of FL10.4 by adding one bounded, read-only physical
measurement command for the already-detached Fast Lane PAPER-shadow service.

The command measures the real running supervisor during an operator-chosen
decision-activity window and records enough host-capacity evidence to calculate
CPU, memory, filesystem, and private-network headroom without inventing a
performance pass threshold.

This slice does not generate synthetic load, tune runtime settings, change
systemd state, mutate PAPER state, fetch providers, sign or submit
transactions, or enable LIVE.

## CLI

Extend the existing trusted-administrator physical commissioning CLI with:

```text
shreks-fast-paper-shadow-physical-commission headroom \
  <expected-release-sha> \
  --observe-seconds <5..900> \
  --minimum-decisions <positive-integer>
```

The explicit minimum is an observation qualifier chosen by the operator for the
target burst. It is not a profitability or performance threshold.

The command succeeds only when the bounded window contains at least that many
authenticated Fast Lane decision-evidence records.

## Preconditions

The command requires:

- effective uid 0;
- exact active immutable release;
- completed protected-host readiness;
- an existing successful physical activation receipt for the same release;
- detached/non-enabled healthy shadow systemd state;
- exact supervisor process provenance;
- stable PID/InvocationID/restart counter during the observation;
- private network namespace with no non-loopback interface.

A previous successful headroom receipt for the same release makes the command
fail closed rather than overwrite evidence.

## Activity evidence

The measurement window reuses the exact start timestamp and duration from the
physical process observation.

After the window closes, the command invokes the existing sealed read-only
Fast PAPER shadow decision telemetry collector over that same interval.

It records:

- authenticated decision-evidence count;
- decision-evidence rate per second;
- decision telemetry fingerprint;
- event-to-evaluation p95;
- decision-latency p95;
- exact manifest/champion/action-policy identity.

The physical observation identity and decision telemetry identity must match.

`decision_evidence_rate_per_second` remains decision evidence throughput, not
a claim about raw observer events/sec.

## Host capacity evidence

Read only:

- logical CPU count from the host runtime;
- `MemTotal` from `/proc/meminfo`;
- filesystem capacity/available blocks for the isolated shadow root;
- existing process CPU ticks/RSS;
- existing shadow-storage byte growth;
- existing private-network byte deltas;
- supervisor completed-cycle delta.

Derived evidence includes:

- process CPU percent in the existing one-core-percent convention;
- normalized host CPU utilization percent;
- CPU headroom percent;
- peak RSS as a percent of host memory;
- memory headroom bytes after peak RSS;
- shadow-filesystem available bytes/percent;
- shadow-storage growth bytes/sec;
- private-network RX/TX bytes/sec;
- completed supervisor cycles/sec.

The command rejects physically impossible measurements such as process CPU
above logical host capacity or RSS above total memory. It does not reject a
valid measurement merely because utilization is high.

## Evidence receipt

A successful measurement writes one canonical, root-private, no-replace
receipt:

```text
/root/shreks-fast-paper-shadow-commissioning/headroom-<release-sha>.json
```

The receipt retains:

```text
shadow_runtime=ACTIVE_DETACHED
shadow_enable_authority=NOT_GRANTED
production_paper_cutover=NOT_GRANTED
authoritative_paper_runtime=LEGACY_UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Acceptance

Repository tests must prove:

1. host logical CPU, total memory, and filesystem capacity are read and
   validated;
2. decision telemetry is collected from the exact configured shadow decision
   evidence directory and exact observation window;
3. a headroom measurement requires a successful activation receipt;
4. the operator-supplied positive minimum decision count is enforced;
5. runtime identity must agree between physical observation and decision
   telemetry;
6. CPU/RSS/storage/network/cycle rates and host headroom are derived from the
   measured values;
7. headroom collection performs no start/restart/enable/stop action;
8. the headroom receipt is canonical, root-private, and write-once;
9. production PAPER authority and LIVE remain unchanged;
10. Python, Rust, repository-safety, and ARM64 release gates stay green.

## Physical acceptance

Repository CI proves the collector boundary and arithmetic, not VPS capacity.

FL10.4 is physically complete only after a trusted administrator runs
`headroom` on the real production-paper VPS during a meaningful real
decision-activity burst and preserves the resulting receipt.

The resulting measurements are evidence for later optimization. No optimization
is authorized merely because a metric is present, and no synthetic threshold is
introduced to manufacture a PASS.

## Following slice

After physical FL10.4 evidence exists, FL10's runtime-integration exit criterion
can be reviewed as a whole. The next canonical build phase is FL11 shadow proof
and champion promotion evidence. LIVE remains disabled.
