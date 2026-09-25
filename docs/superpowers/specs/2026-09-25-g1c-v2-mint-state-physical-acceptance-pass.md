# G1C V2 Mint-State Physical Acceptance — Production PASS

**Date:** 2026-09-25  
**Accepted release SHA:** `816e7c6591d216369b60f893cc5dfe5785e88652`  
**Sealed release-bound verifier PR:** #519  
**Merged-main CI:** `36177523799`  
**Immutable release build:** `36177781254`  
**Protected deploy/verify:** `36178349929`

## Gate closure

The exact sealed release deployed successfully and the protected read-only
mint-state verifier returned physical acceptance `PASS` on an
exact-release-bound evidence window.

The acceptance result was:

```text
g1c_v2_mint_state_acceptance_status=PASS
g1c_v2_mint_state_selected_observations=2
g1c_v2_mint_state_proactive_refreshes=1
g1c_v2_mint_state_missing_selected=0
g1c_v2_mint_state_missing_later_observed=0
g1c_v2_mint_state_missing_unresolved=0
g1c_v2_mint_state_stale_selected=0
g1c_v2_mint_state_invalid_observations=0
g1c_v2_mint_state_reconstructed_checkpoints=1
g1c_v2_mint_state_max_selected_age_ms=346499
g1c_v2_mint_state_max_missing_followup_delay_ms=none
g1c_v2_paper_evidence_completed_cycles=3
g1c_v2_paper_evidence_provider_failures_last_cycle=0
g1c_v2_helius_requests_attempted=1
g1c_v2_helius_requests_limit=500
g1c_v2_helius_requests_remaining=499
g1c_v2_helius_budget_exhausted=false
g1c_v2_mint_state_physical_acceptance=PASS
```

This closes the physical mint-state acceptance conditions defined by the
existing acceptance seal:

- selected point-in-time mint state was present for every sampled PAPER
  observation;
- no selected mint state was stale under the unchanged 900,000 ms B1 ceiling;
- no sampled observation was invalid;
- at least one qualifying proactive pre-expiry refresh was physically observed;
- provider failures were zero for the current evidence cycle;
- Helius budget was not exhausted;
- no database, filesystem, sudo, or manifest authority widening was used.

The maximum selected mint-state age was 346,499 ms, below both the unchanged
900,000 ms B1 ceiling and the point at which the sample would have become
stale.

## Release-bound attribution

This PASS is materially different from the earlier failed cross-release
samples.

The active release includes the sealed release-bound verifier control. Its
effective analysis window is clamped to the active PAPER-evidence process start,
so the PASS does not rely on pre-release decisions or on waiting for an old
30-minute wall-clock window to age out.

The accepted release remained exact through:

- release identity verification;
- release-local service/process verification;
- protected manifest-manager status;
- protected telemetry bridge execution;
- runtime-status authority validation;
- historical checkpoint replay.

## Concurrent production state

The same protected verifier proved:

```text
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
fl9_v2_discovery_status=FOUND_COMPATIBLE
```

The exact release also contains the reviewed G1C V2 candidate/preflight/
authority/authoring/transition/readiness/rotation tools and the FL9 V2
discovery-backed request-preparation tool.

`FOUND_COMPATIBLE` is discovery evidence only. It does not itself execute
request preparation, candidate-value preflight, candidate-value decision,
candidate authoring, manifest rotation, scoring/model fitting, champion
publication, PAPER promotion, or LIVE.

## Next boundary

The mint-state physical gate is closed.

The next repository work may continue only through the existing explicit
G1C/FL9 authority sequence. Any trusted-admin ceremony must remain bound to the
exact active release and authenticated source authority before publishing new
evidence.

Do not reinterpret this PASS as permission to skip:

- discovery-authority/request provenance;
- candidate-value preflight;
- explicit candidate-value decision;
- candidate authority;
- candidate authoring/staging;
- transition binding;
- rotation readiness/plan;
- explicit manifest rotation;
- separate scoring/model-fitting authorization;
- champion/promotion proof.

## Explicit non-authority

```text
G1C_V2_MINT_STATE_PHYSICAL_ACCEPTANCE=PASS
B1_MAX_CRITICAL_DATA_AGE_MS=900000_UNCHANGED
PAPER_MINT_STATE_REFRESH_AGE_MS=540000_DERIVED_OPERATIONAL
PAPER_EVIDENCE_COLLECTION=UNCHANGED
PAPER_CANDIDATE_SELECTION=UNCHANGED
HISTORICAL_POINT_IN_TIME_REPLAY=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
LEARNED_ACTION_PROMOTION=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```

This is a production-evidence record only. Its commit/PR must remain non-`seal:`
so recording the PASS does not create a new immutable release and reopen the
exact-release physical acceptance gate.
