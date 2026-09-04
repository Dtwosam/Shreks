# FL9 Installed Proof-Tool Cache Compatibility — Design

**Date:** 2026-09-04

## Status

Operational compatibility correction discovered by the first genuine PAPER #206 host execution attempt after sealed release `ad2f5ab1fc39b7c60b9f6884515a96fa55e335bb` was deployed successfully.

FL9 superiority remains **EVIDENCE PENDING**.
LIVE remains disabled.

## Observed host failure

The genuine host command:

`shreks-fast-proof-workspace`

failed before reading/exporting PAPER evidence with:

`ValueError: fast proof tools package may contain regular files only`

The sealed wheel had already passed build-time exact-member, source-SHA, platform, size, and SHA-256 authentication. The failure occurs only after installation because Python/pip may create:

`shreks_brain/_sealed_fast_tools/__pycache__/__init__.*.pyc`

inside the installed package directory.

## Problem

`verify_fast_proof_tools_package(...)` intentionally enforces an exact pristine staging-directory member set. `materialize_fast_proof_tools(...)` reuses that exact filesystem-directory verifier against the installed package. That conflates immutable wheel payload membership with interpreter-generated installation cache state.

The result is a false fail-closed condition on a legitimate installed wheel.

## Decision

Keep all existing staging and wheel verification strict and unchanged.

Only the installed-resource materialization path may tolerate one interpreter-generated `__pycache__` directory, and only when every member of that directory:

- is a regular file;
- is not a symlink;
- matches `__init__.*.pyc`.

The installed path must still require the exact sealed source files:

- `__init__.py`;
- `manifest.json`;
- `export_fast_training_features.bin`;
- `shreks-fast-campaign-decision.bin`;
- `shreks-fast-entry-authority.bin`.

The manifest identity and every native binary size/SHA-256 remain authenticated exactly as before. Any other file, directory, symlink, cache member, missing payload, changed payload, source-SHA mismatch, or platform mismatch fails closed.

## Compatibility boundary

The public pristine-directory verifier remains strict so release construction and tests cannot accidentally normalize extra filesystem members.

The wheel verifier remains exact-member and duplicate-member strict.

Only `materialize_fast_proof_tools(...)`, which reads an already-installed authenticated wheel resource, gets the narrow cache compatibility rule.

## Authority boundary

This correction does not:

- open or mutate SQLite;
- change exported training rows;
- change model/training/evaluation policy;
- change strategy families or execution costs;
- change PAPER decisions;
- change risk authority;
- change release top-level allowlists;
- widen SSH/sudo authority;
- enable LIVE.

## Acceptance

The slice is acceptable only if:

1. a regression reproduces the installed `__pycache__` failure;
2. installed materialization succeeds with only canonical `__init__.*.pyc` cache members;
3. unexpected cache members still fail closed;
4. pristine package verification still rejects extra directories;
5. wheel exact-member authentication remains unchanged;
6. full Python, Rust, repository-safety, and ARM64 release CI are green;
7. the fix is sealed/released/deployed through the existing protected path;
8. the same genuine #206 host command advances past proof-tool materialization.

LIVE remains disabled.
