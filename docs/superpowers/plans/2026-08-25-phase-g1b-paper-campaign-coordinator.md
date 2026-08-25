# Phase G1B Paper Campaign Coordinator — Verification Record

**Goal:** Prove one restart-safe multi-token observer-backed PAPER campaign coordinator that assembles multiple token opportunities at one point-in-time timestamp, preserves all required open-position monitoring, ranks entry opportunities with the sealed B7 score, invokes C5 exactly once, and commits E11/C6 evidence exactly once without adding live-money authority.

**Base:** sealed G1 `945c66d3ea725a0aebd8ba86bb71ad8c4f3e0463`.

**Design:** `docs/superpowers/specs/2026-08-25-phase-g1b-paper-campaign-coordinator-design.md`.

## Completed contract

G1B adds `shreks_brain.observer_campaign.coordinator` as a PAPER-only orchestration layer over already-sealed observer, strategy, scoring, decision, risk, execution, accounting, checkpoint, and evaluation components.

It:

- selects recent observer token candidates from SQLite in read-only/query-only mode using explicit caller-supplied lookback and candidate-count bounds;
- never creates or migrates a missing observer database;
- always includes managed OPEN-position mints and a pending-entry mint even when they fall outside recent-entry selection bounds;
- rejects ambiguous or contradictory mint-to-observer-candidate identity instead of guessing;
- reconstructs every selected token against the same restored `PaperLoopState` and the same `as_of_unix_ms`;
- derives only candidate-specific quote attribution (`candidate_id` and token output mint) while preserving all caller-supplied sealed policy/economic values;
- reuses sealed E15 assembly rather than adding a parallel evidence reconstruction path;
- reconstructs Fresh Launch setup assessment and sealed B7 score for deterministic entry ordering;
- ranks score-complete opportunities by descending sealed total score, then observer candidate ID and mint, without inventing a new threshold;
- leaves incomplete/research-only scores behind complete scores rather than manufacturing evidence;
- merges unique entry candidates, all required exit observations, and purpose-correct paper quotes into exactly one `PaperCycleInput` per timestamp;
- invokes sealed C5 `run_paper_cycle` exactly once per aggregate timestamp, preserving C5's one-new-BUY-slot rule;
- preserves sealed C1 latency semantics, including deferred BUY behavior when the selected quote predates the eligible execution timeline;
- writes E11 evidence before C6 checkpointing so interrupted checkpoint commits remain safely retryable under E11 semantic idempotency;
- writes exactly one monotonic C6 checkpoint sequence per completed aggregate cycle;
- reloads the saved checkpoint and requires restart equivalence and non-invalid accounting before returning success;
- treats exact completed-timestamp replay as idempotent without duplicating evidence or checkpoints;
- fails closed on time reversal, E11 corruption/attribution conflict, checkpoint collision/reload mismatch, restart mismatch, invalid accounting, malformed selection data, unsafe assembly, or contradictory aggregate evidence;
- carries one immutable `RegistryCandidate` only as paper-run strategy/model attribution and never instantiates or mutates `RegistryStore`;
- exposes only authority-limited coordinator models, aggregate assembly, and the PAPER runner at the package surface;
- deliberately keeps the runtime-local `ObserverCampaignCandidateStore` internal;
- preserves the existing E15 single-candidate runner/public API behavior;
- imports no promotion, live-execution, transaction, signer, submission, wallet-authority, or provider-credential capability.

## TDD evidence

### Task 1 — read-only campaign candidate selection

- RED `8d843741c8f9bae02a5a71d1d91f3e6fa109dec2` / CI `32892648210`: Python failed during collection because `shreks_brain.observer_campaign.coordinator` did not exist; repository safety was green.
- Initial implementation `f0c4d543cdbfee749829b2a73a8d1b41cd9b12b7` exposed one API-boundary mismatch: invalid `as_of_unix_ms` leaked raw `ValueError`; Python reported 1 failure with 2,230 passes.
- GREEN `26cc85ad55ab75811f36935f97d3fd16d14aa0a0` / CI `32892916997`: validation errors normalized to the coordinator fail-closed domain error; Python, Rust/workspace, and repository safety all green.

### Task 2 — multi-candidate aggregate assembly and sealed-score ordering

- RED `ee136e72b6a4fb9ea3a088f9c918b535ba7ce4dd` / CI `32893369056`: Python failed during collection only because the aggregate audit/assembly API did not yet exist; repository safety was green.
- GREEN `a6cca8aacd174abdd46529783eeace8a5923367a` / CI `32893620128`: aggregate same-timestamp assembly, deterministic sealed-score ordering, quote/exit merging, and versioned audit fingerprinting all green; Python reported 2,233 passes.

### Task 3 — restart-safe aggregate coordinator runner

- RED `b01b4902192144683916d910887db0d85b0ebf35` / CI `32894625224`: Python failed during collection only because `ObserverPaperCampaignCoordinatorRunner` did not exist; repository safety was green.
- Initial implementation `975ea86fb643d30698292421c995ecf34328f341` / CI `32894888909` reached behavior and exposed one incorrect test assumption: Python reported 1 failure with 2,237 passes because sealed C1 correctly deferred the higher-scored token's BUY when its fixture quote predated the eligible execution timeline. Production behavior was not weakened or changed to force a fill.
- Test correction `91420988ebd8ec16fdd7a111f32e7dfe492e77d7` / CI `32895036385`: the test now asserts the sealed deferred-execution result, pending-entry state, E11 entry provenance, and absence of terminal execution evidence. Python reported 2,238 passes; Rust/workspace and repository safety were green.

### Task 4 — restricted public API and authority firewall

- RED `18e53669b9963320b71aee869d875dbfd87f9887` / CI `32895308262`: Python reported exactly 2 intended failures with 2,237 passes—the seven coordinator exports were absent and the coordinator runner was not available through the package surface; repository safety was green.
- GREEN / frozen behavior `4d242aeda6e72de447472cd43cbe79803b32553d` / CI `32895397909`: export-only package change; Python reported **2,239 passed in 13.83s**, Rust/workspace green, repository safety green.

## Restricted public coordinator API added

The existing E15 package exports are preserved and G1B adds exactly:

```text
OBSERVER_PAPER_CAMPAIGN_CYCLE_AUDIT_SCHEMA_VERSION
ObserverCampaignCoordinatorError
ObserverPaperCampaignSelectionPolicy
ObserverCampaignCandidate
ObserverPaperCampaignCycleAudit
assemble_observer_paper_campaign_cycle
ObserverPaperCampaignCoordinatorRunner
```

`ObserverCampaignCandidateStore` remains internal.

Both `ObserverPaperCampaignRunner` and `ObserverPaperCampaignCoordinatorRunner` expose only:

```text
load_state
run_cycle
evaluated_trades
```

The package authority firewall rejects promotion/live/execution imports and permits only the immutable `RegistryCandidate` model from `shreks_brain.registry`.

## Frozen behavior verification

Frozen behavior SHA:

`4d242aeda6e72de447472cd43cbe79803b32553d`

Full behavior CI:

`32895397909`

Verified results:

- Python: **2,239 passed in 13.83s**;
- Rust tests: GREEN;
- Rust workspace metadata: GREEN;
- repository secret-assignment safety: GREEN.

## Scope audit before seal

The exact sealed-G1 -> frozen-G1B comparison is:

- base `945c66d3ea725a0aebd8ba86bb71ad8c4f3e0463`;
- head `4d242aeda6e72de447472cd43cbe79803b32553d`;
- 12 commits ahead;
- 0 commits behind;
- exactly 8 changed files.

Changed files:

```text
docs/superpowers/plans/2026-08-25-phase-g1b-paper-campaign-coordinator.md
docs/superpowers/specs/2026-08-25-phase-g1b-paper-campaign-coordinator-design.md
python/src/shreks_brain/observer_campaign/__init__.py
python/src/shreks_brain/observer_campaign/coordinator.py
python/tests/test_observer_campaign_coordinator_assembly.py
python/tests/test_observer_campaign_coordinator_runner.py
python/tests/test_observer_campaign_coordinator_selection.py
python/tests/test_observer_campaign_public_api.py
```

File-by-file audit confirms:

- no Rust implementation changed;
- no provider collection/RPC code changed;
- no observer storage schema/write path changed;
- no E15 assembler/runner/store implementation changed;
- no B-layer setup/scoring/decision/risk implementation changed;
- no C1 execution math changed;
- no C3 accounting math changed;
- no C4 exit logic changed;
- no C6 checkpoint implementation changed;
- no E11 evaluation-store implementation changed;
- no registry store/promotion implementation changed;
- no live execution, transaction construction, signer, submission, or wallet-authority implementation changed;
- the only production implementation added is the G1B coordinator plus its restricted package exports.

## Profitability and live-money status

G1B proves orchestration mechanics, restart/evidence integrity, deterministic candidate ordering, and authority isolation. Synthetic/static fixtures do **not** prove profitability.

The next proof path remains a real independent paper campaign using actual point-in-time observer data, followed by E10/E11/E12 evaluation for expectancy after realistic costs, profit factor, drawdown, independent trade/mint/time coverage, cost burden, winner concentration, and reproducibility.

**LIVE TRADING REMAINS DISABLED.**

## Final seal protocol

This tracked record intentionally does not contain its own self-referential final seal commit SHA or exact-seal CI run ID. After this record is committed, the branch is frozen. The seal is valid only if:

1. frozen behavior -> seal is exactly one commit ahead and zero behind;
2. the only changed file is this verification record;
3. a fresh full CI run on the exact seal SHA is GREEN;
4. PR #41 records the immutable behavior SHA, seal SHA, CI IDs, scope audit, and live-disabled status.
