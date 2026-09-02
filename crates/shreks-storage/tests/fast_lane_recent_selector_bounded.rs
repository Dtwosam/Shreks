const FAST_LANE_METADATA_SOURCE: &str = include_str!("../src/fast_lane_metadata.rs");

#[test]
fn recent_pumpswap_normalizable_selector_bounds_raw_and_lifecycle_work() {
    let start = FAST_LANE_METADATA_SOURCE
        .find("pub fn recent_normalizable_pump_swap_trade_evidence")
        .expect("recent PumpSwap selector must exist");
    let end = FAST_LANE_METADATA_SOURCE[start..]
        .find("fn recent_pump_rows")
        .map(|offset| start + offset)
        .expect("recent Pump raw helper must follow PumpSwap selector");
    let selector = &FAST_LANE_METADATA_SOURCE[start..end];

    for required in [
        "recent_pumpswap_rows AS MATERIALIZED",
        "recent_pools AS MATERIALIZED",
        "JOIN recent_pools AS recent",
        "recent.pool = lifecycle.pool_address",
        "ORDER BY p.observed_at_unix_ms DESC",
    ] {
        assert!(
            selector.contains(required),
            "recent PumpSwap canonical selector must bound raw/lifecycle work before eligibility checks: missing {required}"
        );
    }

    assert!(
        selector.find("LIMIT ?").is_some(),
        "recent PumpSwap selector must cap the materialized raw frontier"
    );
}
