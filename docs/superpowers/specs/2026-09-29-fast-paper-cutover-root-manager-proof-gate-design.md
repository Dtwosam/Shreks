# Fast Lane Physical Cutover Root-Manager Proof Gate — Design

**Date:** 2026-09-29  
**Base main SHA:** `0b360b8b9455cba504f3b2161da13418dd7c2fef`

## Purpose

Make the protected physical Fast PAPER cutover authenticate the durable
Fast-aware root release-manager installation proof as a hard code gate.

The prior slice can refresh and prove the separately installed root helper:

```text
/usr/local/sbin/shreks-release-manager
```

The physical cutover must not rely on an operator visually reviewing that proof.
It must independently authenticate the proof before any service-control action
and again after legacy PAPER is stopped.

LIVE remains disabled.

## Preflight input

Both physical cutover commands require:

```text
--release-manager-installation-proof-path <root-private-proof.json>
```

The proof must be a regular non-symlink `root:root 0600` file using the exact
closed schema emitted by
`shreks-fast-paper-release-manager-install-proof`.

## Proof authentication

The reader rejects:

- malformed or non-canonical JSON;
- duplicate keys;
- non-finite JSON values;
- unknown or missing fields;
- incompatible authority/status fields;
- invalid SHA-256 fields;
- invalid proof fingerprint;
- wrong file owner/group/mode.

The verifier then re-authenticates the live host against the proof:

- exact current release SHA/directory;
- current canonical release manifest;
- exact manifest-hashed Shreks wheel;
- exact sealed release-manager member and SHA-256;
- exact sealed release-bundle member and SHA-256;
- installed `/usr/local/sbin/shreks-release-manager` root:root 0755 bytes;
- installed `/usr/local/sbin/release_bundle.py` root:root 0755 bytes;
- exact historical one-line deployment sudoers rule and SHA-256.

The proof continues to require:

```text
status=VERIFIED
physical_cutover_authority=NOT_EXERCISED
paper_execution_authority=UNCHANGED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## Before-service-control gate

`preflight_fast_paper_physical_cutover(...)` authenticates the durable proof
immediately after exact release/runtime provenance and **before** any systemd
query or mutation.

A missing, stale, tampered, mismatched, or symlinked proof therefore prevents
all service-control work.

The successful physical-preflight receipt binds:

```text
release_manager_installation_proof_fingerprint_sha256=<exact-proof-fingerprint>
```

## Stop-boundary gate

`activate_fast_paper_physical_cutover(...)` first runs the ordinary physical
preflight with the same proof.

After legacy PAPER is stopped and confirmed inactive/dead, and after detached
shadow quiescence is rechecked, activation re-authenticates the durable proof
again.

The second proof fingerprint must equal the fingerprint bound by the initial
physical-preflight receipt.

Only after that equality proof may activation:

- initialize the final Fast run namespace;
- retarget the authoritative Fast run ID;
- run final stopped-legacy cutover preflight;
- issue cutover authorization;
- install/start the Fast candidate.

If proof identity changes across the stop boundary, activation fails before
final Fast handoff and restores legacy PAPER through the existing pre-start
rollback path.

## Success receipt

A successful physical-cutover receipt also binds the exact root-manager proof
fingerprint, preserving the control-plane prerequisite in the durable authority
chain.

## Authority firewall

This slice adds no new systemd command and no new economic authority.

It must not:

- refresh or replace the root release manager itself;
- change sudoers;
- widen deploy-account authority;
- add start/stop/restart/reload commands;
- execute BUY/SKIP/HOLD/REDUCE/SELL;
- call legacy scoring;
- access wallet/signing/submission paths;
- enable LIVE.

## Acceptance proof

Tests must prove:

1. durable proof canonical read + current-host reauthentication;
2. manager drift after proof fails;
3. sudoers drift after proof fails;
4. proof fingerprint tamper fails;
5. invalid root-manager proof blocks physical preflight before any systemd call;
6. proof fingerprint is included in physical-preflight success;
7. proof drift after legacy stop fails before final Fast handoff;
8. pre-start proof drift restores legacy PAPER authority;
9. physical-cutover success receipt binds the exact proof fingerprint;
10. Python, Rust, ARM64 and repository-safety CI remain green.

## Following protected step

After this gate is sealed and deployed, the protected host sequence is:

1. run the release-bound root-manager refresh/proof;
2. run physical cutover `preflight` with that exact proof;
3. require `READY_FOR_PROTECTED_PAPER_CUTOVER`;
4. run physical cutover `activate` with the same proof and a fresh explicit
   final Fast run ID.

The actual host invocation remains a trusted-administrator ceremony. Repository
merge/deploy alone does not start Fast PAPER trading.

LIVE remains disabled.
