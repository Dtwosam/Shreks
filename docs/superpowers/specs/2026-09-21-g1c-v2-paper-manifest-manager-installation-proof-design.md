# G1C V2 PAPER Manifest Manager Installation Proof — Design

**Date:** 2026-09-21  
**Status:** implementation slice; proof-tool deployment and production use remain unauthorized until separately sealed

## Purpose

The sealed release-bound installer can create exactly one root-owned helper from the exact active immutable release, but the installer deliberately avoids service management and protected runtime state.

This slice adds an independent before/after proof surface for that administrator action.

It does not invoke the installer, does not invoke the manifest manager, and does not rotate the protected PAPER runtime manifest.

## Boundary

The proof tool is root-only because it must read:

- the protected PAPER campaign manifest;
- the root-owned deployment sudoers file;
- service lifecycle state.

Its only process execution is allowlisted read-only `systemctl show` for:

- `shreks-observe.service`;
- `shreks-paper-evidence.service`;
- `shreks-paper-campaign.service`.

There are no stop, start, restart, reload, enable, disable, scoring, promotion, signing, submission, or LIVE commands.

## Prepare phase

`prepare <release-sha>` authenticates the exact current immutable release using the same release-manifest and wheel-verification primitives as the installer.

It then records canonical JSON containing:

- exact release SHA and resolved release directory;
- exact Shreks wheel path and SHA-256;
- exact sealed manager-member SHA-256;
- protected campaign-manifest path, SHA-256, size, uid, gid, and mode;
- deployment sudoers SHA-256 and metadata;
- the three runtime services' active state, substate, restart counter, MainPID, ExecMainStatus, and ActiveEnterTimestampMonotonic;
- a self-fingerprint;
- explicit non-authority fields.

The protected campaign manifest must remain mode 0640.

The sudoers file must remain root:root 0440 and its only effective non-comment line must be the exact sealed release-manager install command.

## Installer action

The proof tool does not perform installation.

Between prepare and verify, the trusted administrator runs the separately sealed:

`shreks-g1c-v2-paper-manifest-manager-install <release-sha>`

and preserves its canonical stdout receipt.

This keeps mutation authority in one existing implementation.

## Verify phase

`verify <release-sha> <prestate> <installer-receipt>` independently re-authenticates the active release and exact sealed manager bytes.

It requires:

- canonical prestate with a valid self-fingerprint;
- canonical installer receipt with `INSTALLED` or `ALREADY_INSTALLED`;
- receipt release/wheel/member/destination/authority fields exactly match the current sealed release;
- installed helper bytes exactly match the sealed wheel member;
- helper metadata is root:root 0755;
- protected campaign-manifest bytes and metadata exactly equal prestate;
- deployment sudoers bytes and metadata exactly equal prestate;
- all three service lifecycle observations exactly equal prestate.

Any drift fails closed.

## Proof receipt

Success emits canonical JSON with:

- `status = VERIFIED`;
- release/wheel/manager identity;
- destination metadata;
- prestate fingerprint;
- installer-receipt SHA-256;
- unchanged campaign/sudoers/service assertions;
- proof fingerprint;
- `installation_authority = PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY`;
- `manifest_rotation_authority = NOT_GRANTED`;
- `scoring_authority = NOT_GRANTED`;
- `paper_promotion_authority = BLOCKED`;
- `live_authority = DISABLED`.

## Tests

Focused tests prove:

1. prepare -> sealed installer -> verify succeeds without runtime drift;
2. protected campaign drift is rejected;
3. service restart/PID/timestamp drift is rejected;
4. sudoers widening is rejected;
5. installer-receipt identity drift is rejected;
6. prestate fingerprint tampering is rejected;
7. the proof implementation contains no mutation or trading-authority surfaces.

## Production boundary

Merging this implementation does not install the helper and does not authorize use of the proof tool on production.

A later seal must transport/deploy this proof capability before it can be used around the already-authorized trusted-administrator helper installation.

**HELPER INSTALLATION PROOF: IMPLEMENTED, NOT YET SEALED.**  
**PRODUCTION V2 MANIFEST ROTATION: NOT AUTHORIZED.**  
**V2 SCORING: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE: DISABLED.**
