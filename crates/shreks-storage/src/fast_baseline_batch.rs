use std::{
    collections::{HashMap, HashSet},
    error::Error,
    fmt,
};

use shreks_core::{FastBaselineKind, FastBaselinePosture};

use crate::{
    evaluate_fast_baseline_campaign, FastBaselineCampaignAssessment, FastBaselineCampaignError,
    FastBaselineCampaignInput, FastTrainingFeatureRecord,
};

pub const FAST_BASELINE_CAMPAIGN_BATCH_VERSION: u16 = 1;

#[derive(Debug, Clone, Copy)]
pub struct FastBaselineCampaignRequest<'a> {
    pub record: &'a FastTrainingFeatureRecord,
    pub posture: FastBaselinePosture,
    pub input: FastBaselineCampaignInput<'a>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FastBaselineCampaignBatchAssessment {
    pub version: u16,
    pub baseline_kind: FastBaselineKind,
    pub baseline_version: u16,
    pub decisions: Vec<FastBaselineCampaignAssessment>,
}

#[derive(Debug)]
pub enum FastBaselineCampaignBatchError {
    EmptyBatch,
    MixedBaselineKind {
        index: usize,
        expected: FastBaselineKind,
        actual: FastBaselineKind,
    },
    Decision {
        index: usize,
        source: FastBaselineCampaignError,
    },
    DuplicateSourceEventId {
        source_event_id: String,
    },
    SequenceRegression {
        market_key: String,
        previous: u64,
        current: u64,
    },
    TimestampRegression {
        market_key: String,
        previous: i64,
        current: i64,
    },
}

impl fmt::Display for FastBaselineCampaignBatchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyBatch => formatter.write_str("FL9 baseline campaign batch must not be empty"),
            Self::MixedBaselineKind {
                index,
                expected,
                actual,
            } => write!(
                formatter,
                "FL9 baseline campaign batch contains mixed baseline kind at index {index}: expected {expected:?}, got {actual:?}"
            ),
            Self::Decision { index, source } => write!(
                formatter,
                "FL9 baseline campaign batch decision {index} failed: {source}"
            ),
            Self::DuplicateSourceEventId { source_event_id } => write!(
                formatter,
                "FL9 baseline campaign batch contains duplicate source event identity '{source_event_id}'"
            ),
            Self::SequenceRegression {
                market_key,
                previous,
                current,
            } => write!(
                formatter,
                "FL9 baseline campaign batch source sequence regressed for market '{market_key}': previous {previous}, current {current}"
            ),
            Self::TimestampRegression {
                market_key,
                previous,
                current,
            } => write!(
                formatter,
                "FL9 baseline campaign batch timestamp regressed for market '{market_key}': previous {previous}, current {current}"
            ),
        }
    }
}

impl Error for FastBaselineCampaignBatchError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Decision { source, .. } => Some(source),
            _ => None,
        }
    }
}

pub fn evaluate_fast_baseline_campaign_batch(
    requests: &[FastBaselineCampaignRequest<'_>],
) -> Result<FastBaselineCampaignBatchAssessment, FastBaselineCampaignBatchError> {
    let Some(first) = requests.first() else {
        return Err(FastBaselineCampaignBatchError::EmptyBatch);
    };

    let baseline_kind = first.input.baseline_kind();
    for (index, request) in requests.iter().enumerate().skip(1) {
        let actual = request.input.baseline_kind();
        if actual != baseline_kind {
            return Err(FastBaselineCampaignBatchError::MixedBaselineKind {
                index,
                expected: baseline_kind,
                actual,
            });
        }
    }

    let mut seen_source_event_ids = HashSet::<String>::with_capacity(requests.len());
    let mut latest_by_market = HashMap::<String, (u64, i64)>::new();
    let mut decisions = Vec::with_capacity(requests.len());

    for (index, request) in requests.iter().enumerate() {
        let decision = evaluate_fast_baseline_campaign(
            request.record,
            request.posture,
            request.input,
        )
        .map_err(|source| FastBaselineCampaignBatchError::Decision { index, source })?;

        if !seen_source_event_ids.insert(decision.source_event_id.clone()) {
            return Err(
                FastBaselineCampaignBatchError::DuplicateSourceEventId {
                    source_event_id: decision.source_event_id,
                },
            );
        }

        if let Some((previous_sequence, previous_at)) =
            latest_by_market.get(&decision.market_key).copied()
        {
            if decision.source_sequence <= previous_sequence {
                return Err(FastBaselineCampaignBatchError::SequenceRegression {
                    market_key: decision.market_key,
                    previous: previous_sequence,
                    current: decision.source_sequence,
                });
            }
            if decision.as_of_unix_ms < previous_at {
                return Err(FastBaselineCampaignBatchError::TimestampRegression {
                    market_key: decision.market_key,
                    previous: previous_at,
                    current: decision.as_of_unix_ms,
                });
            }
        }

        latest_by_market.insert(
            decision.market_key.clone(),
            (decision.source_sequence, decision.as_of_unix_ms),
        );
        decisions.push(decision);
    }

    let baseline_version = decisions[0].baseline_version;
    Ok(FastBaselineCampaignBatchAssessment {
        version: FAST_BASELINE_CAMPAIGN_BATCH_VERSION,
        baseline_kind,
        baseline_version,
        decisions,
    })
}
