use shreks_providers::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID},
    realtime_scope::{
        pump_realtime_initial_mentions, pump_realtime_logs_subscribe_request,
    },
};

#[test]
fn logs_subscribe_request_mentions_exactly_one_explicit_pubkey() {
    let request = pump_realtime_logs_subscribe_request(7, "pool-one").unwrap();

    assert_eq!(request["method"], "logsSubscribe");
    assert_eq!(request["id"], 7);
    assert_eq!(request["params"][0]["mentions"].as_array().unwrap().len(), 1);
    assert_eq!(request["params"][0]["mentions"][0], "pool-one");
    assert_eq!(request["params"][1]["commitment"], "confirmed");

    assert!(pump_realtime_logs_subscribe_request(8, "").is_err());
    assert!(pump_realtime_logs_subscribe_request(8, "   ").is_err());
}

#[test]
fn initial_subscription_plan_is_pump_plus_tracked_pools_never_global_pumpswap() {
    let targets = vec!["pool-a".to_owned(), "pool-b".to_owned()];
    let mentions = pump_realtime_initial_mentions(&targets).unwrap();

    assert_eq!(
        mentions,
        vec![
            PUMP_PROGRAM_ID.to_owned(),
            "pool-a".to_owned(),
            "pool-b".to_owned(),
        ]
    );
    assert!(!mentions.iter().any(|mention| mention == PUMP_AMM_PROGRAM_ID));
}

#[test]
fn empty_target_set_is_pump_only_and_duplicate_or_blank_targets_fail_closed() {
    assert_eq!(
        pump_realtime_initial_mentions(&[]).unwrap(),
        vec![PUMP_PROGRAM_ID.to_owned()]
    );

    assert!(pump_realtime_initial_mentions(&["pool-a".to_owned(), "pool-a".to_owned()]).is_err());
    assert!(pump_realtime_initial_mentions(&["pool-a".to_owned(), " ".to_owned()]).is_err());
    assert!(pump_realtime_initial_mentions(&[PUMP_AMM_PROGRAM_ID.to_owned()]).is_err());
}
