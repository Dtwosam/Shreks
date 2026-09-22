# G1C V2 Candidate-Value Decision Production Presence — Release Seal

**Date:** 2026-09-22  
**Candidate-value decision implementation main SHA:** `16730ab2454b964091938420391a824a23a9adda`  
**Production-presence implementation main SHA:** `1f395dd66aa4d37280cfa74ebf49d5cf06af0083`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF DECISION-TOOL PRESENCE ONLY; AUTOMATIC DECISION EXECUTION DISABLED; CANDIDATE AUTHORING NOT AUTHORIZED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; PAPER PROMOTION BLOCKED; LIVE DISABLED

## Purpose

Seal the explicit G1C v2 candidate-value decision artifact and its read-only exact-release production-presence proof.

The candidate-value decision exists after review-backed sizing because a sizing proposal is evidence only and must not silently become a production candidate value.

The decision tool authenticates one canonical review-backed sizing proposal and records exactly one:

- `ACCEPT_PROPOSAL`;
- `REJECT_PROPOSAL`; or
- `REPLACE_PROPOSAL`.

This seal deploys decision-tool presence only.

It does not execute a production candidate-value decision.

## Current protected production state before this seal

The currently active sealed production release is:

`e1c15cac1dc15e57ca2e715dcfc0feaff13f9322`

Production verification for that release proved:

- active release and release-manifest source identity match exactly;
- `shreks-g1c-v2-review-backed-entry-sizing` is present from the exact active immutable release;
- the review-backed sizing Python module resolves inside that same release;
- the installed manifest-manager helper reports `MATCHED_CURRENT_RELEASE`;
- protected FL9 discovery remains fail-closed at `HOLD_NO_COMPATIBLE`.

The protected multi-reference quote review remains evidence only.

No production review-backed sizing proposal has been created by automation.

No production candidate-value decision exists by authority of this seal.

## Candidate-value decision implementation

The implementation was merged to main as:

`16730ab2454b964091938420391a824a23a9adda`

CLI:

`shreks-g1c-v2-candidate-value-decision`

Module:

`shreks_brain.g1c_v2_candidate_value_decision`

The tool:

1. accepts one explicit sizing-proposal path;
2. authenticates that proposal through the canonical sizing-proposal decoder;
3. requires `quote_evidence_authority=MULTI_REFERENCE_REVIEW`;
4. rejects the legacy `EXPLICIT_REFERENCE_ONLY` provenance path;
5. requires one explicit supported decision and non-empty review reason;
6. forbids replacement input for ACCEPT/REJECT;
7. requires one explicit positive-u64 amount for REPLACE;
8. requires a replacement amount to differ from the proposal amount;
9. binds proposal file SHA-256 and proposal self-fingerprint;
10. preserves source runtime-manifest and quote-evidence provenance;
11. records one selected raw amount only for ACCEPT/REPLACE;
12. re-reads the proposal and fails if it changes while the decision is derived;
13. writes one canonical mode-0600 write-once self-fingerprinted artifact.

The tool never reads SQLite and never executes review or sizing.

## Authority semantics

For `ACCEPT_PROPOSAL` and `REPLACE_PROPOSAL`:

```text
status=CANDIDATE_VALUE_APPROVED
candidate_value_authority=EXPLICIT_PRODUCTION_DECISION_BOUND
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

For `REJECT_PROPOSAL`:

```text
status=CANDIDATE_VALUE_REJECTED
selected_entry_input_amount=null
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

An approved decision grants value authority only.

It does not grant candidate-authoring authority.

## TDD and implementation proof

### Candidate-value decision implementation

Intentional RED PR #394 head:

`7b794a04720d6dff3751d1ca6cb48ec43b272bbf`

RED CI:

`35705852491`

Result:

- Python failed at collection solely because `shreks_brain.g1c_v2_candidate_value_decision` did not exist;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN head:

`dc981ff93c3b2866636f36253fbb6f146b39ceea`

Push CI:

`35706218828`

Independent PR CI:

`35706258454`

Result: SUCCESS across Python, Rust, Repository safety, and ARM64.

Merged implementation main:

`16730ab2454b964091938420391a824a23a9adda`

Merged-main CI:

`35707421328`

Result: SUCCESS across all four canonical gates.

### Production-presence proof

Intentional RED PR #396 head:

`1a799239879c992e20ebc6fed6af6e6eedf694e8`

RED CI:

`35707730420`

Result:

- Python: exactly 1 failed, 3608 passed, 2 known warnings;
- the only failure was the intentionally absent candidate-value decision production-presence contract;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Final GREEN head:

`fd7036827debaa411edabfbbeaec0174f9d391ba`

Push CI:

`35708025039`

Independent PR CI:

`35708046690`

Result: SUCCESS across all four canonical gates.

Merged production-presence main:

`1f395dd66aa4d37280cfa74ebf49d5cf06af0083`

Merged-main CI:

`35708305651`

Result: SUCCESS across all four canonical gates.

The implementation and presence commits are not seal commits, so those merges do not themselves create a production release.

## Production-presence verifier

After this seal deploys, the ordinary production verifier must prove without executing a decision:

- `shreks-g1c-v2-candidate-value-decision` is a regular non-symlink executable;
- its resolved path is exactly inside the expected active immutable release;
- `shreks_brain.g1c_v2_candidate_value_decision` imports through the exact release-local Python;
- the module path resolves inside that same exact release.

Expected evidence includes:

```text
g1c_v2_candidate_value_decision=present
g1c_v2_candidate_value_decision_path=<exact-release-local-path>
g1c_v2_candidate_value_decision_module=<exact-release-local-module-path>
```

The production verifier must not invoke the decision CLI.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include the candidate-value decision CLI/module in the release-local Python environment;
3. publish that immutable release;
4. deploy the exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, services, restart state, existing trusted-admin tool provenance, review-backed sizing presence, candidate-value decision presence, helper status, and protected FL9 discovery.

Automatic release/deploy/verification must not:

- execute quote review;
- execute review-backed sizing;
- execute a candidate-value decision;
- read protected sizing/review artifacts on behalf of the decision;
- invoke candidate authority;
- author or stage a runtime-manifest candidate;
- create a transition binding;
- execute rotation readiness;
- rotate the protected runtime manifest;
- score/model-fit;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin decision boundary

Only after production verification proves the candidate-value decision CLI/module belong to the exact active release may a trusted administrator use the documented runbook ceremony.

That ceremony requires one already-existing authenticated review-backed sizing proposal.

The operator must select exactly one accept/reject/replace outcome and preserve exactly one canonical decision artifact for the reviewed ceremony.

The tool itself does not invoke candidate authority.

Do not run candidate authority from the decision alone.

## Next boundary

The existing candidate-authority binder still accepts raw explicit values and does not authenticate the candidate-value decision artifact.

Do not manually copy the selected amount from a decision into that raw-input binder and thereby discard the decision provenance.

The next software slice is a separate decision-backed candidate-authority bridge that:

- authenticates one approved candidate-value decision;
- uses its exact selected target quote mint, decimals, and raw amount;
- combines those with separately explicit new-run identity/time inputs;
- invokes the existing candidate-authority derivation without inventing economics;
- preserves candidate authoring as a later explicit boundary unless separately granted.

This seal does not implement or authorize that bridge.

## Helper/readiness boundary

Deployment of this seal creates a new current release SHA.

Any helper installation proof bound to an older release remains stale for later rotation-readiness.

A fresh exact-release helper proof will still be mandatory before any later readiness/rotation ceremony.

That helper-proof refresh is not required merely to create an offline sizing proposal or candidate-value decision.

## Promotion boundary

`G1C_V2_CANDIDATE_VALUE_DECISION=SEALED_VALUE_AUTHORITY_TOOL`

`CANDIDATE_VALUE_DECISION_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_CANDIDATE_VALUE_DECISION=DISABLED`

`AUTOMATIC_CANDIDATE_AUTHORITY_EXECUTION=DISABLED`

`CANDIDATE_AUTHORING_AUTHORITY=NOT_GRANTED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
