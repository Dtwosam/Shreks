# G1C V2 PAPER Mint-State Freshness Seal

**Date:** 2026-09-24  
**Integration SHA:** `12d9da9c2b882ba86a81b613d69c8c83ef99dff0`  
**PR:** #486  
**Merged-main CI:** `36057065575`

## Proven production defect

Physical PAPER replay identified candidate `1340728` as the first clean
post-observability 9/9 Fresh Launch continuation case.

At decision time `1790274833523`:

- setup confirmations: 9/9;
- setup score: 78.2188;
- entry quote: EXECUTABLE;
- current market age: 9,439 ms;
- Helius holder-distribution age: 483,642 ms;
- Jupiter exit-quote age: 19,605 ms;
- Helius mint-state age: 28,641,760 ms;
- B1 `max_critical_data_age_ms`: 900,000 ms;
- safety: INCOMPLETE;
- safety blocker: `CRITICAL_DATA_STALE`.

Point-in-time provenance proved the mint-state row was the oldest consumed B1
input and the candidate had exactly one durable Helius mint-state row.

The existing PAPER evidence collector performed a chain mint-state probe only
when no durable row existed. Once any row existed, repeat chain calls were
suppressed forever. B1 safety, however, deliberately treats mint/freeze authority
state as critical evidence and marks the assessment incomplete when the oldest
consumed critical timestamp is older than the authenticated policy limit.

Therefore existence-cached mint state conflicted with B1 freshness semantics.

## Sealed repair

The release-local PAPER-evidence launcher now derives:

`SHREKS_PAPER_MINT_STATE_MAX_AGE_MS`

from the authenticated campaign manifest's exact
`policy_bundle.safety_policy.max_critical_data_age_ms`.

For every selected PAPER evidence candidate:

1. the evidence store checks for an exact Helius mint-state row whose
   `observed_at_unix_ms` is inside
   `[as_of - max_critical_data_age_ms, as_of]`;
2. if such a row exists, chain transport is suppressed;
3. if no such row exists, the existing bounded Helius chain provider receives
   one mint-state refresh attempt;
4. correctly attributed evidence is persisted through the existing
   `insert_mint_state` path;
5. provider failure or misattribution remains fail-closed and increments the
   existing chain-provider failure counter;
6. holder-distribution and Jupiter quote behavior remain unchanged.

Existing collector entry points preserve their historical behavior. The explicit
mint refresh control is used by the PAPER evidence cycle only.

The point-in-time boundary matches B1 exactly: a mint row at age equal to the
configured maximum remains fresh; only evidence older than the maximum requires
refresh.

## Authority source

The freshness value is not a new strategy or host-policy threshold.

The Python launcher authenticates the campaign manifest before process
replacement and projects the exact existing B1 field into the Rust child
environment in memory. No protected manifest bytes are edited.

For the active G1C V2 campaign the value remains:

`max_critical_data_age_ms = 900000`

## RED / GREEN evidence

RED head: `1ff3e441609ba8c276bdb22552daaf5bd6d00ebe`

CI run `36055756715`:

- Rust tests: FAIL;
- Python tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

The Rust failure was the intended regression:

`SafetyEvidenceCollector` had no
`collect_candidate_with_refresh_controls` method, proving the prior collector
could not refresh an existing stale mint-state row.

Final GREEN head: `814623cc9ec2ceed7827bebf1ae21146dfa28365`

CI run `36056534235`:

- Rust tests: PASS;
- Python tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

Behavioral coverage includes:

- stale existing mint state triggers one selected-candidate refresh;
- a mint-state row exactly at the B1 freshness boundary suppresses refresh;
- point-in-time freshness is restricted to Helius evidence;
- missing mint-state backfill semantics remain intact;
- zero `max_critical_data_age_ms` remains representable because B1 permits it;
- V1/V2 authenticated manifests derive the freshness authority;
- holder and quote evidence behavior remains intact.

Merged integration SHA: `12d9da9c2b882ba86a81b613d69c8c83ef99dff0`

Merged-main CI run `36057065575`:

- Rust tests: PASS;
- Python tests: PASS;
- ARM64 release build: PASS;
- repository safety: PASS.

## Physical acceptance required

After immutable release and production deployment:

- deployed release SHA equals this seal commit;
- protected G1C V2 manifest SHA remains
  `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`;
- `shreks-paper-evidence.service` final executable remains release-local Rust;
- observer, evidence, and campaign services remain active and healthy;
- launcher-derived `SHREKS_PAPER_MINT_STATE_MAX_AGE_MS` equals the authenticated
  B1 value 900000 in the final evidence process environment;
- for selected candidates with stale pre-existing Helius mint-state evidence,
  new Helius mint-state rows are observed when provider budget/transport succeeds;
- selected candidate B1 assessments no longer become INCOMPLETE solely because
  an existence-cached historical mint-state row is many multiples older than the
  authenticated B1 freshness limit;
- provider failures remain fail-closed;
- historical replay of candidate `1340728` at its old timestamp remains
  historically INCOMPLETE; the repair does not rewrite history.

## Explicit non-authority

```
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
MINT_STATE_FRESHNESS_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
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
