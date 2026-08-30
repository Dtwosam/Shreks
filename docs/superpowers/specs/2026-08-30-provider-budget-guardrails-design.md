# Provider Budget Guardrails Design

## Status

Production FL1.5 repair. LIVE TRADING remains disabled.

## Problem

Physical-host FL1.5 acceptance exposed two independent provider-consumption failures:

1. full-program Pump/PumpSwap WebSocket ingestion can consume metered provider quota at a rate incompatible with the project's free-source-first operating constraint;
2. the separate paper-evidence daemon repeatedly requests Helius holder-distribution evidence for the same candidate on successive cycles, while only mint-state evidence is currently freshness-suppressed.

The runtime correctly fails closed when realtime providers are unavailable, but it has no explicit provider-consumption budget and therefore can exhaust provider quota before its existing health logic reacts.

## Authority

This repair preserves the source-of-truth requirements that Shreks survive provider rate limits, measure cost burden, run read-only observation before later proof gates, and avoid a hidden paid-RPC requirement. It does not alter strategy, PAPER decision policy, wallet/signing authority, LIVE authority, FL2 authority, canonical event semantics, or evidence provenance.

## Goals

1. Make repeated Helius safety evidence bounded and freshness-aware.
2. Make provider HTTP consumption explicitly bounded per process from host configuration, with fail-closed exhaustion rather than silent overage.
3. Expose non-secret usage counters in runtime cycle output so production evidence can prove actual provider pressure.
4. Keep all provider keys/endpoints redacted.
5. Preserve existing provider ordering and provenance.
6. Leave the larger realtime-firehose redesign as a separate follow-up after this guardrail lands; this change must not pretend process-local HTTP budgets solve WebSocket push billing.

## Non-goals

- no provider plan upgrade;
- no paid infrastructure requirement;
- no new trading authority;
- no change to Pump/PumpSwap parsing or canonicalization;
- no relaxation of FL1.5 acceptance;
- no automatic restart of the currently stopped production services;
- no attempt to infer monetary cost from provider pricing inside consensus/runtime code.

## Design

### 1. Freshness-aware holder evidence

The paper-evidence collector will skip a holder-distribution request when durable holder evidence for the same candidate is newer than a caller-supplied minimum refresh interval. Unlike the current unconditional holder probe, the decision will be based only on SQLite evidence timestamps.

The paper-evidence runtime receives a new required host configuration value:

`SHREKS_PAPER_HOLDER_REFRESH_SECONDS`

It must be a positive integer. There is deliberately no permissive production default. The value is operational collection cadence, not strategy policy.

The candidate collector API receives a `holder_refresh_after_unix_ms` boundary. If current durable evidence exists at or after that boundary, holder-provider calls are suppressed for that candidate while quote evidence remains unaffected.

### 2. Helius HTTP request budget

The Helius adapter receives an optional in-memory request budget configured at construction. Every HTTP JSON-RPC request must reserve one request before transport. Exhaustion returns a fail-closed provider error without making the HTTP request.

The budget is a request-count guardrail, not a provider-credit accounting claim. The paper-evidence daemon and observer each receive explicit required/optional host-side limits appropriate to their process. A later cross-process/monthly ledger may tighten this further; this slice prevents unbounded loops now without adding another persistent subsystem.

New environment values:

- `SHREKS_OBSERVER_HELIUS_MAX_REQUESTS_PER_PROCESS` — optional positive integer; absent keeps current observer behavior for backwards compatibility until production configuration is updated.
- `SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS` — required positive integer for the paper-evidence daemon.

The paper-evidence daemon must refuse startup when its Helius request budget is missing or invalid. This prevents production evidence collection from silently running unbounded.

### 3. Usage telemetry

`HeliusProvider` exposes non-secret request-budget telemetry: attempted reservations, remaining requests when bounded, and whether the limit is bounded. API keys remain private. Paper-evidence cycle logs include the aggregate Helius request count consumed by that process since startup and whether the budget is exhausted.

### 4. Failure semantics

Budget exhaustion is a provider availability failure. Existing evidence semantics remain fail closed: missing evidence stays unknown; it is never converted into a safe fact. The process may continue selecting candidates/cycles, but provider calls after exhaustion are rejected locally and visible in failure counters. FL1.5 cannot pass while a required provider budget is exhausted.

### 5. Realtime follow-up boundary

This PR does not alter global Pump/PumpSwap WebSocket subscriptions because changing the ingestion topology can affect data completeness. Immediately after this guardrail PR is verified, a separate TDD change will replace the global PumpSwap subscription with candidate-focused realtime subscriptions while preserving Pump launch discovery, provenance, sequence integrity, and canonical completeness for tracked candidates.

## Testing

TDD coverage must prove:

1. Helius bounded provider permits requests up to the configured count and rejects the next request before transport.
2. Helius debug/telemetry never exposes the API key.
3. paper-evidence configuration rejects missing/zero/non-integer holder refresh and Helius budget values.
4. fresh durable holder evidence suppresses distribution-provider calls while stale/missing evidence permits them.
5. quote collection remains unchanged when holder evidence is fresh.
6. existing observer/provider/config suites remain green.
7. repository safety, Rust, Python, and ARM64 release-build CI remain green on the exact PR head.

## Production gate after merge

Do not restart production services merely because CI passes. First deploy/seal the exact release, set explicit host-side budgets, then run a short read-only sanity interval proving request counters remain within the configured budget. Realtime FL1.5 remains HOLD until the separate firehose redesign and physical acceptance both pass.
