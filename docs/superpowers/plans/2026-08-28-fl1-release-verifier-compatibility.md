# FL1 Release Verifier Compatibility Implementation Plan

> Execute with TDD. Do not start FL2 or change PAPER/LIVE authority.

**Goal:** Make the merged FL1.5 production acceptance tooling deployable through the existing immutable VPS release verifier without widening host authority.

**Architecture:** Keep the read-only acceptance report implementation. Route production invocation through an early `shreks-observe fast-lane-acceptance` subcommand and restore the release bundle to the historical verifier-compatible payload set.

## Task 1: Pin historical release payload compatibility

**Tests:** `python/tests/test_fl1_fast_lane_acceptance_release_payload.py`

1. Require the exact historical static payload set.
2. Reject an optional standalone acceptance payload in the verifier/build script.
3. Prove RED against the merged FL1.5 release bundle.
4. Restore the historical verifier payload contract and remove the standalone reporter from release staging.
5. Run the Python suite and native ARM64 release-build gate.

## Task 2: Route acceptance through `shreks-observe`

**Files:**
- `crates/shreks-observer/src/bin/shreks-observe.rs`
- `crates/shreks-observer/src/bin/fast_lane_acceptance_cli.rs`
- `crates/shreks-observer/tests/fast_lane_acceptance_observer_subcommand.rs`

1. Require acceptance dispatch before `ObserverRuntimeConfig::from_env()`.
2. Force legacy startup to fail quickly with invalid runtime config in the test harness so RED is observable.
3. Reuse the existing read-only report store/output contract.
4. Verify acceptance succeeds even when normal runtime config is invalid, proving provider/runtime initialization was bypassed.
5. Verify malformed acceptance invocations fail closed.
6. Run the full Rust workspace.

## Task 3: Correct the production runbook

**Files:**
- `crates/shreks-observer/tests/fast_lane_acceptance_runbook.rs`
- `docs/operations/FL1_FAST_LANE_ACCEPTANCE.md`

1. Require the verified `target/release/shreks-observe` payload plus `fast-lane-acceptance` subcommand.
2. Forbid the incompatible standalone release path.
3. Prove the stale runbook RED.
4. Update immutable-release preconditions, reporter description, production command, and hold/exit wording.
5. Run the runbook/full Rust tests.

## Task 4: Final safety and release gate

1. Run full Rust, Python, repository-safety, and native ARM64 sealed-release CI on the exact head.
2. Audit the PR diff for strategy, PAPER authority, risk, wallet/signing, transaction submission, or LIVE changes; any such change is out of scope.
3. Mark PR ready and merge only on a fully green exact head, using a `seal:` merge subject so the immutable release workflow accepts the commit.
4. Verify merged-main CI.
5. Build/deploy that exact sealed release through the existing release/deploy workflows when dispatch authority is available.
6. Capture real-host FL1.5 evidence before any FL2 work.
