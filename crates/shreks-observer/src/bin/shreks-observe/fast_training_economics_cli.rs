use std::{
    ffi::{OsStr, OsString},
    io,
    path::PathBuf,
};

use shreks_storage::{
    encode_fast_training_economics_overlay_manifest_json, ShreksDb,
};

const COMMAND: &str = "export-training-economics";

pub fn run_fast_training_economics_subcommand_if_requested() -> io::Result<bool> {
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
    let db = ShreksDb::open_existing_read_only(&parsed.database)
        .map_err(|error| io::Error::other(error.to_string()))?;
    let manifest = db
        .write_fast_training_economics_overlay(
            &parsed.feature_jsonl,
            parsed.future_path_label_version,
            &parsed.counterfactual_base_quantity,
            parsed.pump_swap_fee_maximum_age_ms,
            &parsed.output,
        )
        .map_err(|error| io::Error::other(error.to_string()))?;
    let encoded = encode_fast_training_economics_overlay_manifest_json(&manifest)
        .map_err(|error| io::Error::other(error.to_string()))?;
    println!("{encoded}");
    Ok(true)
}

struct Arguments {
    database: PathBuf,
    feature_jsonl: PathBuf,
    future_path_label_version: u16,
    counterfactual_base_quantity: String,
    pump_swap_fee_maximum_age_ms: u64,
    output: PathBuf,
}

fn parse_arguments(
    args: &mut impl Iterator<Item = OsString>,
    program: &OsString,
) -> io::Result<Arguments> {
    let mut database = None;
    let mut feature_jsonl = None;
    let mut future_path_label_version = None;
    let mut counterfactual_base_quantity = None;
    let mut pump_swap_fee_maximum_age_ms = None;
    let mut output = None;

    while let Some(flag) = args.next() {
        match flag.to_str() {
            Some("--database") => set_once(
                &mut database,
                PathBuf::from(required_value(args, program, "--database")?),
                "--database",
                program,
            )?,
            Some("--feature-jsonl") => set_once(
                &mut feature_jsonl,
                PathBuf::from(required_value(args, program, "--feature-jsonl")?),
                "--feature-jsonl",
                program,
            )?,
            Some("--future-path-label-version") => {
                let value = required_value(args, program, "--future-path-label-version")?;
                let parsed = parse_positive_u16(
                    &value,
                    "future-path-label-version",
                    program,
                )?;
                set_once(
                    &mut future_path_label_version,
                    parsed,
                    "--future-path-label-version",
                    program,
                )?;
            }
            Some("--counterfactual-base-quantity") => {
                let value = required_value(args, program, "--counterfactual-base-quantity")?;
                let value = value.to_str().ok_or_else(|| {
                    io::Error::other(format!(
                        "counterfactual-base-quantity must be UTF-8 decimal text; {}",
                        usage(program)
                    ))
                })?;
                set_once(
                    &mut counterfactual_base_quantity,
                    value.to_owned(),
                    "--counterfactual-base-quantity",
                    program,
                )?;
            }
            Some("--pump-swap-fee-maximum-age-ms") => {
                let value = required_value(args, program, "--pump-swap-fee-maximum-age-ms")?;
                let parsed = parse_nonnegative_u64(
                    &value,
                    "pump-swap-fee-maximum-age-ms",
                    program,
                )?;
                set_once(
                    &mut pump_swap_fee_maximum_age_ms,
                    parsed,
                    "--pump-swap-fee-maximum-age-ms",
                    program,
                )?;
            }
            Some("--output") => set_once(
                &mut output,
                PathBuf::from(required_value(args, program, "--output")?),
                "--output",
                program,
            )?,
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
        feature_jsonl: feature_jsonl.ok_or_else(|| missing("--feature-jsonl", program))?,
        future_path_label_version: future_path_label_version
            .ok_or_else(|| missing("--future-path-label-version", program))?,
        counterfactual_base_quantity: counterfactual_base_quantity
            .ok_or_else(|| missing("--counterfactual-base-quantity", program))?,
        pump_swap_fee_maximum_age_ms: pump_swap_fee_maximum_age_ms
            .ok_or_else(|| missing("--pump-swap-fee-maximum-age-ms", program))?,
        output: output.ok_or_else(|| missing("--output", program))?,
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

fn parse_positive_u16(value: &OsStr, field: &str, program: &OsString) -> io::Result<u16> {
    let value = value.to_str().ok_or_else(|| {
        io::Error::other(format!(
            "{field} must be UTF-8 decimal text; {}",
            usage(program)
        ))
    })?;
    let parsed = value.parse::<u16>().map_err(|error| {
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

fn parse_nonnegative_u64(
    value: &OsStr,
    field: &str,
    program: &OsString,
) -> io::Result<u64> {
    let value = value.to_str().ok_or_else(|| {
        io::Error::other(format!(
            "{field} must be UTF-8 decimal text; {}",
            usage(program)
        ))
    })?;
    value.parse::<u64>().map_err(|error| {
        io::Error::other(format!(
            "invalid {field} '{value}': {error}; {}",
            usage(program)
        ))
    })
}

fn missing(flag: &str, program: &OsString) -> io::Error {
    io::Error::other(format!("missing {flag}; {}", usage(program)))
}

fn usage(program: &OsString) -> String {
    format!(
        "usage: {} {COMMAND} --database <existing-shreks.db> --feature-jsonl <features.jsonl> --future-path-label-version <positive-u16> --counterfactual-base-quantity <positive-decimal> --pump-swap-fee-maximum-age-ms <nonnegative-u64> --output <new-directory>",
        program.to_string_lossy()
    )
}
