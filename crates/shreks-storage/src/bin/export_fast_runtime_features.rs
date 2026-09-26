use std::{env, error::Error, path::PathBuf, process};

use shreks_storage::{
    encode_fast_runtime_feature_batch_json, FastRuntimeFeatureCursor, ShreksDb,
};

fn main() {
    if let Err(error) = run() {
        eprintln!("Fast runtime feature export failed: {error}");
        process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    if args.len() != 3 && args.len() != 7 {
        return Err(
            "usage: export_fast_runtime_features <existing-shreks.db> <maximum-decisions> [<sequence> <signature> <ordinal> <observed-at-ms>]"
                .into(),
        );
    }

    let input = PathBuf::from(&args[1]);
    let maximum_decisions = args[2]
        .parse::<u64>()
        .map_err(|_| "maximum-decisions must be an unsigned integer")?;

    let cursor = if args.len() == 7 {
        Some(FastRuntimeFeatureCursor {
            decision_sequence: args[3]
                .parse::<u64>()
                .map_err(|_| "cursor sequence must be an unsigned integer")?,
            decision_signature: args[4].clone(),
            decision_ordinal: args[5]
                .parse::<u32>()
                .map_err(|_| "cursor ordinal must be an unsigned integer")?,
            decision_observed_at_unix_ms: args[6]
                .parse::<i64>()
                .map_err(|_| "cursor observed-at-ms must be an integer")?,
        })
    } else {
        None
    };

    let db = ShreksDb::open_existing_read_only(&input)?;
    let batch = db.fast_runtime_feature_batch(cursor.as_ref(), maximum_decisions)?;
    println!("{}", encode_fast_runtime_feature_batch_json(&batch)?);
    Ok(())
}
