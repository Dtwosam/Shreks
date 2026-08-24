use crate::{ProviderId, VenueId};

/// Broad normalized wallet-action classes recorded by D1.
///
/// These labels describe observed behavior only. They are not reconstructed
/// trade outcomes, wallet scores, or trading signals.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum WalletActionKind {
    Buy,
    Sell,
    Transfer,
    LiquidityEvent,
    CreatorAction,
    Other,
}

impl WalletActionKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Buy => "buy",
            Self::Sell => "sell",
            Self::Transfer => "transfer",
            Self::LiquidityEvent => "liquidity_event",
            Self::CreatorAction => "creator_action",
            Self::Other => "other",
        }
    }
}

/// Whether an action classification came from direct or inferred evidence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum WalletObservationEvidence {
    Direct,
    Inferred,
}

impl WalletObservationEvidence {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Direct => "direct",
            Self::Inferred => "inferred",
        }
    }
}

/// One point-in-time wallet action relevant to an observed candidate mint.
///
/// `observed_at_unix_ms` is the decision-safe local availability clock.
/// `occurred_at_unix_ms` is optional chain/audit time only. Raw deltas use
/// signed integer token units so no floating-point precision is introduced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WalletObservation {
    pub provider: ProviderId,
    pub wallet: String,
    pub candidate_mint: String,
    pub action: WalletActionKind,
    pub evidence: WalletObservationEvidence,
    pub signature: String,
    pub event_index: u32,
    pub slot: u64,
    pub observed_at_unix_ms: i64,
    pub occurred_at_unix_ms: Option<i64>,
    pub candidate_token_delta_raw: Option<i128>,
    pub counter_asset_mint: Option<String>,
    pub counter_asset_delta_raw: Option<i128>,
    pub venue: Option<VenueId>,
    pub counterparty: Option<String>,
}
