const OBSERVE_SOURCE: &str = include_str!("../src/bin/shreks-observe.rs");

// Production systemd gives the observer 30 seconds to stop before SIGKILL.
#[test]
fn realtime_shutdown_cleanup_has_an_application_deadline() {
    for required in [
        "PUMP_REALTIME_SHUTDOWN_DRAIN_TIMEOUT",
        "finish_realtime_writer_shutdown",
    ] {
        assert!(
            OBSERVE_SOURCE.contains(required),
            "normal realtime shutdown must bound post-signal cleanup before systemd's stop deadline: {required}"
        );
    }
}

#[test]
fn normal_realtime_shutdown_does_not_wait_on_aborted_auxiliary_tasks() {
    let start = OBSERVE_SOURCE
        .find("observation_result = &mut observation => {")
        .expect("normal observation completion branch must exist");
    let end = OBSERVE_SOURCE[start..]
        .find("target_publisher_result = &mut target_publisher => {")
        .map(|offset| start + offset)
        .expect("target publisher failure branch must follow normal shutdown");
    let normal_shutdown = &OBSERVE_SOURCE[start..end];

    for forbidden in [
        "let _ = target_publisher.await;",
        "let _ = forwarder.await;",
        "let _ = normalizer.await;",
    ] {
        assert!(
            !normal_shutdown.contains(forbidden),
            "normal realtime shutdown must not wait indefinitely after aborting an auxiliary task: {forbidden}"
        );
    }
}
