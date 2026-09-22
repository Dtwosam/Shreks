# G1C V2 Decision-Backed Rotation Plan Production Presence — Release Seal

**Date:** 2026-09-22  
**Decision-backed rotation-plan implementation main SHA:** `ca99ea797414fc5144c14a85931cff3bcdc7eb28`  
**Production-presence implementation main SHA:** `64f81d66f200ae0e3a47938ccbef41a105754af7`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF ROTATION-PLANNER TOOL PRESENCE ONLY; AUTOMATIC PLANNER EXECUTION DISABLED; MANIFEST ROTATION/SCORING/PROMOTION/LIVE BLOCKED

## Purpose

Seal the read-only decision-backed protected PAPER rotation planner together with exact-release production-presence proof.

The planner sits between evidence-only decision-backed readiness and the existing protected-rotation authority boundary.

It authenticates the exact candidate, standard transition binding, decision-backed candidate authority, canonical `READY_EVIDENCE_ONLY` readiness receipt, and exact current release. It re-checks the installed manager, active source, runtime environment contract, deployment sudoers, G7 state, service observations, and the absence of the binding-named rotation evidence directory.

If every check is stable, it emits one canonical rotation-plan artifact containing the exact future trusted-admin manager argv.

The planner does not execute that argv.

This seal deploys planner presence only.

It does not execute planning and does not authorize manifest rotation.

## Current production state before this seal

The latest immutable GitHub release remains:

`shreks-26d07f7b8b977328a8ae63d782d0968342cfacc5`

Production verification for that release proved:

- helper installation-proof refresh CLI/module are exact-release-local;
- `paper_manifest_manager_status=MATCHED_CURRENT_RELEASE`;
- protected FL9 discovery remains `HOLD_NO_COMPATIBLE`.

The decision-backed rotation-plan implementation merge:

`ca99ea797414fc5144c14a85931cff3bcdc7eb28`

completed merged-main CI successfully.

Its release workflow `35748690945` and deploy workflow `35748699573` skipped by design because the main commit subject was not `seal:`.

The production-presence implementation merge:

`64f81d66f200ae0e3a47938ccbef41a105754af7`

completed merged-main CI successfully.

Its release workflow `35750727194` and deploy workflow `35750737764` skipped by design because the main commit subject was not `seal:`.

Therefore production has not yet received the decision-backed rotation-plan CLI/module.

No rotation plan has been automatically created.

No helper proof refresh, decision-backed readiness proof, or manifest rotation has been automatically executed.

## Decision-backed rotation-plan implementation

Implementation main SHA:

`ca99ea797414fc5144c14a85931cff3bcdc7eb28`

Final GREEN implementation head:

`6283566c816a13f2bb005289e581053de2395a7b`

CLI:

`shreks-g1c-v2-decision-backed-rotation-plan`

Module:

`shreks_brain.g1c_v2_decision_backed_rotation_plan`

Inputs are limited to:

- exact canonical v2 candidate runtime manifest;
- exact canonical standard transition binding;
- authenticated decision-backed candidate authority;
- canonical successful decision-backed readiness receipt;
- explicit exact expected immutable release SHA.

The CLI accepts no operator-supplied binding fingerprint and no raw candidate economics, run identity, timestamp, candidate-value decision, review, or sizing values.

The planner requires root because it observes protected production state.

It authenticates candidate/binding/authority/readiness provenance and requires the readiness receipt to remain:

```text
status=READY_EVIDENCE_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

It then rechecks read-only:

- current immutable release;
- exact installed manager bytes/metadata;
- protected active source manifest;
- candidate and transition binding;
- runtime environment path contract;
- deployment sudoers;
- G7 operator-control revision/halt/kill state;
- observer/PAPER evidence/PAPER campaign service observations;
- absence of `/var/lib/shreks/manifest-rotations/<binding-fingerprint>`.

All supplied artifact bytes and mutable host observations are rechecked for stability before a plan is returned.

Success emits:

`shreks.g1c_v2_decision_backed_rotation_plan` version 1

with:

```text
status=READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY
planning_authority=READ_ONLY
manifest_rotation_authority=NOT_EXERCISED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The plan contains exactly one future manager argv:

```text
/usr/local/sbin/shreks-paper-manifest-manager
rotate
<exact-candidate-path>
<exact-binding-path>
<binding-fingerprint>
<exact-release-sha>
```

and records that the planner did not execute it.

## TDD and implementation proof

### Decision-backed rotation planner

Intentional RED PR #424 head:

`3489889cc71657127e17766152e0fdad4b20d6a8`

RED CI:

`35747374970`

Result:

- Python failed at collection because `shreks_brain.g1c_v2_decision_backed_rotation_plan` did not yet exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN implementation head:

`6283566c816a13f2bb005289e581053de2395a7b`

Push CI:

`35747943552`

Independent PR CI:

`35747976403`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`ca99ea797414fc5144c14a85931cff3bcdc7eb28`

Merged-main CI:

`35748400633`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED PR #426 head:

`b6437f026d1dfbbd85865b71dd92fb584d3146ba`

RED CI:

`35748899772`

Result:

- Python: exactly 1 failed, 3645 passed, 2 known warnings;
- the only failure was the intentionally absent decision-backed rotation-plan production-presence surface;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

The first GREEN attempt in PR #427 exposed one contradictory static test assertion that globally forbade the same verifier variable required by the contract's own regular/executable presence checks.

That branch was discarded rather than merged.

The corrected branch was rebuilt from the same clean parent as one commit. The contradictory assertion was removed while explicit non-execution guards remained.

Final GREEN production-presence head:

`58483909a9ecf22ca1ad6a0ca853e2b137aef4b3`

Push CI:

`35749829676`

Independent PR CI:

`35750044072`

Both: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged production-presence main:

`64f81d66f200ae0e3a47938ccbef41a105754af7`

Merged-main CI:

`35750409036`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing the planner:

- the release-local `shreks-g1c-v2-decision-backed-rotation-plan` script is a regular non-symlink executable;
- its resolved path is exactly inside the expected immutable release;
- `shreks_brain.g1c_v2_decision_backed_rotation_plan` imports through exact release-local Python;
- the module path resolves inside that same expected release.

Expected evidence includes:

```text
g1c_v2_decision_backed_rotation_plan=present
g1c_v2_decision_backed_rotation_plan_path=<exact-release-local-path>
g1c_v2_decision_backed_rotation_plan_module=<exact-release-local-module-path>
```

The verifier must not invoke the planner.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the decision-backed rotation-plan CLI/module in release-local Python;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, trusted-admin tooling presence/provenance, read-only helper status, and protected FL9 discovery.

Automatic deployment/verification must not:

- execute helper proof refresh;
- execute decision-backed readiness;
- execute the decision-backed rotation planner;
- create or stage a rotation plan;
- invoke the PAPER manifest manager;
- rotate the protected runtime manifest;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin planner boundary

Only after production verification proves the planner exact-release-local, and only after exact reviewed candidate/binding/authority/readiness artifacts exist for the exact active release, may a trusted administrator run the documented planner ceremony.

That ceremony writes only one root-private `rotation-plan.json`.

The plan is evidence and transcription-risk reduction only.

Plan existence does not authorize the future manager argv.

Actual rotation authority remains the separately reviewed trusted administrator's explicit root invocation under the protected-rotation design.

## Authority boundary

This seal does not authorize:

- automatic planner execution;
- automatic or manual manager execution merely because a plan exists;
- helper proof refresh;
- decision-backed readiness execution;
- manifest rotation;
- V2 scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.

## Promotion boundary

`G1C_V2_DECISION_BACKED_ROTATION_PLAN=SEALED_TOOL_PRESENCE_ONLY`

`DECISION_BACKED_ROTATION_PLAN_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_ROTATION_PLAN_EXECUTION=DISABLED`

`AUTOMATIC_MANIFEST_ROTATION=DISABLED`

`MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED_BY_SEAL`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
