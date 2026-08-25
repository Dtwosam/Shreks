# Phase G1C Paper Campaign Runtime Bootstrap — Implementation Plan

**Base:** sealed G1B `ad1a6527e6cb312af53b16e70b8f0cd26eda47a9`  
**Design:** `docs/superpowers/specs/2026-08-25-phase-g1c-paper-campaign-runtime-bootstrap-design.md`

## Goal

Add one immutable/reproducible PAPER campaign manifest and one supervised Python runtime bootstrap that constructs the sealed G1B coordinator without hard-coded strategy/risk/economic defaults, resumes durable state on restart, and runs unattended in PAPER mode.

No live, signer, submission, promotion, registry-mutation, wallet-authority, or provider-credential authority is in scope.

## Task 1 — immutable campaign manifest model + canonical codec

Files:
- add `python/src/shreks_brain/observer_campaign/runtime_manifest.py`
- add `python/tests/test_observer_campaign_runtime_manifest.py`

RED first:
- explicit schema/version and top-level exact-key validation;
- encode/decode round-trip reconstructs exact sealed domain objects;
- canonical JSON bytes and stable SHA-256 fingerprint;
- unknown/missing keys fail closed;
- malformed enum/dataclass/policy values fail closed;
- fingerprint mismatch and non-canonical payload fail closed;
- no trading/economic defaults are supplied by the codec.

GREEN minimally with explicit codecs for only the already-sealed G1B startup types. Do not introduce a generic arbitrary-object deserializer.

## Task 2 — operational runtime config

Files:
- add `python/src/shreks_brain/observer_campaign/runtime_config.py`
- add `python/tests/test_observer_campaign_runtime_config.py`
- update `.env.example` only with operational path/cadence variables.

RED first:
- require observer DB, E11 evidence, and manifest file paths;
- require explicit positive cycle interval;
- optional positive finite cycle limit for controlled runs;
- relative paths resolve predictably;
- malformed/missing values fail closed;
- no starting capital, strategy thresholds, score weights, risk limits, slippage assumptions, or candidate-selection bounds are accepted from environment config.

GREEN with environment parsing only for operational deployment values.

## Task 3 — PAPER runtime bootstrap and loop

Files:
- add `python/src/shreks_brain/observer_campaign/runtime.py`
- add `python/tests/test_observer_campaign_runtime.py`

RED first:
- bootstrap loads config + manifest and constructs exactly one sealed `ObserverPaperCampaignCoordinatorRunner`;
- restart loads durable state before first cycle;
- each iteration generates one point-in-time timestamp and calls `run_cycle` exactly once;
- finite cycle limit stops deterministically for verification;
- SIGINT/SIGTERM-compatible stop path performs no extra cycle;
- runner/manifest/config failures propagate fail closed;
- status output contains PAPER/runtime/evidence metadata only and no secrets.

GREEN without adding candidate selection/scoring/risk/execution behavior outside G1B.

## Task 4 — supervised systemd deployment

Files:
- add `deploy/systemd/shreks-paper-campaign.service`
- update `deploy/systemd/README.md`
- update deployment tests as needed.

RED first:
- unit runs non-root Shreks service user;
- unit loads shared environment file;
- unit launches Python module runtime bootstrap;
- restart-on-failure and clean SIGINT/SIGTERM semantics;
- persistent observer/evidence/manifest paths outside release checkout;
- no live-mode flag, wallet material, registry mutation, or provider credential values embedded in unit.

GREEN with the smallest systemd wiring consistent with sealed G1 deployment conventions.

## Task 5 — restricted API, authority firewall, freeze/audit/seal

Before seal:
- public runtime surface is exact and PAPER-only;
- full CI GREEN on frozen behavior SHA;
- compare sealed G1B -> G1C and inspect every changed file;
- verify no strategy/scoring/risk/execution/accounting/checkpoint/evaluation implementation drift;
- verify no live/promotion/registry-store/signer/submission authority;
- record RED/GREEN anchors and exact behavior CI here.

Seal:
- replace this plan with final verification record as the only post-behavior change;
- prove behavior -> seal is exactly one commit, zero behind, and one file;
- run fresh exact-seal CI;
- update stacked draft PR with behavior SHA, seal SHA, CI IDs, scope audit, and `LIVE TRADING: DISABLED`.

## Deferred after G1C seal

Deploy the sealed G1/G1B/G1C lineage to the dedicated VPS through G2 delivery mechanics, then run a real point-in-time paper campaign and accumulate independent paper trades for E10/E11/E12 profitability/proof evaluation. Production monitoring/dashboard/alerts continue under later G3+ tasks.
