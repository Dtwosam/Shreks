# FL9 V2 One-Request Scoring Authority Production Presence — Design

**Date:** 2026-09-25  
**Base main SHA:** `f3c71e8940f14a4e356b2695a8f06256e2276715`  
**Status:** read-only production presence proof only; no automatic scoring-authority decision or scoring execution

## Purpose

The one-request FL9 V2 scoring-authority writer is implemented and merged separately.

Before a trusted administrator may create an authority artifact against protected
production-paper evidence, the ordinary production verifier must prove that the exact
active immutable release contains the authority CLI and module.

This slice adds exact-release presence/provenance proof and one bounded trusted-admin
ceremony only.

## Production verifier contract

Require:

- release-local console script `shreks-fl9-v2-scoring-authority-decide`;
- regular non-symlink executable;
- resolved script path exactly under the expected immutable release;
- module `shreks_brain.fl9_v2_scoring_authority`;
- module path resolving inside that same expected release.

Expected evidence:

```text
fl9_v2_scoring_authority_decide=present
fl9_v2_scoring_authority_decide_path=<exact-release-local-path>
fl9_v2_scoring_authority_decide_module=<exact-release-local-module-path>
```

The production verifier must not execute the authority command.

## Trusted-admin scoring-authority ceremony

Document one root-private exact-release ceremony that consumes only one reviewed existing
discovery-backed request-preparation receipt and writes one new authority artifact.

The ceremony must:

- pin `/opt/shreks/current` to the exact successful production-verification release SHA;
- require `RELEASE_MANIFEST.json.source_sha` to equal that SHA;
- use the release-local `shreks-fl9-v2-scoring-authority-decide` executable;
- use one exact reviewed preparation receipt;
- require a new non-existing authority destination;
- require one explicit supported decision;
- require one explicit non-empty decision reason;
- recheck the active release immediately before invocation.

The command writes an authority artifact only. It does not execute the prepared V2 host request.

An authorization artifact may state:

```text
execution_scope=ONE_REQUEST_ONE_DESTINATION
scoring_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN
model_fitting_authority=EXPLICIT_DISCOVERY_BOUND_SINGLE_RUN
champion_publication_authority=SCORING_EVIDENCE_ONLY
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

That artifact is authority for one later, separately implemented and reviewed execution
bridge. This slice does not add that bridge.

A rejection artifact grants no scoring/model-fitting/champion-publication authority.

## Authority boundary

Automatic deployment/verification must not:

- invoke the scoring-authority decision CLI;
- create an authority artifact;
- execute a V2 scoring/model-fitting run;
- publish champion evidence;
- promote PAPER;
- create risk intent;
- access wallets;
- construct, sign, or submit transactions;
- enable LIVE.

The trusted-admin ceremony may create only one write-once scoring-authority decision artifact.

## RED proof

Add a production-presence regression test that requires:

- exact-release CLI presence checks;
- exact-release module provenance checks;
- verifier evidence lines;
- explicit absence of authority-command execution in the verifier;
- the bounded trusted-admin ceremony in the release runbook;
- exact-release pinning and non-overwrite destination checks;
- explicit PAPER/LIVE blocks.

Current main must fail because the verifier and runbook surfaces do not yet exist.

## GREEN proof

Update only the production verifier and release runbook surface required by the RED
contract. Keep all scoring/model, PAPER campaign, risk, wallet, transaction, and LIVE
behavior unchanged.
