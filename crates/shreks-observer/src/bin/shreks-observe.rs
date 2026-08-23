use std::error::Error;

use shreks_observer::{
    build_free_observer, free_observe_provider_plan, ObserverRuntimeConfig,
};
use shreks_storage::ShreksDb;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let runtime = ObserverRuntimeConfig::from_env()?;
    let plan = free_observe_provider_plan(&runtime.providers);

    eprintln!(
        "Shreks observe starting: db={} interval={}s providers={:?}",
        runtime.db_path.display(),
        runtime.cycle_interval.as_secs(),
        plan.all_providers()
    );

    let db = ShreksDb::open(&runtime.db_path)?;
    let mut observer = build_free_observer(db, &runtime.providers)?;

    let completed_cycles = observer
        .run_until_shutdown(runtime.cycle_interval, async {
            if let Err(error) = tokio::signal::ctrl_c().await {
                eprintln!("Shreks observe shutdown signal failed: {error}");
            }
        })
        .await?;

    eprintln!("Shreks observe stopped after {completed_cycles} completed cycles");
    Ok(())
}
