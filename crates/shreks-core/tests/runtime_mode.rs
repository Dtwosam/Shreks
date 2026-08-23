use std::str::FromStr;

use shreks_core::RuntimeMode;

#[test]
fn parses_every_supported_runtime_mode() {
    let cases = [
        ("observe", RuntimeMode::Observe),
        ("paper", RuntimeMode::Paper),
        ("shadow", RuntimeMode::Shadow),
        ("live", RuntimeMode::Live),
        ("halted", RuntimeMode::Halted),
    ];

    for (raw, expected) in cases {
        assert_eq!(RuntimeMode::from_str(raw).unwrap(), expected);
    }
}

#[test]
fn display_round_trips_to_canonical_lowercase() {
    for mode in [
        RuntimeMode::Observe,
        RuntimeMode::Paper,
        RuntimeMode::Shadow,
        RuntimeMode::Live,
        RuntimeMode::Halted,
    ] {
        assert_eq!(RuntimeMode::from_str(&mode.to_string()).unwrap(), mode);
    }
}

#[test]
fn defaults_to_observe() {
    assert_eq!(RuntimeMode::default(), RuntimeMode::Observe);
}

#[test]
fn rejects_unknown_runtime_mode() {
    let error = RuntimeMode::from_str("YOLO").unwrap_err();
    assert!(error.to_string().contains("YOLO"));
}
