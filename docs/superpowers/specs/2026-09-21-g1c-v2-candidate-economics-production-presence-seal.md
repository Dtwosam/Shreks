# G1C V2 Candidate Economics Production Presence — Release Seal

**Date:** 2026-09-21  
**Entry-sizing implementation main SHA:** `315496cbc0627db19bd470a98a14acfbe6f7382b`  
**Quote-valuation implementation main SHA:** `9833cea3ef55458190a904ad90fb8ea7301abc67`  
**Production-presence implementation main SHA:** `3a302d789fee77d2597a4bd2b7317a991b038793`  
**Status:** SEALED FOR IMMUTABLE RELEASE + AUTOMATIC PROTECTED PAPER DEPLOY/VERIFY OF EVIDENCE-TOOL PRESENCE ONLY; AUTOMATIC EVIDENCE CAPTURE DISABLED; PRODUCTION CANDIDATE VALUES NOT AUTHORIZED; CANDIDATE AUTHORITY NOT AUTHORIZED; PRODUCTION V2 MANIFEST ROTATION NOT AUTHORIZED; V2 SCORING NOT AUTHORIZED

## Purpose

Seal two evidence-only G1C v2 candidate-economics tools and their read-only production-presence proof:

- `shreks-g1c-v2-quote-valuation-reference`;
- `shreks-g1c-v2-entry-sizing-proposal`.

The quote-valuation reference binds one exact persisted observer-market row into a canonical reference artifact.

The entry-sizing proposal uses one reviewed quote reference to propose a raw target quote amount under the policy:

`preserve_source_quote_notional_floor`

Neither artifact is production candidate-value authority.

This seal deploys code presence only. It does not execute either evidence tool.

## Production state before this seal

The currently deployed and production-verified sealed release is:

`07814813e10b6e88270a2506cf65d7bbbc68b606`

That release successfully completed:

- sealed-main CI `35651954620`;
- immutable release build `35652197572`;
- protected PAPER deploy/verify `35652754557`.

Production verification proved the candidate-input authority binder physically present in that exact release while preserving:

- healthy PAPER services;
- zero service restarts;
- protected campaign-manifest identity;
- protected FL9 status `HOLD_NO_COMPATIBLE`;
- root manifest-manager helper state `MATCHED_CURRENT_RELEASE`.

A trusted administrator then refreshed the exact-release helper proof for `07814813e10b6e88270a2506cf65d7bbbc68b606`.

The canonical proof returned:

```text
status=VERIFIED
installation_authority=PROVEN_EXACT_RELEASE_BOUND_HELPER_ONLY
proof_fingerprint_sha256=7240399c686d35d39857ebc674ad29fe28b911c227123187e2a529a0d1514ed2
manifest_rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

The proof also established:

- protected campaign manifest unchanged at SHA-256 `3118bc5289b758a02bfd993085ed16f103a524b4d15a29ee50f45922a47fd530`;
- deployment sudoers unchanged at SHA-256 `d21e7ee16e9c9b60ec8f950dcf04bb95a53a49b6bb986602640374e33efc1204`;
- PAPER service lifecycle unchanged;
- exact manager SHA-256 `e612ca524d633fb5ee58be2e4bb38ad5e1ff1bba418354ca2176561a74fef104`;
- exact release wheel SHA-256 `c78dad3b83d63fdfbfb2008e82683704b8f1b8c70d263a079fbc096549934158`.

## Entry-sizing proposal implementation

The evidence-only entry-sizing proposal was merged as:

`315496cbc0627db19bd470a98a14acfbe6f7382b`

Its policy is:

`preserve_source_quote_notional_floor`

The tool:

1. authenticates one canonical v1 source runtime manifest;
2. derives that source manifest's quote-side USD notional;
3. accepts an explicit target quote mint, target decimals, reviewed target quote USD-per-token reference, reference fingerprint, and reference observation time;
4. calculates the target raw amount that preserves source quote notional;
5. floors to whole target raw units so raw-unit rounding cannot increase the source notional;
6. writes one canonical mode-0600 write-once proposal artifact.

The proposal always records:

```text
status=PROPOSAL_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

### TDD and CI

Intentional RED:

- head `f6ace38d772beae52f6cd6b8508f750100fa66fd`;
- CI `35654511919`;
- Python failed only because the sizing-proposal module did not yet exist;
- Repository safety, Rust, and ARM64 succeeded.

The first GREEN attempt correctly preserved its test fixture's authenticated $100 source notional; two tests incorrectly hard-coded the physical production source's $25 notional. The tests were corrected to derive expectations from the authenticated fixture rather than embedding production economics.

Final corrected head:

`bd4cc58a6f98656788f75f83cd80a8c3bab792cc`

Verified push CI:

`35655720132`

Result:

- Python: 3577 passed, 2 known warnings;
- Repository safety: SUCCESS;
- Rust: SUCCESS;
- ARM64: SUCCESS.

Independent PR CI:

`35655726786`

Result: SUCCESS across all four canonical gates.

Merged-main CI for `315496cbc0627db19bd470a98a14acfbe6f7382b`:

`35656661351`

Result: SUCCESS across all four canonical gates.

The associated build/deploy workflow runs correctly skipped because the implementation commit is `feat:`, not `seal:`.

## Quote-valuation reference implementation

The evidence-only quote-valuation reference was merged as:

`9833cea3ef55458190a904ad90fb8ea7301abc67`

The tool requires every market-selection input explicitly:

- observer database path;
- candidate id;
- as-of timestamp;
- source;
- venue;
- base mint;
- quote mint;
- freshness bound;
- optional exact expected market row id;
- private destination.

It reuses only the existing sealed:

`ObserverMarketStore.quote_asset_usd_evidence(...)`

path.

That store opens SQLite through URI `mode=ro`.

The reference derives:

`quote_asset_usd_per_token = base_price_usd / base_price_quote`

from one exact persisted market row and binds:

- exact market row id;
- candidate/source/venue/pair/base/quote identity;
- row observation time;
- requested as-of/freshness boundary;
- exact persisted base-price-in-quote text;
- canonical base USD price;
- canonical derived quote USD-per-token;
- one self-fingerprint.

The reference always records:

```text
status=REFERENCE_EVIDENCE_ONLY
candidate_value_authority=NOT_GRANTED
candidate_authoring_authority=NOT_GRANTED
rotation_authority=NOT_GRANTED
scoring_authority=NOT_GRANTED
paper_promotion_authority=BLOCKED
live_authority=DISABLED
```

### TDD and CI

Intentional RED:

- head `50c57eff0cffa351dff32265807e4af91c38dc51`;
- CI `35657364739`;
- Python failed at collection only because the quote-valuation-reference module did not yet exist.

Final implementation head:

`aea6813c8a80fa93fc6120368ffb216412acf85e`

Push CI:

`35657502915`

Independent PR CI:

`35657540651`

Both completed successfully across Python, Rust, repository safety, and ARM64.

Merged-main CI for `9833cea3ef55458190a904ad90fb8ea7301abc67`:

`35657795294`

Result: SUCCESS across all four canonical gates.

Its build/deploy workflow runs correctly skipped because the implementation commit is `feat:`.

## Production-presence implementation

PR #379 added read-only production presence/provenance checks for both evidence tools.

Final implementation head:

`be33aaf3a94af4d9a0ad5efe2347a209c0b59fe9`

Push CI:

`35658385004`

Independent PR CI:

`35658389143`

Both succeeded across all four canonical gates.

The squash-merged production-presence main commit is:

`3a302d789fee77d2597a4bd2b7317a991b038793`

Exact merged-main CI:

`35658683293`

Result:

- Python: SUCCESS;
- Rust: SUCCESS;
- Repository safety: SUCCESS;
- ARM64: SUCCESS.

The production verifier now requires, without executing either tool:

- each release-local console script to be a regular non-symlink executable;
- each script to resolve exactly under the expected immutable release;
- each imported Python module to resolve exactly under that same release.

Expected production evidence includes:

```text
g1c_v2_quote_valuation_reference=present
g1c_v2_quote_valuation_reference_path=<exact-release-local-path>
g1c_v2_quote_valuation_reference_module=<exact-release-local-module-path>
g1c_v2_entry_sizing_proposal=present
g1c_v2_entry_sizing_proposal_path=<exact-release-local-path>
g1c_v2_entry_sizing_proposal_module=<exact-release-local-module-path>
```

The verifier does not invoke either CLI.

## Automatic authority granted by this seal

After this docs-only `seal:` commit lands on `main` and exact sealed-main CI succeeds, authorize the existing automatic release/deploy chain only to:

1. build one immutable ARM64 release for the exact seal SHA;
2. include both evidence-only CLIs/modules in that release;
3. publish the immutable GitHub release;
4. deploy that exact release through the existing protected PAPER release manager;
5. activate the ordinary protected PAPER runtime;
6. verify release identity, service/process health, restart state, exact-release provenance of all already-sealed trusted-admin tools, candidate-authority presence, quote-reference presence, sizing-proposal presence, helper status, and existing protected FL9 read-only discovery.

Automatic deployment and verification must not:

- execute the quote-valuation reference CLI;
- read the protected observer database on behalf of the new evidence tool;
- execute the entry-sizing proposal;
- choose a quote row or price;
- choose or approve a raw entry amount;
- invoke candidate authority;
- author or stage a candidate manifest;
- create a transition binding;
- execute rotation-readiness;
- invoke manifest rotation;
- retry V2 scoring/model fitting;
- promote PAPER;
- access wallets;
- sign or submit transactions;
- enable LIVE.

## Existing root helper across this release

The root helper remains outside immutable release directories:

`/usr/local/sbin/shreks-paper-manifest-manager`

Automatic deployment must not install, replace, chmod, chown, or execute it.

The evidence-tool implementation does not alter the sealed manager source.

The ordinary verifier may report the helper as matching the new current release if bytes and metadata remain exact.

A mismatch is a failed state, not permission for automatic repair.

## Fresh helper proof after deployment

The current canonical helper proof fingerprint:

`7240399c686d35d39857ebc674ad29fe28b911c227123187e2a529a0d1514ed2`

is bound to release:

`07814813e10b6e88270a2506cf65d7bbbc68b606`.

If this seal deploys a new release SHA, that proof must not be reused for any later rotation-readiness operation.

Before any later readiness proof, a trusted administrator must refresh the three-step exact-release helper proof:

1. installation-proof `prepare`;
2. exact release-bound installer;
3. installation-proof `verify`.

An unchanged matching helper may legitimately produce installer status:

`ALREADY_INSTALLED`.

## Trusted-admin evidence capture after deployment

Only after production verification proves both evidence tools physically present in the exact deployed release may a trusted administrator perform a separate bounded evidence-capture ceremony.

The runbook requires all quote-row selector inputs explicitly.

There are no production defaults.

A quote reference is evidence only.

A sizing proposal is evidence only.

The resulting artifacts must be reviewed before any production candidate-value decision.

## Production candidate-value boundary

This seal does not authorize concrete values for:

- `paper_run_id`;
- `start_at_unix_ms`;
- raw WSOL `entry_input_amount`.

WSOL decimals are established repository protocol knowledge, but this seal does not convert any proposed amount into production authority.

The following remain evidence rather than candidate-value authority:

- persisted observer market rows;
- quote-valuation reference artifacts;
- entry-sizing proposal artifacts;
- historical USDC runtime values;
- historical hydration-policy values;
- unit-test/example values;
- the earlier identity-only runtime quote-evidence diagnostic.

A later separately explicit production candidate-value decision may accept, reject, or replace a reviewed proposal.

Only after such a decision may the candidate-input authority binder be invoked with the exact reviewed values.

## Candidate/readiness boundary

Even after one exact candidate-value set is separately authorized:

1. bind those exact values through the candidate-input authority artifact;
2. emit the exact canonical v2 candidate bytes through the existing candidate-authoring path;
3. require the exact candidate to pass the existing read-only compatible assessment against frozen cohort/request authority;
4. create the exact immutable transition binding;
5. stage the exact candidate/binding inputs;
6. only then execute the already-sealed evidence-only rotation-readiness proof.

A future successful readiness proof remains evidence only and does not itself authorize production manifest rotation.

## Rotation, scoring, promotion, and LIVE boundary

This seal does not authorize:

- production v2 manifest rotation;
- `shreks-paper-manifest-manager rotate`;
- V2 scoring retry;
- model fitting;
- champion publication;
- PAPER promotion;
- wallet access;
- signing;
- transaction construction;
- submission;
- LIVE.

## Promotion boundary

`G1C_V2_QUOTE_VALUATION_REFERENCE=SEALED_EVIDENCE_ONLY`

`G1C_V2_ENTRY_SIZING_PROPOSAL=SEALED_EVIDENCE_ONLY`

`CANDIDATE_ECONOMICS_PRODUCTION_PRESENCE=SEALED_READ_ONLY`

`AUTOMATIC_QUOTE_REFERENCE_CAPTURE=DISABLED`

`AUTOMATIC_ENTRY_SIZING_PROPOSAL=DISABLED`

`PRODUCTION_CANDIDATE_VALUES=NOT_AUTHORIZED`

`AUTOMATIC_CANDIDATE_AUTHORITY_EXECUTION=DISABLED`

`PRODUCTION_V2_MANIFEST_ROTATION=NOT_AUTHORIZED`

`V2_SCORING_RETRY=NOT_AUTHORIZED`

`PAPER_PROMOTION=BLOCKED`

`LIVE=DISABLED`
