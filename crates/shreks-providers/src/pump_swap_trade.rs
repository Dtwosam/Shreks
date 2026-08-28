use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::Value;
use shreks_core::ProviderId;

use crate::{pump::PUMP_AMM_PROGRAM_ID, ProviderError, ProviderErrorKind};

pub const PUMPSWAP_BUY_EVENT_DISCRIMINATOR: [u8; 8] = [103, 244, 82, 31, 44, 245, 119, 119];
pub const PUMPSWAP_SELL_EVENT_DISCRIMINATOR: [u8; 8] = [62, 47, 55, 10, 165, 3, 220, 42];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapTradeEvidence {
    pub log_index: u32,
    pub pool: String,
    pub user: String,
    pub is_buy: bool,
    pub base_amount_raw: u64,
    pub quote_amount_raw: u64,
    pub user_quote_amount_raw: u64,
    pub timestamp_unix_seconds: i64,
    pub pool_base_reserves_raw: u64,
    pub pool_quote_reserves_raw: u64,
}

/// Decode authoritative Anchor trade events emitted directly by PumpSwap.
///
/// Only `Program data:` emitted while PumpSwap is the active invocation is
/// eligible. The parser consumes the stable event prefix through `pool` and
/// `user`; trailing fee/cashback fields may grow without changing the economic
/// prefix Shreks needs for FL1.
pub fn parse_pump_swap_trade_logs(
    logs: &[Value],
) -> Result<Vec<PumpSwapTradeEvidence>, ProviderError> {
    let mut stack: Vec<String> = Vec::new();
    let mut output = Vec::new();

    for (log_index, log) in logs.iter().filter_map(Value::as_str).enumerate() {
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
        if stack.last().map(String::as_str) != Some(PUMP_AMM_PROGRAM_ID) {
            continue;
        }

        let Some(encoded) = log.strip_prefix("Program data: ") else {
            continue;
        };
        let bytes = BASE64_STANDARD.decode(encoded.trim()).map_err(|error| {
            invalid_response(format!("invalid PumpSwap Program data base64: {error}"))
        })?;
        if bytes.len() < 8 {
            continue;
        }

        let discriminator: [u8; 8] = bytes[..8]
            .try_into()
            .expect("length checked before discriminator conversion");
        let is_buy = match discriminator {
            PUMPSWAP_BUY_EVENT_DISCRIMINATOR => true,
            PUMPSWAP_SELL_EVENT_DISCRIMINATOR => false,
            _ => continue,
        };
        let log_index = u32::try_from(log_index)
            .map_err(|_| invalid_response("PumpSwap log index exceeds u32"))?;
        output.push(decode_trade_event_prefix(&bytes, log_index, is_buy)?);
    }

    Ok(output)
}

fn decode_trade_event_prefix(
    bytes: &[u8],
    log_index: u32,
    is_buy: bool,
) -> Result<PumpSwapTradeEvidence, ProviderError> {
    let mut cursor = 8_usize;
    let timestamp_unix_seconds = read_i64(bytes, &mut cursor, "timestamp")?;
    if timestamp_unix_seconds < 0 {
        return Err(invalid_response("PumpSwap trade timestamp must be non-negative"));
    }

    let base_amount_raw = read_u64(bytes, &mut cursor, "base amount")?;
    let _slippage_limit = read_u64(bytes, &mut cursor, "slippage limit")?;
    let _user_base_reserves = read_u64(bytes, &mut cursor, "user base reserves")?;
    let _user_quote_reserves = read_u64(bytes, &mut cursor, "user quote reserves")?;
    let pool_base_reserves_raw = read_u64(bytes, &mut cursor, "pool base reserves")?;
    let pool_quote_reserves_raw = read_u64(bytes, &mut cursor, "pool quote reserves")?;
    let quote_amount_raw = read_u64(bytes, &mut cursor, "quote amount")?;
    let _lp_fee_basis_points = read_u64(bytes, &mut cursor, "LP fee basis points")?;
    let _lp_fee = read_u64(bytes, &mut cursor, "LP fee")?;
    let _protocol_fee_basis_points =
        read_u64(bytes, &mut cursor, "protocol fee basis points")?;
    let _protocol_fee = read_u64(bytes, &mut cursor, "protocol fee")?;
    let _quote_amount_with_or_without_lp_fee =
        read_u64(bytes, &mut cursor, "fee-adjusted quote amount")?;
    let user_quote_amount_raw = read_u64(bytes, &mut cursor, "user quote amount")?;
    let pool = read_pubkey(bytes, &mut cursor, "pool")?;
    let user = read_pubkey(bytes, &mut cursor, "user")?;

    if base_amount_raw == 0 || quote_amount_raw == 0 || user_quote_amount_raw == 0 {
        return Err(invalid_response(
            "PumpSwap trade event contains zero executed quantity",
        ));
    }

    Ok(PumpSwapTradeEvidence {
        log_index,
        pool,
        user,
        is_buy,
        base_amount_raw,
        quote_amount_raw,
        user_quote_amount_raw,
        timestamp_unix_seconds,
        pool_base_reserves_raw,
        pool_quote_reserves_raw,
    })
}

fn read_u64(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<u64, ProviderError> {
    let end = cursor
        .checked_add(8)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw: [u8; 8] = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?
        .try_into()
        .expect("slice length is exactly eight bytes");
    *cursor = end;
    Ok(u64::from_le_bytes(raw))
}

fn read_i64(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<i64, ProviderError> {
    let end = cursor
        .checked_add(8)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw: [u8; 8] = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?
        .try_into()
        .expect("slice length is exactly eight bytes");
    *cursor = end;
    Ok(i64::from_le_bytes(raw))
}

fn read_pubkey(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<String, ProviderError> {
    let end = cursor
        .checked_add(32)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?;
    *cursor = end;
    Ok(bs58::encode(raw).into_string())
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
        ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
}
