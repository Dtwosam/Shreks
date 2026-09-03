# FL8.5 Champion Artifact Design

## Status

Approved for autonomous implementation under the project instruction to continue the Fast Lane build order without repeated approval prompts.

## Source-of-truth alignment

Base: SEALED FL8.4 merged-main `1d74121b2c75f674ac902700610c18ac8d919ab9` with four-gate merged-main CI `33803190407`.

The canonical build order defines FL8.5 as:

> Produce a versioned immutable champion artifact/configuration that can be loaded by the Fast Lane runtime.

The master source of truth additionally requires explicit champion/challenger governance, no self-promotion, point-in-time evidence, deterministic auditability, and LIVE disabled until later promotion/proof gates pass.

FL8.5 is therefore a **packaging and provenance phase**, not a metric-driven promotion phase. It can construct a runtime-loadable forecast champion only from an explicit caller-supplied selection decision plus exact sealed evidence. It does not decide that a model deserves selection.

## Existing evidence reused

FL8.5 reuses rather than recreates:

- FL8.2 `FastForecastBaselineArtifact` as the executable Python reference model artifact;
- FL8.2 canonical artifact fingerprint and pure-Python inference semantics;
- FL8.3 `FastChronologicalValidationRun` as the chronological validation provenance source;
- FL8.4 `FastForecastEvaluationReport` as the selected-partition quality/calibration evidence;
- the legacy E6 governance principle that candidate registration/promotion is explicit and attributable, never inferred automatically from metrics.

The legacy registry remains untouched in FL8.5 because its candidate/evaluation schema is coupled to the older E3/E4/E5 stack. FL8.5 does not silently reinterpret legacy registry evidence as Fast Lane evidence.

## Why the champion is a bundle

The Fast Lane forecasting target is multi-horizon and multi-target. A runtime champion therefore cannot be modeled safely as one arbitrary model file.

FL8.5 packages a coherent set with at most one member for each `(forecast_target, horizon_ms)` pair. Members may use different model families when explicitly selected, but all members must use the same sealed feature schema, source training bundle, and FL4 future-path label version.

This allows the runtime to deterministically request a forecast target/horizon while keeping one immutable top-level champion version.

## Package

Add:

```text
python/src/shreks_brain/fast_champion/
  __init__.py
  models.py
  builder.py
  codec.py
```

No new dependency is required.

## Schema

```python
FAST_FORECAST_CHAMPION_SCHEMA_NAME = "shreks.fast_lane_forecast_champion"
FAST_FORECAST_CHAMPION_SCHEMA_VERSION = 1
```

## Explicit selection record

### `FastForecastChampionSelection`

Frozen/slotted fields:

- `decision_reference: str`
- `decided_at_unix_ms: int`
- `reason: str`

Rules:

- all strings are non-empty;
- timestamp is caller-supplied and non-negative;
- no wall-clock read occurs;
- the record is evidence that a selection decision was supplied, not proof that the selection was economically correct.

The builder has no API that creates this record from metrics or thresholds.

## Member evidence

### `FastForecastChampionMember`

Each frozen/slotted member contains:

- `member_key: str`
- exact embedded `FastForecastBaselineArtifact`;
- `validation_policy_version: str`;
- `validation_run_fingerprint_sha256: str`;
- `test_evaluation_policy_version: str`;
- `test_evaluation_report_fingerprint_sha256: str`;
- `test_scored_observation_count: int`;
- `test_target_unavailable_count: int`.

`member_key` is derived, never caller-invented:

```text
{target.value}@{horizon_ms}ms
```

One champion contains at most one member per target/horizon key.

The full FL8.4 report remains authoritative for detailed metrics/segments. FL8.5 stores only the exact report fingerprint and minimal count evidence needed for inspection; it does not duplicate or reinterpret metric values.

## Champion artifact

### `FastForecastChampionArtifact`

Frozen/slotted fields:

- schema name/version;
- `champion_version: str`;
- exact `FastForecastChampionSelection`;
- common `feature_schema_version: int`;
- common `training_bundle_fingerprint_sha256: str`;
- common `future_path_label_version: int`;
- canonical tuple of `FastForecastChampionMember` values;
- `champion_fingerprint_sha256: str`.

Rules:

- champion version is non-empty;
- at least one member;
- members are in lexical `member_key` order;
- member keys are unique;
- all members share the exact feature schema version;
- all members share the exact FL8.1 source bundle fingerprint;
- all members share the exact FL4 label version;
- the top-level common fields must equal every embedded artifact;
- the champion fingerprint covers every material field except itself.

Convenience lookup:

```python
champion.member_for(target, horizon_ms)
```

returns exactly one member or raises `KeyError`. It never falls back to a nearby horizon or different target.

## Builder input and alignment

Public builder:

```python
build_fast_forecast_champion(
    *,
    champion_version: str,
    decision_reference: str,
    decided_at_unix_ms: int,
    reason: str,
    member_sources: tuple[
        tuple[
            FastForecastBaselineArtifact,
            FastChronologicalValidationRun,
            FastForecastEvaluationReport,
        ], ...
    ],
) -> FastForecastChampionArtifact
```

The builder packages only exact input types and performs structural/evidence alignment. It does **not** train or rank models.

For each member source:

1. the FL8.4 report must be a TEST report;
2. report validation fingerprint must equal the supplied FL8.3 run fingerprint;
3. report source bundle fingerprint must equal both the run and runtime artifact bundle fingerprint;
4. report model version/family/target/horizon must equal the FL8.3 request and the runtime artifact;
5. runtime artifact training policy version must equal the FL8.3 request training-policy version;
6. runtime artifact feature schema and FL4 label version must align with every fold model in the validation run;
7. embedded runtime artifact fingerprint must recompute exactly;
8. the FL8.3 validation-run fingerprint is preserved as sealed upstream evidence and must cross-link exactly to FL8.4; FL8.5 does not regenerate it by replaying training/validation;
9. FL8.4 report fingerprint must recompute exactly;
10. report overall prediction/scored/unavailable counts must reconcile through the sealed FL8.4 contract.

The runtime artifact may be a final refit using the same request over the same sealed source bundle; it is not required to equal a fold artifact fingerprint because chronological fold artifacts are fit on fold-specific training populations. The provenance chain makes that distinction explicit instead of pretending fold weights and final runtime weights are identical.

## No synthetic champion decision

FL8.5 must not:

- compare two reports and pick the lowest error;
- infer a pass/fail from Brier/ECE/MAE/RMSE;
- require a hard-coded performance threshold;
- create a champion because only one source was supplied;
- mutate the legacy registry;
- create a registry `CHAMPION` event;
- declare profitability or economic edge.

A caller must explicitly provide the selection reference/time/reason. Tests use fixture references only and do not represent a real production promotion.

FL11 remains responsible for shadow proof and explicit champion promotion based on independent economic evidence.

## Runtime loadability

FL8.5 writes one self-contained canonical JSON file containing:

- top-level champion metadata and selection record;
- exact embedded FL8.2 model-artifact parameters for every member;
- exact FL8.3/FL8.4 evidence references.

A read round trip reconstructs exact `FastForecastBaselineArtifact` values. A loaded member must produce byte/numerically identical Python reference predictions to the source artifact when passed to sealed FL8.2 inference.

FL8.6 will implement and prove Rust inference/parsing parity against this same champion JSON contract. FL8.5 does not add Rust inference.

## Canonical codec

`codec.py` provides:

```python
write_fast_forecast_champion(champion, path)
read_fast_forecast_champion(path)
```

Rules:

- sorted compact UTF-8 JSON;
- explicit enum strings;
- no NaN/infinity;
- trailing newline;
- refuse overwrite;
- exact-key validation at every object level;
- reconstruct exact FL8.2 artifacts;
- recompute embedded artifact fingerprints;
- recompute champion fingerprint;
- unknown/missing fields or tampering fail closed;
- no pickle/joblib/executable class paths.

## Determinism

Input member order is non-semantic. The builder canonicalizes members by derived member key before fingerprinting.

Champion fingerprint uses canonical recursive encoding with finite floats represented by `float.hex()` for hashing, matching current Fast Lane audit discipline.

Equivalent inputs plus the same explicit selection record produce the same champion artifact and fingerprint.

## Authority boundary

`shreks_brain.fast_champion` may import only sealed Fast Lane artifact/validation/evaluation contracts plus standard-library utilities.

It must not import/use:

- providers/network clients;
- databases;
- wall-clock time or randomness;
- strategy action selection;
- PAPER execution;
- risk `TradeIntent` creation;
- signer/transaction submission;
- legacy registry mutation/promotion APIs;
- LIVE mode.

The artifact itself grants forecast-configuration identity only. It grants no capital-changing authority.

LIVE remains disabled.

## Public API

`shreks_brain.fast_champion.__all__` exposes only:

```text
FAST_FORECAST_CHAMPION_SCHEMA_NAME
FAST_FORECAST_CHAMPION_SCHEMA_VERSION
FastForecastChampionSelection
FastForecastChampionMember
FastForecastChampionArtifact
build_fast_forecast_champion
write_fast_forecast_champion
read_fast_forecast_champion
```

## TDD requirements

Independent RED/GREEN proof covers at least:

1. schema/frozen contracts and exact public API;
2. explicit non-empty selection decision fields and no wall clock;
3. TEST-only evaluation evidence;
4. runtime artifact / FL8.3 request / FL8.4 report alignment;
5. full source-bundle, feature-schema, training-policy, target/horizon/family/version, and FL4 label-version consistency;
6. at most one member per target/horizon;
7. canonical member ordering independent of caller order;
8. multi-target/multi-horizon packaging;
9. no automatic metric ranking/promotion surface;
10. exact embedded artifact fingerprint verification;
11. canonical champion fingerprint;
12. JSON round trip and byte determinism;
13. overwrite refusal and tamper/unknown-key rejection;
14. loaded member produces identical FL8.2 Python reference predictions;
15. no eager sklearn/NumPy/PyArrow import;
16. no provider/DB/PAPER/risk/signer/transaction/registry-mutation/LIVE authority;
17. actual FL8.1 -> FL8.4 integration for continuous and binary members.

## Seal procedure

1. design;
2. implementation plan;
3. intentional RED contracts;
4. implementation GREEN;
5. candidate four-gate CI GREEN;
6. exact scope audit;
7. clean history `design -> plan -> consolidated RED -> implementation` preserving the verified tree;
8. fresh exact-clean-head four-gate GREEN;
9. guarded merge with expected head SHA;
10. fresh merged-main four-gate GREEN;
11. only then mark FL8.5 SEALED.

FL8.5 does not establish profitability, LIVE eligibility, Rust inference parity, action-policy quality, or independent shadow proof.