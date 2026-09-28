# Fast Lane FL11.4 Explicit PAPER Champion Promotion — Design

**Date:** 2026-09-28
**Base main SHA:** `6ea8bd114d9fafcd39f69245ddec319e1829472b`
**Phase:** FL11.4 — champion/challenger promotion

## Purpose

Add the Fast Lane-native authority boundary that turns a sealed
`PROMOTION_READY` result into one explicit, versioned, auditable approved PAPER
champion identity.

This slice records champion approval only. It does not replace the protected
Fast PAPER shadow authority bundle, stop/start services, migrate the
authoritative PAPER ledger, switch production PAPER authority, sign/submit, or
enable LIVE.

The controlled production PAPER cutover remains a later migration slice and
must consume this registry as one of its preconditions.

## Why a new Fast Lane registry

The generic E6/E8 registry predates `FastForecastChampionArtifact` and uses a
different candidate identity model. Reusing it for this transition would create
an unproven identity bridge.

FL11.4 therefore gets a dedicated Fast Lane PAPER champion registry whose
authoritative identity is exactly:

- champion version;
- champion fingerprint;
- promotion-readiness report fingerprint;
- promotion policy version/fingerprint;
- release SHA and shadow runtime manifest fingerprint;
- shadow binding and evidence window.

## Registry schema

`shreks.fast_paper_champion_registry` version `1`.

The registry is one canonical self-fingerprinted JSON document containing:

- `revision`;
- current champion version/fingerprint;
- ordered transition history;
- `production_paper_cutover=NOT_GRANTED`;
- `signing_submission_authority=NOT_GRANTED`;
- `live_authority=DISABLED`;
- registry fingerprint.

Each transition contains:

- monotonically increasing sequence;
- exact readiness report fingerprint as decision reference;
- readiness policy version/fingerprint;
- candidate champion version/fingerprint;
- prior champion version/fingerprint or null on first promotion;
- release SHA;
- shadow runtime manifest fingerprint;
- shadow binding fingerprint;
- evidence window;
- operator-supplied `decided_at_unix_ms`;
- non-empty operator reason;
- transition fingerprint.

The last transition must exactly match the registry's current champion.

## Input authentication

Promotion requires:

1. exact Fast PAPER runtime manifest;
2. exact expected release SHA;
3. canonical FL11.4 readiness report;
4. readiness decision `PROMOTION_READY`;
5. readiness report fingerprint valid;
6. readiness report authority firewall still intact;
7. readiness release/manifest/champion/action-policy identity exactly matching
   the authenticated runtime manifest.

The manifest is authenticated through
`verify_fast_paper_runtime_bindings(...)`, so the candidate champion file,
champion fingerprint/version, decision binary, and feature binary remain
cryptographically bound.

Unknown readiness fields, non-canonical JSON, duplicate keys, fingerprint
drift, identity drift, or authority drift fail closed.

## Compare-and-swap replacement rule

The first promotion may create an empty registry with no incumbent.

Once a current Fast Lane PAPER champion exists, replacing it requires the
caller to supply the exact incumbent champion fingerprint. A stale or absent
expected incumbent fingerprint fails closed.

This prevents a reviewed promotion command from silently replacing a champion
that changed after review.

Promoting the already-current candidate is idempotent and creates no duplicate
history entry.

Reusing an existing readiness decision reference for a conflicting candidate
is rejected.

## Atomic publication

The registry mutation must be atomic and serialized:

1. require a regular non-symlink parent directory;
2. acquire an exclusive sidecar file lock;
3. re-read/authenticate the registry while holding the lock;
4. apply compare-and-swap checks;
5. build the next canonical registry in memory;
6. write a mode-0600 same-directory temporary file;
7. fsync the file;
8. atomically `os.replace(...)` the registry;
9. fsync the parent directory;
10. read back and re-authenticate the exact published registry.

A failed write must leave either the old complete registry or the new complete
registry, never a partially written state.

## Commands

CLI: `shreks-fast-paper-champion-promotion`

Subcommands:

`preflight`
- read-only;
- authenticates manifest/readiness/current registry;
- reports `READY_TO_PROMOTE` or `ALREADY_CURRENT`;
- requires expected incumbent fingerprint for replacement.

`promote`
- performs the atomic registry mutation;
- requires explicit `--decided-at-unix-ms` and `--reason`;
- reports `PROMOTED` or `ALREADY_CURRENT`.

Common arguments:

- `--manifest-path`
- `--readiness-path`
- `--registry-path`
- `--expected-release-sha`
- optional `--expected-current-champion-fingerprint`

## Authority boundary

A successful transition means only:

`paper_champion_authority=RECORDED`

It always retains:

```text
production_paper_cutover=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

No service, PAPER ledger, runtime manifest, champion file, wallet, transaction,
or LIVE setting may be mutated by this module.

## Acceptance tests

Tests must prove:

- first ready candidate becomes the only current champion;
- transition and registry fingerprints are deterministic;
- an already-current candidate is idempotent;
- replacement requires exact expected incumbent fingerprint;
- stale incumbent expectation fails closed without changing bytes;
- non-ready evidence cannot promote;
- readiness fingerprint drift and manifest/champion identity drift fail closed;
- conflicting reuse of a decision reference is rejected;
- registry corruption or unknown fields fail closed;
- an injected write failure preserves the previous complete registry;
- source contains no scoring, PAPER execution, systemd, signing/submission, or
  LIVE-enable control path;
- CLI is packaged.

## Following slice

After this registry is merged and verified, the controlled production PAPER
cutover may use the current registry champion plus the existing flat-ledger,
restart-equivalence, accounting, and protected-host gates to migrate authority
from legacy PAPER to Fast Lane PAPER. LIVE remains disabled.
