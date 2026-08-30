use std::collections::HashSet;

use serde_json::{json, Value};
use shreks_core::ProviderId;

use crate::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID},
    ProviderError, ProviderErrorKind,
};

pub fn pump_realtime_logs_subscribe_request(
    request_id: u64,
    mentioned_pubkey: &str,
) -> Result<Value, ProviderError> {
    let mentioned_pubkey = mentioned_pubkey.trim();
    if mentioned_pubkey.is_empty() {
        return Err(invalid_scope("realtime logs subscription pubkey must not be blank"));
    }

    Ok(json!({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [mentioned_pubkey]},
            {"commitment": "confirmed"}
        ]
    }))
}

pub fn pump_realtime_initial_mentions(
    tracked_pools: &[String],
) -> Result<Vec<String>, ProviderError> {
    let mut seen = HashSet::with_capacity(tracked_pools.len());
    let mut mentions = Vec::with_capacity(tracked_pools.len().saturating_add(1));
    mentions.push(PUMP_PROGRAM_ID.to_owned());

    for pool in tracked_pools {
        let pool = pool.trim();
        if pool.is_empty() {
            return Err(invalid_scope("tracked PumpSwap pool must not be blank"));
        }
        if pool == PUMP_AMM_PROGRAM_ID {
            return Err(invalid_scope(
                "global PumpSwap program subscription is forbidden; use verified pool addresses",
            ));
        }
        if pool == PUMP_PROGRAM_ID {
            return Err(invalid_scope(
                "tracked PumpSwap pool cannot equal the Pump bonding-curve program id",
            ));
        }
        if !seen.insert(pool.to_owned()) {
            return Err(invalid_scope("tracked PumpSwap pool set contains a duplicate"));
        }
        mentions.push(pool.to_owned());
    }

    Ok(mentions)
}

fn invalid_scope(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidRequest,
        message,
    )
}
