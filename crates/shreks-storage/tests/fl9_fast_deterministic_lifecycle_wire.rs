use sha2::{Digest, Sha256};

use shreks_storage::{
    decode_fast_deterministic_lifecycle_results_json,
    encode_fast_deterministic_lifecycle_results_json,
    FastDeterministicLifecycleDecisionWire, FastDeterministicLifecyclePolicyWire,
    FastDeterministicLifecycleResultsWire,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME,
    FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
};

const GOLDEN: &str = include_str!(
    "../../../python/tests/fixtures/fast_deterministic_lifecycle_results_v1.json"
);

fn seal_for_semantic_validation(
    mut results: FastDeterministicLifecycleResultsWire,
) -> FastDeterministicLifecycleResultsWire {
    let mut value = serde_json::to_value(&results).unwrap();
    value
        .as_object_mut()
        .unwrap()
        .remove("batch_fingerprint_sha256");
    let payload = serde_json::to_vec(&value).unwrap();
    results.batch_fingerprint_sha256 = format!("{:x}", Sha256::digest(payload));
    results
}

#[test]
fn shared_golden_lifecycle_wire_round_trips_exactly() {
    let decoded = decode_fast_deterministic_lifecycle_results_json(GOLDEN).unwrap();

    assert_eq!(
        decoded.schema_name,
        FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME
    );
    assert_eq!(
        decoded.schema_version,
        FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION
    );
    assert_eq!(
        decoded.batch_fingerprint_sha256,
        "bd7e267a2a7cf836f6db87ad75306676efaf500446e62097d58004559812a576"
    );
    assert_eq!(decoded.policy.entry_baseline_kind, "IMPULSE_SCALP");
    assert_eq!(decoded.policy.manager_baseline_kind, "LONGER_RUNNER");
    assert_eq!(decoded.decisions.len(), 2);
    assert_eq!(decoded.decisions[0].action, "BUY");
    assert_eq!(decoded.decisions[0].posture, "FLAT");
    assert_eq!(decoded.decisions[0].current_exposure_fraction, None);
    assert_eq!(decoded.decisions[1].action, "REDUCE");
    assert_eq!(decoded.decisions[1].posture, "OPEN");
    assert_eq!(decoded.decisions[1].current_exposure_fraction, Some(0.8));

    assert_eq!(
        encode_fast_deterministic_lifecycle_results_json(&decoded).unwrap(),
        GOLDEN
    );
}

#[test]
fn lifecycle_wire_fingerprint_tampering_fails_closed() {
    let mut decoded = decode_fast_deterministic_lifecycle_results_json(GOLDEN).unwrap();
    decoded.decisions[1].target_exposure_fraction = 0.3;

    let error = encode_fast_deterministic_lifecycle_results_json(&decoded)
        .unwrap_err()
        .to_string();
    assert!(error.contains("fingerprint"), "{error}");
}

#[test]
fn lifecycle_wire_enforces_posture_action_and_explicit_target_semantics() {
    let policy = FastDeterministicLifecyclePolicyWire {
        version: 1,
        entry_baseline_kind: "IMPULSE_SCALP".to_owned(),
        manager_baseline_kind: "LONGER_RUNNER".to_owned(),
        entry_target_exposure_fraction: 0.8,
        reduce_remaining_fraction: 0.5,
    };

    let flat_reduce = seal_for_semantic_validation(FastDeterministicLifecycleResultsWire {
        schema_name: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
        policy: policy.clone(),
        decisions: vec![FastDeterministicLifecycleDecisionWire {
            source_event_id: "sig-a:0".to_owned(),
            market_key: "pump_fun_bonding_curve:mint-life:quote-life".to_owned(),
            source_sequence: 42,
            as_of_unix_ms: 1_100,
            posture: "FLAT".to_owned(),
            component_kind: "IMPULSE_SCALP".to_owned(),
            component_version: 1,
            action: "REDUCE".to_owned(),
            current_exposure_fraction: None,
            target_exposure_fraction: 0.4,
        }],
        batch_fingerprint_sha256: "0".repeat(64),
    });
    let error = encode_fast_deterministic_lifecycle_results_json(&flat_reduce)
        .unwrap_err()
        .to_string();
    assert!(error.contains("action") || error.contains("FLAT"), "{error}");

    let open_wrong_target = seal_for_semantic_validation(FastDeterministicLifecycleResultsWire {
        schema_name: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_LIFECYCLE_RESULTS_SCHEMA_VERSION,
        policy,
        decisions: vec![FastDeterministicLifecycleDecisionWire {
            source_event_id: "sig-b:0".to_owned(),
            market_key: "pump_fun_bonding_curve:mint-life:quote-life".to_owned(),
            source_sequence: 43,
            as_of_unix_ms: 1_200,
            posture: "OPEN".to_owned(),
            component_kind: "LONGER_RUNNER".to_owned(),
            component_version: 1,
            action: "REDUCE".to_owned(),
            current_exposure_fraction: Some(0.8),
            target_exposure_fraction: 0.3,
        }],
        batch_fingerprint_sha256: "0".repeat(64),
    });
    let error = encode_fast_deterministic_lifecycle_results_json(&open_wrong_target)
        .unwrap_err()
        .to_string();
    assert!(error.contains("target") || error.contains("REDUCE"), "{error}");
}

#[test]
fn lifecycle_wire_source_has_no_paper_execution_or_runtime_authority() {
    let source = include_str!("../src/fast_deterministic_lifecycle_wire.rs");

    for forbidden in [
        "rusqlite",
        "reqwest",
        "std::fs",
        "std::net",
        "shreks_providers",
        "PaperLedger",
        "RiskContext",
        "TradeIntent",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "lifecycle wire must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "fast_deterministic_lifecycle_to_wire",
        "batch_fingerprint_sha256",
        "FastDeterministicLifecycleBatchAssessment",
        "Sha256",
    ] {
        assert!(
            source.contains(required),
            "lifecycle wire must preserve required canonical seam: {required}"
        );
    }
}
