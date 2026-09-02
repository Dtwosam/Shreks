use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use serde_json::Value;
use shreks_core::{
    FastEvent, FastEventId, FastEventKind, FastMarketKey, FastReserveContext, ProviderId, VenueId,
};

use crate::{
    pump::{PUMP_PROGRAM_ID, WRAPPED_SOL_MINT},
    ProviderError, ProviderErrorKind,
};

pub const PUMP_BUY_DISCRIMINATOR: [u8; 8] = [102, 6, 61, 18, 1, 218, 235, 234];
pub const PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR: [u8; 8] =
    [56, 252, 116, 8, 158, 223, 205, 95];
pub const PUMP_BUY_V2_DISCRIMINATOR: [u8; 8] = [184, 23, 238, 97, 103, 197, 211, 61];
pub const PUMP_SELL_DISCRIMINATOR: [u8; 8] = [51, 230, 133, 164, 1, 127, 131, 173];
pub const PUMP_SELL_V2_DISCRIMINATOR: [u8; 8] = [93, 246, 130, 60, 231, 233, 64, 178];
pub const PUMP_TRADE_EVENT_DISCRIMINATOR: [u8; 8] =
    [189, 219, 127, 211, 78, 230, 97, 238];

const DEFAULT_SOL_QUOTE_MINT: &str = "11111111111111111111111111111111";
const MAX_SHAREHOLDERS: usize = 4_096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpTradeSignal {
    pub signature: String,
    pub slot: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpTradeEvidence {
    pub mint: String,
    pub quote_mint: String,
    pub user: String,
    pub is_buy: bool,
    pub token_amount_raw: u64,
    pub sol_amount_raw: u64,
    pub quote_amount_raw: u64,
    pub timestamp_unix_seconds: i64,
    pub virtual_sol_reserves_raw: u64,
    pub virtual_token_reserves_raw: u64,
    pub real_sol_reserves_raw: u64,
    pub real_token_reserves_raw: u64,
    pub virtual_quote_reserves_raw: u64,
    pub real_quote_reserves_raw: u64,
    pub ix_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PumpTradeVerification {
    Pending,
    Verified(Vec<PumpTradeEvidence>),
    Rejected(String),
}

pub fn parse_pump_trade_log_notification(
    body: &str,
) -> Result<Option<PumpTradeSignal>, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!("invalid Pump trade websocket JSON: {error}"))
    })?;

    if value.get("method").and_then(Value::as_str) != Some("logsNotification") {
        return Ok(None);
    }

    let result = value
        .pointer("/params/result")
        .ok_or_else(|| invalid_response("Pump trade logsNotification missing params.result"))?;
    let slot = result
        .pointer("/context/slot")
        .and_then(Value::as_u64)
        .ok_or_else(|| invalid_response("Pump trade logsNotification missing context.slot"))?;
    let notification = result
        .get("value")
        .ok_or_else(|| invalid_response("Pump trade logsNotification missing value"))?;

    if !notification.get("err").is_some_and(Value::is_null) {
        return Ok(None);
    }

    let signature = notification
        .get("signature")
        .and_then(Value::as_str)
        .filter(|signature| !signature.trim().is_empty())
        .ok_or_else(|| invalid_response("Pump trade logsNotification missing signature"))?;
    let logs = notification
        .get("logs")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid_response("Pump trade logsNotification missing logs array"))?;

    let has_trade = logs.iter().filter_map(Value::as_str).any(|log| {
        matches!(
            log.trim(),
            "Program log: Instruction: Buy"
                | "Program log: Instruction: BuyExactSolIn"
                | "Program log: Instruction: BuyV2"
                | "Program log: Instruction: Sell"
                | "Program log: Instruction: SellV2"
        )
    });

    Ok(has_trade.then(|| PumpTradeSignal {
        signature: signature.to_owned(),
        slot,
    }))
}

pub fn classify_pump_trade_transaction(
    body: &str,
    signature: &str,
) -> Result<PumpTradeVerification, ProviderError> {
    let value: Value = serde_json::from_str(body).map_err(|error| {
        invalid_response(format!(
            "invalid Pump trade transaction JSON for {signature}: {error}"
        ))
    })?;

    if let Some(error) = value.get("error").filter(|error| !error.is_null()) {
        return Err(invalid_response(format!(
            "Solana RPC returned an error for Pump trade signature {signature}: {error}"
        )));
    }

    let result = value.get("result").ok_or_else(|| {
        invalid_response(format!(
            "Solana RPC response missing result for Pump trade signature {signature}"
        ))
    })?;
    if result.is_null() {
        return Ok(PumpTradeVerification::Pending);
    }
    if result
        .pointer("/meta/err")
        .is_some_and(|error| !error.is_null())
    {
        return Ok(PumpTradeVerification::Rejected(format!(
            "Pump trade signature {signature} failed onchain"
        )));
    }

    let instructions = collect_trade_instruction_sides(result);
    if instructions.is_empty() {
        return Ok(PumpTradeVerification::Rejected(format!(
            "Pump trade signature {signature} contained no verified Pump buy/sell instruction"
        )));
    }

    let logs = result
        .pointer("/meta/logMessages")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            invalid_response(format!(
                "Pump trade signature {signature} missing meta.logMessages"
            ))
        })?;
    let events = collect_pump_trade_events(logs, signature)?;
    if events.is_empty() {
        return Ok(PumpTradeVerification::Rejected(format!(
            "Pump trade signature {signature} contained no verified Pump tradeEvent"
        )));
    }

    let instruction_buys = instructions.iter().filter(|side| **side).count();
    let instruction_sells = instructions.len().saturating_sub(instruction_buys);
    let event_buys = events.iter().filter(|event| event.is_buy).count();
    let event_sells = events.len().saturating_sub(event_buys);
    if instruction_buys != event_buys || instruction_sells != event_sells {
        return Ok(PumpTradeVerification::Rejected(format!(
            "Pump trade signature {signature} instruction/event side counts disagree"
        )));
    }

    Ok(PumpTradeVerification::Verified(events))
}

#[allow(clippy::too_many_arguments)]
pub fn pump_trade_evidence_to_fast_event(
    evidence: &PumpTradeEvidence,
    signature: &str,
    ordinal: u32,
    sequence: u64,
    slot: u64,
    observed_at_unix_ms: i64,
    base_decimals: u8,
    quote_decimals: u8,
) -> Result<FastEvent, ProviderError> {
    if evidence.token_amount_raw == 0 {
        return Err(invalid_response("Pump tradeEvent token amount must be positive"));
    }
    if evidence.timestamp_unix_seconds < 0 {
        return Err(invalid_response(
            "Pump tradeEvent timestamp must be non-negative",
        ));
    }

    let is_sol_quote =
        evidence.quote_mint == DEFAULT_SOL_QUOTE_MINT || evidence.quote_mint == WRAPPED_SOL_MINT;
    let quote_mint = if is_sol_quote {
        WRAPPED_SOL_MINT.to_owned()
    } else {
        evidence.quote_mint.clone()
    };
    let quote_amount_raw = if is_sol_quote {
        evidence.sol_amount_raw
    } else {
        evidence.quote_amount_raw
    };
    if quote_amount_raw == 0 {
        return Err(invalid_response("Pump tradeEvent quote amount must be positive"));
    }

    let (virtual_quote_reserve_raw, real_quote_reserve_raw) = if is_sol_quote {
        (
            evidence.virtual_sol_reserves_raw,
            evidence.real_sol_reserves_raw,
        )
    } else {
        (
            evidence.virtual_quote_reserves_raw,
            evidence.real_quote_reserves_raw,
        )
    };

    let base_scale = decimal_scale(base_decimals)?;
    let quote_scale = decimal_scale(quote_decimals)?;
    let base_quantity = evidence.token_amount_raw as f64 / base_scale;
    let quote_quantity = quote_amount_raw as f64 / quote_scale;
    let price_quote = quote_quantity / base_quantity;

    let occurred_at_unix_ms = evidence
        .timestamp_unix_seconds
        .checked_mul(1_000)
        .ok_or_else(|| invalid_response("Pump tradeEvent timestamp milliseconds overflow"))?;
    if observed_at_unix_ms < occurred_at_unix_ms {
        return Err(invalid_response(format!(
            "Pump tradeEvent observed timestamp {observed_at_unix_ms} precedes occurrence {occurred_at_unix_ms}"
        )));
    }

    let id = FastEventId::new(signature, ordinal)
        .map_err(|error| invalid_response(format!("invalid Pump FastEvent id: {error}")))?;
    let market = FastMarketKey::new(&evidence.mint, quote_mint, VenueId::PumpFunBondingCurve)
        .map_err(|error| invalid_response(format!("invalid Pump FastEvent market: {error}")))?;
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
    .map_err(|error| invalid_response(format!("invalid Pump FastEvent economics: {error}")))?;

    event
        .with_reserve_context(FastReserveContext::PumpCurve {
            virtual_base_reserve_raw: evidence.virtual_token_reserves_raw,
            virtual_quote_reserve_raw,
            real_base_reserve_raw: evidence.real_token_reserves_raw,
            real_quote_reserve_raw,
            base_decimals,
            quote_decimals,
        })
        .map_err(|error| invalid_response(format!("invalid Pump reserve context: {error}")))
}

fn decimal_scale(decimals: u8) -> Result<f64, ProviderError> {
    let scale = 10_f64.powi(i32::from(decimals));
    if !scale.is_finite() || scale <= 0.0 {
        return Err(invalid_response(format!(
            "invalid Pump trade decimal scale for {decimals} decimals"
        )));
    }
    Ok(scale)
}

fn collect_trade_instruction_sides(result: &Value) -> Vec<bool> {
    let mut sides = Vec::new();
    if let Some(instructions) = result
        .pointer("/transaction/message/instructions")
        .and_then(Value::as_array)
    {
        collect_trade_instruction_sides_from(instructions, &mut sides);
    }
    if let Some(groups) = result
        .pointer("/meta/innerInstructions")
        .and_then(Value::as_array)
    {
        for group in groups {
            if let Some(instructions) = group.get("instructions").and_then(Value::as_array) {
                collect_trade_instruction_sides_from(instructions, &mut sides);
            }
        }
    }
    sides
}

fn collect_trade_instruction_sides_from(instructions: &[Value], output: &mut Vec<bool>) {
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
        if discriminator == PUMP_BUY_DISCRIMINATOR
            || discriminator == PUMP_BUY_EXACT_SOL_IN_DISCRIMINATOR
            || discriminator == PUMP_BUY_V2_DISCRIMINATOR
        {
            output.push(true);
        } else if discriminator == PUMP_SELL_DISCRIMINATOR
            || discriminator == PUMP_SELL_V2_DISCRIMINATOR
        {
            output.push(false);
        }
    }
}

fn collect_pump_trade_events(
    logs: &[Value],
    signature: &str,
) -> Result<Vec<PumpTradeEvidence>, ProviderError> {
    let mut program_stack: Vec<String> = Vec::new();
    let mut events = Vec::new();

    for log in logs.iter().filter_map(Value::as_str) {
        if let Some(program) = invocation_program(log) {
            program_stack.push(program.to_owned());
            continue;
        }
        if let Some(program) = terminated_program(log) {
            if program_stack.last().is_some_and(|active| active == program) {
                program_stack.pop();
            }
            continue;
        }
        let Some(encoded) = log.strip_prefix("Program data: ") else {
            continue;
        };
        if program_stack.last().map(String::as_str) != Some(PUMP_PROGRAM_ID) {
            continue;
        }
        let bytes = BASE64_STANDARD.decode(encoded.trim()).map_err(|error| {
            invalid_response(format!(
                "invalid Pump Program data base64 for {signature}: {error}"
            ))
        })?;
        if bytes.get(..8) != Some(PUMP_TRADE_EVENT_DISCRIMINATOR.as_slice()) {
            continue;
        }
        events.push(decode_trade_event(&bytes[8..], signature)?);
    }

    Ok(events)
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

fn decode_trade_event(
    payload: &[u8],
    signature: &str,
) -> Result<PumpTradeEvidence, ProviderError> {
    let mut cursor = BorshCursor::new(payload, signature);
    let mint = cursor.pubkey("mint")?;
    let sol_amount_raw = cursor.u64("solAmount")?;
    let token_amount_raw = cursor.u64("tokenAmount")?;
    let is_buy = cursor.boolean("isBuy")?;
    let user = cursor.pubkey("user")?;
    let timestamp_unix_seconds = cursor.i64("timestamp")?;
    let virtual_sol_reserves_raw = cursor.u64("virtualSolReserves")?;
    let virtual_token_reserves_raw = cursor.u64("virtualTokenReserves")?;
    let real_sol_reserves_raw = cursor.u64("realSolReserves")?;
    let real_token_reserves_raw = cursor.u64("realTokenReserves")?;
    cursor.pubkey("feeRecipient")?;
    cursor.u64("feeBasisPoints")?;
    cursor.u64("fee")?;
    cursor.pubkey("creator")?;
    cursor.u64("creatorFeeBasisPoints")?;
    cursor.u64("creatorFee")?;
    cursor.boolean("trackVolume")?;
    cursor.u64("totalUnclaimedTokens")?;
    cursor.u64("totalClaimedTokens")?;
    cursor.u64("currentSolVolume")?;
    cursor.i64("lastUpdateTimestamp")?;
    let ix_name = cursor.string("ixName")?;
    cursor.boolean("mayhemMode")?;
    cursor.u64("cashbackFeeBasisPoints")?;
    cursor.u64("cashback")?;
    cursor.u64("buybackFeeBasisPoints")?;
    cursor.u64("buybackFee")?;
    cursor.shareholders()?;
    let quote_mint = cursor.pubkey("quoteMint")?;
    let quote_amount_raw = cursor.u64("quoteAmount")?;
    let virtual_quote_reserves_raw = cursor.u64("virtualQuoteReserves")?;
    let real_quote_reserves_raw = cursor.u64("realQuoteReserves")?;
    cursor.finish()?;

    let ix_side = match ix_name.as_str() {
        "buy" | "buy_exact_sol_in" => true,
        "sell" => false,
        other => {
            return Err(invalid_response(format!(
                "Pump trade signature {signature} emitted unsupported tradeEvent ixName '{other}'"
            )))
        }
    };
    if ix_side != is_buy {
        return Err(invalid_response(format!(
            "Pump trade signature {signature} tradeEvent ixName/isBuy disagree"
        )));
    }
    if mint.trim().is_empty() || quote_mint.trim().is_empty() || user.trim().is_empty() {
        return Err(invalid_response(format!(
            "Pump trade signature {signature} tradeEvent contains blank identity"
        )));
    }

    Ok(PumpTradeEvidence {
        mint,
        quote_mint,
        user,
        is_buy,
        token_amount_raw,
        sol_amount_raw,
        quote_amount_raw,
        timestamp_unix_seconds,
        virtual_sol_reserves_raw,
        virtual_token_reserves_raw,
        real_sol_reserves_raw,
        real_token_reserves_raw,
        virtual_quote_reserves_raw,
        real_quote_reserves_raw,
        ix_name,
    })
}

struct BorshCursor<'a> {
    bytes: &'a [u8],
    offset: usize,
    signature: &'a str,
}

impl<'a> BorshCursor<'a> {
    fn new(bytes: &'a [u8], signature: &'a str) -> Self {
        Self {
            bytes,
            offset: 0,
            signature,
        }
    }

    fn take(&mut self, len: usize, field: &str) -> Result<&'a [u8], ProviderError> {
        let end = self.offset.checked_add(len).ok_or_else(|| {
            invalid_response(format!(
                "Pump trade signature {} tradeEvent offset overflow at {field}",
                self.signature
            ))
        })?;
        let slice = self.bytes.get(self.offset..end).ok_or_else(|| {
            invalid_response(format!(
                "Pump trade signature {} tradeEvent truncated at {field}",
                self.signature
            ))
        })?;
        self.offset = end;
        Ok(slice)
    }

    fn u16(&mut self, field: &str) -> Result<u16, ProviderError> {
        let bytes: [u8; 2] = self.take(2, field)?.try_into().expect("exact u16 width");
        Ok(u16::from_le_bytes(bytes))
    }

    fn u32(&mut self, field: &str) -> Result<u32, ProviderError> {
        let bytes: [u8; 4] = self.take(4, field)?.try_into().expect("exact u32 width");
        Ok(u32::from_le_bytes(bytes))
    }

    fn u64(&mut self, field: &str) -> Result<u64, ProviderError> {
        let bytes: [u8; 8] = self.take(8, field)?.try_into().expect("exact u64 width");
        Ok(u64::from_le_bytes(bytes))
    }

    fn i64(&mut self, field: &str) -> Result<i64, ProviderError> {
        let bytes: [u8; 8] = self.take(8, field)?.try_into().expect("exact i64 width");
        Ok(i64::from_le_bytes(bytes))
    }

    fn boolean(&mut self, field: &str) -> Result<bool, ProviderError> {
        match self.take(1, field)?[0] {
            0 => Ok(false),
            1 => Ok(true),
            value => Err(invalid_response(format!(
                "Pump trade signature {} tradeEvent invalid bool {value} at {field}",
                self.signature
            ))),
        }
    }

    fn pubkey(&mut self, field: &str) -> Result<String, ProviderError> {
        Ok(bs58::encode(self.take(32, field)?).into_string())
    }

    fn string(&mut self, field: &str) -> Result<String, ProviderError> {
        let len = usize::try_from(self.u32(field)?).map_err(|_| {
            invalid_response(format!(
                "Pump trade signature {} tradeEvent string length overflow at {field}",
                self.signature
            ))
        })?;
        let bytes = self.take(len, field)?;
        String::from_utf8(bytes.to_vec()).map_err(|error| {
            invalid_response(format!(
                "Pump trade signature {} tradeEvent invalid UTF-8 at {field}: {error}",
                self.signature
            ))
        })
    }

    fn shareholders(&mut self) -> Result<(), ProviderError> {
        let count = usize::try_from(self.u32("shareholders")?).map_err(|_| {
            invalid_response(format!(
                "Pump trade signature {} shareholder count overflow",
                self.signature
            ))
        })?;
        if count > MAX_SHAREHOLDERS {
            return Err(invalid_response(format!(
                "Pump trade signature {} shareholder count {count} exceeds cap {MAX_SHAREHOLDERS}",
                self.signature
            )));
        }
        for _ in 0..count {
            self.pubkey("shareholder.address")?;
            self.u16("shareholder.shareBps")?;
        }
        Ok(())
    }

    fn finish(&self) -> Result<(), ProviderError> {
        if self.offset != self.bytes.len() {
            return Err(invalid_response(format!(
                "Pump trade signature {} tradeEvent has {} unexpected trailing bytes",
                self.signature,
                self.bytes.len() - self.offset
            )));
        }
        Ok(())
    }
}

fn invalid_response(message: impl Into<String>) -> ProviderError {
    ProviderError::new(
        ProviderId::Helius,
        ProviderErrorKind::InvalidResponse,
        message,
    )
}
