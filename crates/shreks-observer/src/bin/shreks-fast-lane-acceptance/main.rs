mod report;

use std::{ffi::OsString, path::PathBuf};

use report::{FastLaneAcceptanceReport, FastLaneAcceptanceStore, LatencySummary};

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = std::env::args_os();
    let program = args
        .next()
        .unwrap_or_else(|| OsString::from("shreks-fast-lane-acceptance"));
    let database = required_argument(&mut args, &program, "database")?;
    let window_start = required_argument(&mut args, &program, "window_start_unix_ms")?;
    let as_of = required_argument(&mut args, &program, "as_of_unix_ms")?;
    if args.next().is_some() {
        return Err(usage(&program));
    }

    let window_start_unix_ms = parse_i64(window_start, "window_start_unix_ms")?;
    let as_of_unix_ms = parse_i64(as_of, "as_of_unix_ms")?;

    let store = FastLaneAcceptanceStore::open(&PathBuf::from(database))
        .map_err(|error| error.to_string())?;
    let report = store
        .report(window_start_unix_ms, as_of_unix_ms)
        .map_err(|error| error.to_string())?;
    print_report(&report)?;
    Ok(())
}

fn required_argument(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
    name: &str,
) -> Result<OsString, String> {
    args.next()
        .ok_or_else(|| format!("missing {name}; {}", usage(program)))
}

fn usage(program: &OsString) -> String {
    format!(
        "usage: {} <database> <window_start_unix_ms> <as_of_unix_ms>",
        program.to_string_lossy()
    )
}

fn parse_i64(value: OsString, field: &str) -> Result<i64, String> {
    let value = value
        .into_string()
        .map_err(|_| format!("{field} must be valid UTF-8 decimal text"))?;
    value
        .parse::<i64>()
        .map_err(|error| format!("invalid {field} '{value}': {error}"))
}

fn print_report(report: &FastLaneAcceptanceReport) -> Result<(), String> {
    let window_duration_ms = report
        .as_of_unix_ms
        .checked_sub(report.window_start_unix_ms)
        .ok_or_else(|| "acceptance window duration overflowed i64".to_owned())?;

    println!("window_start_unix_ms={}", report.window_start_unix_ms);
    println!("as_of_unix_ms={}", report.as_of_unix_ms);
    println!("window_duration_ms={window_duration_ms}");
    println!("database_bytes={}", report.database_bytes);
    println!("wal_bytes={}", report.wal_bytes);
    println!("pump_raw_events={}", report.pump_raw_events);
    println!("pumpswap_raw_events={}", report.pumpswap_raw_events);
    println!("canonical_events={}", report.canonical_events);
    println!("pending_pump_events={}", report.pending_pump_events);
    println!("pending_pumpswap_events={}", report.pending_pumpswap_events);
    println!(
        "sequence_integrity_violations={}",
        report.sequence_integrity_violations
    );
    print_latency("source_latency", &report.source_latency);
    print_latency("normalization_latency", &report.normalization_latency);
    print_latency("end_to_end_latency", &report.end_to_end_latency);
    Ok(())
}

fn print_latency(prefix: &str, latency: &LatencySummary) {
    println!("{prefix}_samples={}", latency.samples);
    println!("{prefix}_p50_ms={}", option_ms(latency.p50_ms));
    println!("{prefix}_p95_ms={}", option_ms(latency.p95_ms));
    println!("{prefix}_p99_ms={}", option_ms(latency.p99_ms));
    println!("{prefix}_max_ms={}", option_ms(latency.max_ms));
}

fn option_ms(value: Option<i64>) -> String {
    value
        .map(|value| value.to_string())
        .unwrap_or_else(|| "none".to_owned())
}
