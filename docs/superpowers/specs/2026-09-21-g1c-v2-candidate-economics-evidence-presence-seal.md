# G1C V2 Candidate-Economics Evidence Tools — Production Presence Seal

**Date:** 2026-09-21  
**Entry-sizing implementation main SHA:** `315496cbc0627db19bd470a98a14acfbe6f7382b`  
**Quote-valuation implementation main SHA:** `9833cea3ef55458190a904ad90fb8ea7301abc67`  
**Production-presence implementation main SHA:** `3a302d789fee77d2597a4bd2b7317a991b038793`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF EVIDENCE-TOOL PRESENCE ONLY; AUTOMATIC EVIDENCE CAPTURE DISABLED; PRODUCTION CANDIDATE VALUES NOT AUTHORIZED; MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal two evidence-only tools needed to resolve the remaining G1C runtime-manifest v2 candidate economics gap:

- `shreks-g1c-v2-quote-valuation-reference`;
- `shreks-g1c-v2-entry-sizing-proposal`.

The tools deliberately separate factual production evidence from production candidate-value authority.

The quote-valuation reference binds one exact persisted market row and the existing sealed exact-market USD derivation into a private self-fingerprinted artifact.

The entry-sizing proposal consumes an explicit reviewed quote reference and proposes one raw target quote amount under:

`preserve_source_quote_notional_floor`

Neither artifact authorizes candidate values.

## Current production state before this seal

The currently active sealed production release is:

`07814813e10b6e88270a2506cf65d7bbbc68b606`

Production verification for that release proved:

- exact release/manifest identity;
- all three core PAPER services active/running with zero restarts;
- candidate-authority CLI/module exact-release-local;
- trusted-admin installer/planner/proof/readiness tools exact-release-local;
- installed root helper status `MATCHED_CURRENT_RELEASE`;
- protected FL9 state remains `HOLD_NO_COMPATIBLE`.

A trusted administrator subsequently produced a fresh helper installation proof bound to that release:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
proof_fingerprint_sha256=7240399c686d35d39857ebc674ad29fe28b911c227123187e2a529a0d1514ed2
campaign_manifest_unchanged=true
deploy_sudoers_unchanged=true
service_lifecycle_unchanged=true
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

That proof remains historical evidence for release `07814813...`. It must not be reused for readiness after this seal deploys a new current release.

## Entry-sizing proposal

The sizing tool authenticates one canonical v1 source runtime manifest and derives the source quote notional from that manifest's own:

- raw entry input amount;
- quote decimals;
- quote USD-per-token authority.

It accepts one explicit target quote USD reference plus its evidence fingerprint/timestamp and applies:

`preserve_source_quote_notional_floor`

The proposed raw target amount is floored to target raw units, so raw-unit rounding cannot make the proposed quote notional exceed the authenticated source quote notional.

The artifact is canonical JSON, write-once, mode `0600`, self-fingerprinted, and always records:

```text
status=PROPOSAL_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

### TDD evidence

Intentional RED head:

`f6ace38d772beae52f6cd6b8508f750100fa66fd`

RED CI:

`35654511919`

Result:

- Python failed only because the sizing-proposal module did not yet exist;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Final tested head:

`bd4cc58a6f98656788f75f83cd80a8c3bab792cc`

Push CI:

`35655720132`

Independent PR CI:

`35655726786`

Final result:

- Python: 3577 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged main:

`315496cbc0627db19bd470a98a14acfbe6f7382b`

Merged-main CI:

`35656661351`

Result: SUCCESS across all four canonical gates.

## Quote-valuation reference

The quote-reference tool accepts explicit:

- observer database path;
- candidate id;
- as-of timestamp;
- source;
- venue;
- base mint;
- quote mint;
- maximum evidence age;
- optional expected exact market row id;
- private destination.

It reuses only the already-sealed:

`ObserverMarketStore.quote_asset_usd_evidence(...)`

The observer store opens SQLite using URI `mode=ro`.

The selected evidence is attributed to one exact persisted market row and derives:

`quote_asset_usd_per_token = base_price_usd / base_price_quote`

The output binds the exact row id, candidate/source/venue/pair/base/quote identities, observation/as-of/freshness boundary, persisted prices, derived USD rate, and one self-fingerprint.

It always records:

```text
status=REFERENCE_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

### TDD evidence

Intentional RED head:

`50c57eff0cffa351dff32265807e4af91c38dc51`

RED CI:

`35657364739`

Result:

- Python failed only because the quote-reference module did not yet exist;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

GREEN implementation head:

`aea6813c8a80fa93fc6120368ffb216412acf85e`

Push CI:

`35657502915`

Independent PR CI:

`35657540651`

Result:

- Python: 3583 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged main:

`9833cea3ef55458190a904ad90fb8ea7301abc67`

Merged-main CI:

`35657795294`

Result: SUCCESS across all four canonical gates.

## Production-presence proof

The production verifier now proves, without executing either evidence tool, that the exact active immutable release physically contains both console scripts and both Python modules.

For each tool it requires:

- regular file;
- non-symlink;
- executable;
- console-script path resolving exactly inside the expected release;
- module import through the exact release-local Python;
- module path resolving exactly inside that same release.

Expected verifier evidence includes:

```text
g1c_v2_entry_sizing_proposal=present
g1c_v2_entry_sizing_proposal_path=<exact-release-local-path>
g1c_v2_entry_sizing_proposal_module=<exact-release-local-module-path>
g1c_v2_quote_valuation_reference=present
g1c_v2_quote_valuation_reference_path=<exact-release-local-path>
g1c_v2_quote_valuation_reference_module=<exact-release-local-module-path>
```

Automatic production verification does not invoke either CLI and performs no new protected database read through them.

### TDD evidence

Intentional RED head:

`bb1f9b6333e585b037e9ce93c845fe47c1ef8536`

RED CI:

`35657978205`

Result:

- Python: exactly 1 failed, 3583 passed, 2 known warnings;
- failure was the intentionally absent production-presence verifier/runbook surface;
- Repository safety: SUCCESS;
- ARM64 release build: SUCCESS;
- Rust remained independent of the absent Python contract.

First implementation head:

`02f66f6dd077647117ad89f2f3a8be5b0acfb9c2`

All runtime/safety gates were green; Python found only a runbook wording mismatch in the guard phrase. No implementation behavior changed.

Final implementation head:

`be33aaf3a94af4d9a0ad5efe2347a209c0b59fe9`

Push CI:

`35658385004`

Independent PR CI:

`35658389143`

Result:

- Python: 3584 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

Squash-merged production-presence main:

`3a302d789fee77d2597a4bd2b7317a991b038793`

Exact merged-main CI:

`35658683293`

Result:

- Python: 3584 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI is green, authorize the existing automatic chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include both evidence CLIs/modules in the release-local Python environment;
3. publish the immutable release;
4. deploy that exact release through the existing protected PAPER release manager;
5. preserve ordinary PAPER runtime behavior;
6. verify exact release/service/process provenance;
7. prove both evidence CLIs/modules are physically present in the exact release;
8. preserve the existing protected FL9 discovery behavior.

Automatic deployment/verification must not:

- invoke `shreks-g1c-v2-quote-valuation-reference`;
- invoke `shreks-g1c-v2-entry-sizing-proposal`;
- read protected SQLite through either new CLI;
- create a quote reference;
- create a sizing proposal;
- invoke candidate authority;
- author or stage a candidate;
- create a transition binding;
- execute rotation-readiness;
- invoke the root manifest manager;
- retry V2 scoring/model fitting;
- promote PAPER;
- sign or submit transactions;
- enable LIVE.

No sudoers change is authorized.

## Trusted-administrator evidence boundary

Only after the new sealed release is deployed and the production verifier has proved both evidence tools exact-release-local may a trusted administrator perform the documented bounded read-only inspection/capture flow.

A later physical quote reference remains evidence only.

A later physical sizing proposal remains evidence only.

A separate reviewed production candidate-value decision is required before candidate-authority invocation.

## Fresh helper proof boundary

Deployment of this seal will change the current release SHA.

Therefore the successful helper installation proof for release `07814813...` cannot be supplied to any future rotation-readiness proof after deployment.

Before readiness is ever attempted against the new release, a trusted administrator must create a fresh exact-release installation proof using the already-sealed idempotent prepare -> installer -> verify sequence.

This requirement does not block read-only valuation/sizing evidence capture.

## Promotion boundary

`G1C_V2_QUOTE_REFERENCE=SEALED_EVIDENCE_TOOL`

`G1C_V2_ENTRY_SIZING_PROPOSAL=SEALED_EVIDENCE_TOOL`

`AUTOMATIC_EVIDENCE_CAPTURE=DISABLED`

`PRODUCTION_CANDIDATE_VALUES=NOT_AUTHORIZED`

`CANDIDATE_AUTHORITY_EXECUTION=NOT_AUTHORIZED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
