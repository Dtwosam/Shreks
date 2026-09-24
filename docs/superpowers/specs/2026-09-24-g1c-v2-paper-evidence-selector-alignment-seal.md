# G1C V2 PAPER Evidence Selector Alignment — Release Seal

**Date:** 2026-09-24  
**Implementation main SHA:** `db3b76bba9a7cd66a9c579f9789c030a14440071`  
**Implementation PR:** #481  
**Merged-main CI:** `36002428464`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF PAPER-EVIDENCE SELECTOR ALIGNMENT ONLY; PROTECTED MANIFEST ROTATION/SCORING/MODEL FITTING/PAPER PROMOTION/LIVE NOT AUTHORIZED

## Purpose

Seal the bounded evidence-collector correction required after production G1C v2 PAPER diagnostics proved that the PAPER campaign could select fresh exact-WSOL candidates while the separately supervised PAPER evidence collector had not hydrated those same candidate identities with Helius mint/holder evidence or exact Jupiter entry/exit quotes.

The already-active protected G1C v2 campaign remains:

- paper run: `g1c-v2-wsol-20260923T190847Z`;
- candidate version: `fresh-launch-paper-v1-commissioning-challenger`;
- quote mint: WSOL `So11111111111111111111111111111111111111112`;
- quote decimals: `9`;
- entry input amount: `211545104`;
- exit input amount: `1000000000000`;
- slippage: `100 bps`;
- runtime-manifest fingerprint: `bf73b9742aebc06ba12ba6e16d8810543a92a7a8476db6950534eb5dfe1f644d`;
- runtime-manifest SHA256: `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`.

The protected manifest must remain byte-identical through this release.

## Production evidence that required this correction

Read-only production diagnostics established that fresh-pair market sampling and the canonical PAPER selector were functioning:

- multiple recently created pairs were physically refreshed after the fresh-pair sampler release;
- the canonical PAPER selector produced exact-WSOL candidates;
- PAPER assembled and evaluated two candidates in memory;
- strategy/safety correctly rejected those candidates without opening a simulated position.

A subsequent quote-readiness diagnostic proved the remaining infrastructure mismatch.

At the diagnostic point:

- selected candidate count: `2`;
- candidate `1308248`, mint `AxZYPsQc2tFUWCvWCUd6sR2FWSJ8huqJbEuexmqXvGXo`:
  - current exact-WSOL market age: about `1.2 s`;
  - mint state: absent;
  - holder evidence: absent;
  - safety-exit quote rows: `0`;
  - PAPER entry quote rows: `0`;
  - PAPER exit quote rows: `0`;
- candidate `1347672`, mint `8Qp8ivGukxP2BHGRKNQMeVg5PgoLb7awBZhGbnTTfrw2`:
  - current exact-WSOL market age: about `21.7 s`;
  - mint state: absent;
  - holder evidence: absent;
  - safety-exit quote rows: `0`;
  - PAPER entry quote rows: `0`;
  - PAPER exit quote rows: `0`.

This demonstrated that the evidence collector could spend its bounded `max_candidates` budget on a different market-row identity than the canonical PAPER selector.

The same production session also established that the two evaluated candidates were legitimate strategy rejections, including hard liquidity failures against the existing `$20,000` minimum. No strategy threshold was shown to be wrong.

## Corrected evidence-selection path

Implementation PR #481 aligns the Rust PAPER evidence collector with the canonical market identity already used by PAPER.

For each candidate, the evidence selector now resolves one canonical current market row by:

1. configured market-source priority;
2. exact `base_mint = candidate mint`;
3. exact `quote_mint = authenticated/configured quote asset mint`;
4. observation inside the configured current-market lookback;
5. non-null `pair_created_at_unix_ms`;
6. `pair_created_at_unix_ms <= observed_at_unix_ms`;
7. newest matching row for the first configured source with a match.

The selector then:

- applies the existing maximum pair-age bound to that canonical row;
- preserves the existing preferred-minimum-age ordering so too-young pairs can still be prewarmed after in-window candidates;
- sorts deterministically by age class, newest canonical observation, then candidate id;
- applies `max_candidates` only after exact quote/source/current-row filtering.

The evidence cycle supplies `config.quote_asset_mint` into this selector. Under the already-sealed V2 manifest-authority launcher, that child-process value is derived from the authenticated campaign manifest rather than from stale host policy.

## RED / GREEN proof

Intentional RED head:

`5a8e715f3ac8c9177f6d67d294ab9b1d95dd229f`

RED CI:

`36001364716`

The Rust suite failed on the intended missing behavior:

`fresh_launch_candidates_use_current_pair_instead_of_requiring_uniform_pair_history`

The old selector returned zero for a candidate whose current pair was valid but whose recent pair-created history was not uniform.

The first implementation run exposed and repaired one bounded compatibility regression: requiring `base_mint` / `quote_mint` at store-open time unnecessarily broke callers that use only the legacy `recent_candidates` method. The final implementation scopes the new schema gate to `fresh_launch_candidates` only.

Final feature-branch head:

`7f598e5f329d4e099d9ebf192cf72933dc0e657b`

Final feature-branch CI:

`36001857950`

Result:

- Rust workspace: SUCCESS;
- Python: SUCCESS;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged implementation main:

`db3b76bba9a7cd66a9c579f9789c030a14440071`

Merged-main CI:

`36002428464`

Result: SUCCESS across all four canonical gates.

## Behavioral boundaries preserved

This correction does not change:

- PAPER's `120000 ms` market-currentness ceiling;
- the active fresh-launch strategy age bounds;
- the `$20,000` minimum liquidity safety threshold;
- setup confirmations;
- score components or thresholds;
- decision semantics;
- risk-control semantics;
- quote amount;
- quote provider;
- taker;
- slippage;
- protected runtime-manifest bytes;
- candidate-value authority;
- PAPER position sizing;
- model-fitting authority;
- promotion authority;
- LIVE authority.

Too-young evidence prewarming remains intentionally available and does not itself make a candidate PAPER-entry eligible.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact seal-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. include the verified PAPER-evidence selector alignment from implementation main `db3b76bba9a7cd66a9c579f9789c030a14440071`;
3. publish the exact immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. preserve the active protected V2 campaign-manifest bytes unchanged;
6. restart the normal protected PAPER runtime services through the existing release manager;
7. allow the separately supervised PAPER evidence collector to use the authenticated V2 quote mint when selecting bounded evidence candidates;
8. verify exact-release process identity and normal service health;
9. collect read-only physical-host evidence showing whether canonical PAPER-selected exact-WSOL candidates now receive matching mint/holder and purpose-correct entry/exit quote evidence.

Automatic deployment must not:

- edit `/etc/shreks/shreks.env`;
- replace or rotate `/etc/shreks/paper-campaign.json`;
- delete or modify existing manifest-rotation evidence;
- create a new candidate-value decision, authority, transition binding, readiness receipt, or rotation plan;
- invoke a protected manifest rotation;
- relax PAPER market, setup, safety, score, decision, or risk thresholds;
- alter sizing or quote economics;
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

The V2 PAPER evidence manifest-authority launcher remains authoritative.

The evidence collector must continue to derive the active V2 quote-policy child environment from the authenticated campaign manifest while preserving final release-local Rust process identity.

This selector-alignment seal consumes that authenticated quote mint for candidate-market identity. It does not create a second source of quote-policy authority and does not authorize host environment mutation.

## Post-deploy acceptance

Successful physical-host acceptance should establish:

- current release equals the exact new seal SHA;
- protected campaign-manifest SHA remains `00a24fcf37031885cd551223a743ebaafb11a1a37f958ca2d9aa34c812d6190e`;
- PAPER run remains `g1c-v2-wsol-20260923T190847Z`;
- `shreks-observe.service` is active/healthy;
- `shreks-paper-evidence.service` is active/healthy and final process identity is the release-local Rust binary;
- `shreks-paper-campaign.service` is active/healthy;
- the evidence collector remains manifest-authorized for WSOL and exact V2 input amounts;
- when current canonical exact-WSOL PAPER candidates exist, the bounded evidence selector considers that same exact quote-pair identity before applying its candidate cap;
- selected candidates can receive Helius mint/holder evidence and exact Jupiter PAPER entry/exit evidence when providers return evidence;
- provider failures remain fail-closed and must not fabricate evidence;
- absence of a qualifying candidate or unavailable route remains a legitimate no-entry outcome.

A successful PAPER simulated entry or completed PAPER trade is observation only and does not authorize scoring/model fitting, champion publication, promotion, or LIVE.

## Helper-proof boundary

This implementation does not modify `deploy/release/paper_manifest_manager.py`.

Any installation/helper proof bound to an older release remains stale after a new immutable release is activated and must not be reused for a future protected-manifest readiness or rotation ceremony.

No helper-proof refresh is required merely to deploy or verify this evidence-selector correction.

## Authority firewall

```text
PAPER_EVIDENCE_SELECTOR=CANONICAL_EXACT_QUOTE_PAIR
PAPER_EVIDENCE_QUOTE_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
TOO_YOUNG_PREWARM=PRESERVED
PAPER_THRESHOLDS=UNCHANGED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
MODEL_FITTING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
