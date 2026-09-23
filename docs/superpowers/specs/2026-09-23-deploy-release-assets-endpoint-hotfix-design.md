# Deploy Release-Asset Endpoint Verification Hotfix — Design

**Date:** 2026-09-23  
**Status:** delivery-control verification fix only; no runtime/trading authority change

## Incident

Immutable release `shreks-6c441abdbabb30d0585175e298effd5a688f7db0` was built successfully, but automatic protected PAPER deploy run `35835299708` failed before host contact.

Both attempt 1 and attempt 2 failed at:

`release asset set mismatch`

The deploy workflow queried:

`GET /repos/<repo>/releases/tags/<tag>`

and derived the asset-name set from the response object's embedded `assets` field.

For the affected immutable release, that tag lookup returned an empty embedded asset list while:

- `GET /repos/<repo>/releases/latest` returned all three expected assets;
- `GET /repos/<repo>/releases/<release-id>/assets` returned all three expected uploaded assets with their immutable digests.

The deployment never reached SSH, SCP, or the host release manager.

## Fix

Keep the existing release-object validation unchanged for:

- exact tag;
- exact target commit SHA;
- non-draft;
- non-prerelease;
- immutable release.

Additionally require the release object to contain a positive numeric release id.

Then query the dedicated release-assets endpoint:

`GET /repos/<repo>/releases/<release-id>/assets?per_page=100`

Validate that endpoint returns exactly these three names:

- `RELEASE_MANIFEST.json`;
- `shreks-release-<source-sha>.tar.gz`;
- `shreks-release-<source-sha>.tar.gz.sha256`.

Only after both metadata and asset-set validation pass may the existing `gh release download`, local bundle verification, SSH, or SCP steps run.

## Authority boundary

This hotfix does not:

- change release eligibility;
- relax tag/SHA/immutability checks;
- skip exact asset-set validation;
- alter archive/checksum/manifest verification;
- change deployment secrets or sudo authority;
- change the release manager;
- alter systemd or runtime configuration;
- run any candidate preflight/decision/authority tool;
- author/stage a candidate;
- rotate PAPER;
- score/model-fit;
- access wallets;
- sign/submit;
- enable LIVE.

After merge, a new release seal is required so the corrected deploy workflow can carry the preflight-bound candidate-authority release into production.
