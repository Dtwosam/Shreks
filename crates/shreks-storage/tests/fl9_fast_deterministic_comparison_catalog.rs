use std::{collections::BTreeSet, process::Command};

use shreks_storage::{
    build_fast_deterministic_comparison_catalog,
    decode_fast_deterministic_comparison_catalog_json,
    encode_fast_deterministic_comparison_catalog_json,
    FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME,
    FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION,
    FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION,
};

const GOLDEN: &str = include_str!(
    "../../../python/tests/fixtures/fast_deterministic_comparison_catalog_v1.json"
);

const EXPECTED: [&str; 8] = [
    "fl9-baseline-graduation-flow-longer-runner-v1",
    "fl9-baseline-graduation-flow-wallet-cohort-v1",
    "fl9-baseline-impulse-scalp-longer-runner-v1",
    "fl9-baseline-impulse-scalp-wallet-cohort-v1",
    "fl9-baseline-micro-pullback-longer-runner-v1",
    "fl9-baseline-micro-pullback-wallet-cohort-v1",
    "fl9-baseline-pre-graduation-longer-runner-v1",
    "fl9-baseline-pre-graduation-wallet-cohort-v1",
];

#[test]
fn comparison_catalog_contains_exact_lexical_eight_candidate_reference_set() {
    let catalog = build_fast_deterministic_comparison_catalog().unwrap();

    assert_eq!(
        catalog.schema_name,
        FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_NAME
    );
    assert_eq!(
        catalog.schema_version,
        FAST_DETERMINISTIC_COMPARISON_CATALOG_SCHEMA_VERSION
    );
    assert_eq!(
        catalog.catalog_version,
        FAST_DETERMINISTIC_COMPARISON_CATALOG_VERSION
    );
    assert_eq!(catalog.candidates.len(), 8);

    let versions: Vec<_> = catalog
        .candidates
        .iter()
        .map(|candidate| candidate.candidate_version.as_str())
        .collect();
    assert_eq!(versions, EXPECTED);

    let pairs: BTreeSet<_> = catalog
        .candidates
        .iter()
        .map(|candidate| {
            (
                candidate.lifecycle_policy.entry_baseline_kind.as_str(),
                candidate.lifecycle_policy.manager_baseline_kind.as_str(),
            )
        })
        .collect();
    assert_eq!(pairs.len(), 8);
    assert!(pairs.contains(&("IMPULSE_SCALP", "WALLET_COHORT")));
    assert!(pairs.contains(&("IMPULSE_SCALP", "LONGER_RUNNER")));
    assert!(pairs.contains(&("MICRO_PULLBACK", "WALLET_COHORT")));
    assert!(pairs.contains(&("MICRO_PULLBACK", "LONGER_RUNNER")));
    assert!(pairs.contains(&("PRE_GRADUATION", "WALLET_COHORT")));
    assert!(pairs.contains(&("PRE_GRADUATION", "LONGER_RUNNER")));
    assert!(pairs.contains(&("GRADUATION_FLOW", "WALLET_COHORT")));
    assert!(pairs.contains(&("GRADUATION_FLOW", "LONGER_RUNNER")));
}

#[test]
fn comparison_catalog_json_round_trip_and_repeat_are_deterministic() {
    let first = build_fast_deterministic_comparison_catalog().unwrap();
    let second = build_fast_deterministic_comparison_catalog().unwrap();
    assert_eq!(first, second);

    let encoded = encode_fast_deterministic_comparison_catalog_json(&first).unwrap();
    let decoded = decode_fast_deterministic_comparison_catalog_json(&encoded).unwrap();
    assert_eq!(decoded, first);
    assert_eq!(
        first.catalog_fingerprint_sha256,
        "64507c55998ba517f7d77e74323c8a84823c696f706d83b66782521c7436979c"
    );
    assert_eq!(encoded, GOLDEN);
}

#[test]
fn catalog_binary_stdout_matches_shared_golden_exactly() {
    let output = Command::new(env!(
        "CARGO_BIN_EXE_shreks-fast-deterministic-catalog"
    ))
    .output()
    .unwrap();

    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert_eq!(String::from_utf8(output.stdout).unwrap(), GOLDEN);
}

#[test]
fn comparison_catalog_source_and_binary_have_no_execution_authority() {
    let source = include_str!("../src/fast_deterministic_comparison_catalog.rs");
    let binary = include_str!("../src/bin/shreks-fast-deterministic-catalog.rs");

    for forbidden in [
        "ShreksDb",
        "rusqlite",
        "reqwest",
        "FastPaper",
        "PaperLedger",
        "RiskContext",
        "RuntimeMode::Live",
        "Signer",
        "submit_transaction",
        "promote",
    ] {
        assert!(!source.contains(forbidden), "forbidden catalog authority: {forbidden}");
        assert!(!binary.contains(forbidden), "forbidden catalog binary authority: {forbidden}");
    }
}
