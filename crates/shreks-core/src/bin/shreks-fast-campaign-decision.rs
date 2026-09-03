use std::{env, fs, process};

use shreks_core::{
    decode_fast_campaign_decision_batch_json, encode_fast_campaign_decision_results_json,
    evaluate_fast_campaign_decision_batch, load_fast_forecast_champion_json,
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
        .unwrap_or_else(|| "shreks-fast-campaign-decision".to_owned());
    let champion_path = args
        .next()
        .ok_or_else(|| format!("usage: {program} <champion.json> <request.json>"))?;
    let request_path = args
        .next()
        .ok_or_else(|| format!("usage: {program} <champion.json> <request.json>"))?;
    if args.next().is_some() {
        return Err(format!("usage: {program} <champion.json> <request.json>"));
    }

    let champion_json = fs::read_to_string(&champion_path)
        .map_err(|error| format!("failed to read champion JSON '{champion_path}': {error}"))?;
    let champion = load_fast_forecast_champion_json(&champion_json)
        .map_err(|error| format!("failed to load champion: {error}"))?;

    let request_json = fs::read_to_string(&request_path)
        .map_err(|error| format!("failed to read request JSON '{request_path}': {error}"))?;
    let request = decode_fast_campaign_decision_batch_json(&request_json)
        .map_err(|error| format!("failed to decode campaign request: {error}"))?;
    let results = evaluate_fast_campaign_decision_batch(&champion, &request)
        .map_err(|error| format!("failed to evaluate campaign request: {error}"))?;
    let encoded = encode_fast_campaign_decision_results_json(&results)
        .map_err(|error| format!("failed to encode campaign results: {error}"))?;
    print!("{encoded}");
    Ok(())
}
