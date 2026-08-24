# Phase E6 Champion / Challenger Registry — Implementation Plan

**Goal:** Build a deterministic, durable Python registry that records evaluated strategy/model provenance and explicit challenger/champion/retired status history without deciding promotion eligibility.

**Base:** sealed A10 `d36ec5fd3d650f0c8d55c56fd461f371e910d8f3`  
**Spec:** `docs/superpowers/specs/2026-08-24-phase-e6-champion-challenger-registry-design.md`

## Global constraints

- E6 is registry/audit only.
- E6 must not inspect metrics to decide whether a candidate should become champion.
- E7 owns shadow/paper challenger operation.
- E8 owns promotion criteria/decision logic.
- Real money remains disabled.
- Reuse E3/E4/E5 sealed schema objects and fingerprints; do not recompute model training, validation, or trading metrics.
- No new external dependency.
- No network, random source, or wall-clock timestamp generation.
- Caller supplies all decision/registration timestamps.
- Corrupt or contradictory persisted state fails closed.

---

## Task 1 — Registry contract and evidence normalization

**Create:**
- `python/src/shreks_brain/registry/models.py`
- `python/src/shreks_brain/registry/builder.py`
- `python/src/shreks_brain/registry/__init__.py`
- `python/tests/test_registry_models.py`
- `python/tests/test_registry_builder.py`
- `python/tests/test_registry_public_api.py`

**Contract:**
- `CHAMPION_CHALLENGER_REGISTRY_SCHEMA_VERSION = "e6-registry-v1"`
- `RegistryStatus`: `CHALLENGER`, `CHAMPION`, `RETIRED`
- immutable `RegistryEvaluationEvidence`
- immutable `RegistryCandidate`
- immutable `RegistryStatusEvent`
- immutable `ChampionChallengerRegistry`
- `build_registry_candidate(...)`

Tests first:

- [ ] lock exact public API;
- [ ] model-backed registration preserves E3 model/training fingerprint and training bounds;
- [ ] E4 request/model feature alignment is enforced;
- [ ] all E4 fold models align with the registered model identity/features;
- [ ] E5 candidate version must match registry candidate version;
- [ ] evaluation evidence snapshots required headline metrics and E5 fingerprint;
- [ ] strategy-only registration requires both E3 and E4 provenance to be absent;
- [ ] partial ML provenance fails closed;
- [ ] candidate fingerprint is deterministic and changes when material provenance/evaluation changes;
- [ ] registration starts `CHALLENGER` only;
- [ ] no API performs metric-driven promotion.

Require a clean RED caused only by missing E6 package/surfaces, then implement the smallest pure dataclass/canonicalization layer and require full CI GREEN.

---

## Task 2 — Durable canonical registry store

**Create:**
- `python/src/shreks_brain/registry/store.py`
- `python/tests/test_registry_store.py`

**Contract:**
- `RegistryStore(path)`
- `load() -> ChampionChallengerRegistry`
- `register(candidate) -> ChampionChallengerRegistry`
- `record_status_event(event) -> ChampionChallengerRegistry`

Behavior:

- [ ] missing file loads a valid empty registry;
- [ ] canonical JSON round-trip preserves fingerprints/status/history exactly;
- [ ] parent directory creation works;
- [ ] write uses deterministic sibling temporary path + `os.replace`;
- [ ] duplicate identical candidate registration is idempotent;
- [ ] same candidate version with different fingerprint fails closed;
- [ ] every persisted candidate/event fingerprint is revalidated on load;
- [ ] registry fingerprint is recomputed and verified on load;
- [ ] truncated/invalid JSON fails closed;
- [ ] tampered material field fails closed;
- [ ] unknown schema/status fails closed;
- [ ] no delete/history-rewrite API exists.

Require clean RED then full CI GREEN before Task 3.

---

## Task 3 — Explicit status history and champion integrity

**Extend tests/models/store only as needed.**

Behavior:

- [ ] status event requires existing candidate;
- [ ] `from_status` must equal reconstructed current status;
- [ ] no-op transitions fail;
- [ ] decision reference/reason must be non-empty;
- [ ] event timestamp cannot precede candidate registration;
- [ ] duplicate identical event is idempotent;
- [ ] conflicting event identity fails closed;
- [ ] at most one candidate may reconstruct to `CHAMPION`;
- [ ] `current_champion()` returns zero or one candidate;
- [ ] challengers are returned in deterministic candidate-version order;
- [ ] status changes never inspect E5 metric thresholds;
- [ ] retired-to-other transitions remain structurally possible for future explicit E8 rollback rules;
- [ ] source firewall contains no execution/sign/submit/live authority.

Require full CI GREEN.

---

## Task 4 — Documentation and seal

- [ ] audit cumulative diff from sealed A10; allowed scope is E6 docs, registry package/tests, plus build-order/readme status documentation only;
- [ ] update `SHREKS_BUILD_ORDER.md` current position to mark E5 and A10 sealed and E6 active/complete as appropriate;
- [ ] add concise README registry usage/boundary section if useful;
- [ ] replace this plan with a verification record containing RED/GREEN SHAs and exact CI run IDs;
- [ ] run final exact-head CI;
- [ ] confirm PR #30 head equals final seal SHA;
- [ ] freeze E6 and only then branch E7.
