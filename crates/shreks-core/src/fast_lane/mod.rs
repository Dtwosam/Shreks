mod event;
mod state;

pub use event::{FastEvent, FastEventError, FastEventId, FastEventKind, FastMarketKey};
pub use state::{
    FastMarketSnapshot, FastMarketState, FastStateError, FastWindowSummary,
    DEFAULT_FAST_WINDOWS_MS,
};
