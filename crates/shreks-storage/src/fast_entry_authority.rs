use std::{error::Error, fmt};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use shreks_core::{
    ExecutionCostModel, ExecutionEconomics, ExecutionEconomicsError,
    ExecutionLegCostInput, ExecutionTradeInput,
};

use crate::{
    FastEntryExecutionWire, FastExecutionLegCostWire,
};


pub const FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_entry_authority_request";
pub const FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION: u16 = 1;
pub const FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME: &str =
    "shreks.fast_deterministic_entry_authority_result";
pub const FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION: u16 = 1;


#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicEntryAuthorityRequestWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub mint: String,
    pub quote_mint: String,
    pub decision_executable_entry_price_quote: f64,
    pub execution: FastEntryExecutionWire,
}


#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FastDeterministicEntryAuthorityResultWire {
    pub schema_name: String,
    pub schema_version: u16,
    pub mint: String,
    pub quote_mint: String,
    pub intended_base_quantity: f64,
    pub decision_executable_entry_price_quote: f64,
    pub maximum_acceptable_entry_price_quote: f64,
    pub expected_entry_variable_cost_bps: u32,
    pub expected_entry_fixed_cost_quote: f64,
    pub result_fingerprint_sha256: String,
}


#[derive(Debug)]
pub enum FastDeterministicEntryAuthorityError {
    Json(String),
    Invalid(&'static str),
    Economics(ExecutionEconomicsError),
    FingerprintMismatch,
}


impl fmt::Display for FastDeterministicEntryAuthorityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(message) => write!(
                formatter,
                "deterministic entry authority JSON error: {message}"
            ),
            Self::Invalid(message) => write!(
                formatter,
                "invalid deterministic entry authority request: {message}"
            ),
            Self::Economics(error) => write!(
                formatter,
                "deterministic entry authority FL3 economics failed: {error}"
            ),
            Self::FingerprintMismatch => formatter.write_str(
                "deterministic entry authority result fingerprint mismatch"
            ),
        }
    }
}


impl Error for FastDeterministicEntryAuthorityError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Economics(error) => Some(error),
            _ => None,
        }
    }
}


impl From<ExecutionEconomicsError> for FastDeterministicEntryAuthorityError {
    fn from(value: ExecutionEconomicsError) -> Self {
        Self::Economics(value)
    }
}


pub fn decode_fast_deterministic_entry_authority_request_json(
    input: &str,
) -> Result<FastDeterministicEntryAuthorityRequestWire, FastDeterministicEntryAuthorityError> {
    if input.is_empty() {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "JSON payload must be non-empty",
        ));
    }
    let request: FastDeterministicEntryAuthorityRequestWire =
        serde_json::from_str(input)
            .map_err(|error| FastDeterministicEntryAuthorityError::Json(error.to_string()))?;
    validate_request_identity(&request)?;
    Ok(request)
}


pub fn derive_fast_deterministic_entry_authority(
    request: &FastDeterministicEntryAuthorityRequestWire,
) -> Result<FastDeterministicEntryAuthorityResultWire, FastDeterministicEntryAuthorityError> {
    validate_request_identity(request)?;
    if request.execution.trade.executable_entry_price_quote
        != request.decision_executable_entry_price_quote
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "execution entry price must equal decision executable entry price",
        ));
    }

    let model = build_cost_model(&request.execution);
    let trade = build_trade(&request.execution);
    let economics = ExecutionEconomics::assess(&model, &trade)?;

    let entry = &request.execution.cost_model.entry;
    let expected_entry_variable_cost_bps = entry
        .effective_fee_bps
        .checked_add(entry.expected_impact_bps)
        .and_then(|value| value.checked_add(entry.expected_slippage_bps))
        .and_then(|value| value.checked_add(entry.expected_latency_bps))
        .ok_or(FastDeterministicEntryAuthorityError::Invalid(
            "entry variable cost basis points overflow",
        ))?;
    let expected_entry_fixed_cost_quote =
        entry.network_fee_quote + entry.priority_fee_quote + entry.expected_failure_cost_quote;
    if !expected_entry_fixed_cost_quote.is_finite()
        || expected_entry_fixed_cost_quote < 0.0
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "entry fixed cost must be finite and non-negative",
        ));
    }

    let mut result = FastDeterministicEntryAuthorityResultWire {
        schema_name: FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME.to_owned(),
        schema_version: FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION,
        mint: request.mint.clone(),
        quote_mint: request.quote_mint.clone(),
        intended_base_quantity: request.execution.trade.base_quantity,
        decision_executable_entry_price_quote: request.decision_executable_entry_price_quote,
        maximum_acceptable_entry_price_quote: economics.maximum_acceptable_entry_price_quote,
        expected_entry_variable_cost_bps,
        expected_entry_fixed_cost_quote,
        result_fingerprint_sha256: "0".repeat(64),
    };
    result.result_fingerprint_sha256 = result_fingerprint_sha256(&result)?;
    Ok(result)
}


pub fn encode_fast_deterministic_entry_authority_result_json(
    result: &FastDeterministicEntryAuthorityResultWire,
) -> Result<String, FastDeterministicEntryAuthorityError> {
    validate_result(result)?;
    let expected = result_fingerprint_sha256(result)?;
    if result.result_fingerprint_sha256 != expected {
        return Err(FastDeterministicEntryAuthorityError::FingerprintMismatch);
    }
    serde_json::to_string(result)
        .map_err(|error| FastDeterministicEntryAuthorityError::Json(error.to_string()))
}


fn validate_request_identity(
    request: &FastDeterministicEntryAuthorityRequestWire,
) -> Result<(), FastDeterministicEntryAuthorityError> {
    if request.schema_name != FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_NAME {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "schema_name is incompatible",
        ));
    }
    if request.schema_version != FAST_DETERMINISTIC_ENTRY_AUTHORITY_REQUEST_SCHEMA_VERSION {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "schema_version is incompatible",
        ));
    }
    if request.mint.trim().is_empty() || request.quote_mint.trim().is_empty() {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "mint and quote_mint must be non-empty",
        ));
    }
    if request.mint == request.quote_mint {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "mint and quote_mint must differ",
        ));
    }
    if !request.decision_executable_entry_price_quote.is_finite()
        || request.decision_executable_entry_price_quote <= 0.0
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "decision executable entry price must be positive and finite",
        ));
    }
    Ok(())
}


fn validate_result(
    result: &FastDeterministicEntryAuthorityResultWire,
) -> Result<(), FastDeterministicEntryAuthorityError> {
    if result.schema_name != FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_NAME
        || result.schema_version != FAST_DETERMINISTIC_ENTRY_AUTHORITY_RESULT_SCHEMA_VERSION
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "result schema is incompatible",
        ));
    }
    if result.mint.trim().is_empty()
        || result.quote_mint.trim().is_empty()
        || result.mint == result.quote_mint
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "result market identity is invalid",
        ));
    }
    for value in [
        result.intended_base_quantity,
        result.decision_executable_entry_price_quote,
        result.maximum_acceptable_entry_price_quote,
    ] {
        if !value.is_finite() || value <= 0.0 {
            return Err(FastDeterministicEntryAuthorityError::Invalid(
                "result quantity/prices must be positive and finite",
            ));
        }
    }
    if !result.expected_entry_fixed_cost_quote.is_finite()
        || result.expected_entry_fixed_cost_quote < 0.0
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "result entry fixed cost must be finite and non-negative",
        ));
    }
    validate_sha256(&result.result_fingerprint_sha256)?;
    Ok(())
}


fn build_cost_model(value: &FastEntryExecutionWire) -> ExecutionCostModel {
    ExecutionCostModel {
        version: value.cost_model.version,
        entry: build_leg(&value.cost_model.entry),
        exit: build_leg(&value.cost_model.exit),
    }
}


fn build_leg(value: &FastExecutionLegCostWire) -> ExecutionLegCostInput {
    ExecutionLegCostInput {
        effective_fee_bps: value.effective_fee_bps,
        expected_impact_bps: value.expected_impact_bps,
        expected_slippage_bps: value.expected_slippage_bps,
        expected_latency_bps: value.expected_latency_bps,
        network_fee_quote: value.network_fee_quote,
        priority_fee_quote: value.priority_fee_quote,
        expected_failure_cost_quote: value.expected_failure_cost_quote,
    }
}


fn build_trade(value: &FastEntryExecutionWire) -> ExecutionTradeInput {
    ExecutionTradeInput {
        base_quantity: value.trade.base_quantity,
        executable_entry_price_quote: value.trade.executable_entry_price_quote,
        forecast_exit_price_quote: value.trade.forecast_exit_price_quote,
        exit_capacity_base: value.trade.exit_capacity_base,
        required_edge_bps: value.trade.required_edge_bps,
        risk_margin_bps: value.trade.risk_margin_bps,
    }
}


fn result_fingerprint_sha256(
    result: &FastDeterministicEntryAuthorityResultWire,
) -> Result<String, FastDeterministicEntryAuthorityError> {
    let mut value = serde_json::to_value(result)
        .map_err(|error| FastDeterministicEntryAuthorityError::Json(error.to_string()))?;
    let object = value
        .as_object_mut()
        .ok_or(FastDeterministicEntryAuthorityError::Invalid(
            "result serialization must be an object",
        ))?;
    object.remove("result_fingerprint_sha256");
    let payload = serde_json::to_vec(&value)
        .map_err(|error| FastDeterministicEntryAuthorityError::Json(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(payload)))
}


fn validate_sha256(value: &str) -> Result<(), FastDeterministicEntryAuthorityError> {
    if value.len() != 64
        || value != value.to_ascii_lowercase()
        || value.bytes().any(|byte| !matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return Err(FastDeterministicEntryAuthorityError::Invalid(
            "result_fingerprint_sha256 must be lowercase SHA-256 hex",
        ));
    }
    Ok(())
}
