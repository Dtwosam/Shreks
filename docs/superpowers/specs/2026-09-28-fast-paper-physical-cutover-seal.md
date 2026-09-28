# Fast Lane Protected Physical PAPER Cutover — Release Seal

**Date:** 2026-09-28  
**Implementation main SHA:** `0f4f6c90b8d8cc2a3e6d303eeb1e04b5f12d102f`  
**Implementation PR:** #657  
**Implementation PR head:** `e19fb98a6178a34266b9fa95fcfb9589187406ee`  
**PR CI:** `36475168158`  
**Status:** SEALED FOR IMMUTABLE RELEASE + ORDINARY PROTECTED DEPLOY/VERIFY OF CUTOVER CAPABILITY ONLY; PHYSICAL FAST PAPER CUTOVER REQUIRES SEPARATE TRUSTED-ADMIN CEREMONY; SIGNING/SUBMISSION NOT AUTHORIZED; LIVE DISABLED

## Purpose

Seal the already-reviewed protected physical Fast PAPER cutover implementation so
the exact code can enter the repository's immutable release chain.

This seal does **not** itself switch production PAPER authority.

The automatic release/deploy chain may install this exact sealed release while
the legacy PAPER campaign remains authoritative. The actual authority switch is
still the separately reviewed root-only physical cutover ceremony implemented by
PR #657.

## Implementation proof

PR #657 merged the protected physical cutover implementation at:

`0f4f6c90b8d8cc2a3e6d303eeb1e04b5f12d102f`

Its exact reviewed head was:

`e19fb98a6178a34266b9fa95fcfb9589187406ee`

Exact-head CI run:

`36475168158`

Result:

- Python: SUCCESS — `4289 passed, 4 warnings`;
- Rust workspace: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

The implementation provides:

- a root-issued release/run/binding-specific Fast PAPER cutover authorization;
- ordinary authoritative runtime startup that fails closed without a valid
  authorization;
- a physical cutover CLI that stops only the legacy PAPER campaign service;
- exact final legacy checkpoint capture after service quiescence;
- append-only initialization of a fresh final Fast run namespace at sequence 0;
- canonical retargeting of only the authoritative Fast run ID;
- final stopped-legacy cutover preflight;
- sealed Fast unit replacement under the existing
  `shreks-paper-campaign.service` name;
- bounded post-start process/status/durable-state verification;
- phase-bounded rollback before the first Fast start attempt;
- fail-closed manual recovery after any Fast start attempt;
- a persistent revoked recovery marker after post-start failure;
- a legacy deployment guard that blocks score-gated PAPER restoration after
  Fast cutover.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact seal-main CI is
green, authorize the existing automatic delivery chain only to:

1. build and verify one immutable release for the exact seal SHA;
2. include the PR #657 physical-cutover CLI, authorization gate, host-prep
   integration, and deployment guard;
3. publish the exact immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. keep the ordinary legacy PAPER campaign authoritative during that deployment;
6. verify exact release/service/process provenance through the existing
   production verification path.

Automatic release/deploy must **not**:

- create `/etc/shreks/fast-paper-cutover-authorization.json`;
- invoke `shreks-fast-paper-physical-cutover activate`;
- replace the active legacy PAPER unit with the Fast candidate outside the
  reviewed physical ceremony;
- invent a final Fast run ID;
- initialize a final Fast handoff namespace;
- stop the detached shadow service;
- alter strategy/model/champion policy;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Trusted-admin physical cutover boundary

Only after the exact sealed release is active and ordinary production
verification succeeds may a trusted administrator continue the separately
reviewed ceremony:

1. authenticate/install the canonical authoritative Fast PAPER host config;
2. provision and verify dedicated authoritative source roots;
3. create and authenticate the final decision baseline while detached shadow is
   quiesced;
4. run physical cutover `preflight` while legacy PAPER is still active;
5. choose one fresh explicit final Fast run ID;
6. run physical cutover `activate`.

The activation command then:

```text
stop legacy PAPER
-> prove inactive/dead
-> read exact final legacy checkpoint
-> initialize fresh final Fast sequence-0 namespace
-> retarget canonical Fast run ID
-> re-run CUTOVER_PREFLIGHT_READY
-> issue exact cutover authorization
-> atomically install sealed Fast unit
-> daemon-reload
-> start authoritative Fast PAPER
-> bounded verify
```

Only a successful root-private receipt with:

```text
state=PRODUCTION_PAPER_CUTOVER_ACTIVE
legacy_paper_runtime=STOPPED
authoritative_paper_runtime=FAST_LANE_LEARNED_ACTIVE
production_paper_cutover=ACTIVE
signing_submission_authority=NOT_GRANTED
live_authority=DISABLED
```

proves that production PAPER authority has actually moved to Fast Lane.

## Failure boundary

Before the first Fast start attempt, the protected ceremony may restore the
exact legacy runtime if cutover fails.

At or after the first Fast start attempt:

- Fast is stopped;
- cutover authorization becomes a revoked manual-recovery marker;
- legacy PAPER authority is not restarted;
- ordinary legacy-style release activation remains blocked;
- PAPER remains stopped pending explicit reconciliation/recovery.

This prevents duplicate or divergent economic PAPER actions across legacy and
Fast namespaces.

## Release/deploy acceptance

The sealed release/deploy step is successful only if:

- sealed-main CI passes all four canonical gates;
- the immutable release is bound to the exact seal SHA;
- protected deployment activates exactly that release;
- the legacy PAPER service remains healthy before the separate cutover ceremony;
- the physical-cutover CLI is release-local and executable;
- no cutover authorization/revocation marker is created by automatic deploy;
- LIVE remains disabled.

## Authority state after this seal

Before the separate physical host ceremony succeeds:

```text
production_paper_runtime=LEGACY
fast_paper_cutover_capability=SEALED_AND_DEPLOYABLE
physical_cutover_authority=TRUSTED_ADMIN_CEREMONY_ONLY
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```

After a separately successful physical ceremony:

```text
production_paper_runtime=FAST_LANE_LEARNED
production_paper_cutover=ACTIVE
signing_submission_authority=NOT_GRANTED
LIVE=DISABLED
```
