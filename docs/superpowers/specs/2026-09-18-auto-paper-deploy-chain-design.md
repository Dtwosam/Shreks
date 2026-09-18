# Automatic PAPER Deploy Chain — Design

**Date:** 2026-09-18  
**Base:** sealed main `ab6d115757bff674d4672b57fe8f963b63d5db66`  
**Status:** approved for implementation

## Goal

Remove the recurring manual `workflow_dispatch` handoff between a successfully built immutable sealed release and production PAPER verification, without widening deployment privileges or weakening any proof/risk/LIVE gate.

The normal path becomes:

`seal merge -> main CI -> immutable release -> PAPER deploy -> production verify -> protected FL9 discovery`

Manual dispatch remains available as an operator fallback.

## Existing boundary to preserve

GitHub remains the source/test/release/deployment control plane. The VPS remains the continuously running host.

The deploy account remains transport-only and may use only the existing root-owned release-manager install command through the existing narrow sudoers rule.

This change must not modify:

- sudoers;
- release-manager code;
- systemd units/timers;
- ownership, modes, or ACLs under `/etc/shreks` or `/var/lib/shreks`;
- wallet/signing/submission paths;
- PAPER promotion authority;
- LIVE authority.

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`  
`PAPER_PROMOTION=BLOCKED`  
`LIVE=DISABLED`

## Trigger architecture

### Release workflow

`.github/workflows/release.yml` remains the only workflow that creates immutable GitHub Releases.

No deployment secrets or production environment are added to the release workflow.

### Deploy workflow

`.github/workflows/deploy.yml` gains a second trigger:

- existing manual `workflow_dispatch` with explicit `release_tag`;
- automatic `workflow_run` on successful completion of `Build sealed Shreks release`.

The automatic deploy path is eligible only when the release workflow itself was triggered by the canonical automatic sealed-main path, not by a manual release build.

Concretely, automatic deploy requires:

- `github.event.workflow_run.conclusion == 'success'`;
- `github.event.workflow_run.event == 'workflow_run'`;
- exact `github.event.workflow_run.head_sha` matching 40 lowercase hex characters.

The automatic release tag is derived mechanically as:

`shreks-<workflow_run.head_sha>`

The manual path continues to validate the supplied tag with the existing exact syntax.

## Resolve job

The deploy workflow adds a non-secret `resolve` job that emits exactly:

- `source_sha`;
- `release_tag`.

It has no production environment and consumes no secrets.

For automatic runs it derives both outputs from the successful release workflow event.

For manual runs it validates and splits the supplied `release_tag`.

All later jobs consume these outputs rather than duplicating release identity logic.

## Immutable release verification

Before any VPS contact, the deploy job must independently verify that the named GitHub Release:

- exists;
- has `tag_name == release_tag`;
- has `target_commitish == source_sha`;
- is not draft;
- is not prerelease;
- is immutable;
- exposes the exact three expected release assets.

This check occurs before downloading/transferring artifacts.

The existing local release-bundle verification remains mandatory after asset download.

## Production environment

The existing deploy job retains:

`environment: production-paper`

Environment reviewers/branch protections, if configured, remain authoritative. This design removes unnecessary manual dispatch; it does not bypass an intentional GitHub Environment approval gate.

The deploy workflow continues to use only the existing transport secrets:

- `SHREKS_DEPLOY_HOST`;
- `SHREKS_DEPLOY_PORT`;
- `SHREKS_DEPLOY_USER`;
- `SHREKS_DEPLOY_SSH_KEY`;
- `SHREKS_DEPLOY_KNOWN_HOSTS`.

## Reusable verifier

`.github/workflows/verify-production-paper.yml` keeps its existing manual `workflow_dispatch` and adds `workflow_call`.

Reusable inputs are:

- `expected_release_sha` — required string;
- `journal_minutes` — optional string, default `"30"`.

The verifier job retains:

`environment: production-paper`

and preserves its existing read-only SSH/provenance/service/journal/FL9-discovery behavior unchanged.

After the deploy job succeeds, the deploy workflow invokes the verifier as a reusable workflow with:

- `expected_release_sha = needs.resolve.outputs.source_sha`;
- `journal_minutes = "30"`;
- inherited repository secrets as needed, while the called verifier still loads the existing `production-paper` environment.

A deploy failure prevents verifier invocation.

A verifier/discovery failure fails the overall deploy-chain run.

## Failure behavior

The chain is fail-closed.

No deployment occurs when:

- the release workflow failed;
- the release workflow was manually dispatched rather than produced by the canonical sealed-main automatic path;
- the release identity is malformed;
- the GitHub Release is missing, mutable, draft/prerelease, or targets a different commit;
- release assets fail verification.

No verification occurs when deployment fails.

No scoring/promotion/LIVE action is added to any success path.

## Backward compatibility

Manual deploy remains:

`Deploy verified Shreks release -> workflow_dispatch -> release_tag`

Manual production verify remains:

`Verify production PAPER runtime -> workflow_dispatch -> expected_release_sha + journal_minutes`

Rollback by manually deploying an earlier immutable release remains unchanged.

## Tests

Static delivery tests must prove:

1. deploy supports both manual dispatch and automatic release-workflow completion;
2. automatic deploy requires successful canonical automatic release workflow provenance;
3. resolve outputs bind exact source SHA and release tag;
4. deployment verifies immutable release identity before host contact;
5. deploy still has only `contents: read`;
6. deploy and verifier retain `production-paper`;
7. verifier supports both `workflow_dispatch` and `workflow_call`;
8. deploy invokes verifier only after successful deploy;
9. no new secret names, sudo, systemd mutation, protected-state write, wallet/signing, promotion, or LIVE authority appear;
10. release workflow remains free of deployment/runtime secrets.
