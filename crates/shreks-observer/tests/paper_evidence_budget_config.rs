use std::collections::HashMap;

#[path = "../src/bin/shreks-paper-evidence/config.rs"]
mod config;

use config::PaperEvidenceRuntimeConfig;

fn valid_env() -> HashMap<&'static str, &'static str> {
    HashMap::from([
        ("SHREKS_DB_PATH", "data/shreks.db"),
        ("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS", "30"),
        ("SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS", "120"),
        ("SHREKS_PAPER_EVIDENCE_MAX_PAIR_AGE_SECONDS", "1800"),
        ("SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS", "60"),
        ("SHREKS_PAPER_EVIDENCE_MARKET_SOURCES", "dexscreener"),
        ("SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES", "16"),
        ("SHREKS_PAPER_PROBE_POLICY_VERSION", "paper-probe-v1"),
        ("SHREKS_PAPER_QUOTE_ASSET_MINT", "So11111111111111111111111111111111111111112"),
        ("SHREKS_PAPER_QUOTE_TAKER", "Taker111111111111111111111111111111111111"),
        ("SHREKS_PAPER_ENTRY_INPUT_AMOUNT", "100000000"),
        ("SHREKS_PAPER_EXIT_INPUT_AMOUNT", "1000000"),
        ("SHREKS_PAPER_SLIPPAGE_BPS", "75"),
        ("SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE", "100"),
        ("SHREKS_PAPER_DISTRIBUTION_MAX_PAGES", "2"),
        ("SHREKS_PAPER_HOLDER_REFRESH_SECONDS", "300"),
        ("SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS", "1000"),
        ("HELIUS_API_KEY", "helius-test-secret"),
        ("JUPITER_API_KEY", "jupiter-test-secret"),
    ])
}

fn from_map(values: &HashMap<&str, &str>) -> Result<PaperEvidenceRuntimeConfig, config::PaperEvidenceRuntimeConfigError> {
    PaperEvidenceRuntimeConfig::from_lookup(|name| values.get(name).map(|value| (*value).to_owned()))
}

#[test]
fn paper_evidence_cost_controls_are_required_and_parsed() {
    let config = from_map(&valid_env()).expect("valid bounded config");
    assert_eq!(config.holder_refresh.as_secs(), 300);
    assert_eq!(config.helius_max_requests_per_process, 1000);

    for name in [
        "SHREKS_PAPER_HOLDER_REFRESH_SECONDS",
        "SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS",
    ] {
        let mut missing = valid_env();
        missing.remove(name);
        let error = from_map(&missing).expect_err("cost control must be required");
        assert!(error.to_string().contains(name), "missing {name}: {error}");

        for invalid in ["0", "-1", "nope"] {
            let mut values = valid_env();
            values.insert(name, invalid);
            let error = from_map(&values).expect_err("invalid cost control must fail");
            assert!(error.to_string().contains(name), "{name}={invalid}: {error}");
        }
    }
}

#[test]
fn env_example_declares_bounded_paper_evidence_controls() {
    let env_example = include_str!("../../../.env.example");
    assert!(env_example.contains("SHREKS_PAPER_HOLDER_REFRESH_SECONDS="));
    assert!(env_example.contains("SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS="));
}
