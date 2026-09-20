# FL9 V2 Runtime Quote-Purpose Vocabulary Correction — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `8f95f56a5885637894277ec763e49659ef23ce30`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; DIAGNOSTIC ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified correction that makes the bounded FL9 persisted PAPER quote-evidence diagnostic consume the canonical persisted purpose vocabulary already defined by `ObserverPaperQuotePurpose`.

The correction changes no runtime authority. It repairs diagnostic interpretation only.

## Production evidence

Prior sealed release:

`32827d210083ab5063cc91f09ec7e8d51d969192`

completed exact-main CI, immutable release, protected PAPER deploy, and production verification.

Production deploy/verify run:

`35524050956`

returned a trusted FL9 result with:

- exact active release and manifest SHA matching the sealed release;
- all three core PAPER services active/running with zero restarts;
- three authenticated historical V2 request authorities;
- one exact request-authority group;
- frozen cohort quote mint WSOL;
- authenticated active campaign-manifest quote mint USDC;
- zero compatible runtime-manifest candidates;
- terminal `HOLD_NO_COMPATIBLE`;
- `runtime_quote_evidence_diagnostic.status=UNAVAILABLE`.

The diagnostic itself had successfully entered the already-sealed startup-only protected read path. Repo inspection identified the data-contract defect instead:

`ObserverPaperQuotePurpose.ENTRY.value == "entry"`

`ObserverPaperQuotePurpose.EXIT.value == "exit"`

while the diagnostic had incorrectly accepted uppercase `ENTRY` and `EXIT`.

Production persisted quote rows therefore failed the diagnostic purpose check before quote-asset aggregation.

## Correction

Merged PR #333, `fix: use canonical PAPER quote purpose vocabulary in FL9 diagnostic`, now:

1. imports the existing canonical `ObserverPaperQuotePurpose`;
2. derives the diagnostic's allowed values from that enum;
3. derives the ENTRY-side input-mint selection from `ObserverPaperQuotePurpose.ENTRY.value`;
4. consumes only canonical persisted `entry` / `exit` values;
5. rejects uppercase aliases rather than silently normalizing them;
6. preserves the existing read-only, query-only, 128-row bounded diagnostic contract.

No database schema, persisted row, manifest, cohort, request, hydration policy, systemd unit, sudoers rule, ownership, mode, ACL, scoring path, or trading authority changes.

## TDD evidence

Intentional RED head:

`4a83e65d4173368d811a875ab9e0f6f931a2283a`

RED CI:

`35526000792`

Result:

- Python: exactly 3 failures, 3470 passed;
- the failures proved canonical lowercase purposes were rejected and an uppercase alias was incorrectly accepted;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Final implementation head:

`729b1b2840905a504b04e92883d471068877b6b7`

Final PR CI:

`35526112742`

Result:

- Python: 3473 passed;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`8f95f56a5885637894277ec763e49659ef23ce30`

Exact merged-main CI:

`35526274088`

Result:

- Python: 3473 passed;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment and verification;
3. the already-sealed protected FL9 discovery path;
4. bounded read-only inspection of recent persisted PAPER quote evidence using canonical purpose values;
5. observation of the resulting diagnostic status and quote mint(s) to choose the next implementation slice.

## Interpretation boundary

A successful quote-evidence diagnostic remains evidence only:

- WSOL evidence does not become a replacement runtime manifest;
- USDC evidence does not make the frozen WSOL cohort compatible;
- ambiguous evidence must not be collapsed to a preferred asset;
- no evidence or unavailable evidence authorizes nothing;
- even a later `FOUND_COMPATIBLE` discovery does not itself authorize scoring.

## Promotion boundary

`RUNTIME_QUOTE_EVIDENCE=DIAGNOSTIC_ONLY`

`RUNTIME_QUOTE_PURPOSE_VOCABULARY=CANONICALIZED`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
