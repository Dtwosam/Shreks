# FL9 Python Offline Deterministic Row Adapter — Implementation Plan

**Date:** 2026-09-04
**Base:** `b2b1e532e60bdcfbd3c91eda7373a4763307b81a`

## TDD

1. Add RED tests for exact request serialization, reserve variants, process isolation, and response authentication.
2. Open draft PR and record exact missing package/API.
3. Implement immutable evidence models and serializers.
4. Implement canonical request builder.
5. Implement canonical row-result decoder/fingerprint authentication.
6. Implement explicit-binary-path offline subprocess runner with temporary-file cleanup.
7. Add package exports.
8. Run focused tests plus full four-gate CI.
9. Freeze exact GREEN head and guarded squash merge.

## Authority boundary

Only this package may launch the offline Rust row evaluator. It may not launch cargo, access providers/network/database, execute PAPER actions itself, promote, sign, submit, or enable LIVE.

## Following work

Chronological campaign driver alternating Rust row evaluation and authoritative PAPER prefix replay, then real same-population baseline run evidence for the sealed FL9 superiority evaluator.
