use std::{error::Error, fmt};

use shreks_observer::{SafetyEvidenceCollector, SafetyEvidenceError};

use crate::candidate_store::{EvidenceCandidateStore, EvidenceCandidateStoreError};
use crate::config::{PaperEvidenceRuntimeConfig, PaperEvidenceRuntimeConfigError};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PaperEvidenceCycleReport {
    pub candidates_selected: usize,
    pub holder_snapshots_stored: usize,
    pub quote_snapshots_stored: usize,
    pub entry_quote_snapshots_stored: usize,
    pub exit_quote_snapshots_stored: usize,
    pub distribution_provider_failures: usize,
    pub quote_provider_failures: usize,
    pub entry_quote_provider_failures: usize,
    pub exit_quote_provider_failures: usize,
}

#[derive(Debug)]
pub enum PaperEvidenceCycleError {
    CandidateStore(EvidenceCandidateStoreError),
    Config(PaperEvidenceRuntimeConfigError),
    Collector(SafetyEvidenceError),
}

impl fmt::Display for PaperEvidenceCycleError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::CandidateStore(error) => {
                write!(formatter, "paper evidence candidate read failed: {error}")
            }
            Self::Config(error) => write!(formatter, "paper evidence probe build failed: {error}"),
            Self::Collector(error) => write!(formatter, "paper evidence collection failed: {error}"),
        }
    }
}

impl Error for PaperEvidenceCycleError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::CandidateStore(error) => Some(error),
            Self::Config(error) => Some(error),
            Self::Collector(error) => Some(error),
        }
    }
}

impl From<EvidenceCandidateStoreError> for PaperEvidenceCycleError {
    fn from(error: EvidenceCandidateStoreError) -> Self {
        Self::CandidateStore(error)
    }
}

impl From<PaperEvidenceRuntimeConfigError> for PaperEvidenceCycleError {
    fn from(error: PaperEvidenceRuntimeConfigError) -> Self {
        Self::Config(error)
    }
}

impl From<SafetyEvidenceError> for PaperEvidenceCycleError {
    fn from(error: SafetyEvidenceError) -> Self {
        Self::Collector(error)
    }
}

pub async fn run_paper_evidence_cycle(
    store: &EvidenceCandidateStore,
    collector: &SafetyEvidenceCollector,
    config: &PaperEvidenceRuntimeConfig,
    as_of_unix_ms: i64,
) -> Result<PaperEvidenceCycleReport, PaperEvidenceCycleError> {
    let candidates = store.fresh_launch_candidates(
        as_of_unix_ms,
        config.candidate_lookback_ms,
        config.preferred_min_pair_age_ms,
        config.max_candidates,
    )?;
    let mut aggregate = PaperEvidenceCycleReport {
        candidates_selected: candidates.len(),
        ..PaperEvidenceCycleReport::default()
    };

    for candidate in candidates {
        let probe = config.probe_for(&candidate.mint)?;
        let report = collector
            .collect_candidate(candidate.candidate_id, &candidate.mint, &probe)
            .await?;

        aggregate.holder_snapshots_stored = aggregate
            .holder_snapshots_stored
            .saturating_add(report.holder_snapshots_stored);
        aggregate.quote_snapshots_stored = aggregate
            .quote_snapshots_stored
            .saturating_add(report.quote_snapshots_stored);
        aggregate.entry_quote_snapshots_stored = aggregate
            .entry_quote_snapshots_stored
            .saturating_add(report.entry_quote_snapshots_stored);
        aggregate.exit_quote_snapshots_stored = aggregate
            .exit_quote_snapshots_stored
            .saturating_add(report.exit_quote_snapshots_stored);
        aggregate.distribution_provider_failures = aggregate
            .distribution_provider_failures
            .saturating_add(report.distribution_provider_failures);
        aggregate.quote_provider_failures = aggregate
            .quote_provider_failures
            .saturating_add(report.quote_provider_failures);
        aggregate.entry_quote_provider_failures = aggregate
            .entry_quote_provider_failures
            .saturating_add(report.entry_quote_provider_failures);
        aggregate.exit_quote_provider_failures = aggregate
            .exit_quote_provider_failures
            .saturating_add(report.exit_quote_provider_failures);
    }

    Ok(aggregate)
}
