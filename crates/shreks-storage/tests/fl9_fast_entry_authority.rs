use std::{fs, process::Command, time::{SystemTime, UNIX_EPOCH}};

use shreks_storage::{
    decode_fast_deterministic_entry_authority_request_json,
    derive_fast_deterministic_entry_authority,
    encode_fast_deterministic_entry_authority_result_json,
    FastDeterministicEntryAuthorityRequestWire,
    FastEntryExecutionWire,
    FastExecutionCostModelWire,
    FastExecutionLegCostWire,
    FastExecutionTradeWire,
    FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME,
    FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION,
    FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME,
    FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION,
};


fn leg(
    fee: u32,
    impact: u32,
    slippage: u32,
    latency: u32,
    network: f64,
    priority: f64,
    failure: f64,
) -> FastExecutionLegCostWire {
    FastExecutionLegCostWire {
        effective_fee_bps: fee,
        expected_impact_bps: impact,
        expected_slippage_bps: slippage,
        expected_latency_bps: latency,
        network_fee_quote: network,
        priority_fee_quote: priority,
        expected_failure_cost_quote: failure,
    }
}


fn request() -> FastDeterministicEntryAuthorityRequestWire {
    FastDeterministicEntryAuthorityRequestWire {
        schema_name: FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION,
        mint: "mint-authority".to_owned(),
        quote_mint: "quote-authority".to_owned(),
        decision_executable_entry_price_quote: 10.0,
        execution: FastEntryExecutionWire {
            cost_model: FastExecutionCostModelWire {
                version: 1,
                entry: leg(50, 20, 30, 10, 0.01, 0.02, 0.03),
                exit: leg(50, 20, 20, 10, 0.01, 0.0, 0.0),
            },
            trade: FastExecutionTradeWire {
                base_quantity: 10.0,
                executable_entry_price_quote: 10.0,
                forecast_exit_price_quote: 12.0,
                exit_capacity_base: 10.0,
                required_edge_bps: 200,
                risk_margin_bps: 100,
            },
        },
    }
}


#[test]
fn derives_paper_authority_from_exact_fl3_execution_economics() {
    let result = derive_fast_deterministic_entry_authority(&request()).unwrap();

    assert_eq!(result.schema_name, FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME);
    assert_eq!(result.schema_version, FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION);
    assert_eq!(result.mint, "mint-authority");
    assert_eq!(result.quote_mint, "quote-authority");
    assert_eq!(result.intended_base_quantity, 10.0);
    assert_eq!(result.decision_executable_entry_price_quote, 10.0);
    assert!((result.maximum_acceptable_entry_price_quote - 11.401592194597294).abs() < 1e-12);
    assert_eq!(result.expected_entry_variable_cost_bps, 110);
    assert!((result.expected_entry_fixed_cost_quote - 0.06).abs() < 1e-12);
    assert_eq!(result.result_fingerprint_sha256.len(), 64);

    let encoded = encode_fast_deterministic_entry_authority_result_json(&result).unwrap();
    assert!(!encoded.contains(char::is_whitespace));
}


#[test]
fn request_decoder_is_strict_and_decision_price_drift_fails_closed() {
    let encoded = serde_json::to_string(&request()).unwrap();
    let decoded = decode_fast_deterministic_entry_authority_request_json(&encoded).unwrap();
    assert_eq!(decoded, request());

    let mut drift = request();
    drift.execution.trade.executable_entry_price_quote = 9.9;
    let error = derive_fast_deterministic_entry_authority(&drift).unwrap_err();
    assert!(error.to_string().contains("decision") || error.to_string().contains("price"));

    let mut unknown: serde_json::Value = serde_json::from_str(&encoded).unwrap();
    unknown
        .as_object_mut()
        .unwrap()
        .insert("unexpected".to_owned(), serde_json::json!(true));
    let error = decode_fast_deterministic_entry_authority_request_json(
        &serde_json::to_string(&unknown).unwrap(),
    )
    .unwrap_err();
    assert!(error.to_string().contains("unknown") || error.to_string().contains("field"));
}


#[test]
fn offline_binary_runs_the_same_authoritative_fl3_derivation() {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!(
        "shreks-fast-entry-authority-{nanos}.json"
    ));
    fs::write(&path, serde_json::to_string(&request()).unwrap()).unwrap();

    let output = Command::new(env!("CARGO_BIN_EXE_shreks-fast-entry-authority"))
        .arg(&path)
        .output()
        .unwrap();
    fs::remove_file(&path).unwrap();

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let result: shreks_storage::FastDeterministicEntryAuthorityResultWire =
        serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result.mint, "mint-authority");
    assert!((result.maximum_acceptable_entry_price_quote - 11.401592194597294).abs() < 1e-12);
    assert_eq!(result.expected_entry_variable_cost_bps, 110);
}
