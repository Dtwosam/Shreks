# G1C V2 Quote-Mint-Aware PAPER Market Selection — Release Seal

**Date:** 2026-09-23  
**Implementation main SHA:** `694b4715be014956010280cb983d3edb26ff1d5a`  
**Implementation PR:** #477  
**Merged-main CI:** `35899556013`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF QUOTE-MINT-AWARE V2 SELECTION ONLY; REPLACEMENT CANDIDATE/BINDING/ROTATION/SCORING/PAPER PROMOTION/LIVE NOT AUTHORIZED

## Purpose

Seal the bounded runtime correction required for authenticated G1C v2 PAPER manifests using `exact_market_ratio`.

Observer ingestion already persists every Solana token pair returned by the configured market provider, including each pair's base mint, quote mint, pair address, source, venue, native price, USD price, and observation time.

Before this fix, PAPER current-market selection chose the newest canonical row by source priority and freshness without considering the authenticated v2 manifest quote mint. Dynamic valuation then required the already-selected row to have the manifest quote mint and exact same-row identity. A newer USDC or other-quote row could therefore win market selection even when a fresh WSOL row also existed, causing v2 assembly to fail closed after selection.

## Corrected behavior

For authenticated dynamic valuation only, the PAPER runtime now binds market selection to the manifest quote identity before feature/valuation assembly.

When `quote_usd_valuation_policy.mode=exact_market_ratio`:

- aggregate recent-candidate selection requires a fresh market row whose base mint is the candidate mint and whose quote mint equals the authenticated manifest quote mint;
- component market-window selection applies that same explicit quote-mint boundary;
- market history/anchors remain on the selected source/pair and exact base/quote identity;
- quote-USD valuation remains derived from the exact same persisted current market row used by the PAPER feature window;
- no conversion from a USDC row to WSOL is invented;
- no external/current internet price is substituted;
- candidates without fresh market evidence for the manifest quote mint are safely excluded from entry selection.

If no eligible candidate has fresh manifest-quote market evidence, a read-only/production PAPER cycle may contain no entry candidate rather than crashing solely because an unrelated quote pair was newer.

Legacy v1 behavior is unchanged. When no authenticated dynamic valuation mode is present, current-market selection retains the existing unconstrained canonical-pair semantics.

## Provider and persistence boundary

This slice does not add a provider or network path.

The existing DEX Screener adapter already returns all Solana pairs whose base token matches the requested mint. Observer V2 already persists each returned pair individually through the existing market snapshot writer.

The fix changes only the read-side selection boundary used by authenticated dynamic v2 PAPER assembly.

It does not manufacture WSOL market evidence. If no fresh WSOL pair is persisted, the candidate is not eligible for dynamic-v2 entry assembly.

## Same-row invariant

The previously sealed dynamic valuation invariant remains authoritative:

`quote_asset_usd_per_token = price_usd / price_native`

from the exact current persisted market row.

Features and dynamic quote valuation continue to be tied to one row identity. The implementation does not weaken `expected_market_row_id`, source, venue, candidate, base-mint, quote-mint, or freshness checks.

## Regression proof

Final PR head:

`959010d5fd867eded755055aee69de5cc9cc4e12`

Final PR CI:

`35899244926`

Result:

- Python: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS;
- Repository safety: SUCCESS.

Regression coverage proves:

1. a newer wrong-quote market row cannot hijack an authenticated dynamic-v2 cycle when a fresh exact manifest-quote row exists;
2. aggregate v2 candidate selection can require the exact manifest quote mint;
3. missing quote-identity schema fails closed for the constrained path;
4. when no fresh exact manifest-quote market row exists, the candidate is safely omitted and next-cycle preflight remains non-mutating;
5. v1 static valuation retains legacy selection behavior.

Merged main:

`694b4715be014956010280cb983d3edb26ff1d5a`

Merged-main CI:

`35899556013`

Result: SUCCESS across all four canonical gates.

## Current protected production authority

The previously failed rotation binding remains terminal evidence:

`d87fa0e1b88be321bf4533d5e90c8b9dd2423ca21c6b2e8edd254fea98b1b667`

Its immutable rotation evidence must not be deleted, overwritten, or retried.

This seal does not authorize reuse of the prior candidate, transition binding, readiness receipt, rotation plan, or rotation authorization.

The currently reviewed economics artifacts may only be reused later through the repository's explicit candidate-value/preflight/decision-backed authority contracts. A new production run identity/time and a new transition binding require a separate reviewed ceremony.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact seal-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. carry the quote-mint-aware v2 PAPER selection code;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. keep the restored active v1 PAPER manifest in place;
6. verify ordinary protected service health and release-local tool presence;
7. report the root manifest-manager helper status read-only;
8. continue existing read-only FL9 discovery/diagnostics.

Automatic deployment must not:

- alter the protected PAPER manifest;
- delete or modify the failed rotation evidence;
- retry the failed transition binding;
- create a replacement candidate or binding;
- execute helper installation/update/proof refresh;
- execute rotation readiness or a rotation plan;
- invoke protected PAPER manifest rotation;
- execute scoring/model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Helper-proof boundary after deployment

This implementation does not modify `deploy/release/paper_manifest_manager.py`.

The expected installed helper bytes after deployment therefore remain the current proven manager bytes if no unrelated commit changes the sealed manager before this seal.

Production verification must establish the actual helper status; do not assume it.

Any earlier helper installation proof remains release-SHA/wheel-bound and becomes stale when the immutable release changes. Before any later decision-backed rotation readiness ceremony, a trusted administrator must create a fresh proof for the exact newly active release.

A fresh helper proof does not authorize candidate creation, binding, readiness, or rotation.

## Future replacement-candidate boundary

Only after this exact release is production-verified may a separate authority slice consider a new v2 candidate.

That future chain must:

- preserve the protected source manifest as the starting authority;
- use explicit reviewed candidate-value/preflight authority;
- use a new future paper run identity and start time;
- author an exact new candidate;
- create a new transition binding;
- preserve the failed binding as terminal historical evidence;
- obtain a fresh exact-release helper proof;
- pass cycle-aware readiness under the quote-mint-aware selector;
- create a new read-only rotation plan;
- require a new explicit trusted-admin rotation authorization.

No automatic workflow may manufacture those authorities.

## Authority firewall

```text
FAILED_ROTATION_BINDING=TERMINAL_DO_NOT_RETRY
REPLACEMENT_CANDIDATE_AUTHORITY=NOT_GRANTED
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
