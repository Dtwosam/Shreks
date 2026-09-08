# FL8.3 Validation V2 Core — Merge/CI Seal

**Date:** 2026-09-08  
**Implementation main SHA:** `840a89eff349e888238305a3fb817730c04d991e`  
**Design/plan main SHA:** `6f77735a34d6f1e8a6419bb71c285786e45099da`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; NOT YET PHYSICALLY DEPLOYED

## Purpose

Seal the merged FL8.3 validation-v2 core after exact-head and merged-main CI proof, so the existing G2 release workflow can produce an immutable ARM64 release containing the V2 runtime code.

This seal authorizes release construction only. It does not authorize champion training, PAPER promotion, transaction execution, signing, submission, or LIVE trading.

## Merged scope

The merged implementation adds only the V2 validation package and its tests:

- `python/src/shreks_brain/fast_validation_v2/__init__.py`
- `python/src/shreks_brain/fast_validation_v2/models.py`
- `python/src/shreks_brain/fast_validation_v2/firewall.py`
- `python/src/shreks_brain/fast_validation_v2/population.py`
- `python/src/shreks_brain/fast_validation_v2/engine.py`
- V2 fixtures/tests under `python/tests/`

The sealed V1 package `shreks_brain.fast_validation` is behaviorally unchanged.

No collector, tradable-universe thresholds, risk, PAPER execution, wallet/signing, transaction submission, or LIVE-enablement code changed.

## V2 contract sealed by implementation

The merged implementation preserves:

- deterministic chronological train/validation/TEST intervals;
- future-label maturity at validation start;
- exact cross-partition transaction/signature quarantine;
- recurring mint retention;
- recurring actor retention;
- exact FL8.2 feature-schema identity firewall;
- no raw mint, actor, signature, provider, pool/pair, sequence/ordinal, or derived identity encoding as model input;
- natural future validation/TEST populations;
- unseen-mint novelty classification relative only to raw training;
- actor novelty as diagnostics only;
- null actor as an explicit diagnostic category;
- deterministic quarantine and novelty fingerprints;
- model/prediction/fold reconciliation;
- no database/network/PAPER/LIVE authority in the pure V2 validator.

## TDD evidence

The implementation was built with explicit RED -> GREEN stages for:

1. V2 immutable contracts;
2. feature identity firewall;
3. target-free population preparation;
4. V2 training/inference engine;
5. exact public API/authority seal;
6. final fold-result contradiction hardening.

Representative RED evidence included:

- missing `fast_validation_v2` package;
- missing firewall module;
- missing population module;
- missing engine module;
- missing V2 runner export;
- fold-result contradictions that were initially accepted and then made fail-closed.

Final tests additionally cover:

- giant mint↔actor connectivity retaining non-empty future populations;
- shared signatures quarantined from affected partitions;
- unseen mint relative only to training;
- recurring mint/actor retained;
- validation/TEST target mutations not affecting fit or predictions;
- all four sealed FL8.2 model families;
- null actor diagnostics;
- input-order invariant novelty/quarantine fingerprints;
- novelty identities exactly reconciling to prediction identities;
- prediction model/target/horizon matching the fitted artifact;
- prediction timestamps remaining inside the declared fold interval.

## Pre-merge exact-head CI

Reviewed implementation head before history cleanup:

`d788e7e8554b64c9b76d665421a25050da0be0b9`

Exact-head push CI:

- run `34272922117`
- Repository safety: SUCCESS
- Python tests: SUCCESS
- Rust tests: SUCCESS
- ARM64 release build: SUCCESS

Exact-head PR CI:

- run `34272924306`
- Repository safety: SUCCESS
- Python tests: SUCCESS
- Rust tests: SUCCESS
- ARM64 release build: SUCCESS

## Main-based retarget proof

After merging the approved design/plan, the feature branch was merged with current `main` without changing its tested content tree.

Cleaned feature head:

`0046bb3648e50b475953f9dfd0faf52509a02d38`

The retargeted diff against current `main` contained only the 11 intended V2 implementation/test files.

Fresh main-based push CI and PR CI both completed with all four gates SUCCESS before merge.

## Merged-main proof

Implementation PR #253 was squash-merged as:

`840a89eff349e888238305a3fb817730c04d991e`

Merged-main CI:

- run `34273786966`
- Repository safety: SUCCESS
- Python tests: SUCCESS
- Rust tests: SUCCESS
- ARM64 release build: SUCCESS

The automatic `Build sealed Shreks release` workflow for this implementation commit was skipped as designed because the commit subject was `feat:`, not `seal:`.

This documentation-only seal exists specifically to create a new main commit whose subject contains `seal`, while preserving the already-reviewed implementation tree plus this evidence note.

## Required next evidence

After this seal lands on `main`:

1. exact seal-main CI must succeed;
2. automatic `Build sealed Shreks release` must create immutable `shreks-<seal-sha>`;
3. release payload verification must succeed;
4. deployment to `production-paper` remains a separate protected/manual action;
5. physical VPS release identity must be proven before executing V2 host-side preflight;
6. the next host action is input-only immutable V2 acceptance evidence only.

No target values, future returns, model-quality metrics, PnL, or first-champion training may be used before that input-only acceptance step is frozen.

## Authority boundary

- FL8.3 V2 core merged: YES
- merged-main CI: PASS
- immutable release for this seal: PENDING
- production-paper deployment: NOT PROVEN
- physical VPS SHA: NOT PROVEN
- eligible identity fingerprint: NOT CREATED
- cohort floor accepted: NO
- final first-champion split: BLOCKED
- champion training: BLOCKED
- PAPER promotion: BLOCKED
- LIVE trading: DISABLED
