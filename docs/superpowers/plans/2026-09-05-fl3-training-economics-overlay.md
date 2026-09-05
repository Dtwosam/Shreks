# FL3/FL8.1 Size-Aware Training Economics Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and physically prove a deterministic PumpSwap-first training-economics overlay that turns eligible immutable FL4 decision/horizon rows into requested-size FL5 BUY/SELL execution evidence without mutating FL4 or inventing Pump bonding-curve economics.

**Architecture:** Rust owns canonical source selection, reserve reconstruction, requested-size projection, causal PumpSwap fee evidence, immutable overlay export, and source fingerprints. Python owns the explicit non-source cost policy, overlay validation/application, FL5 `ExecutableTradeEvidence` construction, and propagation into the existing FL8.1/first-champion runtime path. Unavailable evidence stays explicit and fail-closed; FL4 remains unchanged.

**Tech Stack:** Rust 2021, rusqlite, serde/serde_json, sha2, existing `shreks-core` FL3 projection APIs, Python 3 stdlib dataclasses/json/hashlib/decimal, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-fl3-training-economics-overlay-design.md`

## Global Constraints

- Base implementation on sealed `main` SHA `62e7fc1e5393cdd351a31a8df1d99e2b97dd87b4`.
- Solana-only V1; no new providers or paid sources.
- Rust remains authoritative for source identity, reserve reconstruction, projection, fee normalization, and conflict quarantine.
- Python must not reimplement AMM reserve math or protocol fee semantics.
- Version 1 supports `pump_swap` only; every `pump_fun_bonding_curve` decision/horizon row is `unsupported_venue`.
- `fast_future_path_labels` is immutable input and must never be updated by this slice.
- The counterfactual base quantity is research-label input only; it is not a position size, order request, or risk allocation.
- Missing/stale/rate-unknown/projection-unavailable evidence remains explicit UNKNOWN; no historical backfill or zero-fee substitution.
- Pool-state projection is training-research evidence, not Jupiter route proof or transaction-landing proof.
- No PAPER mutation, signing, submission, promotion, or LIVE authority.
- Provider/PAPER environment must not be required by the offline exporter.
- All new production behavior follows RED → GREEN → REFACTOR TDD.

---

### Task 1: Rust FL4-compatible overlay source model and exact population loader

**Files:**
- Create: `crates/shreks-storage/src/training_economics_overlay.rs`
- Modify: `crates/shreks-storage/src/lib.rs`
- Test: `crates/shreks-storage/tests/fl3_training_economics_overlay.rs`

**Interfaces:**
- Consumes: `FastTrainingFeatureRecord`, `fast_future_path_labels`, canonical `fast_events`, existing reserve reconstruction.
- Produces:
  - `FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME: &str = "shreks.fast_training_economics_overlay"`
  - `FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION: u16 = 1`
  - `FastTrainingEconomicsStatus`
  - `FastTrainingEconomicsOverlayRow`
  - `FastTrainingEconomicsOverlayManifest`
  - `ShreksDb::fast_training_economics_overlay_rows(...)`
  - exact FL4 logical fingerprint compatible with Python `future_path_logical_fingerprint_sha256(...)`

- [ ] **Step 1: Write RED tests for exact FL4 population and canonical identity validation**

Add tests that create the existing real-shaped FL8 fixture and assert the new API returns one row per FL4 decision/horizon/version, in canonical order:

```rust
#[test]
fn training_economics_overlay_has_exact_fl4_population() {
    let fixture = fixture_with_pumpswap_and_pump_rows();
    let features = fixture.db.fast_training_feature_records(1).unwrap();

    let rows = fixture
        .db
        .fast_training_economics_overlay_rows(
            &features,
            1,
            "2",
            60_000,
        )
        .unwrap();

    assert_eq!(rows.len(), fixture.future_path_row_count);
    assert!(rows.windows(2).all(|pair| {
        (
            pair[0].decision_sequence,
            pair[0].horizon_ms,
            pair[0].decision_signature.as_str(),
            pair[0].decision_ordinal,
        ) <= (
            pair[1].decision_sequence,
            pair[1].horizon_ms,
            pair[1].decision_signature.as_str(),
            pair[1].decision_ordinal,
        )
    }));
}
```

Add a second test that tampers one supplied feature identity and expects a hard `StorageError::InvalidData`.

- [ ] **Step 2: Run RED tests**

Run:

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay training_economics_overlay_has_exact_fl4_population -- --exact
```

Expected: FAIL because the module/API does not exist.

- [ ] **Step 3: Add exact wire/domain types**

Create:

```rust
pub const FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_NAME: &str =
    "shreks.fast_training_economics_overlay";
pub const FAST_TRAINING_ECONOMICS_OVERLAY_SCHEMA_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FastTrainingEconomicsStatus {
    Available,
    UnsupportedVenue,
    NoEndpoint,
    EntryReserveUnavailable,
    ExitReserveUnavailable,
    EntryProjectionUnavailable,
    ExitProjectionUnavailable,
    EntryFeeMissing,
    EntryFeeStale,
    EntryFeeRateUnknown,
    ExitFeeMissing,
    ExitFeeStale,
    ExitFeeRateUnknown,
}
```

Define `FastTrainingEconomicsOverlayRow` with every field required by the approved spec: decision identity, endpoint identity, status, canonical decimal quantity, raw quantity, entry/exit reserve provenance, entry/exit projection, and entry/exit fee provenance. Optional evidence groups must be all-null when the status prevents their availability.

- [ ] **Step 4: Add an internal FL4 label row matching Python’s 32-field training-target contract**

Query exactly the same columns and ordering as `python/src/shreks_brain/research/fast_training_targets.py`:

```sql
ORDER BY l.decision_sequence ASC,
         l.horizon_ms ASC,
         l.decision_signature ASC,
         l.decision_ordinal ASC
```

Validate canonical decision and endpoint sources and conflict quarantine before constructing overlay rows.

- [ ] **Step 5: Implement Python-compatible FL4 logical fingerprinting**

Mirror Python’s canonicalization exactly:

```text
labels -> list of dicts
each finite float -> {"__float_hex__": <Python-compatible float.hex()>}
dict keys sorted
json separators = "," and ":"
UTF-8
SHA-256 lowercase hex
```

Implement a private `python_float_hex(f64) -> Result<String, StorageError>` from IEEE-754 bits and cover representative values:

```rust
assert_eq!(python_float_hex(1.0).unwrap(), "0x1.0000000000000p+0");
assert_eq!(python_float_hex(0.5).unwrap(), "0x1.0000000000000p-1");
assert_eq!(python_float_hex(-0.0).unwrap(), "-0x0.0p+0");
```

Reject non-finite floats.

- [ ] **Step 6: Verify cross-language FL4 fingerprint parity**

Add a Python integration assertion in `python/tests/test_fast_training_economics.py` later; for this task, expose the Rust manifest field/API required for that check.

- [ ] **Step 7: Run GREEN storage tests**

Run:

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay
cargo test -p shreks-storage --test fl8_training_fixture
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add crates/shreks-storage/src/training_economics_overlay.rs         crates/shreks-storage/src/lib.rs         crates/shreks-storage/tests/fl3_training_economics_overlay.rs
git commit -m "feat: add training economics overlay source model"
```

---

### Task 2: Rust PumpSwap requested-size projection and causal fee evidence

**Files:**
- Modify: `crates/shreks-storage/src/training_economics_overlay.rs`
- Test: `crates/shreks-storage/tests/fl3_training_economics_overlay.rs`

**Interfaces:**
- Consumes:
  - `project_entry(&FastReserveContext, u64)`
  - `project_exit(&FastReserveContext, u64)`
  - `ShreksDb::pump_swap_effective_fee_context(...)`
  - `fast_events_for_market_with_reserve_context(...)`
- Produces: fully-populated `available` PumpSwap overlay rows or one exact unavailable status.

- [ ] **Step 1: Write RED test for exact decimal-to-raw conversion**

Add:

```rust
#[test]
fn counterfactual_decimal_quantity_is_never_rounded() {
    assert_eq!(decimal_quantity_to_raw("2.5", 6).unwrap(), 2_500_000);
    assert!(decimal_quantity_to_raw("0.0000001", 6).is_err());
    assert!(decimal_quantity_to_raw("2e-7", 6).is_err());
}
```

Normalize accepted decimal text to one canonical non-exponent form for the manifest.

- [ ] **Step 2: Run RED quantity test**

Run:

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay counterfactual_decimal_quantity_is_never_rounded -- --exact
```

Expected: FAIL because the helper is absent.

- [ ] **Step 3: Implement exact decimal parsing without float conversion**

Parse optional leading `+`, integer digits, optional fraction, and optional decimal exponent. Convert to an integer rational scale with checked `u128` arithmetic. For a market with `base_decimals = d`, require the value × `10^d` to be an exact positive integer within `u64`.

Do not add a decimal dependency.

- [ ] **Step 4: Write RED tests for PumpSwap available rows**

Build canonical PumpSwap decision and endpoint events with migration-15 virtual quote reserve evidence and exact BUY/SELL effective fee deltas. Assert:

```rust
assert_eq!(row.status, FastTrainingEconomicsStatus::Available);
assert_eq!(row.requested_base_quantity_raw, Some(2_000_000));
assert_eq!(row.entry_projection.as_ref().unwrap().base_quantity_raw, 2_000_000);
assert_eq!(row.exit_projection.as_ref().unwrap().base_quantity_raw, 2_000_000);
assert_eq!(row.entry_fee.as_ref().unwrap().effective_fee_bps, 50);
assert_eq!(row.exit_fee.as_ref().unwrap().effective_fee_bps, 50);
```

Also independently call `project_entry` / `project_exit` in the test and require exact equality with the overlay projection objects.

- [ ] **Step 5: Write RED chronology/status tests**

Cover:

```text
Pump bonding curve -> unsupported_venue
complete no-trade horizon -> no_endpoint
missing decision virtual quote reserve -> entry_reserve_unavailable
missing endpoint virtual quote reserve -> exit_reserve_unavailable
latest causal BUY fee missing -> entry_fee_missing
latest causal BUY fee stale -> entry_fee_stale
latest causal BUY fee inexact/rebate -> entry_fee_rate_unknown
latest causal SELL fee missing/stale/rate-unknown -> corresponding exit status
requested quantity beyond pool projection -> entry/exit_projection_unavailable
conflict quarantine -> hard error, never a status
```

For no-fallback behavior, create an older clean fee event plus a newer stale or rate-unknown event and assert the older event is never selected.

- [ ] **Step 6: Run RED tests**

Run:

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay
```

Expected: new status/projection tests FAIL for missing implementation.

- [ ] **Step 7: Implement row evaluation in strict order**

Use this order so failures are deterministic:

```text
validate FL4/canonical identity
unsupported venue
no endpoint
load decision reserve
load endpoint reserve
convert exact requested quantity
project entry
project exit
select decision BUY fee context
select endpoint SELL fee context
available
```

Map only truthful absence/projection limitations to row statuses. Propagate corrupt/conflicted source errors.

- [ ] **Step 8: Preserve reserve and fee provenance**

For each available row record exact decision/endpoint source identities and exact raw reserve values. The reserve context must come from existing canonical replay; do not query raw reserve tables separately inside overlay logic.

- [ ] **Step 9: Run GREEN tests**

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay
cargo test -p shreks-storage --test fl3_exit_capacity_replay
cargo test -p shreks-core --test fl3_entry_projection
cargo test -p shreks-core --test fast_lane_exit_capacity
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add crates/shreks-storage/src/training_economics_overlay.rs         crates/shreks-storage/tests/fl3_training_economics_overlay.rs
git commit -m "feat: project PumpSwap training economics"
```

---

### Task 3: Immutable Rust overlay artifact writer and offline host subcommand

**Files:**
- Modify: `crates/shreks-storage/src/training_economics_overlay.rs`
- Create: `crates/shreks-observer/src/bin/shreks-observe/fast_training_economics_cli.rs`
- Modify: `crates/shreks-observer/src/bin/shreks-observe.rs`
- Create: `crates/shreks-observer/tests/fl3_training_economics_subcommand.rs`

**Interfaces:**
- Consumes: database path, feature JSONL, label version, exact decimal quantity text, PumpSwap fee max age, output directory.
- Produces immutable directory:
  - `rows.jsonl`
  - `manifest.json`

- [ ] **Step 1: Write RED artifact tests**

Add a storage-level test:

```rust
let manifest = db
    .write_fast_training_economics_overlay(
        &feature_jsonl,
        1,
        "2",
        60_000,
        &destination,
    )
    .unwrap();

assert!(destination.join("rows.jsonl").is_file());
assert!(destination.join("manifest.json").is_file());
assert_eq!(manifest.row_count, 4);
assert_eq!(
    manifest.status_counts.values().sum::<u64>(),
    manifest.row_count
);
```

A second call to the same destination must return an error and leave existing bytes unchanged.

- [ ] **Step 2: Run RED artifact test**

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay immutable_overlay_writer -- --nocapture
```

Expected: FAIL because writer is absent.

- [ ] **Step 3: Implement stable feature JSONL authentication**

Read the exact input bytes, SHA-256 them, split by normalized lines, decode every record through `decode_fast_training_feature_record_json`, reject blank/duplicate records, and require exact equality to the DB-derived FL4 decision population.

- [ ] **Step 4: Implement canonical row and manifest fingerprints**

Rows are sorted by:

```text
decision_sequence
decision_signature
decision_ordinal
horizon_ms
future_path_label_version
```

Serialize each row with deterministic serde field order and one `\n`. Hash those exact row bytes for `ordered_row_logical_fingerprint_sha256`.

The manifest fingerprint hashes the manifest document excluding its own fingerprint field.

- [ ] **Step 5: Implement atomic create-new directory behavior**

Write to a sibling staging directory, fsync files where existing repository conventions permit, then rename only if the final destination still does not exist. On error, delete staging and never modify SQLite.

- [ ] **Step 6: Write RED CLI test**

Follow the existing `fl4_population_subcommand.rs` pattern. Clear provider/PAPER environment and execute:

```rust
Command::new(binary())
    .arg("export-training-economics")
    .arg("--database").arg(&database)
    .arg("--feature-jsonl").arg(&features)
    .arg("--future-path-label-version").arg("1")
    .arg("--counterfactual-base-quantity").arg("2")
    .arg("--pump-swap-fee-maximum-age-ms").arg("60000")
    .arg("--output").arg(&output)
```

Assert success, exact two-file artifact, and one canonical JSON report on stdout.

- [ ] **Step 7: Run RED CLI test**

```bash
cargo test -p shreks-observer --test fl3_training_economics_subcommand -- --nocapture
```

Expected: FAIL because command is absent.

- [ ] **Step 8: Add CLI dispatch before runtime environment loading**

In `shreks-observe.rs`:

```rust
#[path = "shreks-observe/fast_training_economics_cli.rs"]
mod fast_training_economics_cli;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    if fast_training_economics_cli::run_fast_training_economics_subcommand_if_requested()? {
        return Ok(());
    }
    if fast_future_path_population_cli::run_fast_future_path_population_subcommand_if_requested()? {
        return Ok(());
    }
    // existing runtime path unchanged
}
```

Do not read provider/runtime config inside the new module.

- [ ] **Step 9: Run GREEN CLI/storage tests**

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay
cargo test -p shreks-observer --test fl3_training_economics_subcommand
cargo test -p shreks-observer --test fl4_population_subcommand
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add crates/shreks-storage/src/training_economics_overlay.rs         crates/shreks-observer/src/bin/shreks-observe.rs         crates/shreks-observer/src/bin/shreks-observe/fast_training_economics_cli.rs         crates/shreks-observer/tests/fl3_training_economics_subcommand.rs
git commit -m "feat: export training economics evidence"
```

---

### Task 4: Python overlay codec, cost policy, and FL5 execution-evidence application

**Files:**
- Create: `python/src/shreks_brain/research/fast_training_economics.py`
- Create: `python/tests/test_fast_training_economics.py`

**Interfaces:**
- Produces:
  - `FastTrainingExecutionCostPolicy`
  - `encode_fast_training_execution_cost_policy(policy) -> str`
  - `decode_fast_training_execution_cost_policy(payload) -> FastTrainingExecutionCostPolicy`
  - `fast_training_execution_cost_policy_fingerprint_sha256(policy) -> str`
  - `FastTrainingEconomicsOverlayRow`
  - `FastTrainingEconomicsOverlayDataset`
  - `read_fast_training_economics_overlay(path)`
  - `build_entry_counterfactual_context_from_training_economics(...)`

- [ ] **Step 1: Write RED policy validation tests**

Add:

```python
def test_training_cost_policy_rejects_negative_or_nonfinite_costs() -> None:
    with pytest.raises(ValueError):
        FastTrainingExecutionCostPolicy(
            version="policy-v1",
            additional_entry_slippage_bps=-1,
            additional_exit_slippage_bps=0,
            entry_latency_bps=0,
            exit_latency_bps=0,
            entry_network_fee_quote=0.0,
            exit_network_fee_quote=0.0,
            entry_priority_fee_quote=0.0,
            exit_priority_fee_quote=0.0,
            entry_expected_failure_cost_quote=0.0,
            exit_expected_failure_cost_quote=0.0,
        )
```

Also prove the dataclass has no protocol-fee or price-impact fields.

- [ ] **Step 2: Run RED policy test**

```bash
python -m pytest python/tests/test_fast_training_economics.py -q
```

Expected: collection FAIL because module is absent.

- [ ] **Step 3: Implement exact frozen policy**

Use:

```python
@dataclass(frozen=True, slots=True)
class FastTrainingExecutionCostPolicy:
    version: str
    additional_entry_slippage_bps: int
    additional_exit_slippage_bps: int
    entry_latency_bps: int
    exit_latency_bps: int
    entry_network_fee_quote: float
    exit_network_fee_quote: float
    entry_priority_fee_quote: float
    exit_priority_fee_quote: float
    entry_expected_failure_cost_quote: float
    exit_expected_failure_cost_quote: float
```

Require bps fields `0 <= value <= 10_000`, all fixed costs finite/non-negative, and total exit variable rate including source fee strictly below 10,000 when applying a row.

Add canonical JSON encode/decode using exact keys, sorted-key compact JSON, no NaN/Infinity, and a SHA-256 fingerprint over the canonical policy document. Unknown/missing keys must fail closed.

- [ ] **Step 4: Write RED policy codec/fingerprint tests**

Add a round-trip test:

```python
policy = FastTrainingExecutionCostPolicy(
    version="training-cost-v1",
    additional_entry_slippage_bps=10,
    additional_exit_slippage_bps=20,
    entry_latency_bps=5,
    exit_latency_bps=5,
    entry_network_fee_quote=0.0,
    exit_network_fee_quote=0.0,
    entry_priority_fee_quote=0.0,
    exit_priority_fee_quote=0.0,
    entry_expected_failure_cost_quote=0.0,
    exit_expected_failure_cost_quote=0.0,
)
payload = encode_fast_training_execution_cost_policy(policy)
assert decode_fast_training_execution_cost_policy(payload) == policy
assert len(fast_training_execution_cost_policy_fingerprint_sha256(policy)) == 64
```

Tampering with a key or adding an unknown key must fail.

- [ ] **Step 5: Write RED overlay reader/fingerprint tests**

Generate the artifact with the Rust test fixture/subcommand and assert Python:

```python
overlay = read_fast_training_economics_overlay(path)
assert overlay.manifest.feature_source_jsonl_sha256 == hashlib.sha256(
    feature_path.read_bytes()
).hexdigest()
assert (
    overlay.manifest.future_path_logical_fingerprint_sha256
    == load_future_path_training_labels_from_sqlite(
        database,
        future_path_label_version=1,
    ).logical_fingerprint_sha256
)
```

Tamper one row byte and one manifest fingerprint separately; both must fail closed.

- [ ] **Step 6: Implement canonical reader**

Require exactly `rows.jsonl` and `manifest.json`, exact schema/version, exact row count, unique decision/horizon identities, canonical ordering, valid status enum, valid nullable evidence-group invariants, row fingerprint, and manifest fingerprint.

Use `Decimal` for the manifest counterfactual quantity string. Do not convert it through binary float for equality checks.

- [ ] **Step 7: Write RED cost application tests**

For an available row with:

```text
gross entry = 100
gross exit = 120
entry fee = 50 bps
exit fee = 40 bps
entry extra slippage = 10 bps
exit extra slippage = 20 bps
entry latency = 5 bps
exit latency = 5 bps
entry fixed = 0.1
exit fixed = 0.2
```

assert exact formula parity using `pytest.approx`.

Also assert reserve impact is not represented by any separate policy field.

- [ ] **Step 8: Implement FL5 evidence construction**

For `available`:

```python
buy = ExecutableTradeEvidence(
    evidence_id=...,
    source_event_signature=row.decision_signature,
    source_event_ordinal=row.decision_ordinal,
    observed_at_unix_ms=row.decision_observed_at_unix_ms,
    side=TradeSide.BUY,
    base_quantity=requested_quantity,
    status=ExecutionStatus.EXECUTABLE,
    quote_amount=entry_total_quote,
    evidence_version=evidence_version,
)
```

Create analogous SELL evidence from endpoint identity/time.

For any non-`available` status, set both to `None` so the existing FL5 labeler produces BUY_NOW UNKNOWN and SKIP EXECUTABLE.

- [ ] **Step 9: Run GREEN Python overlay tests**

```bash
python -m pytest python/tests/test_fast_training_economics.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add python/src/shreks_brain/research/fast_training_economics.py         python/tests/test_fast_training_economics.py
git commit -m "feat: apply training economics overlay"
```

---

### Task 5: Integrate overlay into runtime FL8.1 bundle construction

**Files:**
- Modify: `python/src/shreks_brain/research/fast_training_bundle.py`
- Modify: `python/tests/test_fast_runtime_training_bundle.py`

**Interfaces:**
- Change:

```python
def build_fast_training_bundle_from_runtime_sources(
    *,
    feature_jsonl_path: str | Path,
    sqlite_path: str | Path,
    future_path_label_version: int,
    counterfactual_base_quantity: float,
    training_economics_overlay_path: str | Path,
    training_execution_cost_policy: FastTrainingExecutionCostPolicy,
) -> FastTrainingBundle:
```

- [ ] **Step 1: Write RED runtime-bundle available/unavailable tests**

Replace the old blanket-UNKNOWN fixture expectation with a mixed overlay fixture.

Assert:
- every FL4 identity has exactly one overlay row;
- `available` rows yield executable BUY_NOW;
- unavailable rows yield UNKNOWN BUY_NOW;
- every row retains executable SKIP;
- no row disappears.

- [ ] **Step 2: Run RED runtime tests**

```bash
python -m pytest python/tests/test_fast_runtime_training_bundle.py -q
```

Expected: FAIL because the runtime builder does not accept overlay/policy inputs.

- [ ] **Step 3: Validate all cross-source bindings before constructing outcomes**

Require:

```python
overlay.manifest.feature_source_jsonl_sha256 == features.source_sha256
overlay.manifest.future_path_logical_fingerprint_sha256 == future_path.logical_fingerprint_sha256
overlay.manifest.future_path_label_version == future_path_label_version
Decimal(overlay.manifest.counterfactual_base_quantity) == Decimal(str(counterfactual_base_quantity))
set(overlay identities) == set(FL4 identities)
```

For each row, also require the existing `load_entry_counterfactual_from_sqlite(...).provenance` identity to match overlay identity/provenance.

- [ ] **Step 4: Delegate outcome computation to existing FL5 labeler**

Build a new `EntryCounterfactualContext` using overlay execution evidence and call only:

```python
label_entry_counterfactuals(context)
```

Do not compute return/PnL again in the runtime builder.

- [ ] **Step 5: Preserve no-PyArrow and authority firewall tests**

Keep the existing import guard and forbidden-token source test green. Add the new overlay module to the authority-firewall scan for:
`requests.`, `httpx`, `TradeIntent`, `RuntimeMode.LIVE`, `sign_transaction`, `submit_transaction`.

- [ ] **Step 6: Run GREEN runtime tests**

```bash
python -m pytest python/tests/test_fast_runtime_training_bundle.py                      python/tests/test_fast_training_economics.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python/src/shreks_brain/research/fast_training_bundle.py         python/tests/test_fast_runtime_training_bundle.py
git commit -m "feat: bind economics overlay into training bundle"
```

---

### Task 6: Propagate authenticated overlay and policy through first-champion request/preparation/host paths

**Files:**
- Modify: `python/src/shreks_brain/fast_first_champion/file_request.py`
- Modify: `python/src/shreks_brain/fast_first_champion_preparation.py`
- Modify: `python/src/shreks_brain/fast_first_champion_host_run.py`
- Modify: `python/src/shreks_brain/fast_first_champion_host_request_writer.py`
- Modify: corresponding tests:
  - `python/tests/test_fast_first_champion_file_request.py`
  - `python/tests/test_fast_first_champion_preparation.py`
  - `python/tests/test_fast_first_champion_host_run.py`
  - `python/tests/test_fast_first_champion_host_request_writer.py`

**Interfaces:**
- Add authenticated request fields for:
  - training economics overlay path;
  - exact `FastTrainingExecutionCostPolicy`.

- [ ] **Step 1: Write RED request-codec tests**

Bump each request schema version touched by a serialized wire contract. Add exact field-set tests so old payloads are rejected rather than silently interpreted.

The file request must include:

```python
"training_economics_overlay_path"
"training_execution_cost_policy"
```

The policy document uses exactly the eleven fields from `FastTrainingExecutionCostPolicy` (one version field plus ten numeric fields).

- [ ] **Step 2: Run RED request tests**

```bash
python -m pytest   python/tests/test_fast_first_champion_file_request.py   python/tests/test_fast_first_champion_preparation.py   python/tests/test_fast_first_champion_host_run.py   python/tests/test_fast_first_champion_host_request_writer.py -q
```

Expected: FAIL for missing new request fields/signatures.

- [ ] **Step 3: Propagate overlay path and policy without defaults**

Every caller of `build_fast_training_bundle_from_runtime_sources(...)` must pass the authenticated overlay path and exact policy. Do not provide a compatibility default that recreates the old all-UNKNOWN behavior.

- [ ] **Step 4: Add source snapshot authentication**

Where the existing first-champion artifact snapshots input files, add overlay manifest/rows hashes or the overlay manifest fingerprint to the request/artifact fingerprint material so swapping the overlay after request creation fails closed.

- [ ] **Step 5: Add exact host request CLI inputs**

Use exactly two new source inputs:

```text
--training-economics-overlay <directory>
--training-execution-cost-policy <json-file>
```

Read the policy file stably, decode it only with `decode_fast_training_execution_cost_policy(...)`, compute `fast_training_execution_cost_policy_fingerprint_sha256(...)`, and embed the exact decoded policy plus its fingerprint in the authenticated request material. Do not expose per-component CLI defaults.

- [ ] **Step 6: Run GREEN first-champion tests**

```bash
python -m pytest   python/tests/test_fast_first_champion_file_request.py   python/tests/test_fast_first_champion_preparation.py   python/tests/test_fast_first_champion_host_run.py   python/tests/test_fast_first_champion_host_request_writer.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add python/src/shreks_brain/fast_first_champion         python/src/shreks_brain/fast_first_champion_preparation.py         python/src/shreks_brain/fast_first_champion_host_run.py         python/src/shreks_brain/fast_first_champion_host_request_writer.py         python/tests/test_fast_first_champion_file_request.py         python/tests/test_fast_first_champion_preparation.py         python/tests/test_fast_first_champion_host_run.py         python/tests/test_fast_first_champion_host_request_writer.py
git commit -m "feat: authenticate training economics inputs"
```

---

### Task 7: Cross-language regression, repository safety, and release verification

**Files:**
- Modify only files required by failing verification; no scope expansion.
- Test: existing Rust/Python suites and repository safety workflows.

**Interfaces:**
- Produces one reviewed GREEN head ready for PR/merge/seal.

- [ ] **Step 1: Run focused Rust tests**

```bash
cargo test -p shreks-storage --test fl3_training_economics_overlay
cargo test -p shreks-observer --test fl3_training_economics_subcommand
cargo test -p shreks-storage --test fl3_exit_capacity_replay
cargo test -p shreks-core --test fl3_entry_projection
cargo test -p shreks-core --test fast_lane_exit_capacity
```

Expected: PASS.

- [ ] **Step 2: Run focused Python tests**

```bash
python -m pytest   python/tests/test_fast_training_economics.py   python/tests/test_fast_runtime_training_bundle.py   python/tests/test_fast_first_champion_file_request.py   python/tests/test_fast_first_champion_preparation.py   python/tests/test_fast_first_champion_host_run.py   python/tests/test_fast_first_champion_host_request_writer.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full Rust workspace**

```bash
cargo test --workspace
```

Expected: PASS.

- [ ] **Step 4: Run full Python suite**

Use the repository’s existing Python test command from CI/README. Expected: PASS with no new dependency requirement for the production wheel.

- [ ] **Step 5: Run repository safety gates**

Run the exact repository safety/check scripts used by current CI. Expected: PASS, including no secret leakage and no unauthorized LIVE surface.

- [ ] **Step 6: Build native ARM64 release**

Run the exact current release build command/workflow used by the repo. Expected: successful `shreks-observe` release binary containing `export-training-economics`.

- [ ] **Step 7: Review branch diff against sealed base**

```bash
git diff --stat 62e7fc1e5393cdd351a31a8df1d99e2b97dd87b4...HEAD
git diff 62e7fc1e5393cdd351a31a8df1d99e2b97dd87b4...HEAD --   crates/shreks-storage   crates/shreks-observer   python/src/shreks_brain   python/tests
```

Confirm:
- no FL4 mutation path;
- no provider/network code in exporter;
- no Pump fee semantics;
- no hidden cost defaults;
- no route/landing claims;
- no PAPER/LIVE authority.

- [ ] **Step 8: Open PR from exact GREEN head**

Use branch `feat/fl3-training-economics-overlay`, include the approved spec and this plan in the PR body, and require review against the exact head SHA.

- [ ] **Step 9: Merge only exact reviewed GREEN head, then seal/release**

After merge, verify `main` equals the reviewed merge result, create the immutable release/tag using existing repo conventions, deploy once through the verified workflow, and do not redeploy the same SHA.

- [ ] **Step 10: Physical VPS acceptance**

Using the already-proven immutable session-3 population:

```text
512 decisions
6,144 FL4 rows
2,112 Pump decision/horizon rows -> unsupported_venue
4,032 PumpSwap decision/horizon rows -> evidence-derived statuses
```

Export the overlay once, capture `manifest.json`, build the runtime FL8.1 bundle from it, verify executable BUY_NOW exists only for `available` rows, and verify production FL4 logical fingerprint is unchanged before/after.

No favorable profitability threshold is required for acceptance. Truthful UNKNOWN or insufficient evidence remains valid.

- [ ] **Step 11: Commit any verification-only documentation**

Only if the repo convention records sealed verification evidence in tracked docs; otherwise keep host outputs external and leave code unchanged.
