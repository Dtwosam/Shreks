# V1 First-Champion Tradable-Universe Preselection Implementation Plan

**Date:** 2026-10-04  
**Design:** `docs/superpowers/specs/2026-10-04-v1-first-champion-tradable-preselection-design.md`  
**Base main SHA:** `39985879d2c69d19e70fc086c4b5127e1af02418`

## Goal

Implement the authenticated input-side tradable-universe boundary for the score-free V1 first-champion chain without changing model/evaluation/economics semantics or granting any new physical execution authority.

## Task 1 — Add immutable preselection artifact

Create:

- `python/src/shreks_brain/fast_first_champion_preselection.py`
- `python/tests/test_fast_first_champion_preselection.py`

The module must provide:

- immutable accepted-decision model;
- immutable manifest/artifact models;
- builder from proof workspace + read-only observer DB + frozen FL9 policy;
- canonical writer/reader;
- accepted identity fingerprint;
- candidate-binding fingerprint;
- assessment-evidence fingerprint;
- reason counts;
- strict source stability checks;
- immutable destination semantics.

RED tests:

- valid eligible PumpSwap decision accepted;
- valid PumpSwap source row with only bonding-curve candidate rejected before training;
- future-discovered evidence cannot rescue history;
- missing/stale snapshot rejected;
- below-threshold market rejected;
- artifact codec/round-trip/fingerprint tamper rejection;
- duplicate accepted identity rejected;
- no target/model/execution/LIVE imports.

## Task 2 — Add exact identity-restricted bundle build

Modify:

- `python/src/shreks_brain/research/fast_training_bundle.py`
- `python/tests/test_fast_training_bundle.py`

Add optional:

`decision_identities: tuple[tuple[object, ...], ...] | None = None`

to `build_fast_training_bundle_from_runtime_sources`.

When supplied:

- require non-empty canonical unique seven-field identities;
- restrict horizon overlay rows to exactly those identities;
- require every requested identity exists in selected overlay;
- load features and FL4 labels only for those identities;
- preserve full source JSONL SHA binding;
- require labels/overlay/provenance sets equal the requested set;
- return no extra identity.

Existing `None` behavior must remain byte/semantic compatible.

## Task 3 — Bind preselection into context hydration

Modify:

- `python/src/shreks_brain/fast_context_hydration.py`
- `python/tests/test_fast_context_hydration.py`

Add optional authenticated candidate map keyed by exact seven-field decision identity.

When supplied:

- every hydrated identity must be present;
- use the bound positive candidate ID for historical exit-quote identity;
- do not call `resolve_candidate_at`;
- do not require candidate-row venue;
- keep decision quote-mint and decision venue policy checks;
- preserve generic legacy resolver behavior when no binding is supplied.

Add the candidate-binding fingerprint to the hydration artifact manifest so strict readback authenticates the exact binding used.

## Task 4 — Thread preselection through preparation

Modify:

- `python/src/shreks_brain/fast_first_champion_preparation.py`
- `python/tests/test_fast_first_champion_preparation.py`

Preparation must:

- accept exact preselection artifact;
- validate proof feature SHA and policy/fingerprint binding;
- select identities within the validation fold from accepted decisions;
- build the bundle using only accepted identities;
- pass candidate bindings to hydration;
- copy preselection into preparation artifact;
- bind preselection artifact and candidate-binding fingerprints in preparation manifest;
- build the nested file request with the copied preselection path/fingerprint.

## Task 5 — Thread preselection through nested first-champion request

Modify:

- `python/src/shreks_brain/fast_first_champion/file_request.py`
- `python/tests/test_fast_first_champion_file_request.py`

Schema bump.

Request must carry:

- `tradable_preselection_path`
- `expected_tradable_preselection_artifact_fingerprint_sha256`

Runner must:

- strict-read preselection;
- verify artifact fingerprint;
- restrict its training bundle to accepted identities in its validation-policy time domain;
- prove context identities are a subset/equal expected validation population;
- bind preselection fingerprint into final artifact manifest.

## Task 6 — Thread preselection through host request/run

Modify:

- `python/src/shreks_brain/fast_first_champion_host_run.py`
- `python/src/shreks_brain/fast_first_champion_host_request_writer.py`
- `python/tests/test_fast_first_champion_host_run.py`
- `python/tests/test_fast_first_champion_host_request_writer.py`

Schema bumps.

Host writer requires an existing immutable preselection artifact and validates:

- proof-workspace artifact fingerprint;
- feature-source SHA;
- fixed minimum decision timestamp;
- frozen FL9 policy;
- request preselection fingerprint.

Host run:

- strict-reads preselection;
- validates the request binding;
- captures selection clock as before;
- selects accepted identities before `selection_at - horizon`;
- builds filtered bundle;
- creates plan from filtered bundle;
- copies preselection into host-run output;
- passes it to preparation;
- binds artifact/accepted/candidate fingerprints in host-run manifest.

## Task 7 — Production regression and authority tests

Add/extend tests proving:

- the exact incident shape is rejected at preselection;
- no rejected identity appears in plan/hydration/fitting;
- candidate binding from preselection is reused without venue re-resolution;
- all old unrestricted library callers still work;
- V1 request old schema is rejected, not silently upgraded;
- V2 cohort/champion path remains unchanged;
- no score threshold/scoring-control path is introduced;
- no PAPER shadow/cutover/signing/LIVE authority is introduced.

Run:

```bash
python -m pytest \
  python/tests/test_fast_first_champion_preselection.py \
  python/tests/test_fast_training_bundle.py \
  python/tests/test_fast_context_hydration.py \
  python/tests/test_fast_first_champion_preparation.py \
  python/tests/test_fast_first_champion_file_request.py \
  python/tests/test_fast_first_champion_plan.py \
  python/tests/test_fast_first_champion_host_run.py \
  python/tests/test_fast_first_champion_host_request_writer.py \
  python/tests/test_fl9_tradable_universe.py \
  python/tests/test_fast_first_champion_v2_bundle.py \
  python/tests/test_fast_first_champion_v2_builder.py \
  python/tests/test_fast_first_champion_v2_host_run.py -q
```

Then run repository safety + full Python CI on the PR branch.

## Task 8 — Separate authority seal after implementation

Do not create retry authority as part of this implementation PR.

After merge + exact-main CI + immutable release + deployment verification, review a new docs-only authority seal for any future physical champion invocation.
