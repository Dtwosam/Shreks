use shreks_core::{
    FastBaselineKind, FastBaselineNotApplicable, FastBaselinePosture,
    FastBaselineReplayAssessment, FastCampaignActionConstraintsWire,
    FastCampaignContinuousActionPolicyWire, FastCampaignDecisionBatchWire,
    FastCampaignDecisionPositionWire, FastCampaignDecisionRequestWire,
    FastMarketKey, VenueId,
    FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME, FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
    IMPULSE_SCALP_BASELINE_VERSION,
};
use shreks_storage::{
    prove_fast_baseline_population_parity, FastBaselineCampaignAssessment,
    FastBaselineCampaignBatchAssessment, FAST_BASELINE_CAMPAIGN_BATCH_VERSION,
    FAST_BASELINE_CAMPAIGN_VERSION, FAST_BASELINE_POPULATION_PARITY_VERSION,
    FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
};

fn market() -> FastMarketKey {
    FastMarketKey::new(
        "mint-parity",
        "quote-parity",
        VenueId::PumpFunBondingCurve,
    )
    .unwrap()
}

fn learned_policy() -> FastCampaignContinuousActionPolicyWire {
    FastCampaignContinuousActionPolicyWire {
        version: 1,
        horizons_ms: vec![1_000],
        entry_exposure_candidates: vec![1.0],
        reduce_target_exposure_candidates: vec![0.5],
        adverse_excursion_weight: 1.0,
        reversal_penalty_bps: 10.0,
        route_unavailability_penalty_bps: 10.0,
        horizon_disagreement_weight: 1.0,
        minimum_buy_value_bps: 1.0,
        minimum_hold_value_bps: 1.0,
        missing_forecast_open_action: "SELL".to_owned(),
    }
}

fn constraints() -> FastCampaignActionConstraintsWire {
    FastCampaignActionConstraintsWire {
        max_exposure_fraction: 1.0,
        buy_economically_allowed: true,
        expected_future_exit_cost_bps: 10.0,
        reduce_execution_costs: vec![],
        sell_executable: true,
        sell_now_cost_bps: 10.0,
        force_sell: false,
    }
}

fn learned_decision(
    source_event_id: &str,
    sequence: u64,
    at: i64,
    position: FastCampaignDecisionPositionWire,
) -> FastCampaignDecisionRequestWire {
    FastCampaignDecisionRequestWire {
        source_event_id: source_event_id.to_owned(),
        market_key: "pump_fun_bonding_curve:mint-parity:quote-parity".to_owned(),
        source_sequence: sequence,
        as_of_unix_ms: at,
        features: vec![],
        position,
        constraints: constraints(),
    }
}

fn learned_batch() -> FastCampaignDecisionBatchWire {
    FastCampaignDecisionBatchWire {
        schema_name: FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME.to_owned(),
        schema_version: FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
        policy: learned_policy(),
        decisions: vec![
            learned_decision(
                "sig-a:0",
                1,
                1_000,
                FastCampaignDecisionPositionWire::Open {
                    current_exposure_fraction: 0.5,
                },
            ),
            learned_decision(
                "sig-b:0",
                2,
                1_100,
                FastCampaignDecisionPositionWire::Open {
                    current_exposure_fraction: 0.5,
                },
            ),
        ],
    }
}

fn baseline_decision(source_event_id: &str, sequence: u64, at: i64) -> FastBaselineCampaignAssessment {
    FastBaselineCampaignAssessment {
        version: FAST_BASELINE_CAMPAIGN_VERSION,
        hydration_version: FAST_BASELINE_SNAPSHOT_HYDRATION_VERSION,
        replay_version: 1,
        source_event_id: source_event_id.to_owned(),
        market_key: "pump_fun_bonding_curve:mint-parity:quote-parity".to_owned(),
        source_sequence: sequence,
        as_of_unix_ms: at,
        posture: FastBaselinePosture::Open,
        baseline_kind: FastBaselineKind::ImpulseScalp,
        baseline_version: IMPULSE_SCALP_BASELINE_VERSION,
        assessment: FastBaselineReplayAssessment::NotApplicable(FastBaselineNotApplicable {
            version: 1,
            baseline_kind: FastBaselineKind::ImpulseScalp,
            baseline_version: IMPULSE_SCALP_BASELINE_VERSION,
            actual_posture: FastBaselinePosture::Open,
            required_posture: FastBaselinePosture::Flat,
            market: market(),
            as_of_unix_ms: at,
        }),
    }
}

fn baseline_batch() -> FastBaselineCampaignBatchAssessment {
    FastBaselineCampaignBatchAssessment {
        version: FAST_BASELINE_CAMPAIGN_BATCH_VERSION,
        baseline_kind: FastBaselineKind::ImpulseScalp,
        baseline_version: IMPULSE_SCALP_BASELINE_VERSION,
        decisions: vec![
            baseline_decision("sig-a:0", 1, 1_000),
            baseline_decision("sig-b:0", 2, 1_100),
        ],
    }
}

#[test]
fn exact_learned_and_baseline_population_parity_succeeds() {
    let proof = prove_fast_baseline_population_parity(
        &learned_batch(),
        &baseline_batch(),
    )
    .unwrap();

    assert_eq!(proof.version, FAST_BASELINE_POPULATION_PARITY_VERSION);
    assert_eq!(proof.learned_schema_version, FAST_CAMPAIGN_DECISION_SCHEMA_VERSION);
    assert_eq!(
        proof.baseline_batch_version,
        FAST_BASELINE_CAMPAIGN_BATCH_VERSION
    );
    assert_eq!(proof.baseline_kind, FastBaselineKind::ImpulseScalp);
    assert_eq!(proof.baseline_version, IMPULSE_SCALP_BASELINE_VERSION);
    assert_eq!(proof.decision_count, 2);
    assert_eq!(proof.first_source_event_id, "sig-a:0");
    assert_eq!(proof.last_source_event_id, "sig-b:0");
}

#[test]
fn source_event_id_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions[1].source_event_id = "different:0".to_owned();

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("source_event_id") || error.contains("source event"), "{error}");
}

#[test]
fn market_key_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions[1].market_key =
        "pump_swap:mint-parity:quote-parity".to_owned();

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("market"), "{error}");
}

#[test]
fn sequence_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions[1].source_sequence = 3;

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("sequence"), "{error}");
}

#[test]
fn timestamp_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions[1].as_of_unix_ms = 1_101;

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("timestamp") || error.contains("as-of"), "{error}");
}

#[test]
fn posture_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions[1].position = FastCampaignDecisionPositionWire::Flat;

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("posture") || error.contains("position"), "{error}");
}

#[test]
fn count_mismatch_fails_closed() {
    let mut learned = learned_batch();
    learned.decisions.pop();

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(error.contains("count"), "{error}");
}

#[test]
fn reversed_learned_order_fails_instead_of_sorting() {
    let mut learned = learned_batch();
    learned.decisions.reverse();

    let error = prove_fast_baseline_population_parity(&learned, &baseline_batch())
        .unwrap_err()
        .to_string();
    assert!(
        error.contains("source") || error.contains("index") || error.contains("sequence"),
        "{error}"
    );
}

#[test]
fn population_parity_proof_is_deterministic() {
    let first = prove_fast_baseline_population_parity(
        &learned_batch(),
        &baseline_batch(),
    )
    .unwrap();
    let second = prove_fast_baseline_population_parity(
        &learned_batch(),
        &baseline_batch(),
    )
    .unwrap();

    assert_eq!(first, second);
}

#[test]
fn population_parity_source_has_no_execution_or_runtime_authority() {
    let source = include_str!("../src/fast_population_parity.rs");

    for forbidden in [
        "rusqlite",
        "reqwest",
        "std::fs",
        "std::net",
        "shreks_providers",
        "FastPaper",
        "PaperLedger",
        "RiskContext",
        "TradeIntent",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "registry",
        "promote",
    ] {
        assert!(
            !source.contains(forbidden),
            "population parity must not gain forbidden authority: {forbidden}"
        );
    }

    for required in [
        "source_event_id",
        "market_key",
        "source_sequence",
        "as_of_unix_ms",
        "FastCampaignDecisionPositionWire",
        "FastBaselinePosture",
    ] {
        assert!(
            source.contains(required),
            "population parity must compare required field: {required}"
        );
    }
}
