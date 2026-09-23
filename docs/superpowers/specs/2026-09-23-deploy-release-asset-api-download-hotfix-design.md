# Deploy Release Asset API Download Hotfix — Design

**Date:** 2026-09-23  
**Status:** fail-closed delivery hotfix only; no runtime/trading authority change

## Incident

The recovery release `shreks-91a4792cfb4b739884ac5a49ffebe288ed80c7f8` published successfully and the corrected dedicated release-assets endpoint verified exactly the three required uploaded immutable assets.

Automatic deploy run `35838293289` then failed in `Download exact release assets` with:

`no assets to download`

The failure happened before local bundle verification, SSH, SCP, or host release-manager contact.

The remaining problem is therefore `gh release download`, which independently fails to enumerate/download assets even though the dedicated release-assets API has already returned and authenticated them.

## Fix

Use the already-validated dedicated release-assets JSON as the sole download authority.

After validating the asset set and `state=uploaded`, produce a canonical local mapping of exact expected asset name to positive numeric asset id.

For each of the three exact required assets, download bytes through:

`GET /repos/<repo>/releases/assets/<asset-id>`

with:

`Accept: application/octet-stream`

via authenticated `gh api`.

Do not use `gh release download`.

## Required invariants

Before download:

- release identity/tag/SHA/draft/prerelease/immutability checks remain unchanged;
- release id must be positive;
- dedicated assets endpoint must return a JSON array;
- names must equal exactly the three expected names;
- all asset states must be `uploaded`;
- every required asset id must be a positive integer;
- asset ids must be unique.

For download:

- destination directory is new/empty;
- each exact asset path is written from its verified asset id;
- no wildcard/pattern selection is used;
- after download exactly three regular files must exist;
- filenames must equal the exact expected set.

Then the existing `release_bundle.py verify` step remains mandatory before any host contact.

## Authority boundary

This changes GitHub release transport only.

It does not change:

- release contents;
- runtime state;
- sudo/systemd authority;
- candidate/preflight/decision authority;
- manifest rotation;
- scoring/model fitting;
- PAPER promotion;
- wallet access;
- signing/submission;
- LIVE.
