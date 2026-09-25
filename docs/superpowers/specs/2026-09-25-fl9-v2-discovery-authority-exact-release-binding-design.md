# FL9 V2 Discovery Authority Binding Exact-Release Ceremony — Design

**Date:** 2026-09-25  
**Base main SHA:** `8d7cd872fbdbf7964bcdf86548a706292a7f9942`  
**Scope:** trusted-admin discovery-authority binding runbook and regression coverage only

## Production trigger

Protected verifier run `36178349929` for exact release
`816e7c6591d216369b60f893cc5dfe5785e88652` returned:

```text
g1c_v2_mint_state_physical_acceptance=PASS
fl9_v2_discovery_status=FOUND_COMPATIBLE
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

The discovery result is evidence only. The documented next step is to bind that
exact canonical `FOUND_COMPATIBLE` result before preparing any later FL9 V2
request.

## Failure mode

The current runbook changes directory to `/opt/shreks/current` and invokes the
release-local binder, but it does not pin that release to the exact SHA from the
successful production verifier.

A release could therefore change after the verifier result was reviewed and
before the binding artifact was published.

The binder itself correctly requires exact expected/observed release equality
inside the discovery result, but the operator ceremony must also prove that the
executable performing the bind belongs to that same verified release.

## Required ceremony contract

The runbook must require:

```text
EXPECTED_RELEASE_SHA=<exact-production-verified-release-sha>
CURRENT_RELEASE=$(readlink -f /opt/shreks/current)
CURRENT_SHA=$(basename "$CURRENT_RELEASE")
CURRENT_SHA == EXPECTED_RELEASE_SHA
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

The binding destination must be new and root-private.

Immediately before invoking the binder, the runbook must recheck:

```text
readlink -f /opt/shreks/current == CURRENT_RELEASE
```

The exact release SHA must come only from the successful production-verification
run that authorized the ceremony.

## Authority boundary

This slice does not execute the binder or create a production binding.

It changes documentation/tests only and grants no authority to:

- prepare a scoring request;
- execute scoring/model fitting;
- publish champion evidence;
- change the PAPER manifest;
- promote PAPER;
- sign or submit;
- enable LIVE.

## RED proof

The production runbook regression test must fail on current main because the
binding section lacks the explicit release pin and active-release stability
checks.

## GREEN proof

Update only the binding ceremony documentation and keep all four canonical CI
gates green.

## Explicit non-authority

```text
DISCOVERY_AUTHORITY_BINDING_EXECUTION=NOT_AUTHORIZED_BY_THIS_SLICE
REQUEST_PREPARATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
CHAMPION_PUBLICATION_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```
