# G1C V2 Fresh-Pair Sampling Priority — Release Seal

**Date:** 2026-09-24  
**Implementation main SHA:** `ba43bac5efdf1b053e707e91f4cd1936d5e748b1`  
**Implementation PR:** #480  
**Merged-main CI:** `35995405079`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF OBSERVER FRESH-PAIR SAMPLING PRIORITY ONLY; PROTECTED MANIFEST ROTATION/SCORING/PAPER PROMOTION/LIVE NOT AUTHORIZED

## Purpose

Seal the bounded observer correction required after production G1C v2 PAPER diagnostics proved that the broad Observer V2 market-sampling lane could not keep fresh market evidence current enough for the already-active PAPER policy.

The active protected G1C v2 campaign remains:

- paper run: `g1c-v2-wsol-20260923T190847Z`;
- quote mint: WSOL `So11111111111111111111111111111111111111112`;
- quote decimals: `9`;
- entry input amount: `211545104`;
- runtime-manifest fingerprint: `bf73b9742aebc06ba12ba6e16d8810543a92a7a8476db6950534eb5dfe1f644d`;
- runtime-manifest SHA256: `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`.

The protected PAPER campaign and evidence-authority launcher were already active and healthy before this slice.

## Production evidence that required this correction

Read-only physical-host diagnostics established:

- Observer V2 registry candidates: `537`;
- broad candidates already due: `443`;
- overdue by at least PAPER's `120000 ms` market-freshness ceiling: `395`;
- overdue by at least `300000 ms`: `315`;
- nominal broad refresh demand: `2.86 candidates/second`;
- implementation broad-lane upper bound: one broad candidate per sampler cycle.

A concrete production candidate demonstrated the strategy/runtime clock mismatch:

- candidate id: `1258411`;
- mint: `AbKaeNaS8FeyykruJ7sAT9pYyeAHSE4bni9RxirrZxMT`;
- candidate discovery age: more than 21 hours;
- candidate broad policy interval: `300000 ms`;
- a valid WSOL pair appeared inside the active 30-minute fresh-launch window;
- the pair became stale for PAPER after market evidence exceeded `120000 ms`;
- the candidate was substantially overdue in the overloaded broad queue with zero consecutive provider failures.

This proved that token discovery age alone is not sufficient scheduling authority for keeping a newly created pair observable to PAPER.

No PAPER threshold, strategy window, quote identity, or entry amount was shown to be wrong.

## Corrected observer path

Implementation PR #480 adds one bounded fresh-pair priority lane to Observer V2.

The storage selector identifies only candidates with DexScreener-observed pair evidence that:

1. has a non-null pair creation timestamp;
2. satisfies `pair_created_at_unix_ms <= observed_at_unix_ms`;
3. is inside the bounded recent-pair lookback;
4. does not already have a DexScreener refresh inside the configured freshness target.

The sealed initial bounds are:

- recent-pair lookback: `30 minutes`;
- DexScreener freshness target: `45 seconds`;
- priority target limit: `32` candidates per sampler cycle.

The selector is restricted to the indexed recent DexScreener observation window and orders results deterministically.

Observer V2 executes this lane:

1. after the existing active-PumpSwap priority lane;
2. before broad due-candidate sampling;
3. through the existing paced DexScreener request path.

Candidates already attempted by the earlier active-PumpSwap priority lane are excluded from the fresh-pair lane for that cycle. Candidates attempted by either priority lane are excluded from duplicate broad work in the same cycle.

The broad sampler's one-candidate-per-cycle bound remains unchanged.

## RED / GREEN proof

Intentional RED head:

`db9a0a64ced18eb93ebbeae102207c85dba6acd0`

RED CI:

`35993574077`

The Rust suite failed for the intended missing behavior: an old-token/new-pair candidate was not priority refreshed before its broad schedule became due.

The implementation then exposed and repaired one additional bounded regression: the active-PumpSwap and fresh-pair priority lanes could both attempt the same candidate in one cycle after an empty response or provider failure.

Final feature-branch head:

`a8e91c3cdf217a94b8c002893689dd3044ccd6e6`

Final feature-branch CI:

`35994566334`

Result:

- Repository safety: SUCCESS;
- Python: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`ba43bac5efdf1b053e707e91f4cd1936d5e748b1`

Merged-main CI:

`35995405079`

Result: SUCCESS across all four canonical gates.

## Behavioral boundaries preserved

This correction does not change:

- PAPER's `120000 ms` market freshness ceiling;
- the 30-minute fresh-launch pair-age window;
- quote mint or quote decimals;
- entry input amount;
- candidate-value authority;
- protected runtime-manifest bytes;
- PAPER setup/scoring/decision semantics;
- the broad sampler's bounded one-candidate-per-cycle lane;
- provider pacing/rate-limit wrappers;
- risk-control authority.

Malformed future pair-created timestamps remain invalid for this priority selector.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact seal-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. include the verified fresh-pair priority storage selector and Observer V2 sampler lane;
3. publish the exact immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. preserve the already-active protected V2 campaign-manifest bytes unchanged;
6. restart the normal protected runtime services under the existing release manager;
7. allow Observer V2 to priority-refresh bounded recently created DexScreener pairs through the existing paced provider path;
8. verify exact-release process identity and normal service health;
9. collect read-only physical-host evidence showing whether fresh-pair market evidence now remains current enough to reach the existing PAPER selection/assembly gates.

Automatic deployment must not:

- edit `/etc/shreks/shreks.env`;
- replace or rotate `/etc/shreks/paper-campaign.json`;
- delete or modify existing manifest-rotation evidence;
- create a new candidate, decision, authority, transition binding, readiness receipt, or rotation plan;
- invoke the protected PAPER manifest manager;
- relax PAPER market-freshness or fresh-launch thresholds;
- alter candidate sizing or quote economics;
- execute V2 model fitting or promotion scoring;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Protected-manifest boundary

The trusted-administrator rotation already completed for binding:

`3129d8ab15494128d2465c30822823f84fabffe37041de48a13f934c9f1901fd`

This seal grants no second protected-manifest rotation.

The active protected V2 manifest remains input authority and must be preserved byte-for-byte through deployment.

## Evidence-authority boundary

The prior V2 PAPER evidence manifest-authority correction remains in force.

The separately supervised evidence collector must continue to derive its active V2 quote-policy child environment from the authenticated campaign manifest while preserving final release-local Rust process identity.

This fresh-pair sampling seal does not replace or weaken that authority path.

## Post-deploy acceptance

Successful physical-host acceptance should establish all of the following:

- current release equals the exact new seal SHA;
- protected campaign manifest SHA remains `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`;
- `shreks-observe.service` is active/healthy with no unexpected restart loop;
- `shreks-paper-evidence.service` remains active/healthy and manifest-authorized;
- `shreks-paper-campaign.service` remains active/healthy;
- recently created valid pairs can receive bounded priority DexScreener refreshes ahead of broad backlog;
- no same-cycle duplicate request occurs across active-PumpSwap priority, fresh-pair priority, and broad sampling;
- when a fresh WSOL pair exists, read-only market evidence can remain within the existing PAPER `120000 ms` current-data ceiling often enough for the existing PAPER assembler to assess it;
- absence of an eligible fresh WSOL pair remains a legitimate no-entry outcome.

A successful observation that PAPER finally evaluates or simulates a candidate does not itself authorize model fitting, champion promotion, or LIVE.

## Helper-proof boundary

This implementation does not modify `deploy/release/paper_manifest_manager.py`.

Installation/helper proofs remain exact-release/wheel-bound. Any older helper proof becomes stale after a new immutable release is activated and must not be reused for a future protected-manifest readiness/rotation ceremony.

No helper-proof refresh is required merely to deploy or verify this observer correction.

## Authority firewall

```text
OBSERVER_FRESH_PAIR_PRIORITY=BOUNDED
PAPER_MARKET_FRESHNESS_THRESHOLD=UNCHANGED
PAPER_FRESH_LAUNCH_WINDOW=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
