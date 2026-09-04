# FL9 Campaign Invocation Seal — Design

**Date:** 2026-09-04

## Status

Implementation slice after canonical file-backed campaign request merge
`397aa8a2273d59313f8c6f3fd40df5733487de95` (#194).

FL9 economic superiority remains **EVIDENCE PENDING**. LIVE remains disabled.

## Purpose

Bind one canonical campaign request, every physical source consumed by that request, and the resulting immutable #193 campaign artifact into one authenticated invocation record without changing the strict #193 campaign directory layout.

The invocation seal is a sibling directory:

`<campaign-destination>.invocation/`

containing exactly:

- `request.json`
- `sources.json`
- `manifest.json`

The campaign directory remains the unchanged #193 four-entry artifact.

## Source population

Exactly six declared request inputs are fingerprinted:

1. candidate binary;
2. champion artifact;
3. comparison catalog;
4. FL3 entry-authority binary;
5. FL8.1 feature Parquet;
6. observer SQLite database.

All non-database sources are represented by physical byte size and SHA-256.

The observer SQLite source is represented by:

- database file bytes;
- any present `-wal` sidecar bytes.

The `-shm` sidecar is intentionally excluded because it is volatile lock/index state rather than evidence content.

## Pre/post immutability gate

The source snapshot and exact request-file bytes are captured before campaign execution.

After the #194 request runner returns, the request file must be byte-identical and the exact same six-source snapshot is captured again.

Any request or source difference is a hard failure.

Because the campaign destination was required to be absent before invocation, a post-run source mismatch causes the newly-created unsealed campaign directory to be removed.

This prevents a campaign produced across a moving evidence/model/binary boundary from surviving as a usable proof artifact.

## Campaign read-back gate

After source stability is confirmed, the produced campaign is opened through the strict #193 artifact reader.

The read-back artifact fingerprint must exactly equal the manifest returned by the request runner.

Any mismatch invalidates the invocation and removes the newly-created campaign.

## Source snapshot codec

`sources.json` is canonical compact sorted-key JSON.

Schema:

`shreks.fast_deterministic_campaign_sources` v1.

Each source records:

- request-field label;
- exact path string declared in the request;
- one or more physical components;
- component role;
- file name;
- byte size;
- SHA-256.

The top-level source snapshot fingerprint hashes the complete source document excluding only itself.

Source order is fixed lexically by request-field label.

## Invocation manifest

Schema:

`shreks.fast_deterministic_campaign_invocation` v1.

Fields:

- request logical fingerprint;
- exact request-file SHA-256;
- source count;
- source-snapshot fingerprint;
- campaign artifact fingerprint;
- campaign directory name;
- invocation fingerprint.

The invocation fingerprint authenticates every manifest field except itself.

## Atomic seal publication

The seal directory must not already exist.

After campaign completion and all stability/read-back gates, the three seal files are written to a private sibling staging directory.

The staged seal is read through the strict invocation reader.

Only a successful round trip permits rename to the final `.invocation` path.

A staging failure removes staging and removes the newly-created campaign because the invocation never reached a sealed state.

## Reader

The strict invocation reader requires:

1. exact three-file root entry set;
2. canonical request decode;
3. canonical source-snapshot decode;
4. valid source-snapshot fingerprint;
5. canonical invocation manifest;
6. valid invocation fingerprint;
7. request physical SHA match;
8. request logical fingerprint match;
9. source fingerprint/count match;
10. sibling #193 campaign strict read;
11. campaign artifact fingerprint match.

The reader authenticates the recorded invocation. It does not require original source files to remain present after the campaign has been sealed.

## Authority boundary

The invocation layer has no provider/network client, no strategy selection, no superiority evaluator, no signing/submission, and no LIVE authority.

It only authenticates local inputs around the sealed #194 request runner.

## TDD

Intentional RED:

`be485bb16d0cf8e085dd5c68880586394b6a6bc5`.

Tests require:

- exact request/source/campaign binding;
- observer database + WAL capture;
- SHM exclusion;
- source mutation invalidation;
- unsealed campaign cleanup;
- overwrite refusal;
- invocation-manifest tamper rejection;
- source authority firewall.

## Following slice

Add a one-argument console entry point that accepts only the canonical request-file path and executes the invocation-seal runner.

After that, the repository-side FL9 deterministic campaign path is ready for a real non-fixture post-selection evidence run.
