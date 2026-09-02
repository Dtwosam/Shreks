use std::process::Command;

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_shreks-observe")
}

#[test]
fn benchmark_subcommand_reports_capacity_latency_and_memory_metrics() {
    let output = Command::new(binary())
        .args(["fast-state-benchmark", "16", "2000", "64"])
        .output()
        .expect("benchmark command must launch");

    assert!(
        output.status.success(),
        "benchmark failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("benchmark stdout must be UTF-8");
    for key in [
        "benchmark_version",
        "active_markets",
        "burst_events",
        "state_update_samples",
        "events_per_second",
        "apply_latency_p50_ns",
        "apply_latency_p95_ns",
        "apply_latency_p99_ns",
        "apply_latency_max_ns",
        "state_update_latency_p50_ns",
        "state_update_latency_p95_ns",
        "state_update_latency_p99_ns",
        "state_update_latency_max_ns",
        "rss_before_bytes",
        "rss_after_state_init_bytes",
        "rss_state_init_delta_bytes",
        "rss_bytes_per_active_market",
        "rss_after_burst_bytes",
        "snapshot_checksum",
    ] {
        assert!(
            stdout.lines().any(|line| line.starts_with(&format!("{key}="))),
            "missing {key} in benchmark output:\n{stdout}"
        );
    }

    assert!(stdout.contains("benchmark_version=1"));
    assert!(stdout.contains("active_markets=16"));
    assert!(stdout.contains("burst_events=2000"));
    assert!(stdout.contains("state_update_samples=64"));
}

#[test]
fn benchmark_subcommand_rejects_zero_sized_workloads() {
    let output = Command::new(binary())
        .args(["fast-state-benchmark", "0", "100", "10"])
        .output()
        .expect("benchmark command must launch");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains("active_markets must be greater than zero"),
        "unexpected stderr: {stderr}"
    );
}
