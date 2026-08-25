# Phase E10 Trading Evaluation Evidence Store Design

## Purpose

Phase E10 closes the remaining restart-safety gap between sealed E5 trading evaluation and sealed E8 promotion assessment.

E5 produces a full `TradingEvaluationReport` from exact source evidence:

- `TradingEvaluationPolicy`;
- canonical `EvaluatedTrade` values;
- canonical `ProbabilityObservation` values;
- `candidate_version`.

E6 persists only a summary of the E5 report. E8 promotion, however, requires both the full `TradingEvaluationReport` and the raw `EvaluatedTrade` tuple, and baseline comparisons require full baseline reports. Before E10, those full inputs could disappear after restart even while their E6 summary fingerprint survived.

E10 persists the E5 source evidence needed to deterministically reconstruct the full report after restart. It does not persist a second copy of derived metrics. On every load it calls the sealed E5 evaluator and requires the recomputed E5 fingerprint to equal the stored fingerprint.

E10 is based exactly on sealed E9 head `7bf83204f87b210d0f784911413d4870471ed740`.

## Core design choice

Persist source evidence, not duplicated derived output.

The write path is:

```text
candidate_version
+ TradingEvaluationPolicy
+ tuple[EvaluatedTrade, ...]
+ tuple[ProbabilityObservation, ...]
  -> sealed E5 evaluate_trading_performance(...)
  -> evaluation_fingerprint_sha256
  -> exact E10 source-evidence mapping
  -> canonical JSON
  -> fsync temporary sibling
  -> atomic replace
```

The restart path is:

```text
E10 JSON
  -> exact nested schema validation
  -> reconstruct E5 policy/trades/observations
  -> sealed E5 evaluate_trading_performance(...)
  -> independently recompute full TradingEvaluationReport
  -> require E5 fingerprint == stored fingerprint
  -> return immutable TradingEvaluationEvidence bundle
```

This gives one authoritative source representation. Persisting the full report as well would duplicate derived metrics/calibration/segments and create two sources of truth that could drift.

## Why the existing E5 fingerprint is sufficient

The sealed E5 `evaluation_fingerprint_sha256` already commits to:

- evaluation schema;
- full `TradingEvaluationPolicy`;
- candidate version;
- canonical raw trades;
- canonical probability observations;
- overall performance metrics;
- setup segments;
- regime segments;
- calibration.

E5 canonicalizes every float using exact `float.hex()` semantics before hashing. Therefore E10 does not invent a competing evaluation identity. It stores and verifies the existing E5 fingerprint.

## Package changes

Extend `shreks_brain.evaluation` with:

- `evaluation/evidence.py` — immutable in-memory `TradingEvaluationEvidence` bundle;
- `evaluation/codec.py` — exact source-evidence JSON codec and deterministic report reconstruction;
- `evaluation/store.py` — append-only restart-safe `TradingEvaluationEvidenceStore`;
- `evaluation/__init__.py` — additive public exports.

Do not change sealed E5 evaluation arithmetic, canonical ordering, calibration, segmentation, or fingerprint semantics.

## Public in-memory bundle

Add:

```python
@dataclass(frozen=True, slots=True)
class TradingEvaluationEvidence:
    candidate_version: str
    policy: TradingEvaluationPolicy
    trades: tuple[EvaluatedTrade, ...]
    probability_observations: tuple[ProbabilityObservation, ...]
    report: TradingEvaluationReport
```

The bundle is reconstructed from persisted source evidence. `report` is derived by the sealed E5 engine, never trusted from disk.

The bundle validates exact E5 value types and requires:

- candidate version to be non-empty;
- every trade and probability observation to match `candidate_version`;
- `report.candidate_version == candidate_version`;
- `report.policy_version == policy.version`.

The store/codec additionally require the recomputed report fingerprint to match the stored fingerprint.

## Store schema

Use store schema version:

```text
e10-evaluation-evidence-v1
```

Physical document:

```json
{
  "schema_version": "e10-evaluation-evidence-v1",
  "evaluations": [
    {
      "candidate_version": "challenger-v1",
      "evaluation_fingerprint_sha256": "<64 lowercase hex>",
      "policy": {
        "version": "evaluation-policy-v1",
        "starting_equity_usd": 10000.0,
        "calibration_bucket_count": 10
      },
      "trades": [
        {
          "candidate_version": "challenger-v1",
          "position_id": "...",
          "candidate_mint": "...",
          "setup_name": "...",
          "market_regime": "...",
          "opened_at_unix_ms": 0,
          "closed_at_unix_ms": 1,
          "entry_notional_usd": 100.0,
          "turnover_usd": 200.0,
          "gross_pnl_usd": 5.0,
          "execution_friction_usd": 1.0,
          "explicit_cost_usd": 0.5,
          "net_pnl_usd": 3.5
        }
      ],
      "probability_observations": [
        {
          "candidate_version": "challenger-v1",
          "model_version": "model-v1",
          "candidate_mint": "...",
          "as_of_unix_ms": 0,
          "positive_probability": 0.7,
          "target_positive": true,
          "setup_name": "...",
          "market_regime": "...",
          "fold_name": "..."
        }
      ]
    }
  ]
}
```

Every object has an exact field set. Unknown or missing fields fail closed.

## Canonical source ordering

E10 does not define a second ordering rule. Before persistence it relies on sealed E5 by evaluating the supplied source values, then persists the canonical order used by E5:

Trades sort by:

```text
(closed_at_unix_ms, opened_at_unix_ms, position_id, candidate_mint)
```

Probability observations sort by:

```text
(as_of_unix_ms, candidate_mint)
```

On load, E10 requires the persisted arrays already be in these canonical orders and contain no duplicate E5 identities. This makes byte representation deterministic and prevents semantically equivalent reordered files.

## Canonical JSON

Physical JSON uses:

- UTF-8;
- sorted object keys;
- compact separators;
- `ensure_ascii=False`;
- `allow_nan=False`;
- exactly one trailing newline.

The E5 fingerprint remains authoritative and continues to use E5's sealed exact float-hex hashing semantics. E10 does not reimplement that hash.

## Store API

`TradingEvaluationEvidenceStore(path)` exposes only:

```text
load() -> tuple[TradingEvaluationEvidence, ...]
get(candidate_version, evaluation_fingerprint_sha256) -> TradingEvaluationEvidence | None
append(candidate_version, trades, probability_observations, policy) -> tuple[TradingEvaluationEvidence, ...]
```

`append(...)` always computes the E5 report with sealed `evaluate_trading_performance(...)`; callers cannot provide or override a report fingerprint.

Behavior:

- missing file loads as empty;
- each append derives the E5 report and its fingerprint;
- append order is preserved across evaluation records;
- exact repeated evaluation evidence is idempotent;
- duplicate `(candidate_version, evaluation_fingerprint_sha256)` with different persisted source content fails closed;
- `get` returns the exact reconstructed evidence bundle or `None`;
- multiple distinct evaluation fingerprints for the same candidate are allowed so evidence history is append-only;
- there is no delete/rewrite/update/promotion/registry/trade/live method.

## Validation and corruption handling

Load fails closed for:

- malformed JSON;
- wrong/non-object top-level document;
- wrong E10 store schema;
- missing/unknown fields at any object layer;
- wrong list/scalar types;
- non-finite numeric values;
- invalid SHA-256 text;
- invalid E5 policy/trade/observation dataclass content;
- non-canonical trade ordering;
- non-canonical observation ordering;
- duplicate E5 trade/observation identities;
- candidate-version mismatch anywhere in source evidence;
- duplicate evaluation identity with conflicting source content;
- any source tampering that causes sealed E5 to recompute a different fingerprint.

Because the report is rebuilt rather than decoded from disk, corrupted derived metrics cannot be smuggled through an E10 file; there are no derived metrics in the file to trust.

## Atomic persistence

Writes follow the sealed E6/E7/E8/E9 pattern:

1. create parent directories;
2. write canonical payload to `<name>.tmp`;
3. flush and `os.fsync`;
4. `os.replace` temporary -> destination;
5. on write/replace error, best-effort remove the temporary sibling and re-raise.

Successful writes leave no `.tmp` sibling.

## Import/dependency boundary

E10 uses only the Python standard library and sealed E5 public contracts/engine. It adds no new third-party dependency.

Importing `shreks_brain.evaluation` remains light and deterministic.

## Relationship to E6/E8

E6 remains registry/status authority. E10 does not mutate or reinterpret registry evidence.

A runtime can use an E6 candidate's persisted `evaluation_fingerprint_sha256` to fetch the exact E10 evidence bundle and verify that its reconstructed report fingerprint matches E6's summary reference before calling E8.

E8 continues to receive:

- full reconstructed candidate `TradingEvaluationReport`;
- raw evaluated trade tuple;
- reconstructed baseline full reports;
- existing E7 shadow ledger;
- existing E6 registry.

E10 therefore makes E8 inputs restart-safe without changing E8 policy or authority.

## Explicit non-goals

E10 does not:

- change E5 evaluation math or fingerprinting;
- generate trades or probability observations;
- run backtests or paper loops;
- train/tune a model;
- register or promote a challenger;
- choose promotion thresholds;
- create a `TradeIntent`;
- sign or submit transactions;
- enable live mode;
- claim positive expectancy or profitability.

## Exit criterion

E10 is complete when exact E5 source evidence can be appended, recovered after restart, deterministically re-evaluated by the sealed E5 engine, and rejected on any source/fingerprint corruption, while exposing no execution or promotion authority.