# FL9 Deterministic Candidate Manifest — Implementation Plan

**Date:** 2026-09-04
**Base:** `5d90afa561c8f78b2ebc067bfcbc26167dd2a35a`

## TDD

1. Commit shared canonical Impulse Scalp + Longer Runner manifest fixture.
2. Commit Rust RED tests for missing typed manifest builder/codec and full-policy fingerprint sensitivity.
3. Commit Python RED tests for missing manifest decoder and identity extraction.
4. Open draft PR and record exact RED.
5. Implement Rust typed policy mapping, manifest validation, canonical codec, and SHA-256.
6. Implement Python exact decoder/validation against the same fixture.
7. Prove that changing every selected policy family field changes candidate fingerprint or fails validation as appropriate.
8. Run full four-gate repository CI.
9. Freeze exact GREEN head, update provenance, guarded squash merge.

## Authority boundaries

No provider/database/PAPER execution/ledger/risk/promotion/LIVE changes.

## Following slice

Deterministic lifecycle PAPER adapter using manifest identity + canonical decision wire + explicit execution evidence.
