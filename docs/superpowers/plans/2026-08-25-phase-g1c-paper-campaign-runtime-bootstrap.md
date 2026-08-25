# Phase G1C Paper Campaign Runtime Bootstrap — Verification Record

**Base:** sealed G1B `ad1a6527e6cb312af53b16e70b8f0cd26eda47a9`  
**Design:** `docs/superpowers/specs/2026-08-25-phase-g1c-paper-campaign-runtime-bootstrap-design.md`  
**Frozen behavior SHA:** `f074af2549e515615be189f101d362f685739831`

## Result

G1C adds one immutable/reproducible PAPER campaign manifest, an operational-only runtime configuration boundary, a supervised Python PAPER runtime that consumes the sealed G1B coordinator, and systemd wiring for continuous single-host operation.

The slice adds no live execution, signer, transaction construction/submission, wallet authority, promotion, registry mutation, provider-credential ownership, strategy/scoring/risk policy implementation, accounting implementation, checkpoint implementation, or evaluation implementation.

**LIVE TRADING: DISABLED.**

## TDD anchors

### Task 1 — immutable campaign manifest + canonical codec

RED: `19f8b2071e3b7c4dead90192d1ceafd121a2d3bf`
- CI `32896210375`
- failed exactly because `shreks_brain.observer_campaign.runtime_manifest` did not exist.

GREEN: `cad40511e89370862d513f81d9fa431ce632955f`
- CI `32896823532`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN

Proven:
- explicit `g1c-paper-campaign-runtime-manifest-v1` schema;
- canonical JSON and stable SHA-256 manifest fingerprint;
- strict exact field sets and allowlisted sealed dataclass/enum types only;
- malformed/unknown/non-canonical/tampered content fails closed;
- registry candidate fingerprint and strategy/feature attribution are verified;
- initial `PaperLoopState` is embedded through the already-sealed C6 sequence-0 checkpoint codec rather than a duplicate state codec;
- no hidden trading/economic defaults and no generic arbitrary-object deserializer.

### Task 2 — operational runtime config

RED: `11de74f1390a7d72d45a54b21617276953f1a953`
- CI `32897761058`
- failed exactly because `shreks_brain.observer_campaign.runtime_config` did not exist.

GREEN: `be684945ad7b569d625315fca7e7a8835bdbee5a`
- CI `32897893522`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN

Proven:
- only observer DB path, E11 path, manifest path, cycle interval, and optional finite max-cycle limit are accepted;
- relative paths resolve deterministically;
- cadence must be explicit, positive, and finite;
- unsupported `SHREKS_PAPER_CAMPAIGN_*` keys fail closed;
- starting capital, slippage/fill assumptions, strategy thresholds, score weights, risk limits, and candidate-selection bounds cannot become a second environment policy channel;
- provider credentials are not part of the G1C runtime config model.

### Task 3 — PAPER bootstrap and supervised loop

RED: `93772087533dd443f9a7a0acaacb36e845271947`
- CI `32898160965`
- failed exactly because `shreks_brain.observer_campaign.runtime` did not exist.

GREEN: `afe16d3998c16cc18d15abf1c3ef41dec801e918`
- CI `32898280009`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN

Proven against real seeded SQLite/E11/C6 paths:
- config -> manifest decode -> exactly one sealed `ObserverPaperCampaignCoordinatorRunner`;
- `load_state()` runs before autonomous work;
- exactly one wall-clock millisecond timestamp is generated per iteration and passed as both C5 `as_of` and checkpoint creation timestamp;
- one sealed G1B `run_cycle` call per iteration;
- restart reconstructs durable state before more work;
- exact finite cycle limits support controlled verification;
- pre-existing stop requests perform no cycle/checkpoint;
- waits are interruptible for SIGINT/SIGTERM shutdown;
- status output is explicit PAPER runtime/evidence metadata only;
- failures return safe error type metadata without echoing arbitrary exception/secret text;
- G1C adds no second ledger, evidence writer, checkpoint protocol, candidate selector, scorer, risk engine, or execution adapter.

### Task 4 — systemd supervision

RED: `be97eb927a2acfbcdce0f12b668d3a997e93f5f0`
- CI `32898618741`
- Python GREEN and repository safety GREEN;
- Rust failed exactly because `deploy/systemd/shreks-paper-campaign.service` was intentionally absent.

GREEN: `665cd940e1b33188da05ae65386a3c2f139c10d2`
- CI `32898824639`
- Python GREEN
- Rust/workspace GREEN
- repository safety GREEN

Proven:
- `shreks-paper-campaign.service` runs as unprivileged `shreks:shreks`;
- starts the release-coupled `/opt/shreks/current/.venv/bin/python` runtime;
- shared runtime environment remains protected under `/etc/shreks/shreks.env`;
- fingerprinted campaign manifest is a protected `/etc/shreks/paper-campaign.json` artifact;
- SQLite/E11 writes are confined to durable `/var/lib/shreks` under the systemd sandbox;
- service restarts on failure and joins `shreks.target` with observer + paper evidence services;
- per-release `.venv` makes Rust/Python rollback version-aligned;
- no live flag, signer/wallet material, provider credential value, or trading-policy environment override is embedded in the unit/runbook;
- GitHub-to-VPS delivery automation remains deferred to G2.

### Task 5 — restricted public API + authority firewall

RED: `98d30de1bd8746e0600daafcb32d6aa724d55bb8`
- CI `32898993033`
- 2,276 Python tests passed and exactly three failed because the planned G1C package exports were absent.

Initial GREEN: `4b7527a27326f1fe18bed09aa3526b98776244e7`
- CI `32899128544`
- 2,279 Python tests passed in 9.99s
- Rust/workspace GREEN
- repository safety GREEN

The public surface is exact and excludes `main`, raw candidate write stores, provider credentials, registry mutation, promotion, signing, submission, transaction, and live execution authority. Fresh package imports do not pull promotion/live/execution modules.

## Pre-seal audit defect and correction

The first full scope audit found one deployment-specific Python entrypoint defect before seal: eager package export of `.runtime` caused `python -m shreks_brain.observer_campaign.runtime` to pre-import the executable module and emit a `runpy` `RuntimeWarning` before executing it as `__main__`.

Audit RED: `77156e51194e4ca96742328ef6c9615354f8f935`
- CI `32899587280`
- exactly one Python failure with 2,279 passes;
- failure reproduced the `RuntimeWarning: ... found in sys.modules ... prior to execution`;
- repository safety GREEN.

Audit GREEN / final behavior: `f074af2549e515615be189f101d362f685739831`
- CI `32899704688`
- **2,280 Python tests passed in 9.78s**
- Rust/workspace GREEN
- repository safety GREEN

Correction:
- the exact public API remains unchanged;
- manifest/config exports remain normal imports;
- executable runtime exports are resolved lazily through package `__getattr__`;
- `python -m shreks_brain.observer_campaign.runtime` now executes cleanly without package pre-import/runpy ambiguity;
- `main` remains non-public;
- authority/firewall behavior remains unchanged.

## Frozen scope audit

Comparison: sealed G1B `ad1a6527e6cb312af53b16e70b8f0cd26eda47a9` -> frozen G1C `f074af2549e515615be189f101d362f685739831`

Geometry:
- **19 commits ahead**
- **0 behind**
- **15 changed files**

Changed files:
1. `.env.example`
2. `crates/shreks-observer/tests/systemd_units.rs`
3. `deploy/systemd/README.md`
4. `deploy/systemd/shreks-paper-campaign.service`
5. `deploy/systemd/shreks.target`
6. `docs/superpowers/plans/2026-08-25-phase-g1c-paper-campaign-runtime-bootstrap.md`
7. `docs/superpowers/specs/2026-08-25-phase-g1c-paper-campaign-runtime-bootstrap-design.md`
8. `python/src/shreks_brain/observer_campaign/__init__.py`
9. `python/src/shreks_brain/observer_campaign/runtime.py`
10. `python/src/shreks_brain/observer_campaign/runtime_config.py`
11. `python/src/shreks_brain/observer_campaign/runtime_manifest.py`
12. `python/tests/test_observer_campaign_public_api.py`
13. `python/tests/test_observer_campaign_runtime.py`
14. `python/tests/test_observer_campaign_runtime_config.py`
15. `python/tests/test_observer_campaign_runtime_manifest.py`

Every changed file was inspected. The scope contains only G1C design/verification documentation, runtime manifest/config/orchestration code, systemd supervision/runbook wiring, package exports, and their tests.

Verified absent from the G1B -> G1C diff:
- provider implementation changes;
- storage schema/migration changes;
- strategy/setup/scoring implementation changes;
- risk-engine implementation changes;
- paper execution/ledger/accounting/checkpoint/evaluation implementation changes;
- registry-store mutation or promotion authority;
- transaction construction/signing/submission;
- wallet/private-key authority;
- live execution paths.

## Frozen behavior proof

Frozen behavior SHA: `f074af2549e515615be189f101d362f685739831`

Behavior CI: `32899704688`
- Python: **2,280 passed in 9.78s**
- Rust/workspace: GREEN
- repository safety: GREEN

This behavior SHA is immutable. The only permitted post-behavior change is this verification record.

## Seal rule

The final seal commit must differ from `f074af2549e515615be189f101d362f685739831` by exactly this file, be exactly one commit ahead and zero behind, and pass a fresh exact-seal CI run.

## Deferred after G1C

G2 may add GitHub -> VPS release/deployment mechanics for the sealed G1/G1B/G1C lineage. After deployment, Shreks can run a real point-in-time PAPER campaign to accumulate independent E10/E11/E12 evidence and determine whether expectancy after realistic costs is actually positive. Later G3+ work adds broader 24/7 monitoring/telemetry/dashboard/alerts.

Synthetic fixtures and runtime mechanics do not prove profitability.

**LIVE TRADING: DISABLED.**
