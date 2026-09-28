# Fast Lane Authoritative PAPER Protected Host Preparation — Design

**Date:** 2026-09-28  
**Base main SHA:** `f80ca7e41e29bbd085d13a1b4d32a799bd332db7`

## Purpose

Prepare the protected host for the already-sealed authoritative Fast PAPER
runtime without changing service state.

This slice installs only the exact authoritative environment, creates the
service-owned source roots, and proves that the target host still matches the
cutover baseline and reviewed source-writer authority.

It does not install or replace the active PAPER unit and does not invoke
systemd.

## Host configuration

Install:

```text
/etc/shreks/fast-paper-authoritative.env
```

as `root:shreks 0640`.

The candidate environment is parsed with the closed authoritative cutover
environment contract and must bind:

- exact runtime manifest;
- exact observer database;
- exact authoritative Fast run ID;
- exact execution policy;
- exact BUY-writer policy;
- exact source-root paths.

Existing exact bytes are idempotent. Existing different bytes fail closed.

## Source roots

Create only:

```text
/var/lib/shreks/fast-paper-authoritative
/var/lib/shreks/fast-paper-authoritative/decision
/var/lib/shreks/fast-paper-authoritative/execution-sources
/var/lib/shreks/fast-paper-authoritative/buy-authority-sources
/var/lib/shreks/fast-paper-authoritative/quote-usd-sources
/var/lib/shreks/fast-paper-authoritative/reduction-sources
/var/lib/shreks/fast-paper-authoritative/pending-buy-retry-sources
```

as `shreks:shreks 0700`.

The decision baseline checkpoint is provisioned separately by the protected
cutover-baseline command and remains `shreks:shreks 0600`.

## Protected authority verification

Host preflight requires the four reviewed authority files to remain
`root:shreks 0640`:

- runtime manifest;
- learned service policy;
- execution policy;
- BUY-writer policy.

The BUY-writer policy is re-bound to the exact manifest/service policy and
therefore re-authenticates the release-local entry-authority binary and
operator risk-control file.

## Baseline receipt verification

The cutover-baseline receipt must authenticate and match:

- release source SHA;
- manifest fingerprint;
- authoritative decision checkpoint path;
- decision-state fingerprint;
- decision cursor;
- unchanged detached-shadow checkpoint bytes.

The authoritative decision baseline must still equal the quiesced shadow
decision checkpoint exactly.

## Runtime preflight

The final host readiness command bootstraps the authoritative runtime with the
installed environment and requires:

- all source roots exact;
- all protected authority metadata exact;
- authenticated decision baseline;
- authenticated BUY-writer policy;
- no pending authoritative BUY;
- no authoritative open mapped positions.

A successful receipt reports:

```text
state=READY_FOR_PROTECTED_PAPER_CUTOVER_REVIEW
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

## CLI

```text
shreks-fast-paper-authoritative-host-prepare config-preflight <release-sha> <candidate-env>
shreks-fast-paper-authoritative-host-prepare install-config <release-sha> <candidate-env>
shreks-fast-paper-authoritative-host-prepare provision-roots <release-sha>
shreks-fast-paper-authoritative-host-prepare host-preflight <release-sha> <baseline-receipt>
```

All commands require root. None invoke systemd.

## Authority firewall

This slice must not:

- start/stop/restart/reload/enable/disable a service;
- install the Fast PAPER candidate over the active legacy unit;
- execute or commit PAPER actions;
- mutate the authoritative ledger/checkpoint;
- fetch provider/network data;
- sign or submit transactions;
- enable LIVE.

## Following slice

The next explicit slice is the protected physical PAPER cutover ceremony. It
must re-run the final cutover preflight after the legacy PAPER service is
quiesced, atomically install the sealed Fast candidate as the active PAPER
unit, daemon-reload, start it, and run bounded protected verification.

LIVE remains disabled.
