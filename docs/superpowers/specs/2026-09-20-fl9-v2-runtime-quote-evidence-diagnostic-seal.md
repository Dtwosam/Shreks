# FL9 V2 Runtime Quote-Evidence Diagnostic — Release Seal

**Date:** 2026-09-20  
**Implementation main SHA:** `84cb0b70ebb8ceb178f138aad9d2b0d752cab0f5`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY; DIAGNOSTIC EVIDENCE ONLY; V2 SCORING NOT AUTHORIZED

## Purpose

Seal the verified read-only diagnostic that answers the next factual question exposed by protected FL9 V2 runtime-manifest discovery:

> What quote asset is represented by the most recent bounded persisted PAPER quote evidence?

The diagnostic exists only to distinguish an active campaign-manifest mismatch from the quote identity actually represented in recent durable PAPER evidence. It does not create, rewrite, select, or promote runtime authority.

## Production evidence that required this diagnostic

Prior sealed release:

`e4eb10c6b046e9c52ce9ca1c3acc867734d9fcb5`

completed the automatic chain:

`seal -> CI -> immutable release -> protected PAPER deploy -> startup protected discovery -> production verify`

Production deploy/verify run:

`35521908251`

proved:

- exact active release and release-manifest binding;
- all three core PAPER services active/running with zero restarts;
- protected discovery result delivered through the trusted shared-memory exchange;
- three preserved canonical V2 request candidates were found;
- all three request authorities authenticated;
- the three authenticated requests collapsed to one exact authority group;
- no request authority was rejected;
- the active PAPER campaign manifest authenticated;
- the frozen accepted V2 cohort quote mint is WSOL:
  `So11111111111111111111111111111111111111112`;
- the active campaign manifest derives USDC quote authority:
  `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`;
- the active manifest therefore returned `REJECTED_QUOTE_POLICY`;
- compatible runtime-manifest candidate count was zero;
- terminal trusted discovery status was `HOLD_NO_COMPATIBLE`.

That result is not an operational failure. It is a semantic HOLD: authenticated runtime-manifest evidence currently consumed by discovery is incompatible with the frozen WSOL cohort.

Existing authority explicitly forbids editing a USDC manifest into a WSOL manifest, synthesizing policy fields from the cohort, or retrying scoring from this state.

## Implemented diagnostic

Merged PR #331, `feat: report persisted PAPER quote evidence on FL9 runtime HOLD`, adds one bounded read-only evidence reader and integrates it only into the already-authorized protected predeploy discovery helper.

The diagnostic:

1. runs only when the trusted discovery result is `HOLD_NO_COMPATIBLE`;
2. opens the authoritative observer SQLite database with URI `mode=ro`;
3. enables and verifies `PRAGMA query_only = ON`;
4. rejects a symlink, missing database, invalid schema, invalid quote purpose, blank quote mint, or invalid timestamp;
5. requires only the fixed `paper_quote_snapshots` columns needed to identify quote assets;
6. reads at most the 128 most recent rows in production;
7. derives ENTRY quote asset only from `input_mint`;
8. derives EXIT quote asset only from `output_mint`;
9. does not read taker identity, provider credentials, host environment secrets, wallet data, or transaction material;
10. reports only:
    - schema/version;
    - bounded sample limit;
    - sampled row count;
    - distinct quote-asset mint(s);
    - per-mint row count;
    - latest quoted timestamp per mint;
11. emits one of:
    - `NO_EVIDENCE`;
    - `ONE_QUOTE_ASSET`;
    - `AMBIGUOUS_QUOTE_ASSETS`;
12. emits sanitized `UNAVAILABLE` evidence if the diagnostic itself cannot be completed safely;
13. attaches the result as `runtime_quote_evidence_diagnostic` without changing the underlying `HOLD_NO_COMPATIBLE` status;
14. completes the protected read before the predeploy helper irreversibly drops to the existing `shreks` runtime identity;
15. continues to publish the trusted discovery result only after that privilege drop through the already-sealed exchange.

The diagnostic output is observational evidence only. It is not a runtime manifest, hydration policy, scoring request, or policy-selection mechanism.

## TDD and verification evidence

Intentional RED head:

`c49ccebf18793793de317968f5ad8e4ac8ebf419`

RED CI run:

`35522971016`

Result:

- Python: exactly 6 new failures and 3466 existing tests passed;
- the failures were confined to the intentionally absent runtime quote-evidence module and predeploy integration;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

GREEN implementation head:

`4f013dde72223363bd92ce61d23ad3ca2f4229ec`

GREEN push CI:

`35523146589`

Independent PR CI:

`35523149642`

Both completed successfully across the canonical gates.

Python on the GREEN head:

`3472 passed`

Squash-merged implementation main:

`84cb0b70ebb8ceb178f138aad9d2b0d752cab0f5`

Exact merged-main CI run:

`35523344339`

Result:

- Repository safety: SUCCESS;
- Python: SUCCESS, `3472 passed`;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Authority boundary

This implementation and seal do not modify or authorize:

- `/etc/shreks/shreks.env` reads for the diagnostic;
- provider credential disclosure;
- wallet/signing/submission paths;
- protected evidence ownership, modes, or ACLs;
- sudoers;
- release-manager command authority;
- systemd unit behavior;
- frozen cohort bytes;
- existing campaign-manifest bytes;
- preserved V2 request/hydration bytes;
- construction of a replacement runtime manifest;
- selection of WSOL merely because it matches the cohort;
- model fitting or V2 scoring retry;
- champion publication;
- PAPER promotion;
- LIVE trading.

The existing authenticated runtime-manifest chain remains the only source of runtime quote/regime/safety/provider/global-risk authority.

## Authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize only:

1. immutable release creation for the exact sealed SHA;
2. automatic protected PAPER deployment and verification of that immutable release;
3. the already-sealed startup-only protected FL9 discovery;
4. bounded read-only inspection of recent persisted PAPER quote evidence when discovery remains `HOLD_NO_COMPATIBLE`;
5. trusted publication of that diagnostic inside the existing discovery result;
6. use of the resulting evidence to choose the next implementation slice.

## Expected production proof

The automatic production chain must preserve the existing exact-release and service-health gates and return a trusted terminal discovery result.

If discovery remains `HOLD_NO_COMPATIBLE`, it should additionally expose:

`runtime_quote_evidence_diagnostic`

Interpretation remains fail-closed:

- `ONE_QUOTE_ASSET` with WSOL means recent persisted PAPER quote evidence is WSOL while the authenticated campaign manifest remains USDC. That establishes a runtime-authority consistency mismatch requiring a separate canonical reconciliation/authentication slice. It does not make the database rows a replacement runtime manifest and does not authorize scoring.
- `ONE_QUOTE_ASSET` with USDC means recent persisted PAPER quote evidence agrees with the USDC campaign authority. No compatible WSOL runtime authority has been established; remain HOLD.
- `AMBIGUOUS_QUOTE_ASSETS` means recent persisted evidence spans more than one quote identity. Do not choose one; remain HOLD and investigate the transition/provenance.
- `NO_EVIDENCE` or `UNAVAILABLE` supplies no compatible runtime authority. Remain HOLD.

If discovery returns `FOUND_COMPATIBLE`, the quote diagnostic is not required and the existing canonical discovery-authority binding gate remains applicable. Even then, scoring remains separately unauthorized.

## Promotion boundary

`FL9_RUNTIME_QUOTE_EVIDENCE_IMPLEMENTATION=MAIN_GREEN`

`RUNTIME_QUOTE_EVIDENCE=DIAGNOSTIC_ONLY`

`IMMUTABLE_RELEASE=PENDING_SEAL_MAIN_GREEN`

`AUTOMATIC_PRODUCTION_DEPLOY=PENDING_RELEASE_SUCCESS`

`AUTOMATIC_PRODUCTION_VERIFY=PENDING_DEPLOY_SUCCESS`

`RUNTIME_POLICY_DISCOVERY=PENDING_PRODUCTION_EVIDENCE`

`V2_SCORING_RETRY=NOT_YET_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
