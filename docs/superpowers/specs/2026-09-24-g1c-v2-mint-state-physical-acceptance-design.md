# G1C V2 PAPER Mint-State Physical Acceptance Design

**Date:** 2026-09-24  
**Branch:** `fix/g1c-v2-mint-state-physical-acceptance`  
**Base:** `f888a1d68783bf49a3abcedebeb9d36a3d4b4fe7`

## Problem

The deployed immutable PAPER release already contains the mint-state pre-expiry
headroom repair, and release/deploy verification proves exact-release identity
plus immediate service health. That verifier cannot read the protected
operational SQLite evidence as the deploy SSH identity, so it cannot prove the
behavioral physical-host gate required by the seal.

The missing proof is specifically:

- PAPER evidence runtime is configured with B1 max age 900000 ms and proactive
  mint refresh age 540000 ms;
- selected PAPER candidates do not consume Helius mint-state evidence older than
  the unchanged 900000 ms B1 limit;
- at least one selected candidate receives a Helius mint refresh while the prior
  row is older than 540000 ms but not yet older than 900000 ms;
- provider failures remain fail-closed and the Helius process budget is not
  exhausted.

Widening the deploy user's database permissions or sudo authority is not
acceptable merely to collect this evidence.

## Reused authority boundary

Reuse the existing G4 telemetry control pattern:

1. the deploy verifier creates one canonical request marker and one deploy-owned
   result-exchange directory under `/dev/shm`;
2. `shreks-telemetry.service`, already running as `User=shreks`, processes the
   request read-only;
3. the processor binds the request to the exact active release;
4. it reads the protected PAPER manifest and operational SQLite database through
   existing read-only decoders/readers;
5. it publishes only a bounded sanitized result into the pre-created exchange;
6. the deploy verifier reads that result without receiving direct database
   access.

No new sudoers entry, group membership, database mode change, or protected-state
write is introduced.

## Acceptance analysis

The analyzer operates over one caller-bounded historical window and the active
manifest's exact `paper_run_id`.

It must:

- open SQLite with `mode=ro` and `PRAGMA query_only=ON`;
- enumerate only the current run's C6 PAPER checkpoints inside the requested
  window, plus the immediately preceding state required for replay;
- authenticate/decode checkpoint payloads with the existing C6 decoder;
- reconstruct each selected candidate set with
  `assemble_observer_paper_campaign_cycle` using the exact active manifest and
  the prior checkpoint state;
- for each selected candidate, read only point-in-time Helius mint-state rows
  whose observation time is no later than the reconstructed decision time;
- fail the acceptance result if any selected candidate's latest available
  Helius mint-state row is absent or older than B1
  `max_critical_data_age_ms`;
- identify proactive refresh evidence when two consecutive Helius mint rows for
  a selected candidate have an observation gap strictly greater than the derived
  proactive refresh age and no greater than the unchanged B1 max age.

The proactive age is derived from existing authorities, matching the Rust
runtime:

```text
scheduler_headroom_ms = 6 * paper_evidence_cycle_interval_ms
bounded_headroom_ms = min(
    scheduler_headroom_ms,
    max_critical_data_age_ms / 2,
)
mint_state_refresh_age_ms =
    max_critical_data_age_ms - bounded_headroom_ms
```

No acceptance request may supply or override the safety threshold.

## Result states

The sanitized result is one of:

- `PASS`: at least one qualifying proactive refresh was observed, at least one
  selected PAPER observation was reconstructed, and no selected mint row was
  missing or beyond B1 expiry;
- `HOLD_INSUFFICIENT_EVIDENCE`: reconstruction is valid and no stale/missing
  selected mint row was observed, but the window has not yet produced a
  qualifying proactive-refresh example;
- `FAILED`: release binding, request trust, checkpoint integrity, replay,
  schema, attribution, or selected mint freshness is invalid.

The result reports bounded counts and ages only. It does not emit provider
credentials, manifest contents, checkpoint payloads, wallet data, or arbitrary
exception text.

## Runtime log proof

The GitHub verifier remains responsible for journal-only operational checks:

- the PAPER evidence startup line contains
  `mint_state_max_age=900000ms` and
  `mint_state_refresh_age=540000ms`;
- recent PAPER evidence cycle lines do not report non-zero
  `provider_failures`;
- recent cycle lines do not report
  `helius_budget_exhausted=true`.

The acceptance-control result and journal checks are complementary. Neither
changes trading authority.

## TDD / integration

RED tests first must require:

1. the read-only analyzer module and exact result status semantics;
2. a proactive refresh gap in `(refresh_age, max_age]` produces `PASS`;
3. no qualifying gap produces `HOLD_INSUFFICIENT_EVIDENCE`;
4. missing or B1-stale selected mint evidence produces `FAILED`;
5. future mint rows never satisfy historical selection;
6. database bytes/mtime are unchanged by analysis;
7. the telemetry runtime processes and publishes the new control independently
   from FL9 discovery controls;
8. the production verifier contains the request/result exchange and journal
   assertions without sudo or direct database permission widening.

## Non-authority

```text
B1_MAX_CRITICAL_DATA_AGE_MS=UNCHANGED
PAPER_MINT_STATE_REFRESH_FORMULA=UNCHANGED
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
