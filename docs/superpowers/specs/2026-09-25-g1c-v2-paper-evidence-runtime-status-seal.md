# G1C V2 PAPER Evidence Runtime-Status Seal

**Date:** 2026-09-25  
**Integration SHA:** `383143cd6f3d8060cfa5d6177cd32461f715689c`  
**PR:** #491  
**Merged-main CI:** `36078418896`

## Physical failure

Immutable release
`bd51b53f59f3dea1761be61c3b70ee1a80a3f72a`
installed successfully on the production PAPER host, and all protected PAPER
services remained active with zero restart signatures.

The production verifier then failed at:

```text
g1c_v2_mint_state_acceptance_bridge=available
g1c_v2_mint_state_runtime_thresholds=mismatch
```

The deployed Rust source still logged the expected fields and the authenticated
runtime authorities still derived:

```text
evidence_cycle_interval_ms=60000
mint_state_max_age_ms=900000
mint_state_refresh_age_ms=540000
```

The failure was therefore the observation channel: the deploy SSH identity can
query unit state but cannot be treated as authoritative for protected service
journal payload visibility.

No journal, database, group, ACL, sudoers, or protected-state permission was
widened.

## Sealed repair

The PAPER evidence process now publishes a private operational sidecar at:

`/var/lib/shreks/telemetry/paper-evidence-status.json`

The status is written only by the existing `shreks-paper-evidence` process and
read only through the existing `shreks` telemetry control boundary.

The deploy verifier never reads the protected sidecar directly.

## Exact release binding

The release-local Python launcher resolves the real immutable
`shreks-paper-evidence` binary beneath the release tree, extracts the exact
40-character release source SHA, and injects it into the child process as an
internal derived value.

The Rust status document carries that exact `release_source_sha`.

The protected telemetry control rejects the status unless its release SHA equals
the exact active immutable release already authenticated by the control request.

A recent status file from a previous release therefore cannot satisfy the gate.

## Runtime-status evidence

The status document contains only bounded secret-free operational values:

- exact immutable release source SHA;
- schema name/version;
- state: `STARTED` or `CYCLE_COMPLETE`;
- process start and generation timestamps;
- completed cycle count and last cycle timestamp;
- evidence cycle interval;
- authenticated B1 mint-state maximum age;
- derived proactive mint-state refresh age;
- latest completed-cycle aggregate provider failure count;
- Helius request attempted/limit/remaining counts;
- Helius budget exhausted flag;
- latest selected-candidate and stored-mint counts;
- explicit non-authority markers.

No provider credential, provider URL, wallet material, candidate mint,
manifest body, checkpoint payload, arbitrary provider error, signer, or
transaction data is written.

## Persistence contract

Runtime status persistence is:

- private mode `0600`;
- canonical compact JSON plus one newline;
- written to a same-directory temporary regular file;
- flushed and fsynced;
- atomically renamed over the previous status;
- parent directory fsynced;
- nonfatal to PAPER evidence collection if the observability write itself fails.

A status-write failure therefore cannot mutate PAPER behavior. It only prevents
physical acceptance from passing.

## Protected validation

The G1C V2 mint-state acceptance telemetry control now validates:

- trusted deploy-owned request marker;
- exact active release binding;
- authenticated PAPER runtime configuration;
- regular non-symlink runtime-status file;
- current `shreks` ownership;
- exact `0600` mode;
- bounded file size and stable read;
- canonical JSON and exact key set;
- exact runtime-status release SHA match;
- `CYCLE_COMPLETE` with at least one completed cycle;
- sane process/cycle/generation timestamp ordering;
- bounded freshness relative to the evidence cadence;
- exact evidence interval match;
- exact authenticated B1 mint-state maximum age match;
- exact sealed proactive refresh derivation match;
- zero latest-cycle provider failures;
- positive, internally consistent Helius request budget;
- unexhausted Helius budget with remaining capacity.

Only sanitized validated fields are returned to the deploy verifier.

## Verifier behavior

The production verifier no longer hard-fails on deploy-user visibility of PAPER
evidence journal payload lines for:

- startup threshold strings;
- provider failure counts;
- Helius request budget counters.

Journal access remains best-effort for generic restart and SQLite-contention
diagnostics.

The protected telemetry result is now authoritative for the PAPER evidence
runtime values and process health relevant to this gate.

Historical mint-state acceptance semantics are unchanged:

- point-in-time selected candidates are reconstructed from authenticated
  checkpoints and the exact active campaign manifest;
- missing, future, contradictory, or B1-stale selected mint evidence fails;
- a qualifying pre-expiry Helius refresh is required for `PASS`;
- a clean window without a qualifying example remains
  `HOLD_INSUFFICIENT_EVIDENCE`.

## RED / GREEN evidence

Initial RED branch head:
`3c425fae860ec455f6360ffe92ad1e2368483adb`

The RED tests required a runtime-status writer and protected reader that did not
yet exist.

Final GREEN head:
`7bb590873075d7a662c0974b3bbfd8f85b8f244f`

CI run `36077827465`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`383143cd6f3d8060cfa5d6177cd32461f715689c`

Merged-main CI run `36078418896`:

- Python tests: PASS;
- Rust tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Physical acceptance required

After immutable release and protected deployment of this seal:

1. deployed release SHA equals this seal commit;
2. protected PAPER services remain active with zero unexpected restarts;
3. PAPER manifest-manager status remains release-matched;
4. the protected acceptance result carries runtime status bound to the exact
   deployed release SHA;
5. runtime status proves:
   - `evidence_cycle_interval_ms = 60000`;
   - `mint_state_max_age_ms = 900000`;
   - `mint_state_refresh_age_ms = 540000`;
   - `provider_failures_last_cycle = 0`;
   - `helius_budget_exhausted = false`;
   - `helius_requests_remaining > 0`;
6. historical mint-state analysis reports:
   - `selected_missing_mint_count = 0`;
   - `selected_stale_mint_count = 0`;
   - `invalid_observation_count = 0`;
7. physical acceptance reports `PASS` only after at least one qualifying
   proactive refresh transition is present.

`HOLD_INSUFFICIENT_EVIDENCE` is healthy evidence but does not close the
physical acceptance gate.

## Explicit non-authority

```text
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_MINT_STATE_REFRESH_FORMULA=UNCHANGED
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

No strategy threshold, scoring, model fitting, manifest rotation, promotion,
wallet, signing, submission, or LIVE authority is granted by this seal.
