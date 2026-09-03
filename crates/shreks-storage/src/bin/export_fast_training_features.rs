use std::{env, error::Error, path::PathBuf, process};

use shreks_core::FUTURE_PATH_LABEL_VERSION;
use shreks_storage::ShreksDb;

fn main() {
    if let Err(error) = run() {
        eprintln!("FL8.1 training feature export failed: {error}");
        process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let mut args = env::args_os();
    let _program = args.next();
    let input = args.next().map(PathBuf::from).ok_or(
        "usage: export_fast_training_features <existing-shreks.db> <new-features.jsonl>",
    )?;
    let output = args.next().map(PathBuf::from).ok_or(
        "usage: export_fast_training_features <existing-shreks.db> <new-features.jsonl>",
    )?;
    if args.next().is_some() {
        return Err(
            "usage: export_fast_training_features <existing-shreks.db> <new-features.jsonl>"
                .into(),
        );
    }

    let db = ShreksDb::open_existing_read_only(&input)?;
    let manifest = db.write_fast_training_feature_jsonl(FUTURE_PATH_LABEL_VERSION, &output)?;
    eprintln!(
        "exported {} FL8.1 feature rows (decision sequences {}..={}, sha256={})",
        manifest.row_count,
        manifest.min_decision_sequence,
        manifest.max_decision_sequence,
        manifest.sha256
    );
    Ok(())
}
