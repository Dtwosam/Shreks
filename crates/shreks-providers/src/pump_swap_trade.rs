use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::Value;
use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastReserveContext, ProviderId, VenueId,
};

use crate::{pump::PUMP_AMM_PROGRAM_ID, ProviderError, ProviderErrorKind};

pub const PUMPSWAP_BUY_EVENT_DISCRIMINATOR: [u8; 8] = [103, 244, 82, 31, 44, 245, 119, 119];
pub const PUMPSWAP_SELL_EVENT_DISCRIMINATOR: [u8; 8] = [62, 47, 55, 10, 165, 3, 220, 42];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapCurrentEconomicsEvidence {
    pub coin_creator: String,
    pub coin_creator_fee_basis_points: u64,
    pub coin_creator_fee_raw: u64,
    pub cashback_fee_basis_points: u64,
    pub cashback_raw: u64,
    pub buyback_fee_basis_points: u64,
    pub buyback_fee_raw: u64,
    pub virtual_quote_reserves_raw: i128,
    pub can_boost: bool,
    pub base_supply_raw: u64,
}

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
    pub lp_fee_basis_points: u64,
    pub lp_fee_raw: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee_raw: u64,
    pub quote_amount_with_or_without_lp_fee_raw: u64,
    pub current_economics: Option<PumpSwapCurrentEconomicsEvidence>,
}

/// Decode authoritative Anchor trade events emitted directly by PumpSwap.
///
/// Only `Program data:` emitted while PumpSwap is the active invocation is
/// eligible. The stable event prefix remains mandatory. Newer economics fields
/// are retained only when the complete currently-known suffix decodes exactly;
/// older or intermediate suffixes remain valid FL1 evidence but are explicitly
/// unknown to FL3 rather than being assigned today's fee/reserve semantics.
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

/// Convert one verified PumpSwap event into the provider-neutral FastEvent
/// contract. Market identity must come from verified Pump graduation lifecycle
/// evidence; the event payload itself intentionally does not invent mint data.
/// `quote_amount_raw` is the executed market quote quantity. The separate
/// fee-adjusted `user_quote_amount_raw` is not used for FL1 market state.
#[allow(clippy::too_many_arguments)]
pub fn pump_swap_trade_evidence_to_fast_event(
    evidence: &PumpSwapTradeEvidence,
    signature: &str,
    ordinal: u32,
    sequence: u64,
    slot: u64,
    observed_at_unix_ms: i64,
    mint: &str,
    quote_mint: &str,
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<FastEvent, ProviderError> {
    if evidence.base_amount_raw == 0 {
        return Err(invalid_response(
            "PumpSwap trade event base amount must be positive",
        ));
    }
    if evidence.quote_amount_raw == 0 {
        return Err(invalid_response(
            "PumpSwap trade event quote amount must be positive",
        ));
    }
    if evidence.timestamp_unix_seconds < 0 {
        return Err(invalid_response(
            "PumpSwap trade event timestamp must be non-negative",
        ));
    }

    let base_scale = decimal_scale(base_decimals)?;
    let quote_scale = decimal_scale(quote_decimals)?;
    let base_quantity = evidence.base_amount_raw as f64 / base_scale;
    let quote_quantity = evidence.quote_amount_raw as f64 / quote_scale;
    let price_quote = quote_quantity / base_quantity;

    let occurred_at_unix_ms = evidence
        .timestamp_unix_seconds
        .checked_mul(1_000)
        .ok_or_else(|| invalid_response("PumpSwap trade timestamp milliseconds overflow"))?;
    if observed_at_unix_ms < occurred_at_unix_ms {
        return Err(invalid_response(format!(
            "PumpSwap trade observed timestamp {observed_at_unix_ms} precedes occurrence {occurred_at_unix_ms}"
        )));
    }

    let id = FastEventId::new(signature, ordinal)
        .map_err(|error| invalid_response(format!("invalid PumpSwap FastEvent id: {error}")))?;
    let market = FastMarketKey::new(mint, quote_mint, VenueId::PumpSwap)
        .map_err(|error| invalid_response(format!("invalid PumpSwap FastEvent market: {error}")))?;
    let event = FastEvent::new(
        id,
        sequence,
        ProviderId::Helius,
        market,
        if evidence.is_buy {
            FastEventKind::Buy
        } else {
            FastEventKind::Sell
        },
        Some(evidence.user.clone()),
        slot,
        occurred_at_unix_ms,
        observed_at_unix_ms,
        base_quantity,
        quote_quantity,
        price_quote,
    )
    .map_err(|error| invalid_response(format!("invalid PumpSwap FastEvent economics: {error}")))?;

    event
        .with_reserve_context(FastReserveContext::PumpSwapPool {
            pool_base_reserve_raw: evidence.pool_base_reserves_raw,
            pool_quote_reserve_raw: evidence.pool_quote_reserves_raw,
            base_decimals,
            quote_decimals,
        })
        .map_err(|error| invalid_response(format!("invalid PumpSwap reserve context: {error}")))
}

fn decimal_scale(decimals: u8) -> Result<f64, ProviderError> {
    let scale = 10_f64.powi(i32::from(decimals));
    if !scale.is_finite() || scale <= 0.0 {
        return Err(invalid_response(format!(
            "invalid PumpSwap trade decimal scale for {decimals} decimals"
        )));
    }
    Ok(scale)
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
    let lp_fee_basis_points = read_u64(bytes, &mut cursor, "LP fee basis points")?;
    let lp_fee_raw = read_u64(bytes, &mut cursor, "LP fee")?;
    let protocol_fee_basis_points =
        read_u64(bytes, &mut cursor, "protocol fee basis points")?;
    let protocol_fee_raw = read_u64(bytes, &mut cursor, "protocol fee")?;
    let quote_amount_with_or_without_lp_fee_raw =
        read_u64(bytes, &mut cursor, "fee-adjusted quote amount")?;
    let user_quote_amount_raw = read_u64(bytes, &mut cursor, "user quote amount")?;
    let pool = read_pubkey(bytes, &mut cursor, "pool")?;
    let user = read_pubkey(bytes, &mut cursor, "user")?;

    if base_amount_raw == 0 || quote_amount_raw == 0 || user_quote_amount_raw == 0 {
        return Err(invalid_response(
            "PumpSwap trade event contains zero executed quantity",
        ));
    }

    let current_economics = if cursor == bytes.len() {
        None
    } else {
        decode_current_economics_suffix(bytes, cursor, is_buy).ok()
    };

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
        lp_fee_basis_points,
        lp_fee_raw,
        protocol_fee_basis_points,
        protocol_fee_raw,
        quote_amount_with_or_without_lp_fee_raw,
        current_economics,
    })
}

fn decode_current_economics_suffix(
    bytes: &[u8],
    mut cursor: usize,
    is_buy: bool,
) -> Result<PumpSwapCurrentEconomicsEvidence, ProviderError> {
    let _user_base_token_account = read_pubkey(bytes, &mut cursor, "user base token account")?;
    let _user_quote_token_account = read_pubkey(bytes, &mut cursor, "user quote token account")?;
    let _protocol_fee_recipient = read_pubkey(bytes, &mut cursor, "protocol fee recipient")?;
    let _protocol_fee_recipient_token_account =
        read_pubkey(bytes, &mut cursor, "protocol fee recipient token account")?;
    let coin_creator = read_pubkey(bytes, &mut cursor, "coin creator")?;
    let coin_creator_fee_basis_points =
        read_u64(bytes, &mut cursor, "coin creator fee basis points")?;
    let coin_creator_fee_raw = read_u64(bytes, &mut cursor, "coin creator fee")?;

    if is_buy {
        let _track_volume = read_bool(bytes, &mut cursor, "track volume")?;
        let _total_unclaimed_tokens = read_u64(bytes, &mut cursor, "total unclaimed tokens")?;
        let _total_claimed_tokens = read_u64(bytes, &mut cursor, "total claimed tokens")?;
        let _current_sol_volume = read_u64(bytes, &mut cursor, "current SOL volume")?;
        let _last_update_timestamp = read_i64(bytes, &mut cursor, "last update timestamp")?;
        let _min_base_amount_out = read_u64(bytes, &mut cursor, "minimum base amount out")?;
        let _ix_name = read_string(bytes, &mut cursor, "instruction name")?;
    }

    let cashback_fee_basis_points = read_u64(bytes, &mut cursor, "cashback fee basis points")?;
    let cashback_raw = read_u64(bytes, &mut cursor, "cashback")?;
    let buyback_fee_basis_points = read_u64(bytes, &mut cursor, "buyback fee basis points")?;
    let buyback_fee_raw = read_u64(bytes, &mut cursor, "buyback fee")?;
    let virtual_quote_reserves_raw = read_i128(bytes, &mut cursor, "virtual quote reserves")?;
    let can_boost = read_bool(bytes, &mut cursor, "can boost")?;
    let base_supply_raw = read_u64(bytes, &mut cursor, "base supply")?;

    if cursor != bytes.len() {
        return Err(invalid_response(format!(
            "PumpSwap current trade event suffix has {} unexpected trailing bytes",
            bytes.len() - cursor
        )));
    }

    Ok(PumpSwapCurrentEconomicsEvidence {
        coin_creator,
        coin_creator_fee_basis_points,
        coin_creator_fee_raw,
        cashback_fee_basis_points,
        cashback_raw,
        buyback_fee_basis_points,
        buyback_fee_raw,
        virtual_quote_reserves_raw,
        can_boost,
        base_supply_raw,
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

fn read_i128(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<i128, ProviderError> {
    let end = cursor
        .checked_add(16)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw: [u8; 16] = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?
        .try_into()
        .expect("slice length is exactly sixteen bytes");
    *cursor = end;
    Ok(i128::from_le_bytes(raw))
}

fn read_bool(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<bool, ProviderError> {
    let value = *bytes
        .get(*cursor)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?;
    *cursor = cursor
        .checked_add(1)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    match value {
        0 => Ok(false),
        1 => Ok(true),
        other => Err(invalid_response(format!(
            "PumpSwap trade event invalid bool {other} at {field}"
        ))),
    }
}

fn read_u32(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<u32, ProviderError> {
    let end = cursor
        .checked_add(4)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw: [u8; 4] = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?
        .try_into()
        .expect("slice length is exactly four bytes");
    *cursor = end;
    Ok(u32::from_le_bytes(raw))
}

fn read_string(bytes: &[u8], cursor: &mut usize, field: &str) -> Result<String, ProviderError> {
    let len = usize::try_from(read_u32(bytes, cursor, field)?)
        .map_err(|_| invalid_response(format!("PumpSwap {field} length overflow")))?;
    let end = cursor
        .checked_add(len)
        .ok_or_else(|| invalid_response(format!("PumpSwap {field} offset overflow")))?;
    let raw = bytes
        .get(*cursor..end)
        .ok_or_else(|| invalid_response(format!("PumpSwap trade event missing {field}")))?;
    *cursor = end;
    String::from_utf8(raw.to_vec())
        .map_err(|error| invalid_response(format!("PumpSwap invalid UTF-8 at {field}: {error}")))
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