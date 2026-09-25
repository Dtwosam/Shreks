# G1C V2 PAPER Evidence Runtime-Status Physical Acceptance Repair

**Date:** 2026-09-25  
**Branch:** `fix/g1c-v2-paper-evidence-runtime-status`  
**Base / deployed release:** `bd51b53f59f3dea1761be61c3b70ee1a80a3f72a`

## Physical failure

The sealed mint-state physical-acceptance bridge deployed successfully, but the
production verifier failed before issuing the protected acceptance request:

```text
g1c_v2_mint_state_acceptance_bridge=available
g1c_v2_mint_state_runtime_thresholds=mismatch
```

The failure reproduced on a verifier-only rerun.

The deployed release is exact, the three PAPER services are active with zero
restarts, the manifest manager reports `MATCHED_CURRENT_RELEASE`, and the
deployed source still derives:

```text
max_critical_data_age_ms = 900000
evidence_cycle_interval_ms = 60000
mint_state_refresh_age_ms = 540000
```

The mismatch is therefore in the verifier's observation channel. The deploy SSH
identity can execute `journalctl`, but prior successful production verification
already showed that it cannot be relied on to expose service payload lines. The
new gate incorrectly treated a visibility-limited journal as an authoritative
runtime-status source.

No database, group, sudoers, or journal permission will be widened to repair
this.

## Repair

Add one private, derived PAPER-evidence runtime-status sidecar:

```text
/var/lib/shreks/telemetry/paper-evidence-status.json
```

It is written by the already-authorized `shreks-paper-evidence` process and
read only by the already-authorized `shreks` telemetry control processor.

The deploy verifier never reads the file directly.

## Status contents

The status document contains only secret-free operational values:

- schema name/version;
- state: `STARTED` or `CYCLE_COMPLETE`;
- process start timestamp;
- generated timestamp;
- completed-cycle count and last cycle timestamp;
- configured evidence interval;
- authenticated B1 mint-state max age;
- derived proactive mint-state refresh age;
- last-cycle aggregate provider-failure count;
- Helius process request attempted/limit/remaining counts;
- Helius process-budget exhausted boolean;
- last-cycle selected-candidate and stored-mint counts;
- explicit observational/non-authority markers.

No API key, provider URL, wallet, manifest body, candidate mint, checkpoint
payload, or arbitrary provider error text is written.

## Write semantics

The PAPER evidence daemon writes a `STARTED` status after configuration and
provider-budget construction, then atomically replaces it after each completed
evidence cycle.

The write path:

- uses a temporary regular file in the same private telemetry directory;
- creates it mode `0600`;
- writes canonical JSON plus one newline;
- fsyncs the file;
- atomically renames it to the final path;
- keeps failures nonfatal to PAPER evidence collection.

A status-write failure is an observability failure only. It does not stop the
evidence collector, mutate PAPER state, or grant any trading authority. Physical
acceptance cannot pass while the status is unavailable or invalid.

## Telemetry control validation

The existing G1C V2 mint-state acceptance control reads the sidecar only after:

1. the deploy-owned request marker is trusted;
2. the request is bound to the exact active immutable release;
3. the protected PAPER runtime configuration is resolved.

The control validates:

- regular non-symlink file;
- owner is the current `shreks` UID;
- mode `0600`;
- bounded size and stable read;
- exact schema/key set;
- `CYCLE_COMPLETE` with at least one completed cycle;
- generated timestamp is not future-dated and is recent relative to the
  configured evidence cadence;
- sidecar evidence interval matches the same runtime environment consumed by
  telemetry;
- sidecar B1 max age matches the authenticated campaign manifest;
- sidecar proactive refresh age equals the sealed derivation;
- provider failures for the most recently completed cycle are zero;
- Helius budget is positive, internally consistent, and not exhausted.

Only the validated, bounded runtime-status fields are returned in the sanitized
control result.

## Verifier change

Remove hard dependency on deploy-user journal payload visibility for:

- startup threshold strings;
- PAPER evidence provider-failure counts;
- Helius process-budget counters.

The journal remains a best-effort diagnostic source for generic runtime restart
and SQLite-contention signatures.

The verifier instead requires the protected control result to prove:

```text
runtime_status.state=CYCLE_COMPLETE
runtime_status.evidence_cycle_interval_ms=60000
runtime_status.mint_state_max_age_ms=900000
runtime_status.mint_state_refresh_age_ms=540000
runtime_status.provider_failures_last_cycle=0
runtime_status.helius_budget_exhausted=false
runtime_status.helius_requests_limit>0
runtime_status.helius_requests_remaining>0
```

The existing historical acceptance analysis remains unchanged:

- selected observation rows are reconstructed point-in-time;
- missing/stale/invalid selected mint evidence fails;
- a qualifying pre-expiry Helius refresh is required for `PASS`;
- clean evidence without a qualifying refresh remains
  `HOLD_INSUFFICIENT_EVIDENCE`.

## TDD

RED tests must require:

1. a Rust runtime-status writer module and main-daemon integration;
2. mode-0600 canonical atomic status output with no credential fields;
3. startup and completed-cycle status semantics;
4. Python control validation of exact status schema/config/budget/provider
   invariants;
5. stale, future, malformed, exhausted-budget, and non-zero-provider-failure
   status rejection;
6. verifier uses the protected control runtime status rather than hard-failing
   on PAPER evidence journal strings;
7. no new sudo, group, ACL, database permission, strategy, scoring, execution,
   promotion, signer, submission, wallet, or LIVE authority.

## Non-authority

```text
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_EVIDENCE_COLLECTION=UNCHANGED_EXCEPT_DERIVED_STATUS_WRITE
DATABASE_SCHEMA=UNCHANGED
JOURNAL_PERMISSION_WIDENING=FORBIDDEN
DATABASE_PERMISSION_WIDENING=FORBIDDEN
SUDO_AUTHORITY_WIDENING=FORBIDDEN
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
