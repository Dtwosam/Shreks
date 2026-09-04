use std::{error::Error, fmt};

use shreks_core::{
    FastBaselineKind, FastBaselinePosture, FastCampaignDecisionBatchWire,
    FastCampaignDecisionPositionWire, FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME,
    FAST_CAMPAIGN_DECISION_SCHEMA_VERSION,
};

use crate::{
    FastBaselineCampaignBatchAssessment, FAST_BASELINE_CAMPAIGN_BATCH_VERSION,
};

pub const FAST_BASELINE_POPULATION_PARITY_VERSION: u16 = 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastBaselinePopulationParityProof {
    pub version: u16,
    pub learned_schema_version: u16,
    pub baseline_batch_version: u16,
    pub baseline_kind: FastBaselineKind,
    pub baseline_version: u16,
    pub decision_count: usize,
    pub first_source_event_id: String,
    pub last_source_event_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastBaselinePopulationParityError {
    InvalidLearnedSchemaName,
    InvalidLearnedSchemaVersion { actual: u16 },
    InvalidBaselineBatchVersion { actual: u16 },
    EmptyLearnedPopulation,
    EmptyBaselinePopulation,
    DecisionCountMismatch { learned: usize, baseline: usize },
    SourceEventIdMismatch {
        index: usize,
        learned: String,
        baseline: String,
    },
    MarketKeyMismatch {
        index: usize,
        learned: String,
        baseline: String,
    },
    SourceSequenceMismatch {
        index: usize,
        learned: u64,
        baseline: u64,
    },
    TimestampMismatch {
        index: usize,
        learned: i64,
        baseline: i64,
    },
    PostureMismatch {
        index: usize,
        learned: FastBaselinePosture,
        baseline: FastBaselinePosture,
    },
}

impl fmt::Display for FastBaselinePopulationParityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidLearnedSchemaName => formatter.write_str(
                "FL9 population parity learned batch schema name is unsupported",
            ),
            Self::InvalidLearnedSchemaVersion { actual } => write!(
                formatter,
                "FL9 population parity learned batch schema version {actual} is unsupported",
            ),
            Self::InvalidBaselineBatchVersion { actual } => write!(
                formatter,
                "FL9 population parity baseline batch version {actual} is unsupported",
            ),
            Self::EmptyLearnedPopulation => {
                formatter.write_str("FL9 population parity learned population is empty")
            }
            Self::EmptyBaselinePopulation => {
                formatter.write_str("FL9 population parity baseline population is empty")
            }
            Self::DecisionCountMismatch { learned, baseline } => write!(
                formatter,
                "FL9 population parity decision count mismatch: learned {learned}, baseline {baseline}",
            ),
            Self::SourceEventIdMismatch {
                index,
                learned,
                baseline,
            } => write!(
                formatter,
                "FL9 population parity source_event_id mismatch at index {index}: learned '{learned}', baseline '{baseline}'",
            ),
            Self::MarketKeyMismatch {
                index,
                learned,
                baseline,
            } => write!(
                formatter,
                "FL9 population parity market_key mismatch at index {index}: learned '{learned}', baseline '{baseline}'",
            ),
            Self::SourceSequenceMismatch {
                index,
                learned,
                baseline,
            } => write!(
                formatter,
                "FL9 population parity source sequence mismatch at index {index}: learned {learned}, baseline {baseline}",
            ),
            Self::TimestampMismatch {
                index,
                learned,
                baseline,
            } => write!(
                formatter,
                "FL9 population parity as-of timestamp mismatch at index {index}: learned {learned}, baseline {baseline}",
            ),
            Self::PostureMismatch {
                index,
                learned,
                baseline,
            } => write!(
                formatter,
                "FL9 population parity posture mismatch at index {index}: learned {learned:?}, baseline {baseline:?}",
            ),
        }
    }
}

impl Error for FastBaselinePopulationParityError {}

pub fn prove_fast_baseline_population_parity(
    learned: &FastCampaignDecisionBatchWire,
    baseline: &FastBaselineCampaignBatchAssessment,
) -> Result<FastBaselinePopulationParityProof, FastBaselinePopulationParityError> {
    if learned.schema_name != FAST_CAMPAIGN_DECISION_REQUEST_SCHEMA_NAME {
        return Err(FastBaselinePopulationParityError::InvalidLearnedSchemaName);
    }
    if learned.schema_version != FAST_CAMPAIGN_DECISION_SCHEMA_VERSION {
        return Err(FastBaselinePopulationParityError::InvalidLearnedSchemaVersion {
            actual: learned.schema_version,
        });
    }
    if baseline.version != FAST_BASELINE_CAMPAIGN_BATCH_VERSION {
        return Err(FastBaselinePopulationParityError::InvalidBaselineBatchVersion {
            actual: baseline.version,
        });
    }
    if learned.decisions.is_empty() {
        return Err(FastBaselinePopulationParityError::EmptyLearnedPopulation);
    }
    if baseline.decisions.is_empty() {
        return Err(FastBaselinePopulationParityError::EmptyBaselinePopulation);
    }
    if learned.decisions.len() != baseline.decisions.len() {
        return Err(FastBaselinePopulationParityError::DecisionCountMismatch {
            learned: learned.decisions.len(),
            baseline: baseline.decisions.len(),
        });
    }

    for (index, (learned_row, baseline_row)) in learned
        .decisions
        .iter()
        .zip(&baseline.decisions)
        .enumerate()
    {
        if learned_row.source_event_id != baseline_row.source_event_id {
            return Err(FastBaselinePopulationParityError::SourceEventIdMismatch {
                index,
                learned: learned_row.source_event_id.clone(),
                baseline: baseline_row.source_event_id.clone(),
            });
        }
        if learned_row.market_key != baseline_row.market_key {
            return Err(FastBaselinePopulationParityError::MarketKeyMismatch {
                index,
                learned: learned_row.market_key.clone(),
                baseline: baseline_row.market_key.clone(),
            });
        }
        if learned_row.source_sequence != baseline_row.source_sequence {
            return Err(FastBaselinePopulationParityError::SourceSequenceMismatch {
                index,
                learned: learned_row.source_sequence,
                baseline: baseline_row.source_sequence,
            });
        }
        if learned_row.as_of_unix_ms != baseline_row.as_of_unix_ms {
            return Err(FastBaselinePopulationParityError::TimestampMismatch {
                index,
                learned: learned_row.as_of_unix_ms,
                baseline: baseline_row.as_of_unix_ms,
            });
        }

        let learned_posture = match &learned_row.position {
            FastCampaignDecisionPositionWire::Flat => FastBaselinePosture::Flat,
            FastCampaignDecisionPositionWire::Open { .. } => FastBaselinePosture::Open,
        };
        if learned_posture != baseline_row.posture {
            return Err(FastBaselinePopulationParityError::PostureMismatch {
                index,
                learned: learned_posture,
                baseline: baseline_row.posture,
            });
        }
    }

    Ok(FastBaselinePopulationParityProof {
        version: FAST_BASELINE_POPULATION_PARITY_VERSION,
        learned_schema_version: learned.schema_version,
        baseline_batch_version: baseline.version,
        baseline_kind: baseline.baseline_kind,
        baseline_version: baseline.baseline_version,
        decision_count: learned.decisions.len(),
        first_source_event_id: learned.decisions[0].source_event_id.clone(),
        last_source_event_id: learned.decisions[learned.decisions.len() - 1]
            .source_event_id
            .clone(),
    })
}
