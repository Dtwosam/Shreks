use rusqlite::{params, OptionalExtension};

use crate::{ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpTradeExecutionEconomicsWrite {
    pub signature: String,
    pub ordinal: u32,
    pub fee_recipient: String,
    pub fee_basis_points: u64,
    pub fee_raw: u64,
    pub creator: String,
    pub creator_fee_basis_points: u64,
    pub creator_fee_raw: u64,
    pub cashback_fee_basis_points: u64,
    pub cashback_raw: u64,
    pub buyback_fee_basis_points: u64,
    pub buyback_fee_raw: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpSwapExecutionEconomicsWrite {
    pub signature: String,
    pub ordinal: u32,
    pub lp_fee_basis_points: u64,
    pub lp_fee_raw: u64,
    pub protocol_fee_basis_points: u64,
    pub protocol_fee_raw: u64,
    pub quote_amount_with_or_without_lp_fee_raw: u64,
    pub coin_creator: Option<String>,
    pub coin_creator_fee_basis_points: Option<u64>,
    pub coin_creator_fee_raw: Option<u64>,
    pub cashback_fee_basis_points: Option<u64>,
    pub cashback_raw: Option<u64>,
    pub buyback_fee_basis_points: Option<u64>,
    pub buyback_fee_raw: Option<u64>,
    pub virtual_quote_reserves_raw: Option<i128>,
    pub can_boost: Option<bool>,
    pub base_supply_raw: Option<u64>,
}

struct RawPumpEconomics {
    signature: String,
    ordinal: i64,
    fee_recipient: String,
    fee_basis_points: String,
    fee_raw: String,
    creator: String,
    creator_fee_basis_points: String,
    creator_fee_raw: String,
    cashback_fee_basis_points: String,
    cashback_raw: String,
    buyback_fee_basis_points: String,
    buyback_fee_raw: String,
}

struct RawPumpSwapEconomics {
    signature: String,
    ordinal: i64,
    lp_fee_basis_points: String,
    lp_fee_raw: String,
    protocol_fee_basis_points: String,
    protocol_fee_raw: String,
    quote_amount_with_or_without_lp_fee_raw: String,
    coin_creator: Option<String>,
    coin_creator_fee_basis_points: Option<String>,
    coin_creator_fee_raw: Option<String>,
    cashback_fee_basis_points: Option<String>,
    cashback_raw: Option<String>,
    buyback_fee_basis_points: Option<String>,
    buyback_fee_raw: Option<String>,
    virtual_quote_reserves_raw: Option<String>,
    can_boost: Option<i64>,
    base_supply_raw: Option<String>,
}

impl ShreksDb {
    pub fn record_pump_trade_execution_economics(
        &self,
        economics: &PumpTradeExecutionEconomicsWrite,
    ) -> Result<bool, StorageError> {
        validate_pump(economics)?;
        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO pump_trade_execution_economics (
                   signature, ordinal, fee_recipient, fee_basis_points, fee_raw,
                   creator, creator_fee_basis_points, creator_fee_raw,
                   cashback_fee_basis_points, cashback_raw,
                   buyback_fee_basis_points, buyback_fee_raw
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)"#,
            params![
                economics.signature,
                i64::from(economics.ordinal),
                economics.fee_recipient,
                economics.fee_basis_points.to_string(),
                economics.fee_raw.to_string(),
                economics.creator,
                economics.creator_fee_basis_points.to_string(),
                economics.creator_fee_raw.to_string(),
                economics.cashback_fee_basis_points.to_string(),
                economics.cashback_raw.to_string(),
                economics.buyback_fee_basis_points.to_string(),
                economics.buyback_fee_raw.to_string(),
            ],
        )?;
        if changed == 1 {
            return Ok(true);
        }

        let existing = self
            .pump_trade_execution_economics(&economics.signature, economics.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "Pump execution economics '{}' ordinal {} disappeared after duplicate insert",
                    economics.signature, economics.ordinal
                ))
            })?;
        if existing == *economics {
            return Ok(false);
        }
        Err(StorageError::InvalidData(format!(
            "conflicting Pump execution economics for signature '{}' ordinal {}",
            economics.signature, economics.ordinal
        )))
    }

    pub fn pump_trade_execution_economics(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<PumpTradeExecutionEconomicsWrite>, StorageError> {
        validate_nonempty(signature, "Pump execution economics signature")?;
        let raw = self
            .connection
            .query_row(
                r#"SELECT signature, ordinal, fee_recipient, fee_basis_points, fee_raw,
                          creator, creator_fee_basis_points, creator_fee_raw,
                          cashback_fee_basis_points, cashback_raw,
                          buyback_fee_basis_points, buyback_fee_raw
                   FROM pump_trade_execution_economics
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![signature, i64::from(ordinal)],
                |row| {
                    Ok(RawPumpEconomics {
                        signature: row.get(0)?,
                        ordinal: row.get(1)?,
                        fee_recipient: row.get(2)?,
                        fee_basis_points: row.get(3)?,
                        fee_raw: row.get(4)?,
                        creator: row.get(5)?,
                        creator_fee_basis_points: row.get(6)?,
                        creator_fee_raw: row.get(7)?,
                        cashback_fee_basis_points: row.get(8)?,
                        cashback_raw: row.get(9)?,
                        buyback_fee_basis_points: row.get(10)?,
                        buyback_fee_raw: row.get(11)?,
                    })
                },
            )
            .optional()?;
        raw.map(decode_pump).transpose()
    }

    pub fn record_pump_swap_execution_economics(
        &self,
        economics: &PumpSwapExecutionEconomicsWrite,
    ) -> Result<bool, StorageError> {
        validate_pump_swap(economics)?;
        let changed = self.connection.execute(
            r#"INSERT OR IGNORE INTO pump_swap_execution_economics (
                   signature, ordinal,
                   lp_fee_basis_points, lp_fee_raw,
                   protocol_fee_basis_points, protocol_fee_raw,
                   quote_amount_with_or_without_lp_fee_raw,
                   coin_creator, coin_creator_fee_basis_points, coin_creator_fee_raw,
                   cashback_fee_basis_points, cashback_raw,
                   buyback_fee_basis_points, buyback_fee_raw,
                   virtual_quote_reserves_raw, can_boost, base_supply_raw
               ) VALUES (
                   ?1, ?2, ?3, ?4, ?5, ?6, ?7,
                   ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17
               )"#,
            params![
                economics.signature,
                i64::from(economics.ordinal),
                economics.lp_fee_basis_points.to_string(),
                economics.lp_fee_raw.to_string(),
                economics.protocol_fee_basis_points.to_string(),
                economics.protocol_fee_raw.to_string(),
                economics.quote_amount_with_or_without_lp_fee_raw.to_string(),
                economics.coin_creator,
                economics.coin_creator_fee_basis_points.map(|value| value.to_string()),
                economics.coin_creator_fee_raw.map(|value| value.to_string()),
                economics.cashback_fee_basis_points.map(|value| value.to_string()),
                economics.cashback_raw.map(|value| value.to_string()),
                economics.buyback_fee_basis_points.map(|value| value.to_string()),
                economics.buyback_fee_raw.map(|value| value.to_string()),
                economics.virtual_quote_reserves_raw.map(|value| value.to_string()),
                economics.can_boost.map(i64::from),
                economics.base_supply_raw.map(|value| value.to_string()),
            ],
        )?;
        if changed == 1 {
            return Ok(true);
        }

        let existing = self
            .pump_swap_execution_economics(&economics.signature, economics.ordinal)?
            .ok_or_else(|| {
                StorageError::InvalidData(format!(
                    "PumpSwap execution economics '{}' ordinal {} disappeared after duplicate insert",
                    economics.signature, economics.ordinal
                ))
            })?;
        if existing == *economics {
            return Ok(false);
        }
        Err(StorageError::InvalidData(format!(
            "conflicting PumpSwap execution economics for signature '{}' ordinal {}",
            economics.signature, economics.ordinal
        )))
    }

    pub fn pump_swap_execution_economics(
        &self,
        signature: &str,
        ordinal: u32,
    ) -> Result<Option<PumpSwapExecutionEconomicsWrite>, StorageError> {
        validate_nonempty(signature, "PumpSwap execution economics signature")?;
        let raw = self
            .connection
            .query_row(
                r#"SELECT signature, ordinal,
                          lp_fee_basis_points, lp_fee_raw,
                          protocol_fee_basis_points, protocol_fee_raw,
                          quote_amount_with_or_without_lp_fee_raw,
                          coin_creator, coin_creator_fee_basis_points, coin_creator_fee_raw,
                          cashback_fee_basis_points, cashback_raw,
                          buyback_fee_basis_points, buyback_fee_raw,
                          virtual_quote_reserves_raw, can_boost, base_supply_raw
                   FROM pump_swap_execution_economics
                   WHERE signature = ?1 AND ordinal = ?2"#,
                params![signature, i64::from(ordinal)],
                |row| {
                    Ok(RawPumpSwapEconomics {
                        signature: row.get(0)?,
                        ordinal: row.get(1)?,
                        lp_fee_basis_points: row.get(2)?,
                        lp_fee_raw: row.get(3)?,
                        protocol_fee_basis_points: row.get(4)?,
                        protocol_fee_raw: row.get(5)?,
                        quote_amount_with_or_without_lp_fee_raw: row.get(6)?,
                        coin_creator: row.get(7)?,
                        coin_creator_fee_basis_points: row.get(8)?,
                        coin_creator_fee_raw: row.get(9)?,
                        cashback_fee_basis_points: row.get(10)?,
                        cashback_raw: row.get(11)?,
                        buyback_fee_basis_points: row.get(12)?,
                        buyback_fee_raw: row.get(13)?,
                        virtual_quote_reserves_raw: row.get(14)?,
                        can_boost: row.get(15)?,
                        base_supply_raw: row.get(16)?,
                    })
                },
            )
            .optional()?;
        raw.map(decode_pump_swap).transpose()
    }
}

fn validate_pump(economics: &PumpTradeExecutionEconomicsWrite) -> Result<(), StorageError> {
    validate_nonempty(&economics.signature, "Pump execution economics signature")?;
    validate_nonempty(&economics.fee_recipient, "Pump fee recipient")?;
    validate_nonempty(&economics.creator, "Pump creator")?;
    Ok(())
}

fn validate_pump_swap(economics: &PumpSwapExecutionEconomicsWrite) -> Result<(), StorageError> {
    validate_nonempty(
        &economics.signature,
        "PumpSwap execution economics signature",
    )?;
    if economics.ordinal < 0x8000_0000 {
        return Err(StorageError::InvalidData(format!(
            "PumpSwap execution economics ordinal {} is outside the reserved namespace",
            economics.ordinal
        )));
    }

    let current_present = [
        economics.coin_creator.is_some(),
        economics.coin_creator_fee_basis_points.is_some(),
        economics.coin_creator_fee_raw.is_some(),
        economics.cashback_fee_basis_points.is_some(),
        economics.cashback_raw.is_some(),
        economics.buyback_fee_basis_points.is_some(),
        economics.buyback_fee_raw.is_some(),
        economics.virtual_quote_reserves_raw.is_some(),
        economics.can_boost.is_some(),
        economics.base_supply_raw.is_some(),
    ];
    let present_count = current_present.iter().filter(|present| **present).count();
    if present_count != 0 && present_count != current_present.len() {
        return Err(StorageError::InvalidData(
            "PumpSwap current execution economics suffix must be all present or all absent"
                .to_owned(),
        ));
    }
    if let Some(creator) = economics.coin_creator.as_deref() {
        validate_nonempty(creator, "PumpSwap coin creator")?;
    }
    Ok(())
}

fn decode_pump(raw: RawPumpEconomics) -> Result<PumpTradeExecutionEconomicsWrite, StorageError> {
    Ok(PumpTradeExecutionEconomicsWrite {
        signature: raw.signature,
        ordinal: parse_u32_i64(raw.ordinal, "Pump execution economics ordinal")?,
        fee_recipient: raw.fee_recipient,
        fee_basis_points: parse_u64(&raw.fee_basis_points, "Pump fee basis points")?,
        fee_raw: parse_u64(&raw.fee_raw, "Pump fee raw")?,
        creator: raw.creator,
        creator_fee_basis_points: parse_u64(
            &raw.creator_fee_basis_points,
            "Pump creator fee basis points",
        )?,
        creator_fee_raw: parse_u64(&raw.creator_fee_raw, "Pump creator fee raw")?,
        cashback_fee_basis_points: parse_u64(
            &raw.cashback_fee_basis_points,
            "Pump cashback fee basis points",
        )?,
        cashback_raw: parse_u64(&raw.cashback_raw, "Pump cashback raw")?,
        buyback_fee_basis_points: parse_u64(
            &raw.buyback_fee_basis_points,
            "Pump buyback fee basis points",
        )?,
        buyback_fee_raw: parse_u64(&raw.buyback_fee_raw, "Pump buyback fee raw")?,
    })
}

fn decode_pump_swap(
    raw: RawPumpSwapEconomics,
) -> Result<PumpSwapExecutionEconomicsWrite, StorageError> {
    let economics = PumpSwapExecutionEconomicsWrite {
        signature: raw.signature,
        ordinal: parse_u32_i64(raw.ordinal, "PumpSwap execution economics ordinal")?,
        lp_fee_basis_points: parse_u64(&raw.lp_fee_basis_points, "PumpSwap LP fee basis points")?,
        lp_fee_raw: parse_u64(&raw.lp_fee_raw, "PumpSwap LP fee raw")?,
        protocol_fee_basis_points: parse_u64(
            &raw.protocol_fee_basis_points,
            "PumpSwap protocol fee basis points",
        )?,
        protocol_fee_raw: parse_u64(&raw.protocol_fee_raw, "PumpSwap protocol fee raw")?,
        quote_amount_with_or_without_lp_fee_raw: parse_u64(
            &raw.quote_amount_with_or_without_lp_fee_raw,
            "PumpSwap fee-adjusted quote amount",
        )?,
        coin_creator: raw.coin_creator,
        coin_creator_fee_basis_points: parse_optional_u64(
            raw.coin_creator_fee_basis_points,
            "PumpSwap coin creator fee basis points",
        )?,
        coin_creator_fee_raw: parse_optional_u64(
            raw.coin_creator_fee_raw,
            "PumpSwap coin creator fee raw",
        )?,
        cashback_fee_basis_points: parse_optional_u64(
            raw.cashback_fee_basis_points,
            "PumpSwap cashback fee basis points",
        )?,
        cashback_raw: parse_optional_u64(raw.cashback_raw, "PumpSwap cashback raw")?,
        buyback_fee_basis_points: parse_optional_u64(
            raw.buyback_fee_basis_points,
            "PumpSwap buyback fee basis points",
        )?,
        buyback_fee_raw: parse_optional_u64(raw.buyback_fee_raw, "PumpSwap buyback fee raw")?,
        virtual_quote_reserves_raw: parse_optional_i128(
            raw.virtual_quote_reserves_raw,
            "PumpSwap virtual quote reserves raw",
        )?,
        can_boost: raw
            .can_boost
            .map(|value| match value {
                0 => Ok(false),
                1 => Ok(true),
                other => Err(StorageError::InvalidData(format!(
                    "PumpSwap can_boost contains invalid integer {other}"
                ))),
            })
            .transpose()?,
        base_supply_raw: parse_optional_u64(raw.base_supply_raw, "PumpSwap base supply raw")?,
    };
    validate_pump_swap(&economics)?;
    Ok(economics)
}

fn validate_nonempty(value: &str, field: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!("{field} must be non-empty")));
    }
    Ok(())
}

fn parse_u64(value: &str, field: &str) -> Result<u64, StorageError> {
    value.parse::<u64>().map_err(|error| {
        StorageError::InvalidData(format!("invalid {field} '{value}': {error}"))
    })
}

fn parse_optional_u64(value: Option<String>, field: &str) -> Result<Option<u64>, StorageError> {
    value.map(|value| parse_u64(&value, field)).transpose()
}

fn parse_optional_i128(value: Option<String>, field: &str) -> Result<Option<i128>, StorageError> {
    value
        .map(|value| {
            value.parse::<i128>().map_err(|error| {
                StorageError::InvalidData(format!("invalid {field} '{value}': {error}"))
            })
        })
        .transpose()
}

fn parse_u32_i64(value: i64, field: &str) -> Result<u32, StorageError> {
    u32::try_from(value)
        .map_err(|_| StorageError::InvalidData(format!("{field} {value} exceeds u32")))
}
