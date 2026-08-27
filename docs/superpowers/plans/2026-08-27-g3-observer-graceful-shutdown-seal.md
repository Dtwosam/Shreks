# G3 production seal — observer graceful shutdown during provider work

Date: 2026-08-27

## Purpose

Seal the runtime fix for the production observer stop failure where `shreks-observe.service` received its configured interrupt signal but remained blocked inside in-flight provider work until systemd's 30-second stop deadline expired and SIGKILL was required.

This is a Phase G3 supervision/restart correctness fix. It does not change trading strategy, safety, risk, paper execution economics, or LIVE authority.

## Production evidence that motivated the change

The production VPS was running sealed release:

- `f4a08e18e238fb58ffa21992ace797678779ddc3`

Two observer stops reproduced the same failure mode:

- `2026-08-27 20:36:06 UTC` stop requested; at `20:36:36` systemd reported `State 'stop-sigterm' timed out`, sent SIGKILL, and recorded `status=9/KILL` / `Result=timeout`.
- `2026-08-27 20:42:07 UTC` stop requested; at `20:42:37` the same 30-second timeout and SIGKILL occurred.

The service unit already used the intended runtime contract:

- `KillSignal=SIGINT`
- `TimeoutStopSec=30s`

Manual observer-only recovery then returned the unit to `active/running`, while the PAPER campaign remained durable and continued advancing. The new PAPER mint-state evidence path also continued producing correctly attributed mint-state, holder, and Jupiter quote evidence with zero provider failures in the supplied healthy cycles.

The failure was therefore not a missing signal or lost durable state. The runtime was not making shutdown selectable while provider work was in flight.

## Root cause

Both observer loops only honored shutdown between complete cycles:

1. the legacy `Observer::run_until_shutdown` directly awaited `run_cycle()`;
2. Observer V2 `HighResolutionSampler::run_until_shutdown` directly awaited `run_cycle_at()` after its one-second scheduler tick.

If SIGINT arrived while discovery, market, chain, transaction, pacing, or other cycle work was awaiting an external provider, the shutdown future could not win until that whole cycle returned. A sufficiently slow or stuck provider call could therefore outlive systemd's stop deadline.

Increasing `TimeoutStopSec` would only hide this defect, so the service timeout was deliberately left unchanged.

## Sealed behavior

PR #66, `fix: make observer shutdown preempt in-flight provider work`, merged as:

- merge commit: `9e2c051bc0d37c05e3da20ea1238b544cf1e98b9`
- final PR head: `a7d6e47d95ef32aea417b0bb8183de7580a6fd24`

Behavior:

1. `Observer::run_until_shutdown` races each full `run_cycle()` against shutdown.
2. `HighResolutionSampler::run_until_shutdown` races each `run_cycle_at()` against shutdown.
3. When shutdown wins, the in-flight cycle future is cancelled instead of blocking service termination.
4. An interrupted cycle is not counted as completed.
5. Observer V2 still flushes its durable sampling registry before returning from the shutdown path.
6. The existing inter-cycle shutdown behavior remains intact.
7. `KillSignal=SIGINT` remains unchanged.
8. `TimeoutStopSec=30s` remains unchanged.

## TDD evidence

Focused regressions use a discovery provider that signals when its request is definitely in flight and then never returns.

Required behavior:

- legacy observer shutdown must preempt that in-flight provider call;
- V2 sampler shutdown must preempt that in-flight provider call;
- V2 must still persist its durable registry checkpoint after cancellation;
- interrupted work must not increment the completed-cycle count.

RED evidence:

- CI run `33115281963` reproduced the legacy in-flight shutdown hang on the pre-fix runtime.
- CI run `33115427679` reproduced the V2 in-flight shutdown hang as well.

During the GREEN pass, the V2 test itself exposed a test-harness issue: combining Tokio's paused auto-advancing clock with a timeout assertion could advance directly to the timeout before the shutdown wake was observed. The responsiveness regression was corrected to use wall-clock elapsed time. The production runtime fix did not change for that correction.

GREEN feature-branch verification:

- final branch head: `a7d6e47d95ef32aea417b0bb8183de7580a6fd24`
- push CI run: `33116078873`
- Rust/workspace GREEN
- Python GREEN
- repository safety GREEN
- native ARM64 release build GREEN

GREEN PR verification:

- PR #66 CI run: `33116238855`
- Rust/workspace GREEN
- Python GREEN
- repository safety GREEN
- native ARM64 release build GREEN

Merged-main verification:

- merge commit: `9e2c051bc0d37c05e3da20ea1238b544cf1e98b9`
- CI run: `33116371685`
- Rust/workspace GREEN
- Python GREEN
- repository safety GREEN
- native ARM64 release build GREEN

## Scope audit

Changed runtime code:

- `crates/shreks-observer/src/lib.rs`
- `crates/shreks-observer/src/bin/observer_v2/sampler.rs`

Added focused regressions:

- `crates/shreks-observer/tests/shutdown_inflight.rs`
- `crates/shreks-observer/tests/shutdown_sampler_inflight.rs`

Unchanged:

- strategy/setup thresholds
- safety vetoes
- score/decision thresholds
- risk sizing and loss/drawdown controls
- PAPER fill economics
- PAPER evidence candidate bounds
- wallet/signing/submission authority
- LIVE enablement
- systemd stop signal
- systemd stop timeout

## Production promotion boundary

This seal establishes code-level and native-ARM64 build proof for the corrected shutdown contract. It does **not** substitute for physical VPS acceptance.

After deploying this seal, production acceptance must demonstrate at minimum:

1. the new source SHA is the active `/opt/shreks/current` release;
2. a real `systemctl restart shreks-observe.service` or release-manager stop/start completes without the 30-second timeout;
3. no observer SIGKILL / `status=9/KILL` appears for that acceptance restart;
4. the observer returns to `active/running` and resumes observation;
5. the PAPER campaign/evidence state remains durable and advances after restart;
6. the normal `shreks.target` release activation path can stop and start the runtime cleanly.

A physical-host acceptance failure blocks promotion and must be treated as a runtime defect rather than worked around by increasing the stop timeout.

**LIVE TRADING: DISABLED.**
