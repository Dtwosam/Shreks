use std::error::Error;

use shreks_observer::{
    build_free_observer, free_observe_provider_plan, ObserverRuntimeConfig,
};
use shreks_providers::{
    forward_pump_signals,
    pump::{PumpLogStream, PumpLogStreamConfig},
};
use shreks_storage::ShreksDb;
use tokio::sync::mpsc;

const PUMP_SIGNAL_CHANNEL_CAPACITY: usize = 4_096;

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

    let pump_forwarder = if let Some(api_key) = runtime.providers.helius_api_key() {
        let stream = PumpLogStream::new(PumpLogStreamConfig::helius(api_key)?);
        let (sender, receiver) = mpsc::channel(PUMP_SIGNAL_CHANNEL_CAPACITY);
        observer = observer.with_pump_signal_receiver(receiver);

        Some(tokio::spawn(async move {
            if let Err(error) = forward_pump_signals(stream, sender).await {
                eprintln!(
                    "Shreks Pump realtime stream stopped: provider={} kind={:?}: {}",
                    error.provider, error.kind, error.message
                );
            }
        }))
    } else {
        None
    };

    let observer_result = observer
        .run_until_shutdown(runtime.cycle_interval, async {
            if let Err(error) = tokio::signal::ctrl_c().await {
                eprintln!("Shreks observe shutdown signal failed: {error}");
            }
        })
        .await;

    if let Some(forwarder) = pump_forwarder {
        forwarder.abort();
        let _ = forwarder.await;
    }

    let completed_cycles = observer_result?;
    eprintln!("Shreks observe stopped after {completed_cycles} completed cycles");
    Ok(())
}
