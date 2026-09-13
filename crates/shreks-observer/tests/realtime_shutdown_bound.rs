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
