use std::collections::{BTreeMap, HashSet};

use serde_json::{json, Value};
use shreks_core::ProviderId;

use crate::{
    pump::{PUMP_AMM_PROGRAM_ID, PUMP_PROGRAM_ID},
    ProviderError, ProviderErrorKind,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpRealtimeSubscriptionChange {
    Unsubscribe { pool: String, subscription_id: u64 },
    Subscribe { pool: String },
}

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
    let tracked_pools = validated_tracked_pools(tracked_pools)?;
    let mut mentions = Vec::with_capacity(tracked_pools.len().saturating_add(1));
    mentions.push(PUMP_PROGRAM_ID.to_owned());
    mentions.extend(tracked_pools);
    Ok(mentions)
}

/// Return the exact provider-side changes required to move from the current
/// pool subscriptions to the desired bounded target set. Removals are emitted
/// first in canonical pool order so reconciliation never temporarily exceeds
/// the configured target count. Additions preserve target-selection order.
pub fn pump_realtime_subscription_changes(
    current: &BTreeMap<String, u64>,
    targets: &[String],
) -> Result<Vec<PumpRealtimeSubscriptionChange>, ProviderError> {
    let targets = validated_tracked_pools(targets)?;
    let target_set = targets.iter().cloned().collect::<HashSet<_>>();

    for pool in current.keys() {
        let canonical = validate_tracked_pool(pool)?;
        if canonical != *pool {
            return Err(invalid_scope(
                "current PumpSwap subscription pool must use canonical trimmed identity",
            ));
        }
    }

    let mut changes = Vec::new();
    for (pool, subscription_id) in current {
        if !target_set.contains(pool) {
            changes.push(PumpRealtimeSubscriptionChange::Unsubscribe {
                pool: pool.clone(),
                subscription_id: *subscription_id,
            });
        }
    }

    for pool in targets {
        if !current.contains_key(&pool) {
            changes.push(PumpRealtimeSubscriptionChange::Subscribe { pool });
        }
    }

    Ok(changes)
}

fn validated_tracked_pools(tracked_pools: &[String]) -> Result<Vec<String>, ProviderError> {
    let mut seen = HashSet::with_capacity(tracked_pools.len());
    let mut pools = Vec::with_capacity(tracked_pools.len());
    for pool in tracked_pools {
        let pool = validate_tracked_pool(pool)?;
        if !seen.insert(pool.clone()) {
            return Err(invalid_scope("tracked PumpSwap pool set contains a duplicate"));
        }
        pools.push(pool);
    }
    Ok(pools)
}

fn validate_tracked_pool(pool: &str) -> Result<String, ProviderError> {
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
    Ok(pool.to_owned())
}

fn invalid_scope(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidRequest,
        message,
    )
}
