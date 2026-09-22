# G1C V2 Decision-Backed Protected PAPER Rotation Plan — Design

**Date:** 2026-09-22  
**Status:** software contract only; read-only planning; no manifest rotation authority exercised

## Purpose

The repository now has a production-present decision-backed readiness proof and a
production-present read-only helper installation-proof refresh.

A successful decision-backed readiness receipt remains deliberately
`READY_EVIDENCE_ONLY` with `manifest_rotation_authority=NOT_GRANTED`.

The protected rotation design remains authoritative: actual rotation authority is the
trusted administrator's explicit root invocation of the separately installed
`/usr/local/sbin/shreks-paper-manifest-manager rotate ...` command.

This slice adds a read-only planner between those boundaries. It reduces stale evidence,
manual fingerprint transcription, and path-selection risk without invoking the manager
or changing the authority model.

## Inputs

The planner accepts only:

- exact canonical v2 candidate runtime manifest;
- exact canonical standard transition binding;
- authenticated decision-backed candidate authority;
- canonical successful decision-backed readiness receipt;
- explicit expected immutable release SHA.

The CLI accepts:

- `--candidate-runtime-manifest`;
- `--transition-binding`;
- `--decision-backed-candidate-authority`;
- `--readiness-receipt`;
- `--expected-release-source-sha`.

It accepts no operator-supplied binding fingerprint, candidate economics, run identity,
timestamp, candidate-value decision, review, or sizing values.

## Authentication contract

The planner must:

1. require root because it observes protected production state;
2. stable-read candidate, binding, authority, and readiness receipt as regular
   non-symlink files;
3. authenticate the candidate runtime manifest;
4. authenticate the standard transition binding;
5. authenticate the decision-backed candidate authority;
6. require candidate and binding provenance to equal that authority;
7. require the readiness receipt to be canonical JSON with the exact existing
   `shreks.g1c_v2_paper_manifest_rotation_readiness` v1 key set;
8. verify its `readiness_fingerprint_sha256`;
9. require `status=READY_EVIDENCE_ONLY`;
10. require the receipt source/candidate/binding identities and release SHA to equal the
    supplied authority/binding/current release;
11. require `candidate_preflight_status=PASSED`,
    `runtime_env_contract=MATCHED`, and
    `service_lifecycle_unchanged=true`;
12. require readiness authority to remain
    `manifest_rotation_authority=NOT_GRANTED`,
    `scoring_authority=NOT_GRANTED`,
    `paper_promotion_authority=BLOCKED`,
    `live_authority=DISABLED`.

## Current-host recheck

Before emitting a plan, re-check read-only:

- current immutable release identity;
- sealed wheel and installed manager identity;
- helper status is exactly `MATCHED_CURRENT_RELEASE`;
- active protected source + candidate + binding still satisfy the existing manager-critical
  binding checks;
- protected runtime environment path contract;
- deployment sudoers hash still equals the readiness receipt;
- G7 revision/halt/kill state still equals the readiness receipt;
- observer, PAPER evidence, and PAPER campaign service observations still exactly equal
  the readiness receipt;
- derived rotation evidence directory
  `/var/lib/shreks/manifest-rotations/<binding-fingerprint>` does not already exist.

Re-read candidate, binding, authority, and readiness receipt after all observations and
fail closed on byte drift. Re-check helper status, G7 state, services, sudoers, and
rotation-evidence-path absence before returning the plan.

## Plan output

Success emits canonical JSON schema:

`shreks.g1c_v2_decision_backed_rotation_plan` version 1.

Status:

`READY_FOR_TRUSTED_ADMIN_ROTATION_CEREMONY`

The plan binds:

- exact release SHA/directory;
- exact installed manager path and SHA;
- decision-backed authority fingerprint;
- readiness fingerprint;
- source/candidate/binding identities;
- exact absent rotation evidence directory;
- one ordered manager argv:

```text
/usr/local/sbin/shreks-paper-manifest-manager
rotate
<exact-candidate-path>
<exact-binding-path>
<binding-fingerprint>
<exact-release-sha>
```

The planner does not execute that argv.

## Authority boundary

The plan records:

```text
planning_authority=READ_ONLY
manifest_rotation_authority=NOT_EXERCISED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

Actual rotation authority remains only the later trusted administrator's explicit root
invocation after independent review of the plan and evidence.

The implementation contains no manager invocation, service lifecycle mutation, manifest
replacement, helper install/repair, scoring/model fitting, PAPER promotion, wallet,
signing, submission, or LIVE authority.

Production use requires a later separate production-presence proof and seal.
