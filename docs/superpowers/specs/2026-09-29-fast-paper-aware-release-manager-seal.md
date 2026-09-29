# Fast Lane Post-Cutover Release Manager — Release Seal

**Date:** 2026-09-29  
**Implementation main SHA:** `ca30edf0a6f06f8e56fd62ac09402667bb1e747d`  
**Primary implementation PR:** #661  
**Authorization-hardening PR:** #663  
**Hardened implementation PR head:** `314953aa022f4bd6ed7eab9bd9f9e3296bdc40f8`  
**Hardened implementation CI:** `36547773216`  
**Status:** SEALED FOR IMMUTABLE RELEASE + PROTECTED DEPLOY OF FAST-AWARE UPGRADE CAPABILITY; CURRENT PAPER AUTHORITY MUST REMAIN UNCHANGED BY THIS SEAL; SIGNING/SUBMISSION NOT AUTHORIZED; LIVE DISABLED

## Purpose

Seal the reviewed Fast-aware post-cutover release path so the capability can enter
the immutable Shreks release/deploy chain.

This seal does **not** perform the initial physical Fast PAPER cutover and does
not change whichever PAPER runtime is currently authoritative on the protected
host.

Before physical Fast PAPER cutover, deployment of this seal only makes the
post-cutover upgrade machinery available in the immutable release.

After a separately successful physical cutover, later immutable releases may use
the Fast-aware release path instead of reinstalling the legacy score-gated PAPER
runtime.

## Implementation proof

PR #661 merged the protected Fast-aware release manager:

`36219f82e8a7048a61ef3c6321646e9d75b30e3d`

PR #663 then hardened release-bound production authorization and runtime
startup semantics:

`ca30edf0a6f06f8e56fd62ac09402667bb1e747d`

The exact hardened PR head was:

`314953aa022f4bd6ed7eab9bd9f9e3296bdc40f8`

Exact-head CI run:

`36547773216`

Result:

- Python: SUCCESS — `4314 passed, 4 warnings`;
- Rust workspace: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

The sealed implementation provides:

- append-only Fast-to-Fast authoritative release handoff;
- target-release-local Fast runtime tool materialization from sealed wheel
  assets;
- clean learned-action handoff requiring no pending BUY and equal learned
  decision/execution cursors;
- open PAPER position and authoritative market-position mapping preservation;
- release-bound evidence/source archival outside service-writable roots;
- atomic rotation of target runtime manifest, execution policy, BUY-writer
  policy, learned decision checkpoint, Fast run ID, production authorization,
  systemd units and `/opt/shreks/current`;
- production authorization that accepts the original physical-cutover grant or
  one exact Fast-to-Fast release authorization;
- target release authorization bound to source authorization, append-only
  handoff, target release/manifest/run/binding/execution policy;
- pre-start rollback to the prior Fast release only;
- post-start failure that stops authority, revokes the production authorization
  into manual-recovery state, and never restores legacy score-gated PAPER;
- root release-manager routing that keeps the legacy path before Fast cutover
  and dispatches through the Fast-aware path once the production authorization
  marker exists;
- explicit Fast-aware install/activation commands for administrators.

## Routine release compatibility boundary

This seal authorizes only routine code deployment across releases that preserve
the reviewed Fast PAPER trading semantics.

The Fast-aware release manager requires exact compatibility for:

- champion bytes and identity;
- decision binary;
- feature-feed binary;
- continuous action policy;
- Fast state/event-loop versions;
- risk/fill/position-action policies;
- strategy/assessment identity;
- quote provider/mint/decimals;
- route-evidence version;
- authoritative observer database;
- PAPER evidence and learned-decision checkpoint locations;
- BUY-writer authority semantics.

A change to strategy, champion, action policy, risk policy, execution semantics
or any other trading authority remains a separate reviewed promotion/migration
and is not authorized by this seal.

## Automatic delivery authority granted by this seal

After this docs-only `seal:` commit lands on `main` and seal-main CI is green,
authorize the existing immutable delivery chain only to:

1. build and verify one immutable release for the exact seal SHA;
2. include the Fast-aware release manager and hardened authorization/runtime
   gate in that release;
3. publish the exact immutable release;
4. deploy that exact release through the repository's existing protected
   delivery path;
5. preserve the current PAPER authority mode during this deployment;
6. verify exact release/service/process provenance after deployment.

If production PAPER has **not** physically cut over to Fast Lane yet, ordinary
deployment must continue through the existing legacy activation path because no
production Fast authorization marker exists.

If production PAPER **has** already physically cut over to Fast Lane, subsequent
routine immutable releases must route through the Fast-aware path and must not
install/start the legacy score-gated campaign runtime.

## Fast-aware upgrade boundary after physical cutover

When a production Fast authorization exists, a routine immutable release
upgrade may:

```text
stage/verify target immutable release
-> authenticate current Fast authorization/source release
-> stop authoritative Fast PAPER
-> reload exact stopped source state
-> require pending BUY absent
-> require learned decision cursor == authoritative execution cursor
-> create/reuse exact append-only successor namespace
-> archive source release-bound evidence
-> rotate target authority/control files
-> rotate release-bound production authorization
-> install sealed Fast PAPER unit
-> switch /opt/shreks/current
-> daemon-reload
-> start shreks.target
-> bounded verify target Fast PAPER
```

The target run namespace is release-specific and replay-safe.

Open PAPER positions may remain open and carry across the routine release
handoff without flattening exposure.

## Rollback boundary

Before the first target start attempt, a failure may restore the exact source
Fast release and source authority.

At or after the first target start attempt:

- automatic rollback is forbidden;
- target runtime authority is stopped;
- production authorization is revoked into manual-recovery state;
- source Fast is not automatically restarted;
- legacy score-gated PAPER is never restored;
- manual recovery is required.

This prevents duplicate economic PAPER actions across release namespaces.

## Automatic delivery prohibitions

This seal does not authorize automatic delivery to:

- perform the initial physical legacy-to-Fast PAPER cutover;
- create a first physical-cutover authorization when none exists;
- invent strategy/champion/policy migration authority;
- bypass pending-BUY/cursor-gap checks;
- bypass source/target release verification;
- restore legacy score-gated PAPER after Fast cutover;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Acceptance proof

The sealed capability is release-eligible only if:

- exact hardened implementation CI remains four-gate green;
- seal-main CI is green;
- immutable release identity is the exact seal SHA;
- protected deployment verifies exact release/process provenance;
- deployment leaves the current PAPER authority unchanged when no Fast
  production authorization exists;
- after a future physical cutover, post-cutover deployments route through the
  Fast-aware release manager rather than the legacy activation path;
- signing/submission remains not granted;
- LIVE remains disabled.

## Authority state after this seal

Before a separately successful physical Fast PAPER cutover:

```text
production_paper_runtime=UNCHANGED
fast_aware_release_upgrade_capability=SEALED_AND_DEPLOYABLE
initial_fast_paper_cutover=TRUSTED_ADMIN_CEREMONY_ONLY
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

After a separately successful physical cutover:

```text
production_paper_runtime=FAST_LANE_LEARNED
routine_release_path=FAST_AWARE_ONLY
legacy_score_runtime_restore=FORBIDDEN
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```
