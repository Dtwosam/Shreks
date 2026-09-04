use std::{
    fs,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};
use shreks_storage::{
    decode_fast_deterministic_candidate_manifest_json,
    decode_fast_deterministic_row_request_json,
    decode_fast_training_feature_record_json,
    encode_fast_deterministic_row_result_json,
    evaluate_fast_deterministic_row_request,
    materialize_fast_deterministic_candidate_manifest,
    FastTrainingFeatureRecord, FastTrainingWindowSummary,
    FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME,
    FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION,
    FAST_TRAINING_FEATURE_SCHEMA_NAME, FAST_TRAINING_FEATURE_SCHEMA_VERSION,
};
use shreks_core::{FastBaselineKind, FastLaneAction, DEFAULT_FAST_WINDOWS_MS};

const MANIFEST: &str = include_str!(
    "../../../python/tests/fixtures/fast_deterministic_candidate_manifest_v1.json"
);

fn empty_window(window_ms: u64) -> FastTrainingWindowSummary {
    FastTrainingWindowSummary {
        window_ms,
        buy_count: 0,
        sell_count: 0,
        unique_buy_actors: 0,
        unique_sell_actors: 0,
        buy_arrival_rate_per_second: 0.0,
        sell_arrival_rate_per_second: 0.0,
        count_imbalance: 0.0,
        buy_base_quantity: 0.0,
        sell_base_quantity: 0.0,
        buy_quote_quantity: 0.0,
        sell_quote_quantity: 0.0,
        net_quote_quantity: 0.0,
        quote_flow_imbalance: 0.0,
        quote_flow_velocity_per_second: 0.0,
        quote_flow_acceleration_per_second2: 0.0,
        local_high_price_quote: Some(0.0102),
        local_high_sequence: Some(40),
        local_high_observed_at_unix_ms: Some(980),
        local_low_price_quote: Some(0.0095),
        local_low_sequence: Some(30),
        local_low_observed_at_unix_ms: Some(960),
        post_high_low_price_quote: Some(0.0099),
        post_high_low_sequence: Some(41),
        post_high_low_observed_at_unix_ms: Some(990),
        last_price_quote: Some(0.0101),
        drawdown_from_local_high: 0.009_803_921_568_627_45,
        recovery_from_local_low: 0.063_157_894_736_842_1,
    }
}

fn strong_signal_window() -> FastTrainingWindowSummary {
    let mut value = empty_window(500);
    value.buy_count = 8;
    value.sell_count = 2;
    value.unique_buy_actors = 6;
    value.unique_sell_actors = 2;
    value.buy_arrival_rate_per_second = 16.0;
    value.sell_arrival_rate_per_second = 4.0;
    value.count_imbalance = 0.6;
    value.buy_quote_quantity = 4.5;
    value.sell_quote_quantity = 0.8;
    value.net_quote_quantity = 3.7;
    value.quote_flow_imbalance = 3.7 / 5.3;
    value.quote_flow_velocity_per_second = 7.4;
    value.quote_flow_acceleration_per_second2 = 12.0;
    value
}

fn context_window() -> FastTrainingWindowSummary {
    let mut value = empty_window(2_000);
    value.buy_count = 12;
    value.sell_count = 8;
    value.unique_buy_actors = 8;
    value.unique_sell_actors = 6;
    value.count_imbalance = 0.2;
    value.buy_quote_quantity = 7.0;
    value.sell_quote_quantity = 3.0;
    value.net_quote_quantity = 4.0;
    value.quote_flow_imbalance = 0.4;
    value.quote_flow_velocity_per_second = 2.0;
    value.quote_flow_acceleration_per_second2 = 1.0;
    value
}

fn windows() -> Vec<FastTrainingWindowSummary> {
    DEFAULT_FAST_WINDOWS_MS
        .iter()
        .map(|window_ms| match *window_ms {
            500 => strong_signal_window(),
            2_000 => context_window(),
            other => empty_window(other),
        })
        .collect()
}

fn record(signature: &str, sequence: u64, at: i64) -> FastTrainingFeatureRecord {
    FastTrainingFeatureRecord {
        schema_name: FAST_TRAINING_FEATURE_SCHEMA_NAME,
        schema_version: FAST_TRAINING_FEATURE_SCHEMA_VERSION,
        decision_signature: signature.to_owned(),
        decision_ordinal: 0,
        decision_sequence: sequence,
        mint: "mint-life".to_owned(),
        quote_mint: "quote-life".to_owned(),
        venue: "pump_fun_bonding_curve".to_owned(),
        decision_observed_at_unix_ms: at,
        decision_provider: "helius".to_owned(),
        decision_source_observed_at_unix_ms: at - 1,
        decision_occurred_at_unix_ms: at - 2,
        decision_slot: 100 + sequence,
        decision_event_kind: "buy".to_owned(),
        decision_actor: None,
        decision_executable_entry_price_quote: 0.01,
        decision_entry_total_quote: Some(1.01),
        snapshot_as_of_unix_ms: at,
        snapshot_last_sequence: Some(sequence),
        snapshot_last_price_quote: Some(0.0101),
        last_reserve_context: None,
        last_lifecycle_event: None,
        windows: windows(),
    }
}

fn leg() -> Value {
    json!({
        "effective_fee_bps": 50,
        "expected_impact_bps": 20,
        "expected_slippage_bps": 20,
        "expected_latency_bps": 10,
        "network_fee_quote": 0.0001,
        "priority_fee_quote": 0.0,
        "expected_failure_cost_quote": 0.0
    })
}

fn execution() -> Value {
    json!({
        "cost_model": {
            "version": 1,
            "entry": leg(),
            "exit": leg()
        },
        "trade": {
            "base_quantity": 100.0,
            "executable_entry_price_quote": 0.0100,
            "forecast_exit_price_quote": 0.0120,
            "exit_capacity_base": 125.0,
            "required_edge_bps": 200,
            "risk_margin_bps": 100
        }
    })
}

fn request_value(posture: Value, evidence: Value) -> Value {
    json!({
        "schema_name": FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_NAME,
        "schema_version": FAST_DETERMINISTIC_ROW_REQUEST_SCHEMA_VERSION,
        "manifest": serde_json::from_str::<Value>(MANIFEST).unwrap(),
        "record": serde_json::to_value(record("sig-row", 42, 1_100)).unwrap(),
        "posture": posture,
        "evidence": evidence
    })
}

#[test]
fn exact_fl81_json_round_trip_decode_preserves_existing_record() {
    let original = record("sig-json", 42, 1_100);
    let payload = serde_json::to_string(&original).unwrap();
    let decoded = decode_fast_training_feature_record_json(&payload).unwrap();
    assert_eq!(decoded, original);

    let mut malformed = serde_json::to_value(&original).unwrap();
    malformed
        .as_object_mut()
        .unwrap()
        .insert("unexpected".to_owned(), json!(1));
    let error = decode_fast_training_feature_record_json(
        &serde_json::to_string(&malformed).unwrap(),
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("unknown") || error.contains("field"), "{error}");
}

#[test]
fn manifest_materialization_reconstructs_exact_selected_policy_objects() {
    let wire = decode_fast_deterministic_candidate_manifest_json(MANIFEST).unwrap();
    let candidate = materialize_fast_deterministic_candidate_manifest(&wire).unwrap();

    assert_eq!(candidate.lifecycle_policy.entry_baseline_kind, FastBaselineKind::ImpulseScalp);
    assert_eq!(candidate.lifecycle_policy.manager_baseline_kind, FastBaselineKind::LongerRunner);
    assert_eq!(candidate.lifecycle_policy.entry_target_exposure_fraction, 0.8);
    assert_eq!(candidate.lifecycle_policy.reduce_remaining_fraction, 0.5);

    let impulse = candidate.entry_policy.impulse_scalp().unwrap();
    assert_eq!(impulse.signal_window_ms, 500);
    assert_eq!(impulse.context_window_ms, 2_000);
    assert_eq!(impulse.min_buy_count, 5);
    assert_eq!(impulse.min_quote_flow_velocity_per_second, 3.0);

    let runner = candidate.manager_policy.longer_runner().unwrap();
    assert_eq!(runner.downside_risk_weight, 1.0);
    assert_eq!(runner.min_risk_adjusted_continuation_bps_for_hold, 100.0);
    assert_eq!(runner.max_risk_adjusted_continuation_bps_for_sell, -100.0);
}

#[test]
fn flat_impulse_request_delegates_to_exact_sealed_lifecycle_and_buys() {
    let payload = serde_json::to_string(&request_value(
        json!({"kind":"FLAT"}),
        json!({"kind":"IMPULSE_SCALP","execution":execution()}),
    ))
    .unwrap();

    let request = decode_fast_deterministic_row_request_json(&payload).unwrap();
    let result = evaluate_fast_deterministic_row_request(&request).unwrap();

    assert_eq!(result.schema_name, FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_NAME);
    assert_eq!(result.schema_version, FAST_DETERMINISTIC_ROW_RESULT_SCHEMA_VERSION);
    assert_eq!(
        result.candidate_fingerprint_sha256,
        "7377f016783f80c6d3935ff41efd7a66b8da280df13cd7be8d2e6c03146a8676"
    );
    assert_eq!(result.decision.action, "BUY");
    assert_eq!(result.decision.posture, "FLAT");
    assert_eq!(result.decision.current_exposure_fraction, None);
    assert_eq!(result.decision.target_exposure_fraction, 0.8);

    let encoded = encode_fast_deterministic_row_result_json(&result).unwrap();
    let repeated = encode_fast_deterministic_row_result_json(
        &evaluate_fast_deterministic_row_request(&request).unwrap(),
    )
    .unwrap();
    assert_eq!(encoded, repeated);
}

#[test]
fn open_longer_runner_derives_market_time_and_missing_continuation_reduces() {
    let payload = serde_json::to_string(&request_value(
        json!({
            "kind":"OPEN",
            "current_exposure_fraction":0.8,
            "opened_at_unix_ms":1_000
        }),
        json!({
            "kind":"LONGER_RUNNER",
            "protective":{
                "hard_stop_triggered":false,
                "risk_limit_exit_required":false,
                "liquidity_exit_required":false
            },
            "continuation":null
        }),
    ))
    .unwrap();

    let request = decode_fast_deterministic_row_request_json(&payload).unwrap();
    let result = evaluate_fast_deterministic_row_request(&request).unwrap();

    assert_eq!(result.decision.action, "REDUCE");
    assert_eq!(result.decision.posture, "OPEN");
    assert_eq!(result.decision.current_exposure_fraction, Some(0.8));
    assert_eq!(result.decision.target_exposure_fraction, 0.4);
}

#[test]
fn request_cannot_override_entry_market_or_timestamp() {
    let mut value = request_value(
        json!({"kind":"FLAT"}),
        json!({"kind":"IMPULSE_SCALP","execution":execution()}),
    );
    value["evidence"]["execution"]["market"] = json!("other-market");

    let error = decode_fast_deterministic_row_request_json(
        &serde_json::to_string(&value).unwrap(),
    )
    .unwrap_err()
    .to_string();
    assert!(error.contains("unknown") || error.contains("field"), "{error}");
}

#[test]
fn wrong_evidence_kind_for_manifest_posture_fails_closed() {
    let payload = serde_json::to_string(&request_value(
        json!({"kind":"FLAT"}),
        json!({
            "kind":"LONGER_RUNNER",
            "protective":{
                "hard_stop_triggered":false,
                "risk_limit_exit_required":false,
                "liquidity_exit_required":false
            },
            "continuation":null
        }),
    ))
    .unwrap();

    let request = decode_fast_deterministic_row_request_json(&payload).unwrap();
    let error = evaluate_fast_deterministic_row_request(&request)
        .unwrap_err()
        .to_string();
    assert!(error.contains("evidence") || error.contains("entry"), "{error}");
}

#[test]
fn offline_cli_stdout_matches_pure_row_encoder() {
    let payload = serde_json::to_string(&request_value(
        json!({"kind":"FLAT"}),
        json!({"kind":"IMPULSE_SCALP","execution":execution()}),
    ))
    .unwrap();
    let request = decode_fast_deterministic_row_request_json(&payload).unwrap();
    let expected = encode_fast_deterministic_row_result_json(
        &evaluate_fast_deterministic_row_request(&request).unwrap(),
    )
    .unwrap();

    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "shreks-fast-deterministic-row-{nanos}.json"
    ));
    fs::write(&path, payload).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_shreks-fast-deterministic-row"))
        .arg(&path)
        .output()
        .unwrap();
    let _ = fs::remove_file(&path);

    assert!(
        output.status.success(),
        "stderr={}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(String::from_utf8(output.stdout).unwrap(), expected);
}

#[test]
fn row_protocol_source_has_no_db_provider_paper_or_live_authority() {
    let source = include_str!("../src/fast_deterministic_row.rs");
    let binary = include_str!("../src/bin/shreks-fast-deterministic-row.rs");

    for forbidden in [
        "ShreksDb",
        "rusqlite",
        "reqwest",
        "ProviderConfig",
        "execute_fast_paper_buy",
        "PaperLedger",
        "RiskContext",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "row protocol must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "evaluate_fast_deterministic_lifecycle_batch",
        "hydrate_fast_baseline_snapshot",
        "FastDeterministicCandidateManifestWire",
        "FastTrainingFeatureRecord",
        "Sha256",
    ] {
        assert!(
            source.contains(required),
            "row protocol must compose sealed evidence authorities: {required}"
        );
    }

    assert!(!binary.contains("ShreksDb"));
    assert!(!binary.contains("reqwest"));
    assert!(!binary.contains("RuntimeMode"));
}
