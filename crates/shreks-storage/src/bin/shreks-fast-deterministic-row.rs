use std::{env, fs, process};

use shreks_storage::{
    decode_fast_deterministic_row_request_json,
    encode_fast_deterministic_row_result_json,
    evaluate_fast_deterministic_row_request,
};

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args();
    let program = args
        .next()
        .unwrap_or_else(|| "shreks-fast-deterministic-row".to_owned());
    let request_path = args
        .next()
        .ok_or_else(|| format!("usage: {program} <request.json>"))?;
    if args.next().is_some() {
        return Err(format!("usage: {program} <request.json>"));
    }

    let request_json = fs::read_to_string(&request_path)
        .map_err(|error| format!("failed to read deterministic row request '{request_path}': {error}"))?;
    let request = decode_fast_deterministic_row_request_json(&request_json)
        .map_err(|error| format!("failed to decode deterministic row request: {error}"))?;
    let result = evaluate_fast_deterministic_row_request(&request)
        .map_err(|error| format!("failed to evaluate deterministic row request: {error}"))?;
    let encoded = encode_fast_deterministic_row_result_json(&result)
        .map_err(|error| format!("failed to encode deterministic row result: {error}"))?;
    print!("{encoded}");
    Ok(())
}
