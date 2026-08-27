use std::collections::HashMap;

#[path = "../src/bin/shreks-paper-evidence/config.rs"]
mod config;

use config::PaperEvidenceRuntimeConfig;

fn valid_env() -> HashMap<&'static str, &'static str> {
    HashMap::from([
        ("SHREKS_DB_PATH", "data/shreks.db"),
        ("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS", "30"),
        ("SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS", "900"),
        (
            "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
            "60",
        ),
        ("SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES", "16"),
        ("SHREKS_PAPER_PROBE_POLICY_VERSION", "paper-probe-v1"),
        (
            "SHREKS_PAPER_QUOTE_ASSET_MINT",
            "So11111111111111111111111111111111111111112",
        ),
        ("SHREKS_PAPER_QUOTE_TAKER", "Taker111111111111111111111111111111111111"),
        ("SHREKS_PAPER_ENTRY_INPUT_AMOUNT", "100000000"),
        ("SHREKS_PAPER_EXIT_INPUT_AMOUNT", "1000000"),
        ("SHREKS_PAPER_SLIPPAGE_BPS", "75"),
        ("SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE", "100"),
        ("SHREKS_PAPER_DISTRIBUTION_MAX_PAGES", "2"),
        ("HELIUS_API_KEY", "helius-test-secret"),
        ("JUPITER_API_KEY", "jupiter-test-secret"),
    ])
}

fn from_map(values: &HashMap<&str, &str>) -> Result<PaperEvidenceRuntimeConfig, config::PaperEvidenceRuntimeConfigError> {
    PaperEvidenceRuntimeConfig::from_lookup(|name| values.get(name).map(|value| (*value).to_owned()))
}

#[test]
fn valid_config_builds_exact_bidirectional_probe_without_exposing_keys() {
    let values = valid_env();
    let config = from_map(&values).unwrap();
    config.require_providers().unwrap();

    assert_eq!(config.db_path.to_string_lossy(), "data/shreks.db");
    assert_eq!(config.cycle_interval.as_secs(), 30);
    assert_eq!(config.candidate_lookback_ms, 900_000);
    assert_eq!(config.preferred_min_pair_age_ms, 60_000);
    assert_eq!(config.max_candidates, 16);

    let candidate_mint = "Candidate111111111111111111111111111111111";
    let probe = config.probe_for(candidate_mint).unwrap();
    assert_eq!(probe.probe_policy_version, "paper-probe-v1");
    assert_eq!(probe.distribution_request.mint, candidate_mint);
    assert_eq!(probe.distribution_request.page_size, 100);
    assert_eq!(probe.distribution_request.max_pages, 2);

    assert_eq!(probe.exit_quote_request.input_mint, candidate_mint);
    assert_eq!(
        probe.exit_quote_request.output_mint,
        "So11111111111111111111111111111111111111112"
    );
    assert_eq!(probe.exit_quote_request.amount, 1_000_000);
    assert_eq!(
        probe.exit_quote_request.taker,
        "Taker111111111111111111111111111111111111"
    );
    assert_eq!(probe.exit_quote_request.slippage_bps, 75);

    let entry = probe.entry_quote_request.as_ref().unwrap();
    assert_eq!(
        entry.input_mint,
        "So11111111111111111111111111111111111111112"
    );
    assert_eq!(entry.output_mint, candidate_mint);
    assert_eq!(entry.amount, 100_000_000);
    assert_eq!(entry.taker, probe.exit_quote_request.taker);
    assert_eq!(entry.slippage_bps, probe.exit_quote_request.slippage_bps);

    let debug = format!("{config:?}");
    assert!(!debug.contains("helius-test-secret"));
    assert!(!debug.contains("jupiter-test-secret"));
}

#[test]
fn missing_or_blank_required_runtime_inputs_fail_closed() {
    let required = [
        "SHREKS_DB_PATH",
        "SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS",
        "SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS",
        "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
        "SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES",
        "SHREKS_PAPER_PROBE_POLICY_VERSION",
        "SHREKS_PAPER_QUOTE_ASSET_MINT",
        "SHREKS_PAPER_QUOTE_TAKER",
        "SHREKS_PAPER_ENTRY_INPUT_AMOUNT",
        "SHREKS_PAPER_EXIT_INPUT_AMOUNT",
        "SHREKS_PAPER_SLIPPAGE_BPS",
        "SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE",
        "SHREKS_PAPER_DISTRIBUTION_MAX_PAGES",
    ];

    for name in required {
        let mut missing = valid_env();
        missing.remove(name);
        let error = from_map(&missing).unwrap_err();
        assert!(error.to_string().contains(name), "missing {name}: {error}");

        let mut blank = valid_env();
        blank.insert(name, "   ");
        let error = from_map(&blank).unwrap_err();
        assert!(error.to_string().contains(name), "blank {name}: {error}");
    }
}

#[test]
fn invalid_numeric_runtime_inputs_fail_closed() {
    for (name, invalid_values) in [
        ("SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS", &["0", "-1", "nope"][..]),
        ("SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS", &["0", "-1", "nope"][..]),
        (
            "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
            &["-1", "nope"][..],
        ),
        ("SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES", &["0", "-1", "nope"][..]),
        ("SHREKS_PAPER_ENTRY_INPUT_AMOUNT", &["0", "-1", "nope"][..]),
        ("SHREKS_PAPER_EXIT_INPUT_AMOUNT", &["0", "-1", "nope"][..]),
        ("SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE", &["0", "1001", "nope"][..]),
        ("SHREKS_PAPER_DISTRIBUTION_MAX_PAGES", &["0", "-1", "nope"][..]),
        ("SHREKS_PAPER_SLIPPAGE_BPS", &["10001", "-1", "nope"][..]),
    ] {
        for invalid in invalid_values {
            let mut values = valid_env();
            values.insert(name, invalid);
            let error = from_map(&values).unwrap_err();
            assert!(error.to_string().contains(name), "{name}={invalid}: {error}");
        }
    }
}

#[test]
fn preferred_pair_age_cannot_exceed_evidence_lookback() {
    let mut values = valid_env();
    values.insert("SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS", "59");
    values.insert(
        "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
        "60",
    );
    let error = from_map(&values).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS")
    );
}

#[test]
fn quote_asset_equal_to_candidate_is_rejected_when_building_probe() {
    let values = valid_env();
    let config = from_map(&values).unwrap();
    let error = config
        .probe_for("So11111111111111111111111111111111111111112")
        .unwrap_err();
    assert!(error.to_string().contains("candidate"));
}

#[test]
fn required_evidence_providers_are_checked_separately_from_config_parsing() {
    for missing_key in ["HELIUS_API_KEY", "JUPITER_API_KEY"] {
        let mut values = valid_env();
        values.remove(missing_key);
        let config = from_map(&values).unwrap();
        let error = config.require_providers().unwrap_err();
        assert!(error.to_string().contains(missing_key));
    }
}

#[test]
fn repository_env_example_declares_paper_evidence_inputs_without_secret_values() {
    let env_example = include_str!("../../../.env.example");
    for name in [
        "SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS",
        "SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS",
        "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
        "SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES",
        "SHREKS_PAPER_PROBE_POLICY_VERSION",
        "SHREKS_PAPER_QUOTE_ASSET_MINT",
        "SHREKS_PAPER_QUOTE_TAKER",
        "SHREKS_PAPER_ENTRY_INPUT_AMOUNT",
        "SHREKS_PAPER_EXIT_INPUT_AMOUNT",
        "SHREKS_PAPER_SLIPPAGE_BPS",
        "SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE",
        "SHREKS_PAPER_DISTRIBUTION_MAX_PAGES",
        "JUPITER_API_KEY",
    ] {
        assert!(env_example.contains(&format!("{name}=")), "missing {name}");
    }
    assert!(!env_example.contains("helius-test-secret"));
    assert!(!env_example.contains("jupiter-test-secret"));
}
