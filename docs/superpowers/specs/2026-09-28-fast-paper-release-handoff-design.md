# Fast Lane Authoritative PAPER Release Handoff — Design

**Date:** 2026-09-28  
**Base main SHA:** `8cea1cb5907e9b8b1208b383bbc2dceb627be8d8`

## Purpose

Add the state-migration primitive required for future immutable releases after
Fast Lane becomes the authoritative production PAPER runtime.

The existing physical-cutover implementation intentionally blocks the legacy
G2 release manager after Fast cutover, because that manager would reinstall the
legacy score-gated campaign unit.

Before a Fast-aware release manager can be built, Shreks needs one append-only,
auditable way to carry the exact authoritative Fast PAPER state from one
release-bound run namespace into another release-bound run namespace.

This slice adds only that handoff primitive. It grants no service-control or
deployment authority.

## Why a new Fast run is required

The authoritative Fast binding is pinned to:

- release source SHA;
- runtime-manifest fingerprint;
- champion;
- action-policy version;
- execution-policy fingerprint;
- risk/fill/position-action policy versions;
- authoritative database identity.

The learned decision checkpoint is also pinned to the runtime manifest.

Therefore a future immutable release must not reuse the old binding or rewrite
it in place.

A routine Fast release upgrade creates a fresh target Fast run namespace and
retains the old namespace as immutable history.

## Compatibility boundary

This routine release handoff permits a distinct release SHA while requiring
exact equality for trading semantics:

- champion version/fingerprint/file;
- decision binary SHA-256;
- feature-feed binary SHA-256;
- continuous action policy;
- feature schema;
- Fast state/event-loop versions;
- risk policy;
- fill policy;
- position-action policy;
- strategy family/version;
- assessment version;
- authoritative PAPER evidence path;
- learned decision checkpoint path;
- quote provider/mint/decimals;
- route-evidence version;
- authoritative observer database identity.

A change to any of those values is not a routine deployment. It requires its
own separately reviewed champion/policy/runtime migration authority.

## Quiescent handoff boundary

The source authoritative Fast service must be stopped or otherwise quiesced
before the caller uses this primitive.

The handoff fails closed unless:

- the exact source binding is still persisted;
- the latest source Fast checkpoint/runtime pair is untorn;
- the learned decision checkpoint authenticates against the source manifest;
- no pending BUY exists;
- learned decision cursor equals authoritative execution cursor;
- the original final legacy handoff checkpoint remains the exact latest legacy
  checkpoint;
- the target Fast run ID is fresh.

Open PAPER positions are allowed.

Their exact ledger state, position-action state and authoritative market-position
mapping carry into the successor run.

## Successor state

The successor namespace receives:

- one new authoritative binding for the target release;
- one new Fast PAPER checkpoint at sequence 0 containing the exact source
  `FastPaperRuntimeState`;
- one new authoritative runtime-state row at checkpoint sequence 0;
- exact source market-position mapping;
- exact latest learned execution identity;
- one append-only release-handoff audit row.

The target learned decision state is rebuilt against the target manifest with
the exact source decision cursor.

No source binding, checkpoint, runtime-state row or legacy checkpoint is
updated or deleted.

## Audit record

`fast_paper_authoritative_release_handoffs` records at least:

- source/target run IDs;
- source/target release SHAs;
- source/target manifest fingerprints;
- source/target binding fingerprints;
- exact source checkpoint sequence/fingerprint;
- target sequence-0 checkpoint fingerprint;
- source/target runtime-state fingerprints;
- source/target learned decision-state fingerprints;
- creation time;
- canonical handoff fingerprint.

Exact replay is idempotent. Any conflicting target namespace fails closed.

## Authority boundary

This slice must not:

- invoke systemd;
- stage or activate a release;
- change `/opt/shreks/current`;
- replace protected manifests/policies;
- rewrite the canonical learned decision checkpoint file;
- issue/revoke cutover authorization;
- execute BUY/SKIP/HOLD/REDUCE/SELL;
- sign or submit transactions;
- enable LIVE.

## Acceptance proof

Tests must prove:

1. flat state is copied into a fresh target release/run without source mutation;
2. exact replay is storage-idempotent;
3. an unexecuted learned decision blocks handoff;
4. strategy/action-policy drift blocks routine handoff;
5. an actual open PAPER position and authoritative market mapping survive the
   release handoff;
6. pending BUY blocks handoff;
7. source/runtime rows are authenticated inside the transaction;
8. no service-control, signing/submission or LIVE authority is introduced;
9. Python, Rust, ARM64 and repository-safety CI remain green.

## Following slice

Wrap this primitive in a protected Fast-aware release manager.

That later slice must:

1. stage and verify the immutable target release;
2. stop the authoritative Fast PAPER writer;
3. authenticate the old release/run and target release authorities;
4. create the fresh successor Fast namespace through this handoff;
5. atomically rotate target runtime manifest/policies, learned decision state,
   authoritative run ID and release symlink;
6. rotate the release-bound cutover authorization;
7. start and verify the Fast candidate;
8. roll back only before the new Fast start authority boundary;
9. never restore legacy score-gated PAPER authority.

LIVE remains disabled.
