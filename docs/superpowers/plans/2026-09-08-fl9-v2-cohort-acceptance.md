# FL9 V2 Cohort Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, read-only FL9 V2 cohort-acceptance artifact that freezes the exact immutable sessions 115–122 eligible identity population, split, novelty subsets, assessment evidence, and fingerprints before any labels, model training, metrics, or PnL can be read.

**Architecture:** Add a sibling package `shreks_brain.fl9_v2_cohort_acceptance` with four explicit layers: immutable policy/models, a read-only source/builder layer, canonical artifact read/write, and a small CLI. The builder owns only input-side evidence and depends on the sealed FL9 tradable-universe reader plus V2 feature-firewall authentication; artifact creation refuses drift/overwrite and the later first-champion path is intentionally not modified in this slice.

**Tech Stack:** Python 3.12, frozen/slotted dataclasses, sqlite3 read-only URI + `PRAGMA query_only = ON`, canonical JSON/JSONL, hashlib SHA-256, existing `Fl9TradableUniverseStore`, existing V2 feature firewall, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-fl9-v2-cohort-acceptance-design.md`

## Global Constraints

- Schema: `shreks.fl9_v2_cohort_acceptance`, version `1`.
- Acceptance policy: `fl9-v2-cohort-acceptance-v1`.
- Structural floor policy: `fl9-v2-cohort-evidence-floor-v1`.
- Exact source sessions: `115,116,117,118,119,120,121,122`.
- Required later immutable boundary: latest session ID `>= 123`.
- Cohort lower bound: `1788878323281`.
- Forecast horizon: `30_000` ms.
- TEST end exclusive: `1788902289835`.
- Frozen selection timestamp: `1788902319835`.
- Training cut: `1788892302791`.
- Validation cut: `1788898931418`.
- FL9 policy version/fingerprint: `fl9-tradable-universe-v1` / `abfc6d21eb27d722956fbd267a10f352c887a909b3865a7a295eff95631777e4`.
- V2 feature firewall version/fingerprint: `fl8.3-feature-identity-firewall-v1` / `e9f1eb72cf3720dbdda523718f3faf61c70a77b1814841b41af651d2cdebcbc0`.
- Exact raw checkpoint: 504,716 rows, 0 cross-session duplicates, 394 raw unique mints.
- Exact eligible checkpoint: 274,334 rows, 146 unique mints.
- Exact ineligible checkpoint counts: 176,299 missing fresh exact snapshot, 52,974 below minimum liquidity, 1,109 below minimum h24 volume.
- Exact raw partitions: 164,645 / 54,858 / 54,831.
- Exact shared signatures and quarantine: 0 / 0 / 0 / 0.
- Exact validation novelty: 49,754 unseen rows / 24 unseen mints / 5,104 seen rows / 10 seen mints.
- Exact TEST novelty: 54,828 unseen rows / 31 unseen mints / 3 seen rows / 3 seen mints.
- Structural floors: total eligible >=250,000; training >=150,000; validation >=50,000; TEST >=50,000; unseen-validation rows >=40,000; unseen-validation mints >=20; unseen-TEST rows >=40,000; unseen-TEST mints >=25.
- Later target floors are recorded in the manifest policy only: natural TEST scored >=40,000 and unseen-mint TEST scored >=35,000. This package must not read targets to enforce them.
- No hard mint-concentration admission threshold.
- No mint/actor balancing or row reweighting.
- Repeated mint/actor identity never deletes rows.
- Cross-partition transaction signatures are the only entity-overlap quarantine rule.
- Novelty is relative to **raw training**.
- No `FastTrainingBundle`, FL4 label reader/builder, FL8.2 trainer/inference, V1/V2 model-running engine, evaluation, economics, champion, promotion, PAPER executor, signing/submission, or LIVE imports.
- Existing V1 first-champion request/plan/builder/host bytes and behavior remain unchanged.
- Artifact output is immutable and refuses overwrite.
- No generated-at time or current wall clock enters canonical artifact bytes.
- This slice stops after cohort artifact production support; no target inspection/training follows automatically.

---

## File Structure

Create:

- `python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py` — exact public API only.
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/models.py` — frozen constants, policies, session/checkpoint models, accepted/quarantined decision records, manifest, artifact.
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/source.py` — exact read-only SQLite session/FastEvent source and injectable source protocol.
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/builder.py` — authenticated eligibility, exact checkpoint validation, deterministic split, signature quarantine, novelty, concentration, logical fingerprints.
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/artifact.py` — canonical JSON/JSONL encoding, write/read verification, immutable directory creation.
- `python/src/shreks_brain/fl9_v2_cohort_acceptance/cli.py` — minimal host CLI.
- `python/tests/fl9_v2_cohort_acceptance_fixtures.py`
- `python/tests/test_fl9_v2_cohort_acceptance_models.py`
- `python/tests/test_fl9_v2_cohort_acceptance_source.py`
- `python/tests/test_fl9_v2_cohort_acceptance_builder.py`
- `python/tests/test_fl9_v2_cohort_acceptance_artifact.py`
- `python/tests/test_fl9_v2_cohort_acceptance_cli.py`
- `python/tests/test_fl9_v2_cohort_acceptance_authority.py`

Modify:

- `python/pyproject.toml` — add only `shreks-fl9-v2-cohort-acceptance = "shreks_brain.fl9_v2_cohort_acceptance.cli:main"`.

Do not modify:

- `python/src/shreks_brain/fast_first_champion_plan.py`
- `python/src/shreks_brain/fast_first_champion/**`
- `python/src/shreks_brain/fast_first_champion_host_run.py`
- `python/src/shreks_brain/fast_validation/**`
- `python/src/shreks_brain/fast_validation_v2/engine.py`
- collector, execution, risk, PAPER, signing, submission, or LIVE code.

---

### Task 1: Define exact immutable cohort-acceptance contracts

**Files:**
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/models.py`
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py`
- Test: `python/tests/test_fl9_v2_cohort_acceptance_models.py`

**Interfaces:**
- Produces:
  - `FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME = "shreks.fl9_v2_cohort_acceptance"`
  - `FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION = 1`
  - `FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION = "fl9-v2-cohort-acceptance-v1"`
  - `FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION = "fl9-v2-cohort-evidence-floor-v1"`
  - `Fl9V2CoverageSessionCheckpoint`
  - `Fl9V2CohortEvidenceFloorPolicy`
  - `Fl9V2CohortAcceptancePolicy`
  - `Fl9V2ConcentrationSummary`
  - `Fl9V2AcceptedDecision`
  - `Fl9V2QuarantinedDecision`
  - `Fl9V2CohortAcceptanceManifest`
  - `Fl9V2CohortAcceptanceArtifact`

- [ ] **Step 1: Write RED model tests**

Tests must assert exact frozen constants and reject any policy drift:

```python
from dataclasses import FrozenInstanceError, replace

import pytest

from shreks_brain.fl9_v2_cohort_acceptance import (
    FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME,
    FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION,
    FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION,
    Fl9V2CohortAcceptancePolicy,
    Fl9V2CohortEvidenceFloorPolicy,
)


def test_frozen_versions_and_numeric_contract_are_exact() -> None:
    floors = Fl9V2CohortEvidenceFloorPolicy()
    policy = Fl9V2CohortAcceptancePolicy()

    assert FL9_V2_COHORT_ACCEPTANCE_SCHEMA_NAME == (
        "shreks.fl9_v2_cohort_acceptance"
    )
    assert FL9_V2_COHORT_ACCEPTANCE_SCHEMA_VERSION == 1
    assert FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION == (
        "fl9-v2-cohort-acceptance-v1"
    )
    assert FL9_V2_COHORT_EVIDENCE_FLOOR_VERSION == (
        "fl9-v2-cohort-evidence-floor-v1"
    )
    assert policy.source_session_ids == tuple(range(115, 123))
    assert policy.horizon_ms == 30_000
    assert policy.test_end_unix_ms == 1_788_902_289_835
    assert policy.selection_at_unix_ms == 1_788_902_319_835
    assert policy.training_cut_unix_ms == 1_788_892_302_791
    assert policy.validation_cut_unix_ms == 1_788_898_931_418
    assert floors.minimum_total_eligible_rows == 250_000
    assert floors.minimum_unseen_mint_test_unique_mints == 25

    with pytest.raises(FrozenInstanceError):
        policy.horizon_ms = 60_000  # type: ignore[misc]

    with pytest.raises(ValueError, match="immutable|version|frozen"):
        replace(policy, horizon_ms=60_000)
```

Also test:
- exact eight session metadata rows;
- exact raw/eligible/reason/partition/novelty checkpoint values;
- selection minus horizon equals TEST end;
- all structural floors positive;
- later target floors are 40,000/35,000 and explicitly represented as downstream-only policy data;
- SHA fields require lowercase 64-hex;
- accepted decision identity uses exact seven-field shape;
- partition enum/strings limited to `training|validation|test`;
- novelty values limited to `seen|unseen|not_applicable` for mint and `seen|unseen|null|not_applicable` for actor;
- manifest count/fingerprint reconciliation fails closed.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_models.py -q
```

Expected: import/collection failure because package does not exist.

- [ ] **Step 3: Implement frozen models**

Use dataclasses with exact values embedded in default constructors. Do not make the checkpoint caller-configurable in V1.

Core policy shape:

```python
@dataclass(frozen=True, slots=True)
class Fl9V2CohortAcceptancePolicy:
    version: str = FL9_V2_COHORT_ACCEPTANCE_POLICY_VERSION
    source_session_ids: tuple[int, ...] = tuple(range(115, 123))
    required_latest_session_id: int = 123
    minimum_decision_observed_at_unix_ms: int = 1_788_878_323_281
    horizon_ms: int = 30_000
    test_end_unix_ms: int = 1_788_902_289_835
    selection_at_unix_ms: int = 1_788_902_319_835
    training_cut_unix_ms: int = 1_788_892_302_791
    validation_cut_unix_ms: int = 1_788_898_931_418
    expected_raw_row_count: int = 504_716
    expected_cross_session_duplicate_count: int = 0
    expected_raw_unique_mint_count: int = 394
    expected_eligible_row_count: int = 274_334
    expected_eligible_unique_mint_count: int = 146
    expected_training_raw_row_count: int = 164_645
    expected_validation_raw_row_count: int = 54_858
    expected_test_raw_row_count: int = 54_831
    expected_shared_signature_count: int = 0
    expected_validation_unseen_mint_rows: int = 49_754
    expected_validation_unseen_mint_unique_mints: int = 24
    expected_test_unseen_mint_rows: int = 54_828
    expected_test_unseen_mint_unique_mints: int = 31
```

Include exact expected eligibility reason counts as an immutable tuple of `(reason, count)`.

- [ ] **Step 4: Run GREEN + V2 regression**

```bash
python -m pytest   python/tests/test_fl9_v2_cohort_acceptance_models.py   python/tests/test_fast_chronological_v2_models.py   python/tests/test_fl9_tradable_universe.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py   python/src/shreks_brain/fl9_v2_cohort_acceptance/models.py   python/tests/test_fl9_v2_cohort_acceptance_models.py
git commit -m "feat(fl9): define v2 cohort acceptance contracts"
```

---

### Task 2: Add exact read-only source extraction with session-gap preservation

**Files:**
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/source.py`
- Create: `python/tests/fl9_v2_cohort_acceptance_fixtures.py`
- Create: `python/tests/test_fl9_v2_cohort_acceptance_source.py`

**Interfaces:**
- Produces:
  - `Fl9V2SourceDecision`
  - `Fl9V2SourceSnapshot`
  - `Fl9V2CohortSource` protocol
  - `SqliteFl9V2CohortSource(database_path)`
  - `load_source_snapshot(policy) -> Fl9V2SourceSnapshot`

- [ ] **Step 1: Build a focused SQLite fixture schema**

The test fixture creates only tables the source layer owns:

```sql
CREATE TABLE fast_realtime_coverage_sessions (
    session_id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    process_session_sequence INTEGER NOT NULL,
    first_notification_observed_at_unix_ms INTEGER NOT NULL,
    last_notification_observed_at_unix_ms INTEGER NOT NULL,
    notification_count INTEGER NOT NULL
);

CREATE TABLE fast_events (
    sequence INTEGER PRIMARY KEY,
    signature TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    provider TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL,
    mint TEXT NOT NULL,
    quote_mint TEXT NOT NULL,
    venue TEXT NOT NULL,
    actor TEXT
);
```

The source fixture must include:
- all eight required sessions;
- session 123 to prove immutability;
- one event inside a deliberate gap that must never be selected;
- one identical duplicate across overlapping fixture windows;
- one contradictory duplicate variant for failure tests.

- [ ] **Step 2: Write RED source tests**

Required tests:

```python
def test_source_reads_union_of_exact_session_windows_not_broad_timestamp_range(tmp_path):
    db = source_database(tmp_path)
    snapshot = SqliteFl9V2CohortSource(db).load_source_snapshot(
        Fl9V2CohortAcceptancePolicy()
    )

    assert "gap-signature" not in {
        row.signature for row in snapshot.raw_decisions
    }


def test_source_requires_session_122_to_be_immutable(tmp_path):
    db = source_database(tmp_path, include_session_123=False)
    with pytest.raises(ValueError, match="immutable|latest session"):
        SqliteFl9V2CohortSource(db).load_source_snapshot(
            Fl9V2CohortAcceptancePolicy()
        )


def test_identical_cross_window_duplicate_deduplicates_but_contradiction_fails(tmp_path):
    ...
```

Also test:
- session metadata drift in provider/process sequence/first/last/notification count fails;
- missing session fails;
- current session 124 instead of 123 still succeeds and yields identical semantic snapshot;
- non-PumpSwap events excluded;
- actor null retained;
- row order is canonical regardless SQLite insertion order;
- database is opened in `mode=ro` and query-only behavior prevents writes.

- [ ] **Step 3: Run RED**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_source.py -q
```

Expected: missing source module.

- [ ] **Step 4: Implement read-only source**

`SqliteFl9V2CohortSource` must:
1. resolve an existing regular DB path;
2. open via `file://...?mode=ro`;
3. set row factory;
4. execute `PRAGMA query_only = ON`;
5. load `MAX(session_id)`;
6. validate the eight exact session rows;
7. query PumpSwap decisions separately for each exact session window;
8. canonicalize on `(signature, ordinal)`;
9. deduplicate only identical rows;
10. count cross-session duplicates;
11. sort by `(observed_at, sequence, signature, ordinal)`.

Do not import `Fl9TradableUniverseStore` in this module. Source extraction and eligibility are separate review units.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_source.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/source.py   python/tests/fl9_v2_cohort_acceptance_fixtures.py   python/tests/test_fl9_v2_cohort_acceptance_source.py
git commit -m "feat(fl9): read immutable v2 cohort source"
```

---

### Task 3: Build authenticated eligibility, split, quarantine, novelty, and fingerprints

**Files:**
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/builder.py`
- Create: `python/tests/test_fl9_v2_cohort_acceptance_builder.py`

**Interfaces:**
- Consumes:
  - `Fl9V2CohortSource`
  - `Fl9TradableUniverseStore`
  - `Fl9TradableUniversePolicy`
  - V2 firewall functions/constants
  - `Fl9V2CohortAcceptancePolicy`
- Produces:
  - `build_fl9_v2_cohort_acceptance(*, source, tradable_store, policy, floor_policy) -> Fl9V2CohortAcceptanceArtifact` as an in-memory semantic artifact with `path=None`/separate semantic result if necessary; no filesystem writes in builder.

Use dependency injection: tests pass a fake source and fake assessment function/store, production passes the real SQLite source and sealed `Fl9TradableUniverseStore`. The production builder must still type-check exact sealed policy objects/fingerprints.

- [ ] **Step 1: Write RED authenticated eligibility tests**

Prove the builder calls the assessor for each raw row rather than reimplementing thresholds:

```python
class RecordingStore:
    def __init__(self, assessments):
        self.calls = []
        self.assessments = assessments

    def assess(self, **kwargs):
        self.calls.append(kwargs)
        return self.assessments[len(self.calls) - 1]


def test_builder_uses_authenticated_tradable_universe_assessor_for_every_row():
    ...
    result = build_fl9_v2_cohort_acceptance(...)
    assert len(store.calls) == len(source.raw_decisions)
```

Add test that wrong FL9 policy fingerprint fails before population acceptance.

- [ ] **Step 2: Write RED exact checkpoint and structural floor tests**

Tests must prove:
- raw count drift fails;
- raw unique mint drift fails;
- duplicate count drift fails;
- eligibility reason count drift fails;
- eligible count/mint drift fails;
- any of the eight structural floors fails closed;
- no alternate split is searched after a frozen-cut/checkpoint mismatch.

Use a compact injected source/assessment fixture plus a test-only policy created with the same model shape but fixture checkpoint values only if the implementation exposes a private/internal constructor. The **public production policy remains immutable** and exact. Prefer private helper policy factory under tests rather than weakening production constructors.

- [ ] **Step 3: Write RED deterministic split/signature/novelty tests**

Required behavior:

```python
def test_repeated_mint_and_actor_survive_but_shared_signature_is_quarantined():
    result = build_fixture_acceptance(...)
    assert repeated_mint_identity in result.accepted_identities
    assert repeated_actor_identity in result.accepted_identities
    assert shared_signature_identity not in result.accepted_identities


def test_validation_first_mint_stays_unseen_in_test_relative_to_raw_training():
    ...
```

Also assert:
- equal timestamps never straddle cuts;
- raw training is the novelty reference even if signature quarantine removes a training row;
- actor null/seen/unseen counts reconcile;
- exact subset logical fingerprints are input-order invariant;
- assessment fingerprints change if any admitted snapshot/migration/quality evidence changes;
- concentration diagnostics are present but cannot reject a population.

- [ ] **Step 4: Implement assessment fingerprinting**

Canonical per-decision assessment material:

```python
{
    "decision_identity": list(decision.identity),
    "tradable_universe_policy_version": assessment.policy_version,
    "tradable_universe_policy_fingerprint_sha256": (
        assessment.policy_fingerprint_sha256
    ),
    "graduation_detected_at_unix_ms": (
        assessment.graduation_detected_at_unix_ms
    ),
    "candidate_id": assessment.candidate_id,
    "snapshot_row_id": assessment.snapshot_row_id,
    "snapshot_observed_at_unix_ms": (
        assessment.snapshot_observed_at_unix_ms
    ),
    "snapshot_age_ms": assessment.snapshot_age_ms,
    "selected_pair_address": assessment.selected_pair_address,
    "liquidity_usd": _float_hex_or_none(assessment.liquidity_usd),
    "volume_h24_usd": _float_hex_or_none(assessment.volume_h24_usd),
    "reason": assessment.reason,
    "eligible": assessment.eligible,
}
```

Use exact float hex tags, not decimal JSON floats, for fingerprint material.

- [ ] **Step 5: Implement exact 60/20/20 frozen-cut verification**

The builder must recompute the sealed closest-to-60% / closest-to-80% equal-timestamp boundaries and then require they equal:

`1788892302791` and `1788898931418`.

It must not simply trust hard-coded cuts without recomputation.

- [ ] **Step 6: Implement signature-only quarantine and novelty**

Shared signature definition: signature present in >1 raw partition.

Every row carrying a shared signature is removed from all affected partitions.

Mint/actor recurrence is never a deletion criterion.

Training mints/actors for novelty are calculated from **raw training before signature quarantine**.

- [ ] **Step 7: Implement concentration diagnostics and structural floors**

Record row count, unique mints, top-1/3/5/10, HHI, effective mint count for every required population.

The floor evaluator is exact and has only the eight approved floor checks. No top-share/HHI admission threshold exists.

- [ ] **Step 8: Run GREEN**

```bash
python -m pytest   python/tests/test_fl9_v2_cohort_acceptance_builder.py   python/tests/test_fl9_v2_cohort_acceptance_source.py   python/tests/test_fl9_tradable_universe.py   python/tests/test_fast_chronological_v2_firewall.py   python/tests/test_fast_chronological_v2_population.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/builder.py   python/tests/test_fl9_v2_cohort_acceptance_builder.py
git commit -m "feat(fl9): build authenticated v2 cohort acceptance"
```

---

### Task 4: Add canonical immutable artifact write/read

**Files:**
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/artifact.py`
- Create: `python/tests/test_fl9_v2_cohort_acceptance_artifact.py`

**Interfaces:**
- Produces:
  - `write_fl9_v2_cohort_acceptance(semantic, destination) -> Fl9V2CohortAcceptanceArtifact`
  - `read_fl9_v2_cohort_acceptance(path) -> Fl9V2CohortAcceptanceArtifact`
  - exact root files `manifest.json`, `accepted-decisions.jsonl`, `signature-quarantine.jsonl`.

- [ ] **Step 1: Write RED codec/immutability tests**

Tests must prove:
- exact three root entries only;
- canonical sorted-key JSON with one trailing newline;
- canonical JSONL one object per line;
- raw JSON floats rejected; float fields use exact tagged hex strings;
- duplicate keys rejected;
- malformed/unknown/missing fields rejected;
- destination overwrite refused;
- symlink root/member rejected;
- file SHA mismatch rejected;
- logical subset fingerprint mismatch rejected;
- artifact fingerprint mismatch rejected;
- reading then re-writing semantic data produces byte-identical files;
- source/input ordering does not change bytes;
- wall clock monkeypatch does not change bytes.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_artifact.py -q
```

Expected: missing artifact module.

- [ ] **Step 3: Implement canonical serializers**

Use the same defensive conventions as `fast_proof_workspace.py`:
- reject duplicate JSON keys;
- exactly one trailing newline;
- `allow_nan=False`;
- stable SHA256 file reads;
- no symlinks;
- temporary sibling directory;
- chmod 0700 for staging/root and 0600 for files;
- round-trip verification before atomic rename;
- delete staging on failure.

Accepted JSONL line material:

```python
{
    "decision_identity": [...],
    "partition": "training|validation|test",
    "assessment_fingerprint_sha256": "...",
    "mint_novelty": "seen|unseen|not_applicable",
    "actor_novelty": "seen|unseen|null|not_applicable",
}
```

No raw actor address is written. The decision identity necessarily contains mint/signature because the artifact is an identity authority, but actor identity remains absent.

- [ ] **Step 4: Manifest fingerprint verification**

Compute:
1. accepted JSONL file SHA;
2. quarantine JSONL file SHA;
3. logical fingerprints for every required subset;
4. manifest semantic material;
5. final artifact fingerprint over semantic manifest material + exact file hashes.

Reader recomputes every layer.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_artifact.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/artifact.py   python/tests/test_fl9_v2_cohort_acceptance_artifact.py
git commit -m "feat(fl9): persist immutable v2 cohort artifact"
```

---

### Task 5: Add production CLI without expanding authority

**Files:**
- Create: `python/src/shreks_brain/fl9_v2_cohort_acceptance/cli.py`
- Create: `python/tests/test_fl9_v2_cohort_acceptance_cli.py`
- Modify: `python/pyproject.toml`

**Interfaces:**
- CLI: `shreks-fl9-v2-cohort-acceptance --database PATH --destination PATH`.
- No policy/floor/horizon/session override flags in V1. Those values are frozen in the policy and cannot be operator-tuned.

- [ ] **Step 1: Write RED CLI tests**

```python
def test_cli_has_only_database_and_destination_inputs(monkeypatch, tmp_path):
    ...
    assert main([
        "--database", str(db),
        "--destination", str(out),
    ]) == 0


def test_cli_rejects_policy_override_flags():
    with pytest.raises(SystemExit):
        main(["--horizon-ms", "60000", ...])
```

Also test:
- prints one canonical JSON manifest document to stdout on success;
- refuses existing destination;
- non-existent DB fails;
- no current time is read;
- entrypoint exists in installed-script mapping.

- [ ] **Step 2: Run RED**

```bash
python -m pytest python/tests/test_fl9_v2_cohort_acceptance_cli.py -q
```

Expected: missing CLI/entrypoint.

- [ ] **Step 3: Implement CLI**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-fl9-v2-cohort-acceptance"
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)

    policy = Fl9V2CohortAcceptancePolicy()
    floors = Fl9V2CohortEvidenceFloorPolicy()
    source = SqliteFl9V2CohortSource(args.database)
    store = Fl9TradableUniverseStore(args.database)
    semantic = build_fl9_v2_cohort_acceptance(
        source=source,
        tradable_store=store,
        policy=policy,
        floor_policy=floors,
    )
    artifact = write_fl9_v2_cohort_acceptance(
        semantic,
        args.destination,
    )
    print(encode_manifest_for_stdout(artifact.manifest), end="")
    return 0
```

No release-SHA override belongs in the builder CLI: physical release identity is verified by the deployment/preflight layer, while the artifact itself authenticates the exact policy/firewall semantics.

- [ ] **Step 4: Add console script**

Add exactly:

```toml
shreks-fl9-v2-cohort-acceptance = "shreks_brain.fl9_v2_cohort_acceptance.cli:main"
```

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest   python/tests/test_fl9_v2_cohort_acceptance_cli.py   python/tests/test_fl9_v2_cohort_acceptance_artifact.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/cli.py   python/tests/test_fl9_v2_cohort_acceptance_cli.py   python/pyproject.toml
git commit -m "feat(fl9): add v2 cohort acceptance CLI"
```

---

### Task 6: Seal authority boundary and production checkpoint contract

**Files:**
- Create: `python/tests/test_fl9_v2_cohort_acceptance_authority.py`
- Modify only if needed for public exports: `python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py`

**Interfaces:**
- Exact public API:
  - policy/schema constants;
  - policy/model dataclasses needed downstream;
  - `SqliteFl9V2CohortSource`;
  - `build_fl9_v2_cohort_acceptance`;
  - `write_fl9_v2_cohort_acceptance`;
  - `read_fl9_v2_cohort_acceptance`.
- CLI stays available through console entrypoint but need not be re-exported from package root.

- [ ] **Step 1: Write exact public API test**

Assert `__all__` exactly; do not accidentally expose private helpers.

- [ ] **Step 2: Write source authority test**

Inspect all package source and reject these tokens/imports:

```python
FORBIDDEN = (
    "fast_training_bundle",
    "future_path",
    "FastTrainingBundle",
    "train_fast_forecast",
    "predict_fast_forecast",
    "fast_validation_v2.engine",
    "fast_evaluation",
    "training_economics",
    "fast_first_champion",
    "promotion",
    "registry",
    "paper_executor",
    "TradeIntent",
    "RuntimeMode.LIVE",
    "sign_transaction",
    "submit_transaction",
    "requests.",
    "httpx",
)
```

Allow `fl9_tradable_universe`, `fast_validation_v2.firewall`, sqlite3, hashlib/json/pathlib only as needed.

- [ ] **Step 3: Add subprocess import proof**

Importing `shreks_brain.fl9_v2_cohort_acceptance` must not eagerly import sklearn, pyarrow, trainer/evaluation modules, or first-champion modules.

- [ ] **Step 4: Add frozen production-checkpoint test**

Use a compact synthetic/injected fixture that encodes the exact production checkpoint metadata/count constants and asserts the public production policy carries those exact values.

Do **not** generate 504,716 SQLite rows merely to restate constants. The builder logic is already tested on smaller fixtures; the production checkpoint test must verify that the frozen public policy and its manifest material encode the 115–122 evidence exactly.

- [ ] **Step 5: Run focused full slice**

```bash
python -m pytest   python/tests/test_fl9_v2_cohort_acceptance_models.py   python/tests/test_fl9_v2_cohort_acceptance_source.py   python/tests/test_fl9_v2_cohort_acceptance_builder.py   python/tests/test_fl9_v2_cohort_acceptance_artifact.py   python/tests/test_fl9_v2_cohort_acceptance_cli.py   python/tests/test_fl9_v2_cohort_acceptance_authority.py -q
```

Expected: PASS.

- [ ] **Step 6: Run V1/V2 upstream regressions**

```bash
python -m pytest   python/tests/test_fl9_tradable_universe.py   python/tests/test_fast_chronological_v2_models.py   python/tests/test_fast_chronological_v2_firewall.py   python/tests/test_fast_chronological_v2_population.py   python/tests/test_fast_chronological_v2_engine.py   python/tests/test_fast_first_champion_plan.py   python/tests/test_fast_first_champion_host_request_writer.py -q
```

Expected: PASS, with V1 first-champion behavior unchanged.

- [ ] **Step 7: Commit**

```bash
git add   python/src/shreks_brain/fl9_v2_cohort_acceptance/__init__.py   python/tests/test_fl9_v2_cohort_acceptance_authority.py
git commit -m "test(fl9): seal v2 cohort acceptance authority"
```

---

### Task 7: Candidate verification, merge, seal, deploy, and physical artifact generation

**Files:**
- No production code changes unless verification identifies a defect.
- Add a docs/evidence seal only after the physical artifact is generated and verified.

- [ ] **Step 1: Full Python suite**

```bash
python -m pytest python/tests -q
```

Expected: PASS.

- [ ] **Step 2: Repository safety**

Run the repository's exact secret-assignment safety check.

Expected: PASS.

- [ ] **Step 3: Rust workspace regression**

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 4: Scope audit**

```bash
git diff --name-only main...HEAD
```

Expected only:
- approved design/plan docs;
- new `fl9_v2_cohort_acceptance` package/tests;
- one `python/pyproject.toml` console-script addition.

Explicitly reject diffs in:
- first-champion source;
- V1/V2 model-running validator engine;
- collector;
- risk;
- PAPER executor;
- transaction/signing/LIVE paths.

- [ ] **Step 5: Require four GitHub CI gates**

Before merge:
- Repository safety SUCCESS;
- Python tests SUCCESS;
- Rust tests SUCCESS;
- ARM64 release build SUCCESS.

- [ ] **Step 6: Merge exact reviewed head and require merged-main CI**

Guard merge with the exact reviewed SHA; after merge require all four main gates SUCCESS.

- [ ] **Step 7: Create a docs-only `seal:` commit**

The seal records:
- merged implementation SHA;
- exact CI run IDs;
- no-label/no-training authority;
- frozen policy/floor values.

Merge the seal only after its own four PR gates pass.

- [ ] **Step 8: Verify automatic immutable release**

Require release tag:

`shreks-<seal-main-sha>`

and assets:
- `RELEASE_MANIFEST.json`;
- `shreks-release-<sha>.tar.gz`;
- `shreks-release-<sha>.tar.gz.sha256`.

- [ ] **Step 9: Deploy exact sealed release to production-paper**

Use the protected deployment workflow with the exact release tag.

No broader version or `latest` reference.

- [ ] **Step 10: Physically verify runtime identity**

Require:
- `/opt/shreks/current` resolves to exact release;
- manifest source SHA exact;
- observer/evidence/campaign services active;
- zero restarts unless explained;
- process cwd/exe match release;
- post-deploy error journal clean;
- cohort CLI import/entrypoint available.

- [ ] **Step 11: Generate the cohort artifact on VPS**

Use a new destination that does not exist:

```bash
sudo /opt/shreks/current/.venv/bin/shreks-fl9-v2-cohort-acceptance \
  --database /var/lib/shreks/shreks.db \
  --destination /var/lib/shreks/fl9-v2-cohort-acceptance-<seal-sha>
```

This command is the first production artifact-generation authority for this slice. It remains read-only against SQLite.

- [ ] **Step 12: Read back artifact from deployed package**

Run the deployed `read_fl9_v2_cohort_acceptance` against the generated path and print:
- artifact fingerprint;
- accepted row count;
- training/validation/TEST counts;
- unseen validation/TEST counts/mints;
- file SHA values;
- structural floor PASS;
- `target_values_inspected=no`;
- `model_training_performed=no`;
- `LIVE_TRADING=DISABLED`.

- [ ] **Step 13: Seal physical cohort evidence**

Create a docs-only evidence note containing the exact physical artifact fingerprint and immutable release SHA.

Only after this physical seal may the project begin the separate V2 first-champion integration design.

---

## Completion Boundary

This plan is complete only when:

- the input-only cohort package is merged and sealed;
- an immutable release is deployed;
- the exact 115–122 production cohort artifact is physically generated;
- every artifact/file fingerprint round-trips;
- structural floors pass;
- a docs/evidence seal records that artifact fingerprint.

At completion:

```text
cohort_floor_accepted=YES
eligible_identity_fingerprint_created=YES
final_v2_cohort_artifact=CREATED_AND_VERIFIED
target_values_inspected=NO
future_returns_inspected=NO
model_training_performed=NO
model_performance_inspected=NO
pnl_inspected=NO
paper_promotion=BLOCKED
live_trading=DISABLED
```

The next slice is then the separately versioned V2 first-champion integration that consumes this artifact exactly and enforces the already-precommitted 40,000 natural TEST / 35,000 unseen-mint TEST per-target scoring floors.
