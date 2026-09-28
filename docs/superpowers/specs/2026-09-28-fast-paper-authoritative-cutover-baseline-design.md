# Fast Lane Authoritative PAPER Cutover Baseline Provisioning — Design

**Date:** 2026-09-28  
**Base main SHA:** `86df9f478dd7d4b50dcc38c6bca56852f59a58b4`

## Purpose

Add the protected write-once operation that transfers the detached shadow's
authenticated learned-decision cursor into the dedicated authoritative Fast
PAPER decision namespace.

This is not the physical PAPER authority switch.

The operation exists because the detached shadow may have already consumed many
learned decision rows while the authoritative Fast execution namespace is still
at economic sequence zero. Production must start after that learned history
without replaying those historical shadow decisions economically.

The authoritative coordinator introduced by PR #653 already understands this
non-economic baseline. This slice provisions and authenticates that baseline.

## Command

Add:

```text
shreks-fast-paper-authoritative-cutover-baseline
```

Required arguments:

- `--fast-manifest-path`;
- `--authoritative-runtime-env-path`;
- `--receipt-path`;
- `--expected-release-sha`.

The destination checkpoint path is not supplied by the operator. It comes only
from the closed authoritative production environment:

```text
SHREKS_FAST_PAPER_AUTHORITATIVE_DECISION_CHECKPOINT_PATH
```

## Quiescence requirement

The command does not stop, start, restart, reload, enable, or disable any
service.

It performs only read-only systemd inspection:

```text
systemctl show shreks-fast-paper-shadow.service
```

and requires:

```text
ActiveState=inactive
SubState=dead
MainPID=0
```

The same systemd state must remain stable before and after shadow-checkpoint
authentication and again after destination publication.

The external protected ceremony remains responsible for quiescing the detached
shadow before invoking this command.

## Source authentication

The source is exactly the `checkpoint_path` sealed in the authenticated Fast
runtime manifest.

The command requires:

1. exact release SHA;
2. authenticated manifest immutable bindings;
3. regular non-symlink shadow checkpoint;
4. canonical authenticated `FastPaperRuntimeState`;
5. reconstructed state from the exact manifest and cursor equals the source;
6. source bytes, inode identity, size, and mtime remain unchanged while
   quiescence is rechecked.

The source file is never modified.

## Destination contract

The authoritative decision root must already exist and be a regular
non-symlink directory.

Before first provisioning it must be empty.

The baseline checkpoint must live directly inside that directory at the exact
production-configured path.

Publication is create-only:

- `O_CREAT|O_EXCL`;
- mode `0600`;
- ownership `shreks:shreks`;
- file fsync;
- parent-directory fsync.

The destination bytes must equal the authenticated shadow checkpoint bytes
exactly.

## Crash/replay behavior

A crash after checkpoint publication but before receipt publication must not
brick cutover.

A retry may accept a preexisting destination only when:

- it is a regular non-symlink file;
- it is the only member of the authoritative decision directory;
- its bytes equal the currently authenticated, still-quiescent shadow
  checkpoint exactly;
- decoded decision state equals the source state exactly.

The retry never overwrites the checkpoint. The receipt records
`baseline_replayed=true`.

Any conflicting destination or additional production decision evidence fails
closed.

## Receipt

The command writes one canonical no-replace receipt outside the service-writable
authoritative decision tree:

```text
schema_name=shreks.fast_paper_authoritative_cutover_baseline
schema_version=1
state=AUTHORITATIVE_DECISION_BASELINE_PROVISIONED
```

It binds:

- release SHA;
- runtime-manifest fingerprint;
- inactive/dead shadow unit state;
- shadow checkpoint path and file SHA-256;
- decision-state fingerprint;
- decision cursor sequence;
- authoritative checkpoint path;
- whether this was exact crash recovery;
- observation timestamp.

Every receipt states:

```text
production_fast_paper_runner=SEALED_NOT_ACTIVE
production_paper_cutover=NOT_GRANTED
service_control_authority=NOT_GRANTED
authoritative_paper_mutation=NOT_GRANTED
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

The receipt is self-fingerprinted and has a strict canonical reader.

## Cutover preflight integration

Upgrade `shreks-fast-paper-cutover-preflight` to schema version 3 and require:

```text
--authoritative-decision-baseline-receipt-path
```

Preflight must authenticate the receipt and require it to match the current:

- release;
- manifest;
- shadow checkpoint path and bytes;
- authoritative decision checkpoint path;
- decision-state fingerprint;
- decision cursor sequence.

A READY report gains:

```text
AUTHORITATIVE_DECISION_BASELINE_PROVISIONED_QUIESCENT=PASS
```

This prevents a manually copied or stale decision checkpoint from satisfying
the cutover gate.

## Authority firewall

This slice must not:

- stop/start/restart/reload/enable/disable systemd;
- mutate the shadow checkpoint;
- write decision evidence;
- execute BUY/SKIP/HOLD/REDUCE/SELL;
- write the authoritative PAPER ledger/checkpoint;
- modify the authoritative economic runtime state;
- sign or submit transactions;
- enable LIVE.

The only authoritative write is the non-economic learned-decision baseline
checkpoint plus its external receipt.

## Acceptance proof

Tests must prove:

1. active shadow service blocks provisioning before any destination write;
2. inactive/dead/MainPID=0 permits provisioning;
3. source bytes and authenticated state are copied exactly;
4. destination is no-replace and mode 0600;
5. additional authoritative decision evidence blocks provisioning;
6. source change during authentication blocks provisioning;
7. crash-after-copy retry accepts only an exact preexisting checkpoint;
8. receipt fingerprint drift is rejected;
9. provisioner source contains only read-only `systemctl show` authority;
10. cutover preflight requires the baseline receipt and rejects identity drift;
11. existing authoritative economic handoff remains sequence zero and unchanged;
12. Python, Rust, ARM64, and repository-safety CI remain green.

## Following slice

Adapt the proven persisted-evidence source writers/publishers to the
authoritative checkpoint/runtime pair so the production runner can continuously
obtain BUY authority, quote/USD, OPEN reduction/exit authority, and pending-BUY
retry authority without reading the shadow ledger.

That source-production slice still does not perform the systemd PAPER authority
switch.

LIVE remains disabled.
