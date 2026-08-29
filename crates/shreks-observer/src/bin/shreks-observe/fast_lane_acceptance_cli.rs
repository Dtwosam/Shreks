use std::{
    ffi::OsString,
    io,
    path::PathBuf,
};

#[path = "../shreks-fast-lane-acceptance/report.rs"]
mod report;

use report::{FastLaneAcceptanceReport, FastLaneAcceptanceStore, LatencySummary};

pub fn run_fast_lane_acceptance_subcommand_if_requested() -> io::Result<bool> {
    let mut args = std::env::args_os();
    let program = args
        .next()
        .unwrap_or_else(|| OsString::from("shreks-observe"));

    let Some(command) = args.next() else {
        return Ok(false);
    };
    if command != "fast-lane-acceptance" {
        return Ok(false);
    }

    let database = required_argument(&mut args, &program, "database")?;
    let window_start = required_argument(&mut args, &program, "window_start_unix_ms")?;
    let as_of = required_argument(&mut args, &program, "as_of_unix_ms")?;
    if args.next().is_some() {
        return Err(io::Error::other(usage(&program)));
    }

    let window_start_unix_ms = parse_i64(window_start, "window_start_unix_ms")?;
    let as_of_unix_ms = parse_i64(as_of, "as_of_unix_ms")?;

    let store = FastLaneAcceptanceStore::open(&PathBuf::from(database))
        .map_err(|error| io::Error::other(error.to_string()))?;
    let report = store
        .report(window_start_unix_ms, as_of_unix_ms)
        .map_err(|error| io::Error::other(error.to_string()))?;
    print_report(&report)?;
    Ok(true)
}

fn required_argument(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
    name: &str,
) -> io::Result<OsString> {
    args.next()
        .ok_or_else(|| io::Error::other(format!("missing {name}; {}", usage(program))))
}

fn usage(program: &OsString) -> String {
    format!(
        "usage: {} fast-lane-acceptance <database> <window_start_unix_ms> <as_of_unix_ms>",
        program.to_string_lossy()
    )
}

fn parse_i64(value: OsString, field: &str) -> io::Result<i64> {
    let value = value
        .into_string()
        .map_err(|_| io::Error::other(format!("{field} must be valid UTF-8 decimal text")))?;
    value
        .parse::<i64>()
        .map_err(|error| io::Error::other(format!("invalid {field} '{value}': {error}")))
}

fn print_report(report: &FastLaneAcceptanceReport) -> io::Result<()> {
    let window_duration_ms = report
        .as_of_unix_ms
        .checked_sub(report.window_start_unix_ms)
        .ok_or_else(|| io::Error::other("acceptance window duration overflowed i64"))?;

    println!("window_start_unix_ms={}", report.window_start_unix_ms);
    println!("as_of_unix_ms={}", report.as_of_unix_ms);
    println!("window_duration_ms={window_duration_ms}");
    println!("database_bytes={}", report.database_bytes);
    println!("wal_bytes={}", report.wal_bytes);
    println!("pump_raw_events={}", report.pump_raw_events);
    println!("pumpswap_raw_events={}", report.pumpswap_raw_events);
    println!("canonical_events={}", report.canonical_events);
    println!(
        "pump_conflict_quarantine_total={}",
        report.pump_conflict_quarantine_total
    );
    println!(
        "pumpswap_conflict_quarantine_total={}",
        report.pumpswap_conflict_quarantine_total
    );
    println!(
        "pump_conflict_quarantine_events={}",
        report.pump_conflict_quarantine_events
    );
    println!(
        "pumpswap_conflict_quarantine_events={}",
        report.pumpswap_conflict_quarantine_events
    );
    println!(
        "canonical_conflict_quarantine_violations={}",
        report.canonical_conflict_quarantine_violations
    );
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
