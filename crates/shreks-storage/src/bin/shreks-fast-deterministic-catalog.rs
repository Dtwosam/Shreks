use std::error::Error;

use shreks_storage::{
    build_fast_deterministic_comparison_catalog,
    encode_fast_deterministic_comparison_catalog_json,
};

fn main() -> Result<(), Box<dyn Error>> {
    if std::env::args_os().nth(1).is_some() {
        return Err("usage: shreks-fast-deterministic-catalog".into());
    }
    let catalog = build_fast_deterministic_comparison_catalog()?;
    let payload = encode_fast_deterministic_comparison_catalog_json(&catalog)?;
    print!("{payload}");
    Ok(())
}
