use std::{
    fs,
    path::{Path, PathBuf},
    process,
    time::{SystemTime, UNIX_EPOCH},
};

use shreks_core::ProviderId;
use shreks_storage::{FastRealtimeCoverageSession, ShreksDb};

fn unique_test_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "shreks-fast-coverage-{label}-{}-{nanos}",
        process::id()
    ))
}

fn cleanup_dir(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn coverage_session_opens_extends_and_reopens_exactly() {
    let root = unique_test_dir("roundtrip");
    let db_path = root.join("shreks.db");
    let db = ShreksDb::open(&db_path).unwrap();

    let first = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            1_000,
            100,
            "sig-a",
        )
        .unwrap();
    assert_eq!(
        first,
        FastRealtimeCoverageSession {
            session_id: 1,
            provider: ProviderId::SolanaPublic,
            process_session_sequence: 1,
            first_notification_observed_at_unix_ms: 1_000,
            last_notification_observed_at_unix_ms: 1_000,
            first_notification_slot: 100,
            last_notification_slot: 100,
            first_notification_signature: "sig-a".to_owned(),
            last_notification_signature: "sig-a".to_owned(),
            notification_count: 1,
        }
    );

    let extended = db
        .extend_fast_realtime_coverage_session(
            first.session_id,
            ProviderId::SolanaPublic,
            1,
            1_500,
            101,
            "sig-b",
        )
        .unwrap();
    assert_eq!(extended.first_notification_observed_at_unix_ms, 1_000);
    assert_eq!(extended.last_notification_observed_at_unix_ms, 1_500);
    assert_eq!(extended.first_notification_slot, 100);
    assert_eq!(extended.last_notification_slot, 101);
    assert_eq!(extended.first_notification_signature, "sig-a");
    assert_eq!(extended.last_notification_signature, "sig-b");
    assert_eq!(extended.notification_count, 2);

    drop(db);
    let reopened = ShreksDb::open(&db_path).unwrap();
    assert_eq!(
        reopened.fast_realtime_coverage_sessions().unwrap(),
        vec![extended]
    );

    cleanup_dir(&root);
}

#[test]
fn new_process_session_sequence_creates_a_distinct_durable_session() {
    let root = unique_test_dir("distinct");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    let first = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            1_000,
            100,
            "sig-a",
        )
        .unwrap();
    let second = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            2_000,
            200,
            "sig-c",
        )
        .unwrap();

    assert_ne!(first.session_id, second.session_id);
    assert_eq!(db.fast_realtime_coverage_sessions().unwrap().len(), 2);

    cleanup_dir(&root);
}

#[test]
fn coverage_extension_rejects_identity_or_clock_regression() {
    let root = unique_test_dir("reject");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();
    let first = db
        .begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            4,
            1_000,
            100,
            "sig-a",
        )
        .unwrap();

    let provider = db
        .extend_fast_realtime_coverage_session(
            first.session_id,
            ProviderId::Alchemy,
            4,
            1_100,
            101,
            "sig-b",
        )
        .unwrap_err();
    assert!(provider.to_string().contains("identity changed"));

    let time = db
        .extend_fast_realtime_coverage_session(
            first.session_id,
            ProviderId::SolanaPublic,
            4,
            999,
            101,
            "sig-b",
        )
        .unwrap_err();
    assert!(time.to_string().contains("time moved backward"));

    let slot = db
        .extend_fast_realtime_coverage_session(
            first.session_id,
            ProviderId::SolanaPublic,
            4,
            1_100,
            99,
            "sig-b",
        )
        .unwrap_err();
    assert!(slot.to_string().contains("slot moved backward"));

    cleanup_dir(&root);
}

#[test]
fn coverage_input_requires_positive_session_nonnegative_time_and_signature() {
    let root = unique_test_dir("validation");
    let db = ShreksDb::open(root.join("shreks.db")).unwrap();

    for result in [
        db.begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            0,
            1_000,
            100,
            "sig",
        ),
        db.begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            -1,
            100,
            "sig",
        ),
        db.begin_fast_realtime_coverage_session(
            ProviderId::SolanaPublic,
            1,
            1_000,
            100,
            " ",
        ),
    ] {
        assert!(result.is_err());
    }

    cleanup_dir(&root);
}
