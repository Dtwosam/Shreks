mod observer_v2 {
    pub mod sampler;
    pub mod sampling;
}
#[path = "shreks-observe/fast_lane_acceptance_cli.rs"]
mod fast_lane_acceptance_cli;
#[path = "shreks-observe/fast_state_benchmark_cli.rs"]
mod fast_state_benchmark_cli;
#[path = "shreks-observe/realtime_targets.rs"]
mod realtime_targets;
#[path = "shreks-observe/realtime_target_publisher.rs"]
mod realtime_target_publisher;

#[path = "../fast_event_normalizer.rs"]
mod fast_event_normalizer;
#[path = "../sqlite_busy_retry.rs"]
mod sqlite_busy_retry;

use std::{
    error::Error,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use fast_event_normalizer::{
    normalize_pending_pump_trade_evidence_at, FastEventNormalizationError,
};
use observer_v2::{
    sampler::{HighResolutionSampler, SamplerError, SamplerProvider},
    sampling::SamplingPolicy,
};
use realtime_target_publisher::{
    refresh_pumpswap_realtime_targets_now, run_pumpswap_realtime_target_publisher,
    RealtimeTargetPublisherError,
};
use shreks_observer::{
    free_observe_provider_plan, Observer, ObserverError, ObserverRuntimeConfig,
};
use shreks_providers::{
    bounded_pump_realtime::BoundedPumpRealtimeLogStreamConfig,
    bounded_pump_realtime_failover::{
        forward_bounded_pump_realtime_sessions, BoundedPumpRealtimeFailoverStream,
    },
    config::ProviderConfig,
    dexscreener::DexScreenerProvider,
    meteora::MeteoraProvider,
    solana_rpc::StandardSolanaRpcProvider,
    DiscoveryProvider, ProviderError,
};
use shreks_storage::{ShreksDb, StorageError};
use sqlite_busy_retry::{is_storage_sqlite_busy_or_locked, retry_bounded};
use tokio::{
    sync::{mpsc, watch},
    task::{JoinError, JoinHandle},
};

const PUMP_REALTIME_CHANNEL_CAPACITY: usize = 4_096;
const FAST_EVENT_NORMALIZER_BATCH_LIMIT: usize = 256;
const FAST_EVENT_NORMALIZER_INTERVAL: Duration = Duration::from_millis(250);

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    if fast_lane_acceptance_cli::run_fast_lane_acceptance_subcommand_if_requested()? {
        return Ok(());
    }
    if fast_state_benchmark_cli::run_fast_state_benchmark_subcommand_if_requested()? {
        return Ok(());
    }

    let runtime = ObserverRuntimeConfig::from_env()?;
    let plan = free_observe_provider_plan(&runtime.providers);

    eprintln!(
        "Shreks observe starting: db={} interval={}s providers={:?} observer_v2=enabled",
        runtime.db_path.display(),
        runtime.cycle_interval.as_secs(),
        plan.all_providers()
    );

    // Observer V2 deliberately uses a second connection to the same WAL database.
    // The lifecycle observer retains Pump/chain truth; V2 owns public discovery and
    // dense market-path sampling so free-tier requests are not duplicated.
    let observer_db = ShreksDb::open(&runtime.db_path)?;
    let sampler_db = ShreksDb::open(&runtime.db_path)?;
    let observer = build_lifecycle_observer(observer_db, &runtime.providers)?;
    let mut sampler = build_high_resolution_sampler(sampler_db, &runtime.providers)?;
    sampler.restore_registry()?;

    // Broad Pump capture is deliberately pinned to the official public Solana
    // websocket. Paid provider credentials may remain configured for other
    // binaries, but they cannot activate the FL1 realtime firehose. The same
    // bounded target engine keeps Pump-wide evidence plus verified PumpSwap pools.
    let realtime_configs = build_pump_realtime_configs()?;
    let pump_realtime_tasks = if realtime_configs.is_empty() {
        None
    } else {
        let pumpswap_tracking_max_age = runtime.pumpswap_tracking_max_age.ok_or_else(|| {
            std::io::Error::other(
                "bounded PumpSwap realtime tracking age is required when realtime is enabled",
            )
        })?;
        let pumpswap_max_tracked_pools = runtime.pumpswap_max_tracked_pools.ok_or_else(|| {
            std::io::Error::other(
                "bounded PumpSwap realtime tracked-pool limit is required when realtime is enabled",
            )
        })?;
        let pumpswap_tracking_max_age_ms =
            i64::try_from(pumpswap_tracking_max_age.as_millis()).map_err(|_| {
                std::io::Error::other(
                    "bounded PumpSwap realtime tracking age exceeds i64 milliseconds",
                )
            })?;

        let writer_db = ShreksDb::open(&runtime.db_path)?;
        let normalizer_db = ShreksDb::open(&runtime.db_path)?;
        let (target_sender, target_receiver) = watch::channel(Vec::<String>::new());

        // Establish the verified canonical target set before any websocket is
        // opened. This avoids a startup gap where the first provider would
        // otherwise begin with an incidental empty PumpSwap target snapshot.
        refresh_pumpswap_realtime_targets_now(
            &runtime.db_path,
            pumpswap_tracking_max_age_ms,
            pumpswap_max_tracked_pools,
            &target_sender,
        )?;
        eprintln!(
            "Shreks bounded PumpSwap realtime scope: tracked_pools={} max_tracked_pools={} max_age_seconds={}",
            target_sender.borrow().len(),
            pumpswap_max_tracked_pools,
            pumpswap_tracking_max_age.as_secs(),
        );

        let stream = BoundedPumpRealtimeFailoverStream::new(realtime_configs, target_receiver)?;
        let (sender, receiver) = mpsc::channel(PUMP_REALTIME_CHANNEL_CAPACITY);

        let target_publisher = tokio::spawn(run_pumpswap_realtime_target_publisher(
            runtime.db_path.clone(),
            pumpswap_tracking_max_age_ms,
            pumpswap_max_tracked_pools,
            target_sender,
        ));
        let forwarder = tokio::spawn(forward_bounded_pump_realtime_sessions(stream, sender));
        let writer = tokio::spawn(Observer::run_pump_realtime_session_writer(
            writer_db,
            receiver,
        ));
        let normalizer = tokio::spawn(run_fast_event_normalizer(normalizer_db));

        Some((target_publisher, forwarder, writer, normalizer))
    };

    let (observer_cycles, sampler_cycles) = if let Some((
        target_publisher,
        forwarder,
        writer,
        normalizer,
    )) = pump_realtime_tasks
    {
        run_observation_with_realtime(
            observer,
            sampler,
            runtime.cycle_interval,
            target_publisher,
            forwarder,
            writer,
            normalizer,
        )
        .await?
    } else {
        run_observation_loops(observer, sampler, runtime.cycle_interval).await?
    };

    eprintln!(
        "Shreks observe stopped: legacy_cycles={observer_cycles} v2_sampler_cycles={sampler_cycles}"
    );
    Ok(())
}

fn build_pump_realtime_configs() -> Result<Vec<BoundedPumpRealtimeLogStreamConfig>, ProviderError> {
    Ok(vec![BoundedPumpRealtimeLogStreamConfig::solana_public()?])
}

fn build_lifecycle_observer(
    db: ShreksDb,
    config: &ProviderConfig,
) -> Result<Observer, ProviderError> {
    let mut observer = Observer::new(db);
    if config.dexscreener_enabled {
        observer = observer.with_pump_market_provider(Arc::new(DexScreenerProvider::new()));
    }

    // Launch/migration verification uses the same read-only standard Solana
    // semantics as before, but the broad verifier is public-only. Paid Helius
    // and Chainstack credentials are intentionally not consulted here.
    let solana_public = Arc::new(StandardSolanaRpcProvider::solana_public()?);
    observer = observer
        .with_chain_provider(solana_public.clone())
        .with_transaction_provider(solana_public);

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

async fn run_fast_event_normalizer(
    db: ShreksDb,
) -> Result<(), FastEventNormalizationError> {
    loop {
        let accepted_at_unix_ms = normalizer_unix_time_ms()?;
        retry_bounded(
            || {
                normalize_pending_pump_trade_evidence_at(
                    &db,
                    FAST_EVENT_NORMALIZER_BATCH_LIMIT,
                    accepted_at_unix_ms,
                )
            },
            |error| {
                matches!(
                    error,
                    FastEventNormalizationError::Storage(storage_error)
                        if is_storage_sqlite_busy_or_locked(storage_error)
                )
            },
        )?;
        tokio::time::sleep(FAST_EVENT_NORMALIZER_INTERVAL).await;
    }
}

fn normalizer_unix_time_ms() -> Result<i64, FastEventNormalizationError> {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(StorageError::from)?
        .as_millis();
    i64::try_from(millis).map_err(|_| {
        FastEventNormalizationError::Storage(StorageError::InvalidData(
            "FastEvent normalizer clock exceeds i64 milliseconds".to_owned(),
        ))
    })
}

async fn run_observation_with_realtime(
    observer: Observer,
    sampler: HighResolutionSampler,
    cycle_interval: Duration,
    mut target_publisher: JoinHandle<Result<(), RealtimeTargetPublisherError>>,
    mut forwarder: JoinHandle<Result<(), ProviderError>>,
    mut writer: JoinHandle<Result<usize, ObserverError>>,
    mut normalizer: JoinHandle<Result<(), FastEventNormalizationError>>,
) -> Result<(usize, u64), Box<dyn Error>> {
    let observation = run_observation_loops(observer, sampler, cycle_interval);
    tokio::pin!(observation);

    tokio::select! {
        observation_result = &mut observation => {
            // Normal observer shutdown closes the producer first, then drains every
            // realtime envelope already accepted into the bounded channel.
            target_publisher.abort();
            let _ = target_publisher.await;
            forwarder.abort();
            let _ = forwarder.await;
            normalizer.abort();
            let _ = normalizer.await;
            let writer_result = writer.await;
            let cycles = observation_result?;
            let rows = writer_result.map_err(boxed_error)?.map_err(boxed_error)?;
            eprintln!("Shreks Pump realtime writer stopped: new_trade_rows={rows}");
            Ok(cycles)
        }
        target_publisher_result = &mut target_publisher => {
            forwarder.abort();
            let _ = forwarder.await;
            normalizer.abort();
            let _ = normalizer.await;
            writer.abort();
            let _ = writer.await;
            let message = match target_publisher_result {
                Ok(Ok(())) => "PumpSwap realtime target publisher stopped unexpectedly".to_owned(),
                Ok(Err(error)) => format!(
                    "PumpSwap realtime target publisher stopped unexpectedly: {error}"
                ),
                Err(error) => format!(
                    "PumpSwap realtime target publisher stopped unexpectedly: task join failure: {error}"
                ),
            };
            Err(Box::new(std::io::Error::other(message)))
        }
        forwarder_result = &mut forwarder => {
            target_publisher.abort();
            let _ = target_publisher.await;
            normalizer.abort();
            let _ = normalizer.await;
            writer.abort();
            let _ = writer.await;
            let message = match forwarder_result {
                Ok(Ok(())) => "Pump realtime forwarder stopped unexpectedly".to_owned(),
                Ok(Err(error)) => format!(
                    "Pump realtime forwarder stopped unexpectedly: provider={} kind={:?}",
                    error.provider, error.kind
                ),
                Err(error) => format!(
                    "Pump realtime forwarder stopped unexpectedly: task join failure: {error}"
                ),
            };
            Err(Box::new(std::io::Error::other(message)))
        }
        writer_result = &mut writer => {
            // The realtime durability lane is mandatory whenever realtime is
            // active. Any writer exit means the process can no longer prove it
            // is collecting Pump evidence, so fail closed.
            target_publisher.abort();
            let _ = target_publisher.await;
            forwarder.abort();
            let _ = forwarder.await;
            normalizer.abort();
            let _ = normalizer.await;
            let rows = writer_result.map_err(boxed_error)?.map_err(boxed_error)?;
            Err(Box::new(std::io::Error::other(format!(
                "Pump realtime writer stopped unexpectedly after {rows} new trade rows"
            ))))
        }
        normalizer_result = &mut normalizer => {
            // Canonicalization is part of the realtime evidence contract. A task
            // exit means raw Pump evidence can no longer become replayable FastEvents.
            target_publisher.abort();
            let _ = target_publisher.await;
            forwarder.abort();
            let _ = forwarder.await;
            writer.abort();
            let _ = writer.await;
            normalizer_result.map_err(boxed_error)?.map_err(boxed_error)?;
            Err(Box::new(std::io::Error::other(
                "FastEvent normalizer stopped unexpectedly"
            )))
        }
    }
}

async fn run_observation_loops(
    mut observer: Observer,
    mut sampler: HighResolutionSampler,
    cycle_interval: Duration,
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
