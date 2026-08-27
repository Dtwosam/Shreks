use std::{error::Error, fmt, path::PathBuf, time::Duration};

use shreks_core::{QuoteRequest, TokenDistributionRequest, MAX_TOKEN_DISTRIBUTION_PAGE_SIZE};
use shreks_observer::SafetyEvidenceProbe;
use shreks_providers::config::ProviderConfig;

#[derive(Debug)]
pub struct PaperEvidenceRuntimeConfig {
    pub db_path: PathBuf,
    pub cycle_interval: Duration,
    pub candidate_lookback_ms: i64,
    pub preferred_min_pair_age_ms: i64,
    pub max_candidates: usize,
    pub probe_policy_version: String,
    pub quote_asset_mint: String,
    pub quote_taker: String,
    pub entry_input_amount: u64,
    pub exit_input_amount: u64,
    pub slippage_bps: u16,
    pub distribution_page_size: usize,
    pub distribution_max_pages: usize,
    pub providers: ProviderConfig,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PaperEvidenceRuntimeConfigError {
    message: String,
}

impl PaperEvidenceRuntimeConfigError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for PaperEvidenceRuntimeConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for PaperEvidenceRuntimeConfigError {}

impl PaperEvidenceRuntimeConfig {
    pub fn from_lookup<F>(lookup: F) -> Result<Self, PaperEvidenceRuntimeConfigError>
    where
        F: Fn(&str) -> Option<String>,
    {
        let db_path = PathBuf::from(required(&lookup, "SHREKS_DB_PATH")?);
        let cycle_interval_seconds = parse_positive_u64(
            &lookup,
            "SHREKS_PAPER_EVIDENCE_INTERVAL_SECONDS",
        )?;
        let lookback_seconds = parse_positive_u64(
            &lookup,
            "SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS",
        )?;
        let preferred_min_pair_age_seconds = parse_non_negative_u64(
            &lookup,
            "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
        )?;
        if preferred_min_pair_age_seconds > lookback_seconds {
            return Err(PaperEvidenceRuntimeConfigError::new(
                "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS must be <= SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS",
            ));
        }
        let candidate_lookback_ms = seconds_to_i64_ms(
            lookback_seconds,
            "SHREKS_PAPER_EVIDENCE_LOOKBACK_SECONDS",
        )?;
        let preferred_min_pair_age_ms = seconds_to_i64_ms(
            preferred_min_pair_age_seconds,
            "SHREKS_PAPER_EVIDENCE_PREFERRED_MIN_PAIR_AGE_SECONDS",
        )?;
        let max_candidates = parse_positive_usize(
            &lookup,
            "SHREKS_PAPER_EVIDENCE_MAX_CANDIDATES",
        )?;

        let probe_policy_version = required(&lookup, "SHREKS_PAPER_PROBE_POLICY_VERSION")?;
        let quote_asset_mint = required(&lookup, "SHREKS_PAPER_QUOTE_ASSET_MINT")?;
        let quote_taker = required(&lookup, "SHREKS_PAPER_QUOTE_TAKER")?;
        let entry_input_amount = parse_positive_u64(
            &lookup,
            "SHREKS_PAPER_ENTRY_INPUT_AMOUNT",
        )?;
        let exit_input_amount = parse_positive_u64(
            &lookup,
            "SHREKS_PAPER_EXIT_INPUT_AMOUNT",
        )?;
        let slippage_bps = parse_slippage_bps(&lookup)?;
        let distribution_page_size = parse_positive_usize(
            &lookup,
            "SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE",
        )?;
        if distribution_page_size > MAX_TOKEN_DISTRIBUTION_PAGE_SIZE {
            return Err(PaperEvidenceRuntimeConfigError::new(format!(
                "SHREKS_PAPER_DISTRIBUTION_PAGE_SIZE must be <= {MAX_TOKEN_DISTRIBUTION_PAGE_SIZE}"
            )));
        }
        let distribution_max_pages = parse_positive_usize(
            &lookup,
            "SHREKS_PAPER_DISTRIBUTION_MAX_PAGES",
        )?;
        let providers = ProviderConfig::from_lookup(|name| lookup(name));

        Ok(Self {
            db_path,
            cycle_interval: Duration::from_secs(cycle_interval_seconds),
            candidate_lookback_ms,
            preferred_min_pair_age_ms,
            max_candidates,
            probe_policy_version,
            quote_asset_mint,
            quote_taker,
            entry_input_amount,
            exit_input_amount,
            slippage_bps,
            distribution_page_size,
            distribution_max_pages,
            providers,
        })
    }

    pub fn from_env() -> Result<Self, PaperEvidenceRuntimeConfigError> {
        Self::from_lookup(|name| std::env::var(name).ok())
    }

    pub fn require_providers(&self) -> Result<(), PaperEvidenceRuntimeConfigError> {
        if !self.providers.helius_enabled() {
            return Err(PaperEvidenceRuntimeConfigError::new(
                "HELIUS_API_KEY is required for paper holder evidence",
            ));
        }
        if !self.providers.jupiter_enabled() {
            return Err(PaperEvidenceRuntimeConfigError::new(
                "JUPITER_API_KEY is required for purpose-correct paper quote evidence",
            ));
        }
        Ok(())
    }

    pub fn probe_for(
        &self,
        candidate_mint: &str,
    ) -> Result<SafetyEvidenceProbe, PaperEvidenceRuntimeConfigError> {
        if candidate_mint.trim().is_empty() {
            return Err(PaperEvidenceRuntimeConfigError::new(
                "candidate mint must not be blank",
            ));
        }
        if candidate_mint == self.quote_asset_mint {
            return Err(PaperEvidenceRuntimeConfigError::new(
                "candidate mint must differ from the configured quote asset",
            ));
        }

        let distribution_request = TokenDistributionRequest::new(
            candidate_mint,
            self.distribution_page_size,
            self.distribution_max_pages,
        )
        .map_err(|error| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "candidate distribution request is invalid: {error}"
            ))
        })?;

        let exit_quote_request = QuoteRequest::new(
            candidate_mint,
            self.quote_asset_mint.clone(),
            self.exit_input_amount,
            self.quote_taker.clone(),
            self.slippage_bps,
        )
        .map_err(|error| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "candidate EXIT quote request is invalid: {error}"
            ))
        })?;

        let entry_quote_request = QuoteRequest::new(
            self.quote_asset_mint.clone(),
            candidate_mint,
            self.entry_input_amount,
            self.quote_taker.clone(),
            self.slippage_bps,
        )
        .map_err(|error| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "candidate ENTRY quote request is invalid: {error}"
            ))
        })?;

        Ok(SafetyEvidenceProbe {
            probe_policy_version: self.probe_policy_version.clone(),
            distribution_request,
            exit_quote_request,
            entry_quote_request: Some(entry_quote_request),
        })
    }
}

fn required<F>(
    lookup: &F,
    name: &'static str,
) -> Result<String, PaperEvidenceRuntimeConfigError>
where
    F: Fn(&str) -> Option<String>,
{
    lookup(name)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "{name} is required and must not be blank"
            ))
        })
}

fn parse_positive_u64<F>(
    lookup: &F,
    name: &'static str,
) -> Result<u64, PaperEvidenceRuntimeConfigError>
where
    F: Fn(&str) -> Option<String>,
{
    let raw = required(lookup, name)?;
    raw.parse::<u64>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "{name} must be a positive integer; got '{raw}'"
            ))
        })
}

fn parse_non_negative_u64<F>(
    lookup: &F,
    name: &'static str,
) -> Result<u64, PaperEvidenceRuntimeConfigError>
where
    F: Fn(&str) -> Option<String>,
{
    let raw = required(lookup, name)?;
    raw.parse::<u64>().map_err(|_| {
        PaperEvidenceRuntimeConfigError::new(format!(
            "{name} must be a non-negative integer; got '{raw}'"
        ))
    })
}

fn parse_positive_usize<F>(
    lookup: &F,
    name: &'static str,
) -> Result<usize, PaperEvidenceRuntimeConfigError>
where
    F: Fn(&str) -> Option<String>,
{
    let raw = required(lookup, name)?;
    raw.parse::<usize>()
        .ok()
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "{name} must be a positive integer; got '{raw}'"
            ))
        })
}

fn seconds_to_i64_ms(
    seconds: u64,
    name: &'static str,
) -> Result<i64, PaperEvidenceRuntimeConfigError> {
    let milliseconds = seconds.checked_mul(1_000).ok_or_else(|| {
        PaperEvidenceRuntimeConfigError::new(format!("{name} is too large"))
    })?;
    i64::try_from(milliseconds).map_err(|_| {
        PaperEvidenceRuntimeConfigError::new(format!("{name} is too large"))
    })
}

fn parse_slippage_bps<F>(lookup: &F) -> Result<u16, PaperEvidenceRuntimeConfigError>
where
    F: Fn(&str) -> Option<String>,
{
    const NAME: &str = "SHREKS_PAPER_SLIPPAGE_BPS";
    let raw = required(lookup, NAME)?;
    raw.parse::<u16>()
        .ok()
        .filter(|value| *value <= 10_000)
        .ok_or_else(|| {
            PaperEvidenceRuntimeConfigError::new(format!(
                "{NAME} must be an integer between 0 and 10000; got '{raw}'"
            ))
        })
}
