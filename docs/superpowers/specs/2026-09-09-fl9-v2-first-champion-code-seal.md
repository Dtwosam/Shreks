# FL9 V2 First Champion — Code/CI Production Seal

**Date:** 2026-09-09  
**Corrected implementation main SHA:** `b399baff7ee39bf04c1c6d15aeba49d5a4a3b6e5`  
**Design/plan main SHA:** `a73ff694d28712cc9dc9a9143cda144259a41dd7`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; PHYSICAL V2 CHAMPION EVIDENCE NOT YET CREATED

## Purpose

Seal the merged FL9 V2 first-champion core, production host/request path, and the four pre-release evidence-integrity corrections after exact-head and merged-main CI proof.

This seal authorizes immutable ARM64 release construction and a later production-paper **evidence-generation attempt only**.

It does **not** authorize:

- learned-vs-deterministic superiority claims;
- PAPER promotion;
- action-policy promotion;
- risk-intent creation;
- registry promotion;
- transaction construction;
- signing/submission;
- LIVE trading.

No physical V2 champion/model result is accepted by this document.

## Frozen upstream cohort authority

Physical cohort artifact fingerprint:

`bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`

Accepted identity fingerprint:

`75cf6dbac938286f508d978a14149cd083ff7a8470c8fce20fca9abbc1faf56b`

TEST unseen-mint identity fingerprint:

`f896c03590a66f4385a01a347039c9dd8a3ab60a4a181e631fa2e838e12ef285`

Feature identity firewall fingerprint:

`e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`

The physical cohort was previously generated and accepted from production evidence. This seal consumes that exact artifact identity; it does not reinterpret or regenerate the cohort.

## Frozen V2 first-champion policy

Policy:

`fl9-v2-first-champion-v1`

Frozen chronology:

- horizon: `30,000 ms`;
- selection timestamp: `1788902319835`;
- training start: `1788878323281`;
- training end/cut: `1788892302791`;
- validation start: `1788892302791`;
- validation end/cut: `1788898931418`;
- TEST start: `1788898931418`;
- TEST end: `1788902289835`.

Per-target scoring floors:

- natural TEST scored observations >= `40,000`;
- unseen-mint TEST scored observations >= `35,000`.

Required member families remain the exact five frozen V2 members. No caller can override cohort fingerprint, horizon, split, selection timestamp, or scoring floors under this policy version.

## Merged implementation chain

### PR #261 — V2 core evidence

Reviewed head:

`8c1b79482afb7c52abf10980895f1647c0422828`

Merged main:

`fb44c04e964aec93488a4cc35b779cfcfa80d697`

Merged-main CI run:

`34331849458`

Result:

- Repository safety: SUCCESS;
- Python tests: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Core behavior includes:

- exact physical-cohort-bound training-bundle construction;
- canonical SQLite counterfactual provenance reconciliation;
- five V2 chronological-generalization members;
- natural TEST evaluation;
- unseen-mint TEST evaluation from the same TEST prediction set;
- all five natural/unseen scoring gates before runtime refit;
- runtime-compatible champion packaging;
- immutable V2 evidence artifact plus readback.

### PR #262 — production host/request path

Reviewed head:

`66abb1e8072791c83111932b1c812cf23165e21e`

Merged main:

`251d5490ecc063f40c8ae229b78acad23df46102`

PR CI run:

`34337081538`

Merged-main CI run:

`34337377428`

Both passed:

- Repository safety;
- Python tests;
- Rust tests;
- ARM64 release build.

Production host behavior includes:

- canonical separately versioned V2 request;
- exact active deployed-release identity binding;
- exact physical cohort path/fingerprint binding;
- authenticated proof-workspace/feature source;
- hydration-policy fingerprint;
- training-economics overlay fingerprint;
- execution-cost policy fingerprint;
- frozen chronology derived from authenticated cohort/V2 policy only;
- no host wall clock as selection authority;
- single request-path CLI:
  `shreks-fl9-v2-first-champion`;
- staged evidence readback/source revalidation before final atomic publication.

The V2 request contains no ad-hoc horizon, split, selection, or minimum-floor tuning fields.

### PR #263 — pre-release P1 integrity corrections

Reviewed GREEN head:

`88fc998ec1a75334650058e6056ab22598982f31`

Merged corrected main:

`b399baff7ee39bf04c1c6d15aeba49d5a4a3b6e5`

Exact-head CI run:

`34340499082`

Merged-main CI run:

`34340771403`

Both passed all four gates.

The corrections close every late P1 finding discovered before seal:

1. unseen-mint member evidence must equal the exact frozen physical TEST-unseen identity fingerprint;
2. BuildResult reconciliation rechecks that same identity even for hand-assembled values;
3. natural and unseen evidence reports must carry evaluation partition `TEST`;
4. champion runtime artifact model family must exactly match frozen member evidence;
5. bundle/target assembly and context hydration use one private immutable SQLite backup snapshot for each production attempt;
6. that snapshot must pass SQLite `quick_check` and is removed after hydration.

The original four review threads on PRs #261/#262 were replied to with this corrected SHA/CI evidence and resolved only after merged-main verification.

## Authority boundary

The sealed implementation has no automatic:

- PAPER execution or promotion;
- learned-vs-baseline superiority decision;
- risk-intent creation;
- model-registry promotion;
- capital-sizing change;
- transaction construction;
- signing;
- submission;
- LIVE enablement.

V1 first-champion schemas and semantics remain unchanged.

The existing V2 authority regression scan covers the V2 package and forbids trading-authority imports.

## Production release identity requirement

The V2 host runner fails closed unless all deployed-release identities agree:

- `/opt/shreks/current` resolves to the expected immutable release directory;
- the directory basename equals the expected 40-character source SHA;
- `RELEASE_MANIFEST.json` records the same source SHA;
- the executing V2 Python package resolves inside that active release.

A proof workspace from a different release cannot silently execute under another active deployment.

## Immutable observer-state requirement

The production observer may continue receiving writes.

For one V2 champion attempt, however, all target/bundle and evaluation-context reads are derived from one SQLite backup snapshot created after release/cohort/input authentication.

The live database is not opened independently by bundle and hydration stages.

This prevents internally valid evidence from combining targets and contexts from different live database states.

## Required next evidence

After this docs-only seal lands on `main`:

1. seal-main CI must pass Repository safety, Python, Rust, and ARM64;
2. automatic `Build sealed Shreks release` must build the exact seal SHA;
3. verify immutable release tag `shreks-<seal-sha>` and its exact three release assets;
4. deploy that exact release through the protected `Deploy verified Shreks release` workflow to `production-paper`;
5. verify `/opt/shreks/current`, release manifest, service process identity, and service working directories against that SHA;
6. verify the exact physical cohort artifact still exists and reads back to:
   `bd6875c4d65ee9b2eb67783e7ecfa2332305bf6c3251f5d474e66465fd17d93a`;
7. choose a new immutable V2 first-champion evidence destination;
8. create a new canonical V2 host request from authenticated deployed sources, binding that destination into the request;
9. execute:
   `sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-first-champion <canonical-request-path>`;
10. read the V2 evidence artifact back with the deployed package;
11. record exact:
    - cohort artifact fingerprint;
    - training-bundle fingerprint;
    - five V2 generalization-run fingerprints;
    - five natural TEST scored counts and report fingerprints;
    - five unseen-mint TEST scored counts and report fingerprints;
    - runtime champion fingerprint;
    - final V2 evidence artifact fingerprint;
12. only after all artifact identities are frozen and read back may model/economic metrics be inspected.

No automatic PAPER promotion occurs after step 12.

## Physical completion boundary

A later physical evidence seal may claim this integration complete only if production evidence proves:

```text
physical_cohort_fingerprint_verified=YES
bundle_identity_reconciliation=PASS
v2_generalization_members=5
natural_test_floor_per_target=PASS
unseen_mint_test_floor_per_target=PASS
runtime_compatible_champion=CREATED_AND_VERIFIED
v2_evidence_artifact=CREATED_AND_VERIFIED
paper_promotion=BLOCKED
live_trading=DISABLED
```

That later physical evidence seal must record exact fingerprints/counts. This code/CI seal records none of those downstream results because they have not yet been generated from the corrected sealed release.

## Current authority state

- V2 physical cohort: **CREATED AND VERIFIED**;
- V2 core implementation: **MERGED**;
- V2 production host/request implementation: **MERGED**;
- four pre-release P1 findings: **FIXED, VERIFIED, AND RESOLVED**;
- corrected merged-main CI: **PASS**;
- immutable release containing corrected first-champion path: **PENDING THIS SEAL**;
- corrected production-paper deployment: **NOT YET PROVEN**;
- physical V2 first-champion evidence artifact: **NOT YET CREATED**;
- model/economic result inspection from corrected physical run: **NOT YET PERFORMED**;
- learned-vs-deterministic PAPER/shadow superiority: **NOT PROVEN**;
- PAPER promotion: **BLOCKED**;
- LIVE trading: **DISABLED**.
