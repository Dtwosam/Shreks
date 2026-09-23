# G1C V2 PAPER Evidence Manifest Authority — Release Seal

**Date:** 2026-09-23  
**Implementation main SHA:** `1a5e18ff768102858918a90e0b4fb8a4087b8a6e`  
**Implementation PR:** #479  
**Merged-main CI:** `35914837963`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF V2 PAPER-EVIDENCE MANIFEST AUTHORITY ONLY; PROTECTED MANIFEST ROTATION/SCORING/PAPER PROMOTION/LIVE NOT AUTHORIZED

## Purpose

Seal the bounded runtime correction required after the trusted-administrator activation of the canonical G1C v2 WSOL PAPER campaign.

Protected production currently authenticates the active canonical v2 campaign manifest:

- paper run: `g1c-v2-wsol-20260923T190847Z`;
- quote mint: WSOL `So11111111111111111111111111111111111111112`;
- quote decimals: `9`;
- entry input amount: `211545104`;
- manifest fingerprint: `bf73b9742aebc06ba12ba6e16d8810543a92a7a8476db6950534eb5dfe1f644d`.

The protected PAPER campaign is active and healthy.

Production diagnostics then proved that the separately supervised `shreks-paper-evidence` daemon remained configured from legacy host-environment economics:

- configured/live quote mint: USDC `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`;
- configured/live entry input amount: `25000000`;
- active-manifest quote mint and entry amount therefore did not match the evidence daemon;
- exact V2 ENTRY evidence rows after the V2 start were `0`.

This is not a quote-mint-aware selector failure. The campaign's persisted PAPER quote lookup intentionally requires an exact candidate/purpose/provider/probe/input/output/taker/input-amount/slippage identity. Legacy USDC evidence cannot satisfy the active WSOL manifest.

## Corrected authority path

Implementation PR #479 adds one release-local launcher:

`shreks_brain.paper_evidence_runtime_launcher`

For an authenticated canonical v2 campaign manifest, the launcher derives only the PAPER evidence collector's quote-policy child environment from the already-authenticated manifest:

- `SHREKS_PAPER_QUOTE_ASSET_MINT`;
- `SHREKS_PAPER_ENTRY_INPUT_AMOUNT`;
- `SHREKS_PAPER_EXIT_INPUT_AMOUNT`;
- `SHREKS_PAPER_PROBE_POLICY_VERSION`;
- `SHREKS_PAPER_QUOTE_TAKER`;
- `SHREKS_PAPER_SLIPPAGE_BPS`.

Those values are not guessed, copied from production diagnostics, or promoted from database rows. They are taken from the canonical manifest after the existing Python manifest decoder authenticates schema, structure, invariants, canonical encoding, and manifest fingerprint.

The launcher does not modify `/etc/shreks/shreks.env`. Provider credentials and unrelated evidence-collection controls remain environment-driven.

For canonical v1 manifests, the legacy environment-driven collector policy remains unchanged.

## Process-identity boundary

`shreks-paper-evidence.service` now starts the release-local Python launcher, which immediately replaces itself with the existing release-local Rust binary through `execve`.

The final supervised process therefore remains:

`/opt/shreks/releases/<exact-release-sha>/target/release/shreks-paper-evidence`

This preserves the existing release-manager native-process identity proof.

The launcher fails closed before executing the Rust daemon when the protected manifest cannot be read stably/authenticated or the release-local Rust executable is unavailable.

## RED / GREEN proof

Intentional RED SHA:

`7d136f12a94156482afc0f9732a6b46f3822854d`

RED CI:

`35913042996`

The Python gate failed for the intended missing implementation:

```text
ModuleNotFoundError: No module named 'shreks_brain.paper_evidence_runtime_launcher'
```

Final feature-branch head:

`c6d811324a32789bf176b610cb6a53f88e239354`

Final feature-branch CI:

`35913948558`

Result:

- Repository safety: SUCCESS;
- Python: SUCCESS;
- Rust: SUCCESS;
- ARM64 release build: SUCCESS.

Independent PR CI:

`35914408257`

Result: SUCCESS across all four canonical gates.

Squash-merged implementation main:

`1a5e18ff768102858918a90e0b4fb8a4087b8a6e`

Merged-main CI:

`35914837963`

Result: SUCCESS across all four canonical gates.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact seal-main CI succeeds, authorize the existing automatic chain only to:

1. build and verify one immutable ARM64 release for the exact seal SHA;
2. include the verified V2 PAPER evidence manifest-authority launcher and systemd wiring;
3. publish the exact immutable GitHub release;
4. deploy that exact release through the existing protected release manager;
5. preserve the already-active protected V2 campaign-manifest bytes unchanged;
6. restart the normal protected runtime services under the existing release manager;
7. allow `shreks-paper-evidence` to derive its in-memory V2 quote-policy child environment from the authenticated protected campaign manifest;
8. verify exact-release process identity and normal service health;
9. perform read-only post-deploy evidence diagnostics to confirm whether exact V2 WSOL quote evidence begins to persist.

Automatic deployment must not:

- edit `/etc/shreks/shreks.env`;
- replace or rotate `/etc/shreks/paper-campaign.json`;
- delete or modify existing rotation evidence;
- create a new candidate, decision, authority, transition binding, readiness receipt, or rotation plan;
- invoke the protected PAPER manifest manager;
- execute V2 scoring or model fitting;
- publish champion evidence;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Protected-manifest boundary

The trusted-administrator rotation already completed for binding:

`3129d8ab15494128d2465c30822823f84fabffe37041de48a13f934c9f1901fd`

This seal does not grant a second rotation and does not reinterpret that authorization.

The active protected V2 manifest is an input authority to the evidence launcher. It is not modified by this runtime correction.

## Helper-proof boundary

This implementation does not modify `deploy/release/paper_manifest_manager.py`.

However, installation-proof artifacts are exact-release/wheel-bound. Any helper proof from the currently deployed release becomes stale after a new immutable release is activated and must not be reused for a future readiness/rotation ceremony.

No helper-proof refresh is required merely to deploy or verify this evidence-authority correction.

## Post-deploy interpretation

Successful deployment should establish all of the following before any later authority slice is considered:

- current release equals the exact sealed release;
- protected campaign manifest remains the exact active V2 manifest;
- `shreks-paper-evidence.service` is healthy and its final process is the release-local Rust binary;
- the live evidence process receives WSOL quote authority and entry amount `211545104` from the authenticated V2 manifest even if the host env file still contains legacy v1 values;
- newly persisted quote evidence can be inspected read-only for exact active-manifest identity.

Absence of an eligible WSOL route/candidate remains a legitimate no-entry outcome.

Even if exact V2 quote evidence begins to persist, this seal does not authorize scoring, model fitting, champion publication, PAPER promotion, or LIVE.

## Authority firewall

```text
PAPER_EVIDENCE_V2_QUOTE_AUTHORITY=AUTHENTICATED_CAMPAIGN_MANIFEST
HOST_ENV_POLICY_MUTATION=NOT_REQUIRED
ACTIVE_V2_MANIFEST=PRESERVE_EXACT_BYTES
MANIFEST_ROTATION_AUTHORITY=NOT_GRANTED
SCORING_AUTHORITY=NOT_GRANTED
PAPER_PROMOTION=BLOCKED
LIVE=DISABLED
```
