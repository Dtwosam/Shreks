# Fast PAPER Shadow Commissioning Asset Transport — Design

**Date:** 2026-09-27  
**Base main SHA:** `42110ac5b99ffca384f5fc8890401843d99751bb`

## Purpose

Make the already-proven learned Fast PAPER shadow service physically
commissionable from an immutable Shreks release without changing the historical
top-level G2 release payload allowlist and without granting automatic start,
PAPER cutover, signing, submission, or LIVE authority.

The supervised lifecycle is already proven in-repo. The current release bundle,
however, does not transport:

- `deploy/systemd/shreks-fast-paper-shadow.service`;
- `deploy/systemd/shreks-fast-paper-shadow.env.example`.

Adding those files directly to the top-level release archive would break the
backward-compatible G2 verifier boundary used by the currently installed root
release manager. Therefore the commissioning assets must ride inside the
already manifest-hashed Shreks wheel.

## Transport contract

Add a sealed wheel package:

```text
shreks_brain/_sealed_fast_paper_shadow_commissioning/
  __init__.py
  manifest.json
  shreks-fast-paper-shadow.service
  shreks-fast-paper-shadow.env.example
```

The nested manifest binds:

- exact release source SHA;
- exact native platform;
- exact canonical asset names;
- byte size;
- SHA-256;
- canonical manifest fingerprint.

Release construction must stage those two files from the exact checkout before
building the wheel and verify the completed wheel byte-for-byte against them.

The historical top-level release payload allowlist stays unchanged.

## Runtime/authority boundary

This slice transports assets only.

It must not:

- install a systemd unit on the host;
- create `/etc/shreks/fast-paper-shadow.env`;
- provision the shadow ledger;
- start, stop, enable, disable, or restart any service;
- add the shadow service to `shreks.target`;
- change the active legacy PAPER service;
- access provider credentials;
- access wallet/signing material;
- submit transactions;
- enable LIVE.

The existing shadow unit remains deliberately outside `shreks.target`.

## Materialization boundary

Provide a library helper that can materialize the authenticated assets into an
explicit caller-supplied private directory for later trusted-administrator
commissioning.

Rules:

- destination root must not be a symlink;
- materialization is source-SHA namespaced;
- existing exact materialization is idempotent;
- drift/tampering fails closed;
- materialized files are regular non-symlink files;
- no `/etc`, `/usr/local`, or systemd mutation occurs.

## RED acceptance

Tests require:

1. exact canonical manifest schema and fingerprint;
2. exact two-asset package member set;
3. tamper-evident package verification;
4. idempotent private materialization and drift rejection;
5. completed wheel verification against exact checkout files;
6. release build stages and verifies the sealed commissioning package;
7. `pyproject.toml` includes package data;
8. the top-level G2 release bundle does not add the shadow unit/env assets;
9. source contains no systemctl, sudo, signing/submission, scoring, or LIVE
   authority.

## Following slice

Use the sealed commissioning assets to build a trusted-administrator,
exact-release host installer/preflight that installs the dormant unit only,
then collect physical VPS commissioning evidence before any learned PAPER
cutover.
