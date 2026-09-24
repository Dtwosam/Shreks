# G1C V2 PAPER Mint-State Pre-Expiry Headroom Seal

**Date:** 2026-09-24  
**Integration SHA:** `61302828cf0621783fc5801c886597b7dd0c4651`  
**PR:** #487  
**Merged-main CI:** `36061943104`

## Residual defect proven physically

The previous mint-state freshness repair correctly refreshed stale existing Helius
mint-state evidence, but production acceptance exposed a residual scheduling race.

Production runtime:

- evidence interval: 60 seconds;
- evidence candidate limit: 2;
- authenticated B1 max critical-data age: 900,000 ms;
- Helius request budget: 500 per process;
- provider failures: zero;
- budget exhaustion: zero.

Three PAPER evaluations consumed mint-state rows just after the B1 boundary:

- candidate 1381030: 921,299 ms old, 21,299 ms past expiry;
- candidate 1381414: 1,041,462 ms old, 141,462 ms past expiry;
- candidate 1381335: 915,016 ms old, 15,016 ms past expiry.

All three received successful Helius mint-state refreshes after the decision,
roughly 50.8--54.9 seconds later. Helius timestamps mint-state evidence at actual
request/observation time, so this was not a source-timestamp artifact.

Point-in-time reconstruction of the evidence selector proved all three candidates
had already been selected for PAPER evidence before their mint-state row expired.
At the last useful selected evidence cycle, remaining B1 lifetime was:

- 1381030: 57,318 ms;
- 1381414: 313,233 ms;
- 1381335: 311,999 ms.

Therefore provider availability and selector reachability were sufficient in the
observed cases. The remaining defect was that mint refresh waited until evidence
was already stale.

## Sealed repair

No new manifest or host policy threshold is introduced.

The PAPER evidence runtime derives proactive refresh timing from existing
authorities:

```
scheduler_headroom_ms = 6 * evidence_cycle_interval_ms
bounded_headroom_ms = min(
    scheduler_headroom_ms,
    mint_state_max_age_ms / 2,
)
mint_state_refresh_age_ms =
    mint_state_max_age_ms - bounded_headroom_ms
```

For the active production configuration:

- evidence cycle interval = 60,000 ms;
- scheduler headroom = 360,000 ms;
- half B1 max age = 450,000 ms;
- bounded headroom = 360,000 ms;
- proactive mint refresh age = 540,000 ms;
- B1 safety validity remains 900,000 ms.

A selected evidence candidate with an exact Helius mint row no older than
540,000 ms suppresses the chain call. Once the row is older than 540,000 ms, one
refresh attempt is made through the existing bounded Helius provider.

The half-age cap prevents a large evidence interval from consuming more than
half of the authenticated B1 evidence lifetime as proactive headroom.

## Boundary semantics

The evidence collection boundary and B1 safety boundary are intentionally
different:

- exactly 540,000 ms old: collector still treats the row as inside the proactive
  window and suppresses refresh;
- 540,001 ms old: collector requests one proactive refresh;
- B1 itself continues to treat evidence as valid through its unchanged
  900,000 ms maximum age.

No B1 evaluator threshold was changed.

## RED / GREEN evidence

RED head: `7cdcd82ab5ed5a786d4201b6275ebbb9c758111e`

CI run `36061292543`:

- Rust tests: FAIL;
- repository safety: PASS;
- ARM64 release build: PASS.

The Rust failure was the intended regression: `PaperEvidenceRuntimeConfig`
had no `mint_state_refresh_age_ms()` behavior.

Final GREEN head: `397af58695052e6ae9bb6a913dfd615c67cd895d`

CI run `36061536414`:

- Rust tests: PASS;
- Python tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Merged integration SHA:
`61302828cf0621783fc5801c886597b7dd0c4651`

Merged-main CI run `36061943104`:

- Rust tests: PASS;
- Python tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Physical acceptance required

After immutable release/deploy:

- deployed release SHA equals this seal commit;
- protected G1C V2 manifest SHA remains
  `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`;
- services remain healthy and release-local;
- startup runtime reports
  `mint_state_max_age=900000ms` and
  `mint_state_refresh_age=540000ms`;
- selected PAPER evaluations have no mint-state-only
  `CRITICAL_DATA_STALE` blocker;
- proactive mint refreshes are observed before the 900,000 ms B1 boundary;
- provider failures remain fail-closed;
- Helius budget remains unexhausted;
- historical point-in-time replay remains unchanged.

## Explicit non-authority

```
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_EVIDENCE_CANDIDATE_LIMIT=2_UNCHANGED
PAPER_EVIDENCE_SELECTOR_ORDER=UNCHANGED
HOLDER_REFRESH_SEMANTICS=UNCHANGED
JUPITER_QUOTE_SEMANTICS=UNCHANGED
FEATURE_SCHEMA_VERSION=B2_V1_UNCHANGED
PAPER_THRESHOLDS=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

No scoring, model fitting, threshold relaxation, promotion, signing, wallet, or
LIVE authority is granted by this seal.
