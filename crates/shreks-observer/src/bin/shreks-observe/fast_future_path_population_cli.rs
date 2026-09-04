use std::{
    ffi::{OsStr, OsString},
    io,
    path::PathBuf,
};

use shreks_storage::{
    encode_fast_covered_future_path_population_report_json,
    populate_fast_future_path_labels, FastCoveredFuturePathPopulationRequest, ShreksDb,
};

const COMMAND: &str = "populate-future-path-labels";

pub fn run_fast_future_path_population_subcommand_if_requested() -> io::Result<bool> {
    let mut args = std::env::args_os();
    let program = args
        .next()
        .unwrap_or_else(|| OsString::from("shreks-observe"));

    let Some(command) = args.next() else {
        return Ok(false);
    };
    if command != COMMAND {
        return Ok(false);
    }

    let parsed = parse_arguments(&mut args, &program)?;
    let db = ShreksDb::open(&parsed.database)
        .map_err(|error| io::Error::other(error.to_string()))?;
    let request = FastCoveredFuturePathPopulationRequest {
        coverage_session_id: parsed.coverage_session_id,
        from_observed_at_unix_ms: parsed.from_observed_at_unix_ms,
        through_observed_at_unix_ms: parsed.through_observed_at_unix_ms,
        maximum_decisions: parsed.maximum_decisions,
    };
    let report = populate_fast_future_path_labels(&db, &request)
        .map_err(|error| io::Error::other(error.to_string()))?;
    let encoded = encode_fast_covered_future_path_population_report_json(&report)
        .map_err(|error| io::Error::other(error.to_string()))?;
    println!("{encoded}");
    Ok(true)
}

struct Arguments {
    database: PathBuf,
    coverage_session_id: u64,
    from_observed_at_unix_ms: i64,
    through_observed_at_unix_ms: i64,
    maximum_decisions: u64,
}

fn parse_arguments(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
) -> io::Result<Arguments> {
    let mut database = None;
    let mut coverage_session_id = None;
    let mut from_observed_at_unix_ms = None;
    let mut through_observed_at_unix_ms = None;
    let mut maximum_decisions = None;

    while let Some(flag) = args.next() {
        match flag.to_str() {
            Some("--database") => set_once(
                &mut database,
                PathBuf::from(required_value(args, program, "--database")?),
                "--database",
                program,
            )?,
            Some("--coverage-session-id") => {
                let value = required_value(args, program, "--coverage-session-id")?;
                let parsed = parse_positive_u64(&value, "coverage-session-id", program)?;
                set_once(
                    &mut coverage_session_id,
                    parsed,
                    "--coverage-session-id",
                    program,
                )?;
            }
            Some("--from-observed-at-unix-ms") => {
                let value = required_value(args, program, "--from-observed-at-unix-ms")?;
                let parsed = parse_nonnegative_i64(
                    &value,
                    "from-observed-at-unix-ms",
                    program,
                )?;
                set_once(
                    &mut from_observed_at_unix_ms,
                    parsed,
                    "--from-observed-at-unix-ms",
                    program,
                )?;
            }
            Some("--through-observed-at-unix-ms") => {
                let value = required_value(args, program, "--through-observed-at-unix-ms")?;
                let parsed = parse_nonnegative_i64(
                    &value,
                    "through-observed-at-unix-ms",
                    program,
                )?;
                set_once(
                    &mut through_observed_at_unix_ms,
                    parsed,
                    "--through-observed-at-unix-ms",
                    program,
                )?;
            }
            Some("--maximum-decisions") => {
                let value = required_value(args, program, "--maximum-decisions")?;
                let parsed = parse_positive_u64(&value, "maximum-decisions", program)?;
                set_once(
                    &mut maximum_decisions,
                    parsed,
                    "--maximum-decisions",
                    program,
                )?;
            }
            _ => {
                return Err(io::Error::other(format!(
                    "unknown {COMMAND} argument '{}'; {}",
                    flag.to_string_lossy(),
                    usage(program)
                )));
            }
        }
    }

    Ok(Arguments {
        database: database.ok_or_else(|| missing("--database", program))?,
        coverage_session_id: coverage_session_id
            .ok_or_else(|| missing("--coverage-session-id", program))?,
        from_observed_at_unix_ms: from_observed_at_unix_ms
            .ok_or_else(|| missing("--from-observed-at-unix-ms", program))?,
        through_observed_at_unix_ms: through_observed_at_unix_ms
            .ok_or_else(|| missing("--through-observed-at-unix-ms", program))?,
        maximum_decisions: maximum_decisions
            .ok_or_else(|| missing("--maximum-decisions", program))?,
    })
}

fn required_value(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
    flag: &str,
) -> io::Result<OsString> {
    args.next().ok_or_else(|| missing(flag, program))
}

fn set_once<T>(
    destination: &mut Option<T>,
    value: T,
    flag: &str,
    program: &OsString,
) -> io::Result<()> {
    if destination.is_some() {
        return Err(io::Error::other(format!(
            "duplicate {flag}; {}",
            usage(program)
        )));
    }
    *destination = Some(value);
    Ok(())
}

fn parse_positive_u64(value: &OsStr, field: &str, program: &OsString) -> io::Result<u64> {
    let value = value.to_str().ok_or_else(|| {
        io::Error::other(format!("{field} must be UTF-8 decimal text; {}", usage(program)))
    })?;
    let parsed = value.parse::<u64>().map_err(|error| {
        io::Error::other(format!(
            "invalid {field} '{value}': {error}; {}",
            usage(program)
        ))
    })?;
    if parsed == 0 {
        return Err(io::Error::other(format!(
            "{field} must be greater than zero; {}",
            usage(program)
        )));
    }
    Ok(parsed)
}

fn parse_nonnegative_i64(value: &OsStr, field: &str, program: &OsString) -> io::Result<i64> {
    let value = value.to_str().ok_or_else(|| {
        io::Error::other(format!("{field} must be UTF-8 decimal text; {}", usage(program)))
    })?;
    let parsed = value.parse::<i64>().map_err(|error| {
        io::Error::other(format!(
            "invalid {field} '{value}': {error}; {}",
            usage(program)
        ))
    })?;
    if parsed < 0 {
        return Err(io::Error::other(format!(
            "{field} must be non-negative; {}",
            usage(program)
        )));
    }
    Ok(parsed)
}

fn missing(flag: &str, program: &OsString) -> io::Error {
    io::Error::other(format!("missing {flag}; {}", usage(program)))
}

fn usage(program: &OsString) -> String {
    format!(
        "usage: {} {COMMAND} --database <shreks.db> --coverage-session-id <positive-u64> --from-observed-at-unix-ms <nonnegative-i64> --through-observed-at-unix-ms <nonnegative-i64> --maximum-decisions <positive-u64>",
        program.to_string_lossy()
    )
}
