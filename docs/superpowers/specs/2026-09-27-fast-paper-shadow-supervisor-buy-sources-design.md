# Fast PAPER Shadow Supervisor BUY Source Wiring — Design

**Date:** 2026-09-27  
**Base main SHA:** `04f5b426bf80e58fee5346308fd1b44a68802120`

## Purpose

Wire the bounded initial BUY source publisher into the supervised learned Fast
PAPER shadow service without expanding its authority.

The supervisor must gain one dedicated BUY-authority source root, provision it
as a private isolated leaf, and invoke the already-bounded BUY publisher before
the coordinator.

This slice does not create BUY authority facts.

## Configuration

Add required supervisor path:

`SHREKS_FAST_PAPER_SHADOW_BUY_AUTHORITY_SOURCE_DIRECTORY`

Expose it as `FastPaperShadowSupervisorConfig.buy_authority_source_directory`.

It must be absolute and must participate in the same strict existing-directory,
non-symlink, distinct/non-overlapping source-root validation as decision,
execution, quote/USD, reduction, and pending-BUY-retry roots.

## Provisioning

The explicit one-time shadow provisioner must create the BUY-authority source
root as a private mode-0700 leaf beneath an existing host-owned parent.

It must participate in root-separation validation.

The example systemd environment file must include the setting.

## Supervisor ordering

For each coordinated cycle:

```text
SKIP publisher
-> BUY publisher
-> OPEN publisher
-> coordinator
```

The BUY publisher receives exactly:

- current runtime manifest;
- current execution bootstrap;
- decision evidence directory;
- BUY authority source directory;
- quote/USD source directory.

No values are derived by the supervisor.

## Authority boundary

```text
BUY_AUTHORITY_PRODUCTION=NOT_GRANTED
BUY_SOURCE_PUBLICATION=DELEGATED_TO_BOUNDED_PUBLISHER
PAPER_EXECUTION=COORDINATOR_ONLY
PROVIDER_NETWORK_AUTHORITY=NOT_GRANTED
SCORING_CONTROL_PATH=FORBIDDEN
SIGNING_SUBMISSION=NOT_GRANTED
AUTHORITATIVE_PAPER_LEDGER=UNCHANGED
LIVE=DISABLED
```

## RED acceptance

The intentional RED contract requires:

- required BUY-authority supervisor config/env path;
- source-root separation and private provisioner inclusion;
- exact SKIP -> BUY -> OPEN -> coordinator ordering;
- exact argument forwarding to the existing BUY publisher;
- env example coverage;
- no BUY authority derivation, provider/network, scoring, signing/submission,
  or LIVE authority.

Current main is expected to fail only because this supervisor wiring does not
exist yet.
