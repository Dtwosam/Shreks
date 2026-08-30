mod candidate_store;
mod config;
mod cycle;

use std::{
    error::Error,
    io,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use candidate_store::EvidenceCandidateStore;
use config::PaperEvidenceRuntimeConfig;
use cycle::run_paper_evidence_cycle;
use shreks_observer::SafetyEvidenceCollector;
use shreks_providers::{
    helius::HeliusProvider,
    jupiter::JupiterProvider,
    ChainDataProvider,
    DistributionDataProvider,
    QuoteProvider,
};
use shreks_storage::ShreksDb;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let config = PaperEvidenceRuntimeConfig::from_env()?;
    config.require_providers()?;

    let candidate_store = EvidenceCandidateStore::open(&config.db_path)?;
    let evidence_db = ShreksDb::open(&config.db_path)?;

    let helius_key = config
        .providers
        .helius_api_key()
        .expect("provider gate must leave Helius enabled");
    let jupiter_key = config
        .providers
        .jupiter_api_key()
        .expect("provider gate must leave Jupiter enabled");

    let helius_provider = Arc::new(
        HeliusProvider::new(helius_key)?
            .with_request_budget(config.helius_max_requests_per_process)?,
    );
    let chain_provider: Arc<dyn ChainDataProvider> = helius_provider.clone();
    let distribution_provider: Arc<dyn DistributionDataProvider> = helius_provider.clone();
    let quote_provider: Arc<dyn QuoteProvider> =
        Arc::new(JupiterProvider::new(jupiter_key)?);
    let collector = SafetyEvidenceCollector::new(
        evidence_db,
        vec![distribution_provider],
        vec![quote_provider],
    )
    .with_chain_provider(chain_provider);

    eprintln!(
        "Shreks paper evidence starting: db={} interval={}s lookback={}ms max_candidates={} holder_refresh={}s helius_request_limit={} probe_policy={} providers=helius+jupiter",
        config.db_path.display(),
        config.cycle_interval.as_secs(),
        config.candidate_lookback_ms,
        config.max_candidates,
        config.holder_refresh.as_secs(),
        config.helius_max_requests_per_process,
        config.probe_policy_version,
    );

    loop {
        let as_of_unix_ms = unix_time_ms()?;
        let report = run_paper_evidence_cycle(
            &candidate_store,
            &collector,
            &config,
            as_of_unix_ms,
        )
        .await?;
        let provider_failures = report
            .chain_provider_failures
            .saturating_add(report.distribution_provider_failures)
            .saturating_add(report.quote_provider_failures);
        let helius_usage = helius_provider.request_usage();
        let helius_requests_limit = helius_usage.limit.unwrap_or(0);
        let helius_requests_remaining = helius_usage.remaining.unwrap_or(0);

        eprintln!(
            "Shreks paper evidence cycle: as_of={} candidates_selected={} mint_states_stored={} holder_snapshots_stored={} quote_snapshots_stored={} entry_quote_snapshots_stored={} exit_quote_snapshots_stored={} provider_failures={} helius_requests_attempted={} helius_requests_limit={} helius_requests_remaining={} helius_budget_exhausted={}",
            as_of_unix_ms,
            report.candidates_selected,
            report.mint_states_stored,
            report.holder_snapshots_stored,
            report.quote_snapshots_stored,
            report.entry_quote_snapshots_stored,
            report.exit_quote_snapshots_stored,
            provider_failures,
            helius_usage.attempted,
            helius_requests_limit,
            helius_requests_remaining,
            helius_usage.exhausted,
        );

        tokio::select! {
            signal = tokio::signal::ctrl_c() => {
                signal?;
                break;
            }
            _ = tokio::time::sleep(config.cycle_interval) => {}
        }
    }

    eprintln!("Shreks paper evidence stopped");
    Ok(())
}

fn unix_time_ms() -> Result<i64, io::Error> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| io::Error::other(format!("system clock before Unix epoch: {error}")))?;
    i64::try_from(elapsed.as_millis())
        .map_err(|_| io::Error::other("system clock exceeds i64 milliseconds"))
}
