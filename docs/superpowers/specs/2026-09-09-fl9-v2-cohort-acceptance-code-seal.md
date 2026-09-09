# FL9 V2 Cohort Acceptance — Code/CI Seal

**Date:** 2026-09-09  
**Implementation main SHA:** `03a5e7e580044237d8c63152c67dab3fe8b0334a`  
**Design/plan main SHA:** `23756d179febca013901e01164179851f6cdca36`  
**Status:** SEALED FOR IMMUTABLE RELEASE BUILD; PHYSICAL COHORT ARTIFACT NOT YET CREATED

## Purpose

Seal the merged, input-only FL9 V2 cohort-acceptance implementation after exact-head and merged-main CI proof so the existing immutable ARM64 release workflow can package the production cohort builder.

This seal authorizes release construction and later read-only cohort-artifact generation only.

It does **not** authorize:

- FL4 target reads for this cohort;
- future-return inspection;
- model training;
- model-quality inspection;
- PnL/economics inspection;
- first-champion promotion;
- PAPER execution changes;
- signing/submission;
- LIVE trading.

## Frozen cohort contract

Acceptance policy:

`fl9-v2-cohort-acceptance-v1`

Evidence-floor policy:

`fl9-v2-cohort-evidence-floor-v1`

The implementation freezes:

- source sessions: `115,116,117,118,119,120,121,122` exactly;
- required immutability boundary: latest session ID >= 123;
- cohort lower bound: `1788878323281`;
- horizon: `30,000 ms`;
- TEST end exclusive: `1788902289835`;
- selection timestamp: `1788902319835`;
- training cut: `1788892302791`;
- validation cut: `1788898931418`.

Structural evidence floors:

- eligible rows >= 250,000;
- training rows >= 150,000;
- validation rows >= 50,000;
- TEST rows >= 50,000;
- unseen-mint validation rows >= 40,000;
- unseen validation unique mints >= 20;
- unseen-mint TEST rows >= 40,000;
- unseen TEST unique mints >= 25.

Downstream target-scoring floors are recorded now but are not inspected or enforced by this package:

- natural TEST scored observations >= 40,000;
- unseen-mint TEST scored observations >= 35,000.

## Frozen input-only production checkpoint

The public production policy records the previously audited immutable checkpoint:

- raw PumpSwap decisions: 504,716;
- cross-session duplicates: 0;
- raw unique mints: 394;
- FL9-v1 eligible rows: 274,334;
- eligible unique mints: 146;
- missing fresh exact snapshot: 176,299;
- below minimum liquidity: 52,974;
- below minimum h24 volume: 1,109;
- raw training: 164,645;
- raw validation: 54,858;
- raw TEST: 54,831;
- shared cross-partition signatures: 0;
- validation unseen-mint rows / mints: 49,754 / 24;
- TEST unseen-mint rows / mints: 54,828 / 31.

The builder fails closed if immutable production evidence no longer reproduces these checkpoint values.

## Authenticated policies

Tradable universe:

- version: `fl9-tradable-universe-v1`;
- fingerprint:
  `abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`.

Feature identity firewall:

- version: `fl8.3-feature-identity-firewall-v1`;
- fingerprint:
  `e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`.

The cohort builder delegates eligibility to the sealed FL9 assessor; it does not copy or weaken tradability thresholds.

## Merged implementation scope

Added:

- `python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py`
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/models.py`
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/source.py`
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/builder.py`
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/artifact.py`
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/cli.py`
- focused fixtures/tests for models, source, builder, artifact, CLI, and authority.

Modified:

- `python/pyproject.toml` only to register:
  `shreks-fl9-v2-cohort-acceptance`.

No first-champion runner/plan/builder, collector, risk, PAPER, signing, submission, or LIVE source was changed.

## Authority boundary enforced in code

The package:

- opens source SQLite with `mode=ro`;
- sets `PRAGMA query_only = ON`;
- reads the union of eight exact session windows, never one broad gap-spanning interval;
- preserves repeated mints and actors;
- quarantines only cross-partition transaction signatures;
- derives mint/actor novelty relative to raw training;
- records concentration diagnostics without adding a concentration admission threshold;
- writes immutable canonical `manifest.json`, `accepted-decisions.jsonl`, and `signature-quarantine.jsonl`;
- refuses destination overwrite;
- rejects symlink members and file/fingerprint tamper;
- excludes wall-clock time from canonical artifact bytes;
- has no label/trainer/evaluation/economics/PAPER/LIVE authority.

The root package uses lazy builder/artifact exports so importing
`shreks_brain.fl9_v2_cohort_acceptance` does not eagerly load sklearn, pyarrow, first-champion, training-bundle, target, or evaluation modules.

## TDD trail

Intentional RED stages proved absence/failure before each implementation unit:

1. missing cohort package/model contracts;
2. missing exact-window source reader;
3. missing authenticated cohort builder;
4. missing canonical artifact codec;
5. missing frozen CLI;
6. incomplete public authority export.

The implementation also fixed defects exposed by GREEN verification rather than weakening tests:

- session-contract import initialization order;
- a malformed TOML console-script newline;
- complete manifest semantics for session metadata, novelty diagnostics, concentration summaries, floor policy, and all required subset fingerprints.

## Exact-head verification

Reviewed feature head:

`a2b3e23003d0ef2b78222836bbc206da4d0812a1`

Push CI:

- run `34295620624`;
- Repository safety: SUCCESS;
- Python tests: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

PR CI:

- run `34295623796`;
- Repository safety: SUCCESS;
- Python tests: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Merged-main verification

PR #257 was squash-merged as:

`03a5e7e580044237d8c63152c67dab3fe8b0334a`

Merged-main CI:

- run `34295856364`;
- Repository safety: SUCCESS;
- Python tests: SUCCESS;
- Rust tests: SUCCESS;
- ARM64 release build: SUCCESS.

## Required next evidence

After this docs-only seal lands on `main`:

1. seal-main CI must pass all four gates;
2. automatic immutable release construction must succeed;
3. exact release tag/assets must be verified;
4. deploy the exact sealed release to `production-paper`;
5. verify physical release/process identity;
6. run exactly:
   `sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-cohort-acceptance --database /var/lib/shreks/shreks.db --destination <new-immutable-path>`;
7. read the artifact back with the deployed package;
8. verify exact row counts, subset fingerprints, file hashes, structural-floor PASS, and final artifact fingerprint;
9. record that physical artifact fingerprint in a separate evidence seal.

Only after step 9 may the project begin the separate V2 first-champion integration slice.

## Current authority state

- cohort acceptance implementation merged: **YES**;
- merged-main CI: **PASS**;
- immutable release containing cohort builder: **PENDING THIS SEAL**;
- production-paper deployment of builder: **NOT YET PROVEN**;
- physical cohort artifact: **NOT CREATED**;
- eligible identity fingerprint: **NOT YET PHYSICALLY CREATED**;
- cohort floor accepted: **NO**;
- target values inspected for accepted cohort: **NO**;
- model training: **BLOCKED**;
- model performance: **NOT INSPECTED**;
- PnL: **NOT INSPECTED**;
- PAPER promotion: **BLOCKED**;
- LIVE trading: **DISABLED**.
