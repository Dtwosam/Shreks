# FL9 Telemetry Runtime Control Compatibility — Release Seal

**Date:** 2026-09-19  
**Implementation main SHA:** `d3a87067f98aed4a9ca7282d24fbb8fdeb5d3195`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the compatibility fix that makes pending FL9 discovery controls execute from the normal telemetry runtime as well as `--preflight`.

This is required because production diagnostics proved the already-installed telemetry timer/service can run successfully while using an older unit definition that invokes only the normal telemetry runtime. Release-local Python code is updated on every normal Shreks release, so processing controls from the normal runtime removes that stale-unit dependency without any root/systemd update.

## Production evidence that justified the fix

Sealed diagnostic release `a5d62bfddd80c58c8af9705def031b2484472c30` automatically released and deployed successfully.

Production verifier run `35448319848` showed:

- exact active release and manifest SHA matched;
- all three PAPER services were active/running with `NRestarts=0`;
- recent runtime journals were clean;
- telemetry discovery bridge import succeeded;
- `shreks-telemetry.timer` was active/waiting;
- telemetry had triggered during the verifier window;
- `shreks-telemetry.service` exited successfully;
- the discovery marker remained present;
- no discovery result was emitted before the bounded 180-second timeout.

This demonstrated that the scheduler was working but the installed telemetry unit did not execute the newer preflight hook.

## Implemented compatibility behavior

Merged PR #318, `fix: process FL9 controls in normal telemetry runtime`, changes only release-local Python telemetry runtime behavior:

1. pending FL9 discovery controls are processed before telemetry config loading for the normal snapshot invocation;
2. the existing `--preflight` path keeps the same behavior;
3. control-processor exceptions remain isolated from normal telemetry execution;
4. emitted control results remain canonical and sanitized;
5. the underlying discovery processor remains bounded, read-only, release-bound, and idempotent.

No systemd unit, timer, sudoers rule, filesystem permission, release-manager path, wallet/signing/submission path, promotion authority, or LIVE authority changes.

## TDD evidence

Intentional RED head:

`8858cdb7d1cff99186bec2bbf6f29d4e53e2e517`

RED CI:

`35461678171`

The new snapshot-path contracts failed because normal telemetry skipped discovery-control processing.

GREEN feature head:

`a3fc2e62939fc5f049921c208817c6401908f6dd`

GREEN feature CI:

`35461821200`

All four canonical gates passed.

Independent PR #318 CI:

`35461981209`

All four canonical gates passed.

Merged implementation main:

`d3a87067f98aed4a9ca7282d24fbb8fdeb5d3195`

Exact merged-main CI:

`35462165431`

All four canonical gates passed.

The non-seal automatic release/deploy runs for this implementation skipped as intended, proving that the compatibility fix cannot reach production without this explicit seal.

## Authority granted by this seal

After this docs-only `seal:` commit lands and exact sealed-main CI is green, authorize only:

- immutable release creation for the exact seal SHA;
- automatic protected PAPER deployment of that immutable release;
- automatic production verification;
- telemetry-mediated read-only FL9 protected discovery through the normal telemetry runtime or preflight path.

The existing `production-paper` environment, immutable-release verification, narrow deploy account, and protected runtime-state boundaries remain authoritative.

## Expected proof after deploy

The automatic chain must demonstrate:

1. the sealed release is immutable and exact-SHA bound;
2. production activates that exact release;
3. the normal telemetry timer/service consumes the verifier's discovery marker using release-local runtime code;
4. the verifier observes a canonical terminal FL9 discovery result rather than a timeout;
5. any HOLD result remains HOLD;
6. `FOUND_COMPATIBLE` remains evidence only and does not authorize scoring.

## Authority not granted

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`

No model fitting, champion publication, risk-intent creation, signing, submission, wallet handling, or live-capital action is authorized by this seal.
