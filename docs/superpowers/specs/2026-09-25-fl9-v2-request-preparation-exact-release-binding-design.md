# FL9 V2 Discovery-Backed Request Preparation Exact-Release Binding — Design

**Date:** 2026-09-25  
**Base main SHA:** `816e7c6591d216369b60f893cc5dfe5785e88652`  
**Scope:** trusted-admin runbook contract and regression coverage only

## Production trigger

Protected production verification for exact release
`816e7c6591d216369b60f893cc5dfe5785e88652` returned:

```text
fl9_v2_discovery_status=FOUND_COMPATIBLE
g1c_v2_mint_state_physical_acceptance=PASS
paper_manifest_manager_status=MATCHED_CURRENT_RELEASE
```

The release-local discovery-backed request-preparation CLI/module is present.

This makes the request-preparation ceremony the next reachable FL9 V2 authority
boundary, but the current runbook ceremony resolves `/opt/shreks/current`
without binding that path to the exact release SHA proven by the production
verifier.

Downstream G1C candidate ceremonies already require exact-release binding.

## Failure mode

Without an explicit release pin, an operator could review a production verifier
result for release A, then run request preparation after `/opt/shreks/current`
has moved to release B.

The preparation tool validates the discovery/request source authority encoded in
its inputs, but the shell ceremony would no longer prove that the executable
being invoked belongs to the exact production-verified release that authorized
the ceremony.

A release change between initial path resolution and publication is also not
explicitly rejected by the runbook.

## Required ceremony contract

The runbook must require:

```text
EXPECTED_RELEASE_SHA=<exact-production-verified-release-sha>
CURRENT_RELEASE=$(readlink -f /opt/shreks/current)
CURRENT_SHA=$(basename "$CURRENT_RELEASE")
CURRENT_SHA == EXPECTED_RELEASE_SHA
RELEASE_MANIFEST.source_sha == EXPECTED_RELEASE_SHA
```

Before invoking the preparation tool it must also prove:

- request destination absent;
- future evidence destination absent;
- preparation receipt destination absent;
- `/opt/shreks/current` still resolves to the same `CURRENT_RELEASE`.

The exact release SHA must come from the successful production-verification run
that authorized the ceremony, not from the latest repository commit or latest
release tag.

## Behavior boundary

This slice changes documentation/tests only.

It does not:

- execute discovery-authority binding;
- execute request preparation;
- create a scoring request;
- create evidence directories;
- run model fitting/scoring;
- publish champion evidence;
- alter the active PAPER manifest;
- grant scoring or promotion authority;
- enable LIVE.

## RED proof

Add focused production-presence assertions requiring the exact-release ceremony
binding described above.

The test must fail on current main because the request-preparation runbook
section does not yet define `EXPECTED_RELEASE_SHA`, verify
`RELEASE_MANIFEST.json`, or recheck `/opt/shreks/current` immediately before
invocation.

## GREEN proof

Update only the trusted-admin request-preparation runbook section so the new
assertions pass.

Canonical Python, Rust, repository-safety, and ARM64 release gates must remain
green.

## Explicit non-authority

```text
FL9_V2_DISCOVERY=FOUND_COMPATIBLE_EVIDENCE_ONLY
REQUEST_PREPARATION_EXECUTION=NOT_AUTHORIZED_BY_THIS_SLICE
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
CHAMPION_PUBLICATION_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
LIVE=DISABLED
```
