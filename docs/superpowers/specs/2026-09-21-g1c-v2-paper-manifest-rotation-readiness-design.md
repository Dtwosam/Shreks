# G1C V2 Protected PAPER Manifest Rotation Readiness — Design

**Date:** 2026-09-21  
**Status:** implementation slice; production use remains unauthorized until separately sealed

## Purpose

Add a root-only, evidence-only readiness proof for one future protected PAPER runtime-manifest v1 -> v2 rotation.

The proof is intended to run only after the release-bound manifest-manager helper has been installed and independently proven.

It does not perform the rotation.

## Inputs

The readiness proof takes:

- exact staged canonical v2 candidate runtime manifest;
- exact staged canonical transition binding;
- canonical successful helper-installation proof;
- explicit 64-character transition-binding fingerprint;
- explicit 40-character current immutable release SHA.

Production paths remain fixed to the same protected DB, E11, active manifest, G7 control, sudoers, current release, and installed manager locations used by the sealed manager/install/proof chain.

## Release and helper identity

The tool reuses the sealed installer/proof release-verification primitives to authenticate:

- `/opt/shreks/current`;
- canonical release manifest source SHA;
- the single manifest-hashed Shreks wheel;
- the exact sealed manager wheel member;
- the installed root helper bytes and root:root 0755 metadata.

The supplied installation proof must be canonical, fingerprint-valid, status `VERIFIED`, and bound to the same release, wheel, manager, destination, and non-authority fields.

## Sudoers invariant

The tool independently re-reads `/etc/sudoers.d/shreks-release-manager`.

It must remain root:root 0440 and contain exactly the historical release-manager install rule.

Its SHA-256 must equal the value preserved in the helper-installation proof.

Thus a valid old installation proof cannot be reused after deploy-account authority widens.

## Protected runtime path contract

The runtime environment file must still bind exactly:

- operational SQLite DB;
- E11 evidence;
- protected campaign manifest;
- G7 operator-control state.

No alternate protected path is accepted.

## Source, candidate, and transition binding

The active source manifest must be:

- regular non-symlink;
- mode 0640;
- authenticated canonical v1.

The candidate must be authenticated canonical v2.

The transition binding must be canonical and fingerprint-valid.

The explicit binding fingerprint must equal the binding fingerprint.

The proof checks the same manager-critical source and candidate fields:

- raw manifest SHA-256;
- authenticated runtime-manifest fingerprint;
- paper run ID;
- source quote mint;
- candidate start timestamp;
- candidate quote mint;
- candidate quote decimals.

Any mismatch fails closed.

## G7 state

The operator risk-control state must decode successfully.

The readiness receipt records:

- revision;
- entry-halt state;
- kill-switch state.

The exact state must remain unchanged across the proof window.

This is evidence only; the proof does not alter operator controls.

## Service state

The tool uses the already-sealed read-only `systemctl show` observation surface.

Observer, PAPER evidence, and PAPER campaign services must be active/running with valid process identity fields.

The complete observations must remain identical across the readiness proof window.

No service lifecycle command exists in this tool.

## Candidate preflight

The authenticated candidate bytes are copied into a private temporary directory with mode-0600 candidate storage.

The existing `preflight_observer_paper_campaign_runtime` runs against that exact private copy using:

- real operational SQLite state;
- real E11 evidence;
- real G7 operator-control state;
- no campaign cycle.

The private copy is removed automatically when preflight finishes.

The active protected campaign manifest is never replaced.

## Stability recheck

After preflight, the tool re-authenticates/re-reads:

- current release identity;
- sealed manager identity;
- installed helper;
- sudoers;
- runtime environment;
- active source bytes;
- staged candidate bytes;
- transition-binding bytes;
- G7 state;
- service lifecycle observations.

Any drift fails the proof.

## Readiness receipt

Success emits canonical JSON:

- `status = READY_EVIDENCE_ONLY`;
- exact release/wheel/manager identity;
- helper-installation proof fingerprint;
- sudoers SHA-256;
- source and candidate hashes/fingerprints/run IDs;
- binding fingerprint;
- G7 state;
- service observations;
- candidate preflight status;
- environment-contract status;
- readiness fingerprint.

Authority remains explicit:

- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

## Tests

Focused tests cover:

1. complete release/helper/install-proof/source/candidate/binding readiness success;
2. installed helper drift rejection;
3. tampered installation proof rejection;
4. active source drift rejection;
5. protected runtime environment drift rejection;
6. candidate preflight failure without source mutation;
7. service lifecycle drift rejection;
8. static authority firewall proving no rotation/service mutation/scoring/promotion/signing/LIVE surface.

## Authority boundary

This implementation creates evidence only.

Merging it does not deploy the CLI and does not authorize its production use.

A later seal is required before production readiness proof use.

A later separately explicit authority slice is still required before invoking the manifest manager's `rotate` command.

**ROTATION READINESS: IMPLEMENTED, NOT YET SEALED.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
