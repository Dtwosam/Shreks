use std::{env, fs, process};

use shreks_storage::{
    decode_fast_deterministic_entry_authority_request_json,
    derive_fast_deterministic_entry_authority,
    encode_fast_deterministic_entry_authority_result_json,
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
        .unwrap_or_else(|| "shreks-fast-entry-authority".to_owned());
    let request_path = args
        .next()
        .ok_or_else(|| format!("usage: {program} <request.json>"))?;
    if args.next().is_some() {
        return Err(format!("usage: {program} <request.json>"));
    }

    let request_json = fs::read_to_string(&request_path)
        .map_err(|error| format!(
            "failed to read deterministic entry authority request '{request_path}': {error}"
        ))?;
    let request = decode_fast_deterministic_entry_authority_request_json(&request_json)
        .map_err(|error| format!(
            "failed to decode deterministic entry authority request: {error}"
        ))?;
    let result = derive_fast_deterministic_entry_authority(&request)
        .map_err(|error| format!(
            "failed to derive deterministic entry authority: {error}"
        ))?;
    let encoded = encode_fast_deterministic_entry_authority_result_json(&result)
        .map_err(|error| format!(
            "failed to encode deterministic entry authority result: {error}"
        ))?;
    print!("{encoded}");
    Ok(())
}
