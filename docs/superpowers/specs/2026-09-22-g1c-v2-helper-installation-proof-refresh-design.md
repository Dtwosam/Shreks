# G1C V2 Exact-Release Helper Installation-Proof Refresh — Design

**Date:** 2026-09-22  
**Status:** software contract only; proof refresh for an already-matching helper; no helper publication or manifest mutation

## Purpose

The decision-backed rotation-readiness wrapper is now production-present and requires a
fresh helper installation proof bound to the exact current immutable release.

Production verification already proves the installed
`/usr/local/sbin/shreks-paper-manifest-manager` bytes and metadata match the current
release. The existing install/proof ceremony can produce a fresh proof, but invoking the
ordinary installer retains authority to publish the helper if the destination is absent.

A proof-refresh path must therefore fail closed unless the helper is already exact and
must have no path that publishes or replaces helper bytes.

## Contract

Add a release-local CLI:

`shreks-g1c-v2-paper-manifest-manager-install-proof-refresh`

Required input:

- exact expected immutable release source SHA.

The refresh implementation must:

1. require root through the existing installation-proof contract;
2. capture the existing canonical pre-installation state snapshot for the exact release;
3. invoke the existing release-bound installer only in a new
   `require_already_installed=True` mode;
4. require the installer receipt status to be exactly `ALREADY_INSTALLED`;
5. fail before publication if the destination is absent;
6. fail without replacement if destination bytes differ;
7. fail without chmod/chown if destination metadata differs;
8. pass the canonical prestate and ALREADY_INSTALLED receipt into the existing
   `verify_postinstall_state`;
9. return the existing
   `shreks.g1c_v2_paper_manifest_manager_installation_proof` version 1 proof unchanged.

The installer default remains unchanged for the separately authorized first-install
ceremony. The new mode only narrows behavior.

## Non-mutation guarantee

When `require_already_installed=True`:

- no temporary publication file is created;
- `_publish_no_replace` is unreachable;
- no helper bytes are written;
- no helper ownership or mode is changed;
- no service is stopped, started, or restarted;
- no protected campaign manifest, sudoers, database, evidence, or risk-control state is modified.

The refresh wrapper itself must not contain or call any helper-publication primitive.

## Proof semantics

A successful refresh produces the same exact-release proof schema already required by
rotation readiness:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

It grants no install authority beyond observing the already-installed helper and grants
no manifest-rotation authority.

## Authority boundary

This slice does not:

- execute decision-backed readiness;
- create or stage candidate/binding/readiness artifacts;
- install an absent helper;
- replace or repair a helper;
- modify sudoers;
- rotate the runtime manifest;
- retry scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

Production execution requires a later separate production-presence proof and explicit
trusted-admin ceremony.
