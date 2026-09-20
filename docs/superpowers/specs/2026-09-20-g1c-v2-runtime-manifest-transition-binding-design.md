# G1C Runtime Manifest V2 Transition Binding — Design

**Date:** 2026-09-20  
**Status:** implementation slice; PAPER-only authority binding; no installation/activation/rotation authority

## Purpose

The sealed G1C v2 dynamic quote-valuation bridge can execute an authenticated runtime-manifest v2, and the repository can now author one canonical new-run v2 candidate from authenticated v1 authority. The remaining authority gap must be crossed in small explicit steps.

This slice adds the next non-mutating step only: bind one exact v1 source manifest, one exact canonically authored v2 candidate, and one read-only COMPATIBLE FL9 V2 assessment into an immutable fingerprinted artifact.

The artifact is evidence that a candidate is coherent and compatible. It is not permission to install or activate it.

## Inputs

The binder requires explicit paths to:

1. the authenticated canonical v1 source runtime manifest;
2. the authenticated canonical v2 candidate runtime manifest;
3. the frozen FL9 V2 cohort;
4. the preserved authenticated V2 host-request authority;
5. a new destination for the binding artifact.

No value is inferred from an active host path or environment variable.

## Canonical derivation proof

Authenticating a v2 manifest is not enough. A separately constructed v2 manifest could carry valid fingerprints while drifting unrelated strategy, risk, or execution policy.

The binder therefore replays the existing canonical candidate-authoring function using only the target transition values present in the candidate:

- new paper_run_id;
- new-run start timestamp;
- target quote mint;
- target quote decimals;
- target entry input amount.

The replayed manifest must equal the supplied candidate exactly.

This proves that the candidate changes only the fields already authorized by the new-run authoring contract and resets PAPER state through that same contract.

## Compatibility proof

The binder reuses the existing read-only FL9 V2 candidate assessment.

It requires:

- assessment schema/version match;
- terminal assessment status COMPATIBLE;
- candidate authentication AUTHENTICATED;
- candidate compatibility COMPATIBLE;
- exact candidate source path;
- exact runtime-manifest fingerprint;
- runtime-manifest schema v2;
- quote valuation mode exact_market_ratio;
- candidate quote mint equal to the frozen cohort quote mint;
- regime and safety quote identities equal to that same quote mint;
- authenticated V2 host-request authority;
- valid request, cohort, and hydration-policy fingerprints.

The resulting artifact commits to the canonical assessment payload by SHA-256.

## Binding artifact

The binding is canonical JSON written once with private mode 0600.

It commits to:

- raw source manifest SHA-256;
- authenticated source manifest fingerprint;
- source run and quote identity;
- raw candidate manifest SHA-256;
- authenticated candidate manifest fingerprint;
- candidate run/start/quote identity;
- candidate dynamic valuation mode;
- candidate hydration-policy fingerprint;
- frozen cohort fingerprint and quote mint;
- preserved request fingerprint and release-source SHA;
- request hydration-policy fingerprint;
- canonical assessment SHA-256;
- the explicit no-escalation authority boundary.

The artifact itself is fingerprinted over all material fields.

Existing destinations are never overwritten.

## Authority boundary

This slice deliberately records:

- installation_authority = NOT_GRANTED
- activation_authority = NOT_GRANTED
- rotation_authority = NOT_GRANTED
- scoring_authority = NOT_GRANTED
- paper_promotion_authority = BLOCKED
- live_authority = DISABLED

The implementation contains no protected-host destination, service-control command, scorer/model fitting path, promotion operation, wallet/signing path, or transaction submission path.

It does not mutate the active PAPER campaign manifest, current PAPER runtime state, frozen FL9 V2 cohort, preserved request/hydration authority, scoring evidence, champion state, or LIVE state.

## Fail-closed behavior

Binding fails without output when:

- source or candidate bytes do not authenticate;
- source is not v1 or candidate is not v2;
- source and candidate are the same file;
- the candidate cannot be reproduced exactly by canonical authoring;
- the candidate assessment is not COMPATIBLE;
- any candidate/report identity disagrees;
- request/cohort authority is malformed or inconsistent;
- the destination already exists;
- canonical write/readback changes the binding.

## TDD / verification plan

Focused tests cover:

1. successful immutable binding of an exact authored compatible candidate;
2. rejection of a candidate whose quote identity is incompatible with the frozen cohort;
3. rejection of an authenticated v2 candidate containing unrelated policy drift;
4. write-once behavior and decoder rejection of authority escalation;
5. CLI registration and an implementation-source authority firewall.

After focused GREEN, run the repository's canonical Python, Rust/workspace, repository-safety, and ARM64 lanes through PR CI.

## Next separate slice

A later sealed slice may consume a verified transition binding to design an explicit protected PAPER installation/rotation operation.

That future slice must independently define quiesce, checkpoint/evidence preservation, backup/rollback, atomic manifest replacement, runtime preflight, restart/recovery, and post-activation verification.

This design does not grant that authority.

**V2 SCORING RETRY: NOT AUTHORIZED.**  
**PAPER PROMOTION: BLOCKED.**  
**LIVE TRADING: DISABLED.**
