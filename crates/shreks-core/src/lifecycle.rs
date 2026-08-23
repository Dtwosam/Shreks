use super::{ProviderId, VenueId};

/// Provider-neutral lifecycle transition captured from verified protocol evidence.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LifecycleEventKind {
    PumpGraduation,
}

impl LifecycleEventKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::PumpGraduation => "pump_graduation",
        }
    }
}

/// Durable point-in-time lifecycle truth used by later feature/setup layers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TokenLifecycleEvent {
    pub kind: LifecycleEventKind,
    pub provider: ProviderId,
    pub mint: String,
    pub quote_mint: String,
    pub from_venue: VenueId,
    pub to_venue: VenueId,
    pub pool_address: String,
    pub signature: String,
    pub slot: u64,
    pub detected_at_unix_ms: i64,
    pub occurred_at_unix_ms: Option<i64>,
}
