# G1C V2 PAPER Mint-State Physical Acceptance Seal

**Date:** 2026-09-25  
**Integration SHA:** `5fbeeb4f1dd8ba42636d56bbbd7a4a78a458b7c4`  
**PR:** #489  
**Merged-main CI:** `36074572248`

## Purpose

The deployed G1C V2 PAPER mint-state pre-expiry repair already derives a
540,000 ms proactive Helius refresh boundary from the unchanged 900,000 ms B1
critical-data age limit.

The remaining gate is physical acceptance on the production host. The deploy
SSH identity intentionally cannot read the protected PAPER SQLite/checkpoint
evidence, so acceptance must not be achieved by widening database, group, sudo,
or filesystem authority.

This seal adds a release-bound, read-only evidence bridge through the existing
telemetry service authority and extends the production verifier to consume only
sanitized acceptance results.

## Sealed acceptance path

The production verifier now:

1. verifies the exact immutable release and existing PAPER service health;
2. confirms the PAPER evidence runtime startup reports:
   - `mint_state_max_age=900000ms`;
   - `mint_state_refresh_age=540000ms`;
3. rejects recent non-zero provider-failure evidence;
4. rejects Helius process-budget exhaustion;
5. creates a canonical deploy-owned request marker and mode-0733 result exchange
   under `/dev/shm`;
6. waits for `shreks-telemetry.service`, running as `shreks`, to perform the
   protected read-only historical analysis;
7. verifies the result is canonical, owned by `shreks`, bound to the exact
   release SHA, and explicitly grants only read-only observation authority.

The verifier does not receive direct SQLite permission, sudo authority, or
protected manifest write authority.

## Historical analyzer

The acceptance analyzer:

- decodes the authenticated active PAPER campaign manifest;
- opens the operational SQLite database with `mode=ro` and
  `PRAGMA query_only = ON`;
- reads only the active `paper_run_id` checkpoints in the requested bounded
  window plus the immediately preceding state;
- validates checkpoint checksum/envelope integrity through the sealed C6
  decoder;
- reconstructs each historical selected candidate set through
  `assemble_observer_paper_campaign_cycle` using the exact manifest policy and
  prior PAPER state;
- reads only Helius mint-state rows at or before each reconstructed decision
  timestamp;
- rejects a selected candidate when its point-in-time mint state is missing,
  future-dated, contradictory, or older than the unchanged B1 maximum;
- counts one proactive refresh transition when consecutive Helius mint rows for
  a selected candidate have a gap in
  `(mint_state_refresh_age_ms, max_critical_data_age_ms]`.

For production:

```text
evidence_cycle_interval_ms = 60000
max_critical_data_age_ms = 900000
scheduler_headroom_ms = 6 * 60000 = 360000
bounded_headroom_ms = min(360000, 450000) = 360000
mint_state_refresh_age_ms = 900000 - 360000 = 540000
```

No acceptance request can override the B1 safety threshold.

## Acceptance status semantics

The sanitized analyzer result is:

- `PASS` when the bounded window reconstructs selected PAPER observations,
  finds at least one qualifying proactive refresh transition, and finds no
  missing/stale/invalid selected mint-state evidence;
- `HOLD_INSUFFICIENT_EVIDENCE` when the reconstructed window is clean but has
  not yet produced a qualifying proactive-refresh example;
- `FAILED` when release binding, request trust, runtime authority, checkpoint
  integrity, historical replay, attribution, or selected mint-state freshness
  fails closed.

`HOLD_INSUFFICIENT_EVIDENCE` is deliberately non-promotional. It does not
satisfy the physical acceptance gate and does not authorize manifest rotation,
scoring, model fitting, PAPER promotion, or LIVE.

## Trust boundary

The request/result transport reuses the FL9 telemetry control pattern:

- request marker must be canonical JSON, regular/non-symlink, mode 0644,
  bounded in size, and owned by `shreks-deploy`;
- request is bound to the exact active release and bounded in age/window;
- result exchange must be a real mode-0733 directory owned by
  `shreks-deploy`;
- result is written once by `shreks`, mode 0644, canonical JSON, and size
  bounded;
- arbitrary exception text is not emitted;
- protected database contents, checkpoint payloads, manifest contents,
  credentials, and wallet data are not returned.

When no mint-acceptance request exists, the telemetry path is inert and does not
require PAPER evidence interval configuration or emit a control line.

## RED / GREEN evidence

Initial RED head:
`6c1a3c6480d3cec865dbbb1fc105fbceb9f98e73`

CI run `36066256895`:

- Python tests: FAIL as intended because the acceptance analyzer module did not
  yet exist;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Final GREEN head:
`8b50d5b814782ff98e61b3a38f54e45f448d2ecc`

CI run `36068901830`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`5fbeeb4f1dd8ba42636d56bbbd7a4a78a458b7c4`

Merged-main CI run `36074572248`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

The implementation diff is confined to:

- production verification workflow;
- acceptance design/seal documentation;
- telemetry acceptance analyzer/control bridge/runtime hook;
- acceptance and integration tests.

No strategy, scoring, risk, PAPER execution, wallet, signer, transaction
submission, or LIVE implementation changed.

## Physical acceptance required

After immutable release and deployment of this seal:

- deployed release SHA must equal this seal commit;
- the protected G1C V2 campaign manifest remains unchanged;
- observer, PAPER evidence, PAPER campaign, and telemetry services remain
  healthy and release-local;
- the PAPER evidence startup line proves
  `mint_state_max_age=900000ms` and
  `mint_state_refresh_age=540000ms`;
- recent PAPER evidence cycles show no provider-failure escalation and no Helius
  budget exhaustion;
- the read-only acceptance result is exact-release-bound and reports `PASS`;
- `selected_missing_mint_count = 0`;
- `selected_stale_mint_count = 0`;
- `invalid_observation_count = 0`;
- `proactive_refresh_count >= 1`;
- no filesystem/database permission widening is used to obtain that proof.

A `HOLD_INSUFFICIENT_EVIDENCE` deployment verification is healthy but does not
close this gate. The gate closes only when a later read-only verifier run
observes `PASS`.

## Explicit non-authority

```text
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_MINT_STATE_REFRESH_FORMULA=UNCHANGED
PAPER_EVIDENCE_SELECTOR=UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
DATABASE_PERMISSION_WIDENING=FORBIDDEN
SUDO_AUTHORITY_WIDENING=FORBIDDEN
OBSERVATION_AUTHORITY=READ_ONLY
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No scoring, model fitting, threshold relaxation, promotion, signing, wallet, or
LIVE authority is granted by this seal.
