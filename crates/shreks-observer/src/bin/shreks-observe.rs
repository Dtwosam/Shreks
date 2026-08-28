mod observer_v2 {
    pub mod sampler;
    pub mod sampling;
}

use std::{error::Error, sync::Arc};

use observer_v2::{
    sampler::{HighResolutionSampler, SamplerError, SamplerProvider},
    sampling::SamplingPolicy,
};
use shreks_observer::{
    free_observe_provider_plan, Observer, ObserverError, ObserverRuntimeConfig,
};
use shreks_providers::{
    config::ProviderConfig,
    dexscreener::DexScreenerProvider,
    forward_pump_signals,
    helius::HeliusProvider,
    meteora::MeteoraProvider,
    pump::{PumpLogStream, PumpLogStreamConfig},
    DiscoveryProvider, ProviderError,
};
use shreks_storage::ShreksDb;
use tokio::{sync::{mpsc, watch}, task::JoinError};

const PUMP_SIGNAL_CHANNEL_CAPACITY: usize = 4_096;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let runtime = ObserverRuntimeConfig::from_env()?;
    let plan = free_observe_provider_plan(&runtime.providers);

    eprintln!(
        "Shreks observe starting: db={} interval={}s providers={:?} observer_v2=enabled",
        runtime.db_path.display(),
        runtime.cycle_interval.as_secs(),
        plan.all_providers()
    );

    // Observer V2 deliberately uses a second connection to the same WAL database.
    // The legacy observer retains Pump/chain truth; V2 owns public discovery and
    // dense market-path sampling so free-tier requests are not duplicated.
    let observer_db = ShreksDb::open(&runtime.db_path)?;
    let sampler_db = ShreksDb::open(&runtime.db_path)?;
    let mut observer = build_lifecycle_observer(observer_db, &runtime.providers)?;
    let mut sampler = build_high_resolution_sampler(sampler_db, &runtime.providers)?;
    sampler.restore_registry()?;

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

    let observation_result = run_observation_loops(
        observer,
        sampler,
        runtime.cycle_interval,
    )
    .await;

    if let Some(forwarder) = pump_forwarder {
        forwarder.abort();
        let _ = forwarder.await;
    }

    let (observer_cycles, sampler_cycles) = observation_result?;
    eprintln!(
        "Shreks observe stopped: legacy_cycles={observer_cycles} v2_sampler_cycles={sampler_cycles}"
    );
    Ok(())
}

fn build_lifecycle_observer(
    db: ShreksDb,
    config: &ProviderConfig,
) -> Result<Observer, ProviderError> {
    let mut observer = Observer::new(db);
    if config.dexscreener_enabled {
        observer = observer.with_pump_market_provider(Arc::new(DexScreenerProvider::new()));
    }
    if let Some(api_key) = config.helius_api_key() {
        let helius = Arc::new(HeliusProvider::new(api_key)?);
        observer = observer
            .with_chain_provider(helius.clone())
            .with_transaction_provider(helius);
    }
    Ok(observer)
}

fn build_high_resolution_sampler(
    db: ShreksDb,
    config: &ProviderConfig,
) -> Result<HighResolutionSampler, SamplerError> {
    let discovery: Option<Arc<dyn DiscoveryProvider>> = if config.dexscreener_enabled {
        Some(Arc::new(DexScreenerProvider::new()))
    } else {
        None
    };

    let mut market = Vec::new();
    if config.dexscreener_enabled {
        market.push(SamplerProvider::paced(
            Arc::new(DexScreenerProvider::new()),
            config.dexscreener_market_rps,
        )?);
    }
    if config.meteora_enabled {
        market.push(SamplerProvider::paced(
            Arc::new(MeteoraProvider::new()),
            config.meteora_market_rps,
        )?);
    }

    HighResolutionSampler::new(db, discovery, market, SamplingPolicy::default_v1())
}

async fn run_observation_loops(
    mut observer: Observer,
    mut sampler: HighResolutionSampler,
    cycle_interval: std::time::Duration,
) -> Result<(usize, u64), Box<dyn Error>> {
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let observer_shutdown = shutdown_receiver.clone();
    let sampler_shutdown = shutdown_receiver;

    let mut observer_task = tokio::spawn(async move {
        observer
            .run_until_shutdown(cycle_interval, wait_for_shutdown(observer_shutdown))
            .await
    });

    let sampler_future = sampler.run_until_shutdown(wait_for_shutdown(sampler_shutdown));
    tokio::pin!(sampler_future);

    let completion = tokio::select! {
        signal = tokio::signal::ctrl_c() => LoopCompletion::Signal(signal),
        observer_result = &mut observer_task => LoopCompletion::Observer(observer_result),
        sampler_result = &mut sampler_future => LoopCompletion::Sampler(sampler_result),
    };

    // Whichever side stopped first, notify the other side. The sampler's normal
    // shutdown path flushes its durable registry before returning.
    let _ = shutdown_sender.send(true);

    match completion {
        LoopCompletion::Signal(signal) => {
            let sampler_result = sampler_future.await;
            let observer_result = observer_task.await;
            signal.map_err(boxed_error)?;
            let sampler_cycles = sampler_result.map_err(boxed_error)?;
            let observer_cycles = observer_cycles(observer_result)?;
            Ok((observer_cycles, sampler_cycles))
        }
        LoopCompletion::Observer(observer_result) => {
            let sampler_result = sampler_future.await;
            let observer_cycles = observer_cycles(observer_result)?;
            let sampler_cycles = sampler_result.map_err(boxed_error)?;
            Ok((observer_cycles, sampler_cycles))
        }
        LoopCompletion::Sampler(sampler_result) => {
            let observer_result = observer_task.await;
            let sampler_cycles = sampler_result.map_err(boxed_error)?;
            let observer_cycles = observer_cycles(observer_result)?;
            Ok((observer_cycles, sampler_cycles))
        }
    }
}

enum LoopCompletion {
    Signal(std::io::Result<()>),
    Observer(Result<Result<usize, ObserverError>, JoinError>),
    Sampler(Result<u64, SamplerError>),
}

async fn wait_for_shutdown(mut receiver: watch::Receiver<bool>) {
    if *receiver.borrow() {
        return;
    }
    while receiver.changed().await.is_ok() {
        if *receiver.borrow() {
            return;
        }
    }
}

fn observer_cycles(
    result: Result<Result<usize, ObserverError>, JoinError>,
) -> Result<usize, Box<dyn Error>> {
    result.map_err(boxed_error)?.map_err(boxed_error)
}

fn boxed_error<E>(error: E) -> Box<dyn Error>
where
    E: Error + 'static,
{
    Box::new(error)
}
