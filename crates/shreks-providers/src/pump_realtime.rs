use serde_json::{json, Value};

use crate::{
    pump::{
        parse_pump_lifecycle_log_notification, PumpLifecycleSignal, PUMP_PROGRAM_ID,
    },
    pump_trade::{
        classify_pump_trade_transaction, PumpTradeEvidence, PumpTradeVerification,
        PUMP_BUY_DISCRIMINATOR, PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR,
        PUMP_BUY_V2_DISCRIMINATOR, PUMP_SELL_DISCRIMINATOR, PUMP_SELL_V2_DISCRIMINATOR,
    },
    ProviderError, ProviderErrorKind,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpRealtimeNotification {
    pub signature: String,
    pub slot: u64,
    pub lifecycle: Option<PumpLifecycleSignal>,
    pub trades: Vec<PumpTradeEvidence>,
}

/// Parse one confirmed standard-Solana Pump `logsNotification` into the complete
/// realtime evidence Shreks can obtain without an additional RPC request.
///
/// The already-audited transaction trade decoder remains the single economic
/// codec. This function derives only the Pump instruction-side evidence that is
/// present in the runtime logs, then feeds the original log stream through that
/// decoder. No instruction max/min amount is treated as a fill.
pub fn parse_pump_realtime_log_notification(
    body: &str,
) -> Result<Option<PumpRealtimeNotification>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump realtime websocket JSON: {error}"))
    })?;

    if value.get("method").and_then(Value::as_str) != Some("logsNotification") {
        return Ok(None);
    }

    let result = value
        .pointer("/params/result")
        .ok_or_else(|| invalid_response("Pump realtime logsNotification missing params.result"))?;
    let slot = result
        .pointer("/context/slot")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump realtime logsNotification missing context.slot"))?;
    let notification = result
        .get("value")
        .ok_or_else(|| invalid_response("Pump realtime logsNotification missing value"))?;

    if !notification.get("err").is_some_and(Value::is_null) {
        return Ok(None);
    }

    let signature = notification
        .get("signature")
        .and_then(Value::as_str)
        .filter(|signature| !signature.trim().is_empty())
        .ok_or_else(|| invalid_response("Pump realtime logsNotification missing signature"))?;
    let logs = notification
        .get("logs")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_response("Pump realtime logsNotification missing logs array"))?;

    let lifecycle = parse_pump_lifecycle_log_notification(body)?;
    let trade_discriminators = pump_trade_instruction_discriminators(logs);
    let trades = if trade_discriminators.is_empty() {
        Vec::new()
    } else {
        decode_trade_evidence_from_notification_logs(signature, slot, logs, &trade_discriminators)?
    };

    if lifecycle.is_none() && trades.is_empty() {
        return Ok(None);
    }

    Ok(Some(PumpRealtimeNotification {
        signature: signature.to_owned(),
        slot,
        lifecycle,
        trades,
    }))
}

fn decode_trade_evidence_from_notification_logs(
    signature: &str,
    slot: u64,
    logs: &[Value],
    discriminators: &[[u8; 8]],
) -> Result<Vec<PumpTradeEvidence>, ProviderError> {
    let instructions: Vec<Value> = discriminators
        .iter()
        .map(|discriminator| {
            json!({
                "accounts": [],
                "data": bs58::encode(discriminator).into_string(),
                "programId": PUMP_PROGRAM_ID
            })
        })
        .collect();

    let synthetic = json!({
        "jsonrpc": "2.0",
        "result": {
            "slot": slot,
            "meta": {
                "err": null,
                "logMessages": logs,
                "innerInstructions": []
            },
            "transaction": {
                "message": {
                    "instructions": instructions
                }
            }
        },
        "id": "shreks-pump-realtime"
    });

    match classify_pump_trade_transaction(&synthetic.to_string(), signature)? {
        PumpTradeVerification::Verified(events) => Ok(events),
        PumpTradeVerification::Pending => Err(invalid_response(format!(
            "Pump realtime signature {signature} unexpectedly classified as pending"
        ))),
        PumpTradeVerification::Rejected(reason) => Err(invalid_response(format!(
            "Pump realtime signature {signature} contained a trade instruction but no authoritative trade evidence: {reason}"
        ))),
    }
}

fn pump_trade_instruction_discriminators(logs: &[Value]) -> Vec<[u8; 8]> {
    let mut stack: Vec<String> = Vec::new();
    let mut output = Vec::new();

    for log in logs.iter().filter_map(Value::as_str) {
        if let Some(program) = invocation_program(log) {
            stack.push(program.to_owned());
            continue;
        }
        if let Some(program) = terminated_program(log) {
            if stack.last().is_some_and(|active| active == program) {
                stack.pop();
            }
            continue;
        }
        if stack.last().map(String::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }

        let discriminator = match log.trim() {
            "Program log: Instruction: Buy" => Some(PUMP_BUY_DISCRIMINATOR),
            "Program log: Instruction: BuyExactSolIn" => {
                Some(PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR)
            }
            "Program log: Instruction: BuyV2" => Some(PUMP_BUY_V2_DISCRIMINATOR),
            "Program log: Instruction: Sell" => Some(PUMP_SELL_DISCRIMINATOR),
            "Program log: Instruction: SellV2" => Some(PUMP_SELL_V2_DISCRIMINATOR),
            _ => None,
        };
        if let Some(discriminator) = discriminator {
            output.push(discriminator);
        }
    }

    output
}

fn invocation_program(log: &str) -> Option<&str> {
    let rest = log.strip_prefix("Program ")?;
    rest.split_once(" invoke [").map(|(program, _)| program)
}

fn terminated_program(log: &str) -> Option<&str> {
    let rest = log.strip_prefix("Program ")?;
    if let Some(program) = rest.strip_suffix(" success") {
        return Some(program);
    }
    rest.split_once(" failed:").map(|(program, _)| program)
}

fn invalid_response(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        shreks_core::ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
}
