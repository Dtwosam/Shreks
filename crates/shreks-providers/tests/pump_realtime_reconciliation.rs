use std::collections::BTreeMap;

use shreks_providers::realtime_scope::{
    pump_realtime_subscription_changes, PumpRealtimeSubscriptionChange,
};

#[test]
fn reconciliation_removes_stale_before_adding_new_targets() {
    let current = BTreeMap::from([
        ("pool-a".to_owned(), 11_u64),
        ("pool-b".to_owned(), 12_u64),
    ]);
    let targets = vec!["pool-b".to_owned(), "pool-c".to_owned()];

    let changes = pump_realtime_subscription_changes(&current, &targets).unwrap();
    assert_eq!(
        changes,
        vec![
            PumpRealtimeSubscriptionChange::Unsubscribe {
                pool: "pool-a".to_owned(),
                subscription_id: 11,
            },
            PumpRealtimeSubscriptionChange::Subscribe {
                pool: "pool-c".to_owned(),
            },
        ]
    );
}

#[test]
fn reconciliation_is_noop_when_targets_are_unchanged() {
    let current = BTreeMap::from([
        ("pool-a".to_owned(), 11_u64),
        ("pool-b".to_owned(), 12_u64),
    ]);
    let targets = vec!["pool-a".to_owned(), "pool-b".to_owned()];

    assert!(pump_realtime_subscription_changes(&current, &targets)
        .unwrap()
        .is_empty());
}

#[test]
fn reconciliation_order_is_canonical_and_invalid_scope_fails_closed() {
    let current = BTreeMap::from([
        ("pool-z".to_owned(), 21_u64),
        ("pool-a".to_owned(), 22_u64),
    ]);
    let targets = vec!["pool-c".to_owned(), "pool-b".to_owned()];

    let changes = pump_realtime_subscription_changes(&current, &targets).unwrap();
    assert_eq!(
        changes,
        vec![
            PumpRealtimeSubscriptionChange::Unsubscribe {
                pool: "pool-a".to_owned(),
                subscription_id: 22,
            },
            PumpRealtimeSubscriptionChange::Unsubscribe {
                pool: "pool-z".to_owned(),
                subscription_id: 21,
            },
            PumpRealtimeSubscriptionChange::Subscribe {
                pool: "pool-c".to_owned(),
            },
            PumpRealtimeSubscriptionChange::Subscribe {
                pool: "pool-b".to_owned(),
            },
        ]
    );

    assert!(pump_realtime_subscription_changes(
        &BTreeMap::new(),
        &["pool-a".to_owned(), "pool-a".to_owned()]
    )
    .is_err());
}
