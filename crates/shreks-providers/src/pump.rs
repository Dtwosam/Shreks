//! Direct Pump.fun launch parsing from standard Solana logs and transactions.
//!
//! This module deliberately separates the cheap log signal from the verified
//! transaction decode. A log notification can tell Shreks which signatures are
//! worth fetching; only a Pump-program instruction with a known creation
//! discriminator is allowed to become a discovered token.

use std::time::Duration;

use serde_json::{json, Value};
use shreks_core::{DiscoveredToken, ProviderId, VenueId};

use crate::{ProviderError, ProviderErrorKind};

pub const PUMP_PROGRAM_ID: &str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";
pub const PUMP_AMM_PROGRAM_ID: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";

pub const PUMP_CREATE_DISCRIMINATOR: [u8; 8] = [24, 30, 200, 40, 5, 28, 7, 119];
pub const PUMP_CREATE_V2_DISCRIMINATOR: [u8; 8] = [214, 144, 76, 236, 95, 139, 49, 180];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpCreationSignal {
    pub signature: String,
    pub slot: u64,
}

/// Build the standard Solana `logsSubscribe` request used for Pump discovery.
/// The `mentions` filter intentionally contains exactly one pubkey, matching
/// the standard PubSub contract.
pub fn pump_logs_subscribe_request() -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [
            {
                "mentions": [PUMP_PROGRAM_ID]
            },
            {
                "commitment": "confirmed"
            }
        ]
    })
}

/// Parse the acknowledgement for Shreks' Pump log subscription.
/// Notifications and other unrelated websocket frames are not acknowledgements.
pub fn parse_pump_subscription_ack(body: &str) -> Result<Option<u64>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump subscription JSON: {error}"))
    })?;

    if value.get("id").and_then(Value::as_u64) != Some(1) {
        return Ok(None);
    }

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        let code = error.get("code").and_then(Value::as_i64);
        let message = error
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("subscription rejected");
        let kind = match code {
            Some(-32602..=-32600) => ProviderErrorKind::InvalidRequest,
            _ => ProviderErrorKind::InvalidResponse,
        };
        return Err(ProviderError::new(
            ProviderId::Helius,
            kind,
            format!("Pump log subscription rejected: {message}"),
        ));
    }

    let subscription_id = value
        .get("result")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump subscription acknowledgement missing result"))?;
    Ok(Some(subscription_id))
}

/// Bounded exponential reconnect delay for a dropped Pump websocket.
pub fn pump_reconnect_delay(attempt: u32) -> Duration {
    let exponent = attempt.min(5);
    let seconds = (1_u64 << exponent).min(30);
    Duration::from_secs(seconds)
}

/// Parse one standard Solana `logsNotification` frame and return a cheap Pump
/// creation signal when the transaction succeeded and logged Create/CreateV2.
///
/// Subscription acknowledgements and unrelated websocket messages are ignored
/// rather than treated as provider failures.
pub fn parse_pump_log_notification(
    body: &str,
) -> Result<Option<PumpCreationSignal>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump log websocket JSON: {error}"))
    })?;

    if value.get("method").and_then(Value::as_str) != Some("logsNotification") {
        return Ok(None);
    }

    let result = value
        .pointer("/params/result")
        .ok_or_else(|| invalid_response("Pump logsNotification missing params.result"))?;
    let slot = result
        .pointer("/context/slot")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump logsNotification missing context.slot"))?;
    let notification = result
        .get("value")
        .ok_or_else(|| invalid_response("Pump logsNotification missing value"))?;

    if !notification.get("err").is_some_and(Value::is_null) {
        return Ok(None);
    }

    let signature = notification
        .get("signature")
        .and_then(Value::as_str)
        .filter(|signature| !signature.trim().is_empty())
        .ok_or_else(|| invalid_response("Pump logsNotification missing signature"))?;
    let logs = notification
        .get("logs")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_response("Pump logsNotification missing logs array"))?;

    let is_creation = logs.iter().filter_map(Value::as_str).any(|log| {
        log.contains("Instruction: CreateV2") || log.contains("Instruction: Create")
    });

    if !is_creation {
        return Ok(None);
    }

    Ok(Some(PumpCreationSignal {
        signature: signature.to_owned(),
        slot,
    }))
}

/// Verify a fetched Solana transaction contains an actual Pump Create/CreateV2
/// instruction and normalize account #1 (the instruction's first account) as
/// the newly created mint.
pub fn parse_pump_creation_transaction(
    body: &str,
    signature: &str,
    discovered_at_unix_ms: i64,
) -> Result<DiscoveredToken, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!(
            "invalid Pump transaction JSON for {signature}: {error}"
        ))
    })?;

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        return Err(invalid_response(format!(
            "Solana RPC returned an error for Pump signature {signature}: {error}"
        )));
    }

    let result = value
        .get("result")
        .filter(|result| !result.is_null())
        .ok_or_else(|| {
            invalid_response(format!(
                "Solana RPC returned no transaction for Pump signature {signature}"
            ))
        })?;

    if result
        .pointer("/meta/err")
        .is_some_and(|error| !error.is_null())
    {
        return Err(invalid_response(format!(
            "Pump signature {signature} failed onchain"
        )));
    }

    if let Some(mint) = find_creation_mint(result) {
        return Ok(DiscoveredToken {
            mint,
            pair_address: None,
            dex_id: Some("pumpfun".to_owned()),
            venue: Some(VenueId::PumpFunBondingCurve),
            discovered_at_unix_ms,
            source: ProviderId::Helius,
        });
    }

    Err(invalid_response(format!(
        "Pump signature {signature} contained no verified Create/CreateV2 instruction"
    )))
}

fn find_creation_mint(result: &Value) -> Option<String> {
    if let Some(instructions) = result
        .pointer("/transaction/message/instructions")
        .and_then(Value::as_array)
    {
        if let Some(mint) = find_creation_mint_in_instructions(instructions) {
            return Some(mint);
        }
    }

    let inner_groups = result
        .pointer("/meta/innerInstructions")
        .and_then(Value::as_array)?;
    for group in inner_groups {
        let Some(instructions) = group.get("instructions").and_then(Value::as_array) else {
            continue;
        };
        if let Some(mint) = find_creation_mint_in_instructions(instructions) {
            return Some(mint);
        }
    }

    None
}

fn find_creation_mint_in_instructions(instructions: &[Value]) -> Option<String> {
    for instruction in instructions {
        if instruction.get("programId").and_then(Value::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }

        let Some(data) = instruction.get("data").and_then(Value::as_str) else {
            continue;
        };
        let Ok(decoded) = bs58::decode(data).into_vec() else {
            continue;
        };
        let Some(discriminator) = decoded.get(..8) else {
            continue;
        };
        if discriminator != PUMP_CREATE_DISCRIMINATOR
            && discriminator != PUMP_CREATE_V2_DISCRIMINATOR
        {
            continue;
        }

        let Some(mint) = instruction
            .get("accounts")
            .and_then(Value::as_array)
            .and_then(|accounts| accounts.first())
            .and_then(Value::as_str)
            .filter(|mint| !mint.trim().is_empty())
        else {
            continue;
        };

        return Some(mint.to_owned());
    }

    None
}

fn invalid_response(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
}
