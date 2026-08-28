# FL1 Release Verifier Compatibility Design

## Problem

FL1.5 originally packaged `target/release/shreks-fast-lane-acceptance` as a new runtime payload. The production VPS release manager was bootstrapped from an older sealed release whose verifier accepts an exact static payload set. That verifier rejects any additional static payload as unexpected before activation, so a newly sealed FL1.5 bundle containing the standalone reporter cannot reach the production host through the existing verified delivery path.

The verifier is a security boundary. FL1.5 must not solve this by weakening its allowlist, widening SSH/sudo authority, copying an unverified binary to the host, or bypassing immutable release verification.

## Decision

Keep the proven read-only acceptance implementation, but expose production acceptance as an early subcommand of the already-allowlisted `target/release/shreks-observe` binary:

```text
shreks-observe fast-lane-acceptance <database> <window_start_unix_ms> <as_of_unix_ms>
```

The standalone `shreks-fast-lane-acceptance` source target may remain for development/test coverage, but it is not included in the production release bundle.

## Dispatch boundary

`shreks-observe` must inspect the acceptance subcommand before `ObserverRuntimeConfig::from_env()` and before any provider plan/client/stream construction. Acceptance mode therefore:

- does not require provider credentials or normal observer runtime configuration;
- makes no network/provider calls;
- opens only the explicitly supplied SQLite path through the existing `SQLITE_OPEN_READ_ONLY | SQLITE_OPEN_NO_MUTEX` report store;
- performs no migration, database creation, service mutation, PAPER action, wallet/signing action, transaction submission, or LIVE action;
- preserves the existing stable `key=value` report and fail-closed argument/schema/timing behavior.

Normal `shreks-observe` startup remains unchanged when the first argument is not `fast-lane-acceptance`.

## Release compatibility boundary

New production bundles must return to the historical verifier-compatible static payload set:

- `deploy/systemd/shreks-observe.service`
- `deploy/systemd/shreks-paper-campaign.service`
- `deploy/systemd/shreks-paper-evidence.service`
- `deploy/systemd/shreks.target`
- `target/release/shreks-observe`
- `target/release/shreks-paper-evidence`
- exactly one `wheelhouse/shreks_brain-*.whl`

The release verifier implementation used for this bundle is restored to the exact historical blob already trusted by the VPS bootstrap. The current release build no longer builds or copies the standalone acceptance binary into staging.

## Operator evidence

The production FL1.5 runbook must invoke acceptance from the exact verified `/opt/shreks/current/target/release/shreks-observe` payload. A locally compiled/copy-only reporter or an unmanifested executable does not count as production evidence.

## Exit rule

This hotfix is complete only when Rust, Python, repository safety, and native ARM64 release-build CI are green, the immutable release bundle is verifier-compatible, and the runbook points only at the verified observer subcommand. FL1.5 still requires real-host acceptance evidence after deployment; FL2 remains blocked and LIVE remains disabled until that gate passes.
