# G1C V2 Decision-Backed Candidate Authoring — Design

**Date:** 2026-09-22  
**Status:** exact offline candidate-file authoring only; no transition/runtime authority

## Purpose

A decision-backed candidate-authority artifact now commits one exact canonical G1C v2 candidate identity and grants:

`candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND`

The existing candidate author accepts raw new-run and quote inputs. Those values must not be copied manually out of the authority and re-supplied as unbound CLI arguments.

This slice adds one authoring bridge that authenticates the decision-backed authority and the matching source runtime manifest, derives the candidate through the existing canonical author, and writes only the exact candidate bytes already committed by that authority.

## Inputs

The authoring bridge accepts only:

- canonical v1 source runtime-manifest path;
- decision-backed candidate-authority path;
- new non-existent candidate destination.

There are no CLI inputs for:

- paper run id;
- start timestamp;
- quote mint;
- quote decimals;
- entry input amount;
- cohort;
- request authority;
- candidate-value decision.

Those values are already committed by the authenticated decision-backed authority.

## Authority requirements

The authority must authenticate as:

`shreks.g1c_v2_decision_backed_candidate_authority`

and preserve:

```text
authority_status=BOUND_EXACT_CANONICAL_CANDIDATE
candidate_authoring_authority=DECISION_BACKED_INPUTS_BOUND
installation_authority=NOT_GRANTED
activation_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The supplied source manifest bytes, manifest fingerprint, and source paper-run id must match the source authority committed by the decision-backed authority.

## Derivation

The bridge invokes the existing canonical candidate author using only authority-bound:

- candidate paper-run id;
- candidate start timestamp;
- candidate quote mint;
- candidate quote decimals;
- candidate entry input amount.

It then canonical-encodes the candidate and requires both:

- SHA-256 of the exact encoded candidate bytes equals `candidate_manifest_sha256`;
- runtime-manifest fingerprint equals `candidate_runtime_manifest_fingerprint_sha256`.

Any mismatch fails closed.

The source and authority inputs are re-read before persistence and must be byte-identical to the authenticated inputs.

## Output

One canonical write-once mode-0600 G1C v2 runtime-manifest candidate file.

The output is the runtime manifest itself, not a new authority wrapper.

The destination must not already exist.

## Authority boundary

This slice does not:

- create a transition binding;
- execute candidate assessment as runtime authority;
- execute readiness;
- install or activate a manifest;
- rotate the protected runtime manifest;
- score/model-fit;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

The exact candidate must be reviewed and assessed separately. A later transition-binding step must authenticate the exact candidate identity already committed by the decision-backed authority.
