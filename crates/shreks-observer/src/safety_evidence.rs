use std::{error::Error, fmt, sync::Arc};

use shreks_core::{
    QuoteRequest, QuoteSnapshot, TokenDistributionRequest, TokenHolderDistribution,
    MAX_TOKEN_DISTRIBUTION_PAGE_SIZE,
};
use shreks_providers::{DistributionDataProvider, QuoteProvider};
use shreks_storage::{ShreksDb, StorageError};

/// Caller-supplied, versioned recipe for one bounded read-only safety probe.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SafetyEvidenceProbe {
    pub probe_policy_version: String,
    pub distribution_request: TokenDistributionRequest,
    pub quote_request: QuoteRequest,
}

/// Counts from one explicitly invoked evidence collection pass.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct SafetyEvidenceCycleReport {
    pub holder_snapshots_stored: usize,
    pub quote_snapshots_stored: usize,
    pub distribution_provider_failures: usize,
    pub quote_provider_failures: usize,
}

/// Fatal collection errors. Provider transport failures and misattributed
/// responses are nonfatal and are counted in SafetyEvidenceCycleReport.
#[derive(Debug)]
pub enum SafetyEvidenceError {
    Storage(StorageError),
    InvalidProbe(String),
}

impl fmt::Display for SafetyEvidenceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Storage(error) => write!(formatter, "safety evidence storage error: {error}"),
            Self::InvalidProbe(message) => write!(formatter, "invalid safety evidence probe: {message}"),
        }
    }
}

impl Error for SafetyEvidenceError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Storage(error) => Some(error),
            Self::InvalidProbe(_) => None,
        }
    }
}

impl From<StorageError> for SafetyEvidenceError {
    fn from(error: StorageError) -> Self {
        Self::Storage(error)
    }
}

/// Explicit read-only collector kept separate from the normal observer cycle.
/// Construction is caller-controlled; no default runtime path creates one.
pub struct SafetyEvidenceCollector {
    db: ShreksDb,
    distribution_providers: Vec<Arc<dyn DistributionDataProvider>>,
    quote_providers: Vec<Arc<dyn QuoteProvider>>,
}

impl SafetyEvidenceCollector {
    pub fn new(
        db: ShreksDb,
        distribution_providers: Vec<Arc<dyn DistributionDataProvider>>,
        quote_providers: Vec<Arc<dyn QuoteProvider>>,
    ) -> Self {
        Self {
            db,
            distribution_providers,
            quote_providers,
        }
    }

    /// Collect and persist read-only holder/exitability evidence for exactly
    /// one candidate. Provider failures remain unknown evidence, never false
    /// facts. Storage failures are fatal because losing audit truth is unsafe.
    pub async fn collect_candidate(
        &self,
        candidate_id: i64,
        candidate_mint: &str,
        probe: &SafetyEvidenceProbe,
    ) -> Result<SafetyEvidenceCycleReport, SafetyEvidenceError> {
        validate_probe(candidate_id, candidate_mint, probe)?;
        let mut report = SafetyEvidenceCycleReport::default();

        for provider in &self.distribution_providers {
            let provider_id = provider.provider_id();
            let result = match provider
                .token_holder_distribution(&probe.distribution_request)
                .await
            {
                Ok(result) => result,
                Err(_) => {
                    report.distribution_provider_failures =
                        report.distribution_provider_failures.saturating_add(1);
                    continue;
                }
            };

            if !distribution_identity_matches(provider_id, candidate_mint, &result) {
                report.distribution_provider_failures =
                    report.distribution_provider_failures.saturating_add(1);
                continue;
            }

            self.db.insert_holder_distribution(candidate_id, &result)?;
            report.holder_snapshots_stored = report.holder_snapshots_stored.saturating_add(1);
        }

        for provider in &self.quote_providers {
            let provider_id = provider.provider_id();
            let result = match provider.quote(&probe.quote_request).await {
                Ok(result) => result,
                Err(_) => {
                    report.quote_provider_failures =
                        report.quote_provider_failures.saturating_add(1);
                    continue;
                }
            };

            if !quote_identity_matches(provider_id, &probe.quote_request, &result) {
                report.quote_provider_failures = report.quote_provider_failures.saturating_add(1);
                continue;
            }

            self.db.insert_exit_quote_snapshot(
                candidate_id,
                &probe.probe_policy_version,
                &probe.quote_request,
                &result,
            )?;
            report.quote_snapshots_stored = report.quote_snapshots_stored.saturating_add(1);
        }

        Ok(report)
    }
}

fn validate_probe(
    candidate_id: i64,
    candidate_mint: &str,
    probe: &SafetyEvidenceProbe,
) -> Result<(), SafetyEvidenceError> {
    if candidate_id <= 0 {
        return Err(SafetyEvidenceError::InvalidProbe(
            "candidate id must be positive".to_owned(),
        ));
    }
    if candidate_mint.trim().is_empty() {
        return Err(SafetyEvidenceError::InvalidProbe(
            "candidate mint must not be blank".to_owned(),
        ));
    }
    if probe.probe_policy_version.trim().is_empty() {
        return Err(SafetyEvidenceError::InvalidProbe(
            "probe policy version must not be blank".to_owned(),
        ));
    }

    TokenDistributionRequest::new(
        probe.distribution_request.mint.clone(),
        probe.distribution_request.page_size,
        probe.distribution_request.max_pages,
    )
    .map_err(|error| SafetyEvidenceError::InvalidProbe(error.to_string()))?;
    if probe.distribution_request.page_size > MAX_TOKEN_DISTRIBUTION_PAGE_SIZE {
        return Err(SafetyEvidenceError::InvalidProbe(
            "distribution page size exceeds bounded maximum".to_owned(),
        ));
    }
    if probe.distribution_request.mint != candidate_mint {
        return Err(SafetyEvidenceError::InvalidProbe(format!(
            "distribution mint '{}' does not match candidate mint '{candidate_mint}'",
            probe.distribution_request.mint
        )));
    }

    QuoteRequest::new(
        probe.quote_request.input_mint.clone(),
        probe.quote_request.output_mint.clone(),
        probe.quote_request.amount,
        probe.quote_request.taker.clone(),
        probe.quote_request.slippage_bps,
    )
    .map_err(|error| SafetyEvidenceError::InvalidProbe(error.to_string()))?;
    if probe.quote_request.input_mint != candidate_mint {
        return Err(SafetyEvidenceError::InvalidProbe(format!(
            "quote input mint '{}' does not match candidate mint '{candidate_mint}'",
            probe.quote_request.input_mint
        )));
    }
    Ok(())
}

fn distribution_identity_matches(
    provider_id: shreks_core::ProviderId,
    candidate_mint: &str,
    result: &TokenHolderDistribution,
) -> bool {
    result.provider == provider_id && result.mint == candidate_mint
}

fn quote_identity_matches(
    provider_id: shreks_core::ProviderId,
    request: &QuoteRequest,
    result: &QuoteSnapshot,
) -> bool {
    result.provider == provider_id
        && result.input_mint == request.input_mint
        && result.output_mint == request.output_mint
        && result.input_amount == request.amount
        && result.slippage_bps == request.slippage_bps
}
