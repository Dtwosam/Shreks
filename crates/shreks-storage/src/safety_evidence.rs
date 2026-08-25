use std::fmt::Write as _;

use rusqlite::{params, OptionalExtension};
use shreks_core::{QuotePurpose, QuoteRequest, QuoteSnapshot, TokenHolderDistribution};

use crate::{ShreksDb, StorageError};

#[derive(Debug, PartialEq)]
struct StoredHolderEvidence {
    reported_total_accounts: String,
    accounts_scanned: i64,
    unique_owners: i64,
    pages_scanned: i64,
    complete: i64,
    total_balance_raw: String,
    largest_owner: Option<String>,
    largest_owner_balance_raw: Option<String>,
    top_holder_concentration_pct: Option<f64>,
}

#[derive(Debug, PartialEq, Eq)]
struct StoredQuoteEvidence {
    output_amount: String,
    minimum_output_amount: String,
    route_available: i64,
    price_impact_pct: Option<String>,
    route_labels_json: String,
}

impl ShreksDb {
    /// Persist one normalized owner-distribution scan for an exact candidate.
    /// Exact semantic replays are no-ops; contradictory replays fail closed.
    pub fn insert_holder_distribution(
        &self,
        candidate_id: i64,
        distribution: &TokenHolderDistribution,
    ) -> Result<(), StorageError> {
        let candidate_mint = safety_candidate_mint(self, candidate_id)?;
        validate_holder_distribution(distribution, &candidate_mint)?;

        let accounts_scanned =
            safety_usize_as_i64(distribution.accounts_scanned, "holder accounts_scanned")?;
        let unique_owners =
            safety_usize_as_i64(distribution.unique_owners, "holder unique_owners")?;
        let pages_scanned =
            safety_usize_as_i64(distribution.pages_scanned, "holder pages_scanned")?;
        let complete = i64::from(distribution.complete);
        let expected = StoredHolderEvidence {
            reported_total_accounts: distribution.reported_total_accounts.to_string(),
            accounts_scanned,
            unique_owners,
            pages_scanned,
            complete,
            total_balance_raw: distribution.total_balance_raw.to_string(),
            largest_owner: distribution.largest_owner.clone(),
            largest_owner_balance_raw: distribution
                .largest_owner_balance_raw
                .map(|value| value.to_string()),
            top_holder_concentration_pct: distribution.top_holder_concentration_pct,
        };

        let existing = self
            .connection
            .query_row(
                r#"SELECT reported_total_accounts, accounts_scanned, unique_owners, pages_scanned,
                          complete, total_balance_raw, largest_owner, largest_owner_balance_raw,
                          top_holder_concentration_pct
                   FROM token_holder_distributions
                   WHERE candidate_id = ?1
                     AND provider = ?2
                     AND mint = ?3
                     AND last_indexed_slot = ?4
                     AND observed_at_unix_ms = ?5"#,
                params![
                    candidate_id,
                    distribution.provider.as_str(),
                    distribution.mint.as_str(),
                    distribution.last_indexed_slot.to_string(),
                    distribution.observed_at_unix_ms,
                ],
                |row| {
                    Ok(StoredHolderEvidence {
                        reported_total_accounts: row.get(0)?,
                        accounts_scanned: row.get(1)?,
                        unique_owners: row.get(2)?,
                        pages_scanned: row.get(3)?,
                        complete: row.get(4)?,
                        total_balance_raw: row.get(5)?,
                        largest_owner: row.get(6)?,
                        largest_owner_balance_raw: row.get(7)?,
                        top_holder_concentration_pct: row.get(8)?,
                    })
                },
            )
            .optional()?;

        if let Some(existing) = existing {
            if existing == expected {
                return Ok(());
            }
            return Err(StorageError::InvalidData(format!(
                "holder distribution replay contradicts stored evidence for candidate {candidate_id} at {}",
                distribution.observed_at_unix_ms
            )));
        }

        self.connection.execute(
            r#"INSERT INTO token_holder_distributions (
                   candidate_id, provider, mint, last_indexed_slot, observed_at_unix_ms,
                   reported_total_accounts, accounts_scanned, unique_owners, pages_scanned,
                   complete, total_balance_raw, largest_owner, largest_owner_balance_raw,
                   top_holder_concentration_pct
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)"#,
            params![
                candidate_id,
                distribution.provider.as_str(),
                distribution.mint.as_str(),
                distribution.last_indexed_slot.to_string(),
                distribution.observed_at_unix_ms,
                expected.reported_total_accounts,
                expected.accounts_scanned,
                expected.unique_owners,
                expected.pages_scanned,
                expected.complete,
                expected.total_balance_raw,
                expected.largest_owner,
                expected.largest_owner_balance_raw,
                expected.top_holder_concentration_pct,
            ],
        )?;
        Ok(())
    }

    /// Persist one successful normalized read-only quote with the exact request
    /// that produced it. The request is required because QuoteSnapshot does not
    /// contain the taker identity needed for deterministic replay attribution.
    pub fn insert_exit_quote_snapshot(
        &self,
        candidate_id: i64,
        probe_policy_version: &str,
        request: &QuoteRequest,
        snapshot: &QuoteSnapshot,
    ) -> Result<(), StorageError> {
        let candidate_mint = safety_candidate_mint(self, candidate_id)?;
        validate_exit_quote(
            probe_policy_version,
            request,
            snapshot,
            &candidate_mint,
        )?;

        let route_labels_json = encode_route_labels(&snapshot.route_labels)?;
        let expected = StoredQuoteEvidence {
            output_amount: snapshot.output_amount.to_string(),
            minimum_output_amount: snapshot.minimum_output_amount.to_string(),
            route_available: i64::from(snapshot.route_available),
            price_impact_pct: snapshot.price_impact_pct.clone(),
            route_labels_json,
        };

        let existing = self
            .connection
            .query_row(
                r#"SELECT output_amount, minimum_output_amount, route_available,
                          price_impact_pct, route_labels_json
                   FROM exit_quote_snapshots
                   WHERE candidate_id = ?1
                     AND provider = ?2
                     AND probe_policy_version = ?3
                     AND input_mint = ?4
                     AND output_mint = ?5
                     AND taker = ?6
                     AND input_amount = ?7
                     AND slippage_bps = ?8
                     AND quoted_at_unix_ms = ?9"#,
                params![
                    candidate_id,
                    snapshot.provider.as_str(),
                    probe_policy_version,
                    request.input_mint.as_str(),
                    request.output_mint.as_str(),
                    request.taker.as_str(),
                    request.amount.to_string(),
                    i64::from(request.slippage_bps),
                    snapshot.quoted_at_unix_ms,
                ],
                |row| {
                    Ok(StoredQuoteEvidence {
                        output_amount: row.get(0)?,
                        minimum_output_amount: row.get(1)?,
                        route_available: row.get(2)?,
                        price_impact_pct: row.get(3)?,
                        route_labels_json: row.get(4)?,
                    })
                },
            )
            .optional()?;

        if let Some(existing) = existing {
            if existing == expected {
                return Ok(());
            }
            return Err(StorageError::InvalidData(format!(
                "exit quote replay contradicts stored evidence for candidate {candidate_id} at {}",
                snapshot.quoted_at_unix_ms
            )));
        }

        self.connection.execute(
            r#"INSERT INTO exit_quote_snapshots (
                   candidate_id, provider, probe_policy_version, input_mint, output_mint, taker,
                   input_amount, output_amount, minimum_output_amount, slippage_bps,
                   route_available, price_impact_pct, route_labels_json, quoted_at_unix_ms
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)"#,
            params![
                candidate_id,
                snapshot.provider.as_str(),
                probe_policy_version,
                request.input_mint.as_str(),
                request.output_mint.as_str(),
                request.taker.as_str(),
                request.amount.to_string(),
                expected.output_amount,
                expected.minimum_output_amount,
                i64::from(request.slippage_bps),
                expected.route_available,
                expected.price_impact_pct,
                expected.route_labels_json,
                snapshot.quoted_at_unix_ms,
            ],
        )?;
        Ok(())
    }

    /// Persist one purpose-attributed read-only quote for paper-proof replay.
    /// Purpose is part of semantic identity; exact replays are no-ops and
    /// contradictory replays fail closed. Direction policy is enforced by the
    /// E15 collector rather than this storage boundary.
    pub fn insert_paper_quote_snapshot(
        &self,
        candidate_id: i64,
        purpose: QuotePurpose,
        probe_policy_version: &str,
        request: &QuoteRequest,
        snapshot: &QuoteSnapshot,
    ) -> Result<(), StorageError> {
        let candidate_mint = safety_candidate_mint(self, candidate_id)?;
        validate_paper_quote(
            probe_policy_version,
            request,
            snapshot,
            &candidate_mint,
        )?;

        let route_labels_json = encode_route_labels(&snapshot.route_labels)?;
        let expected = StoredQuoteEvidence {
            output_amount: snapshot.output_amount.to_string(),
            minimum_output_amount: snapshot.minimum_output_amount.to_string(),
            route_available: i64::from(snapshot.route_available),
            price_impact_pct: snapshot.price_impact_pct.clone(),
            route_labels_json,
        };

        let existing = self
            .connection
            .query_row(
                r#"SELECT output_amount, minimum_output_amount, route_available,
                          price_impact_pct, route_labels_json
                   FROM paper_quote_snapshots
                   WHERE candidate_id = ?1
                     AND purpose = ?2
                     AND provider = ?3
                     AND probe_policy_version = ?4
                     AND input_mint = ?5
                     AND output_mint = ?6
                     AND taker = ?7
                     AND input_amount = ?8
                     AND slippage_bps = ?9
                     AND quoted_at_unix_ms = ?10"#,
                params![
                    candidate_id,
                    purpose.as_str(),
                    snapshot.provider.as_str(),
                    probe_policy_version,
                    request.input_mint.as_str(),
                    request.output_mint.as_str(),
                    request.taker.as_str(),
                    request.amount.to_string(),
                    i64::from(request.slippage_bps),
                    snapshot.quoted_at_unix_ms,
                ],
                |row| {
                    Ok(StoredQuoteEvidence {
                        output_amount: row.get(0)?,
                        minimum_output_amount: row.get(1)?,
                        route_available: row.get(2)?,
                        price_impact_pct: row.get(3)?,
                        route_labels_json: row.get(4)?,
                    })
                },
            )
            .optional()?;

        if let Some(existing) = existing {
            if existing == expected {
                return Ok(());
            }
            return Err(StorageError::InvalidData(format!(
                "paper quote replay contradicts stored evidence for candidate {candidate_id}, purpose '{}', at {}",
                purpose.as_str(),
                snapshot.quoted_at_unix_ms
            )));
        }

        self.connection.execute(
            r#"INSERT INTO paper_quote_snapshots (
                   candidate_id, purpose, provider, probe_policy_version, input_mint, output_mint,
                   taker, input_amount, output_amount, minimum_output_amount, slippage_bps,
                   route_available, price_impact_pct, route_labels_json, quoted_at_unix_ms
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)"#,
            params![
                candidate_id,
                purpose.as_str(),
                snapshot.provider.as_str(),
                probe_policy_version,
                request.input_mint.as_str(),
                request.output_mint.as_str(),
                request.taker.as_str(),
                request.amount.to_string(),
                expected.output_amount,
                expected.minimum_output_amount,
                i64::from(request.slippage_bps),
                expected.route_available,
                expected.price_impact_pct,
                expected.route_labels_json,
                snapshot.quoted_at_unix_ms,
            ],
        )?;
        Ok(())
    }
}

fn safety_candidate_mint(db: &ShreksDb, candidate_id: i64) -> Result<String, StorageError> {
    db.connection
        .query_row(
            "SELECT mint FROM token_candidates WHERE id = ?1",
            [candidate_id],
            |row| row.get::<_, String>(0),
        )
        .optional()?
        .ok_or_else(|| {
            StorageError::InvalidData(format!(
                "safety evidence candidate id {candidate_id} is not known"
            ))
        })
}

fn validate_holder_distribution(
    distribution: &TokenHolderDistribution,
    candidate_mint: &str,
) -> Result<(), StorageError> {
    safety_non_blank("holder distribution mint", &distribution.mint)?;
    if distribution.mint != candidate_mint {
        return Err(StorageError::InvalidData(format!(
            "holder distribution mint '{}' does not match candidate mint '{candidate_mint}'",
            distribution.mint
        )));
    }
    if distribution.observed_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "holder distribution timestamp must be nonnegative".to_owned(),
        ));
    }
    if distribution.pages_scanned == 0 {
        return Err(StorageError::InvalidData(
            "holder distribution pages_scanned must be positive".to_owned(),
        ));
    }
    if distribution.unique_owners > distribution.accounts_scanned {
        return Err(StorageError::InvalidData(
            "holder distribution unique_owners cannot exceed accounts_scanned".to_owned(),
        ));
    }
    if distribution.largest_owner.is_some() != distribution.largest_owner_balance_raw.is_some() {
        return Err(StorageError::InvalidData(
            "holder distribution largest owner and raw balance must be paired".to_owned(),
        ));
    }
    if let Some(owner) = distribution.largest_owner.as_deref() {
        safety_non_blank("holder distribution largest owner", owner)?;
    }
    if distribution
        .largest_owner_balance_raw
        .is_some_and(|value| value > distribution.total_balance_raw)
    {
        return Err(StorageError::InvalidData(
            "holder distribution largest owner balance exceeds total balance".to_owned(),
        ));
    }
    if !distribution.complete && distribution.top_holder_concentration_pct.is_some() {
        return Err(StorageError::InvalidData(
            "incomplete holder distribution must not expose concentration".to_owned(),
        ));
    }
    if let Some(value) = distribution.top_holder_concentration_pct {
        if !value.is_finite() || !(0.0..=100.0).contains(&value) {
            return Err(StorageError::InvalidData(
                "holder distribution concentration must be finite within 0..=100".to_owned(),
            ));
        }
    }
    if distribution.complete
        && distribution.total_balance_raw > 0
        && distribution.top_holder_concentration_pct.is_none()
    {
        return Err(StorageError::InvalidData(
            "complete positive-balance holder distribution requires concentration".to_owned(),
        ));
    }
    if distribution.total_balance_raw == 0 && distribution.top_holder_concentration_pct.is_some() {
        return Err(StorageError::InvalidData(
            "zero-balance holder distribution must not expose concentration".to_owned(),
        ));
    }
    if distribution.total_balance_raw > 0 && distribution.largest_owner.is_none() {
        return Err(StorageError::InvalidData(
            "positive-balance holder distribution requires largest owner provenance".to_owned(),
        ));
    }
    Ok(())
}

fn validate_exit_quote(
    probe_policy_version: &str,
    request: &QuoteRequest,
    snapshot: &QuoteSnapshot,
    candidate_mint: &str,
) -> Result<(), StorageError> {
    safety_non_blank("exit quote probe policy version", probe_policy_version)?;
    safety_non_blank("exit quote input mint", &request.input_mint)?;
    safety_non_blank("exit quote output mint", &request.output_mint)?;
    safety_non_blank("exit quote taker", &request.taker)?;
    if request.input_mint == request.output_mint {
        return Err(StorageError::InvalidData(
            "exit quote input and output mints must differ".to_owned(),
        ));
    }
    if request.amount == 0 {
        return Err(StorageError::InvalidData(
            "exit quote input amount must be positive".to_owned(),
        ));
    }
    if request.slippage_bps > 10_000 {
        return Err(StorageError::InvalidData(
            "exit quote slippage must be within 0..=10000 bps".to_owned(),
        ));
    }
    if request.input_mint != candidate_mint {
        return Err(StorageError::InvalidData(format!(
            "exit quote input mint '{}' does not match candidate mint '{candidate_mint}'",
            request.input_mint
        )));
    }
    if snapshot.input_mint != request.input_mint
        || snapshot.output_mint != request.output_mint
        || snapshot.input_amount != request.amount
        || snapshot.slippage_bps != request.slippage_bps
    {
        return Err(StorageError::InvalidData(
            "exit quote snapshot does not match originating request".to_owned(),
        ));
    }
    if snapshot.quoted_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "exit quote timestamp must be nonnegative".to_owned(),
        ));
    }
    if snapshot.minimum_output_amount > snapshot.output_amount {
        return Err(StorageError::InvalidData(
            "exit quote minimum output cannot exceed output amount".to_owned(),
        ));
    }
    if snapshot.route_available && snapshot.output_amount == 0 {
        return Err(StorageError::InvalidData(
            "available exit quote route requires positive output amount".to_owned(),
        ));
    }
    if snapshot.route_available && snapshot.route_labels.is_empty() {
        return Err(StorageError::InvalidData(
            "available exit quote route requires route labels".to_owned(),
        ));
    }
    if let Some(value) = snapshot.price_impact_pct.as_deref() {
        let parsed = value.parse::<f64>().map_err(|error| {
            StorageError::InvalidData(format!(
                "exit quote price impact is not numeric: {error}"
            ))
        })?;
        if !parsed.is_finite() || parsed < 0.0 {
            return Err(StorageError::InvalidData(
                "exit quote price impact must be finite and nonnegative".to_owned(),
            ));
        }
    }
    for label in &snapshot.route_labels {
        safety_non_blank("exit quote route label", label)?;
    }
    Ok(())
}

fn validate_paper_quote(
    probe_policy_version: &str,
    request: &QuoteRequest,
    snapshot: &QuoteSnapshot,
    candidate_mint: &str,
) -> Result<(), StorageError> {
    safety_non_blank("paper quote probe policy version", probe_policy_version)?;
    safety_non_blank("paper quote input mint", &request.input_mint)?;
    safety_non_blank("paper quote output mint", &request.output_mint)?;
    safety_non_blank("paper quote taker", &request.taker)?;
    if request.input_mint == request.output_mint {
        return Err(StorageError::InvalidData(
            "paper quote input and output mints must differ".to_owned(),
        ));
    }
    if request.amount == 0 {
        return Err(StorageError::InvalidData(
            "paper quote input amount must be positive".to_owned(),
        ));
    }
    if request.slippage_bps > 10_000 {
        return Err(StorageError::InvalidData(
            "paper quote slippage must be within 0..=10000 bps".to_owned(),
        ));
    }
    if request.input_mint != candidate_mint && request.output_mint != candidate_mint {
        return Err(StorageError::InvalidData(format!(
            "paper quote request is not attributed to candidate mint '{candidate_mint}'"
        )));
    }
    if snapshot.input_mint != request.input_mint
        || snapshot.output_mint != request.output_mint
        || snapshot.input_amount != request.amount
        || snapshot.slippage_bps != request.slippage_bps
    {
        return Err(StorageError::InvalidData(
            "paper quote snapshot does not match originating request".to_owned(),
        ));
    }
    if snapshot.quoted_at_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "paper quote timestamp must be nonnegative".to_owned(),
        ));
    }
    if snapshot.minimum_output_amount > snapshot.output_amount {
        return Err(StorageError::InvalidData(
            "paper quote minimum output cannot exceed output amount".to_owned(),
        ));
    }
    if snapshot.route_available && snapshot.output_amount == 0 {
        return Err(StorageError::InvalidData(
            "available paper quote route requires positive output amount".to_owned(),
        ));
    }
    if snapshot.route_available && snapshot.route_labels.is_empty() {
        return Err(StorageError::InvalidData(
            "available paper quote route requires route labels".to_owned(),
        ));
    }
    if let Some(value) = snapshot.price_impact_pct.as_deref() {
        let parsed = value.parse::<f64>().map_err(|error| {
            StorageError::InvalidData(format!(
                "paper quote price impact is not numeric: {error}"
            ))
        })?;
        if !parsed.is_finite() || parsed < 0.0 {
            return Err(StorageError::InvalidData(
                "paper quote price impact must be finite and nonnegative".to_owned(),
            ));
        }
    }
    for label in &snapshot.route_labels {
        safety_non_blank("paper quote route label", label)?;
    }
    Ok(())
}

fn safety_usize_as_i64(value: usize, field: &str) -> Result<i64, StorageError> {
    i64::try_from(value).map_err(|_| {
        StorageError::InvalidData(format!("{field} exceeds SQLite signed integer range"))
    })
}

fn safety_non_blank(field: &str, value: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!("{field} must not be blank")));
    }
    Ok(())
}

fn encode_route_labels(labels: &[String]) -> Result<String, StorageError> {
    let mut output = String::from("[");
    for (index, label) in labels.iter().enumerate() {
        if index != 0 {
            output.push(',');
        }
        output.push('"');
        for character in label.chars() {
            match character {
                '"' => output.push_str("\\\""),
                '\\' => output.push_str("\\\\"),
                '\n' => output.push_str("\\n"),
                '\r' => output.push_str("\\r"),
                '\t' => output.push_str("\\t"),
                '\u{08}' => output.push_str("\\b"),
                '\u{0c}' => output.push_str("\\f"),
                control if control <= '\u{1f}' => {
                    write!(&mut output, "\\u{:04x}", control as u32).map_err(|_| {
                        StorageError::InvalidData(
                            "failed to encode exit quote route labels".to_owned(),
                        )
                    })?;
                }
                other => output.push(other),
            }
        }
        output.push('"');
    }
    output.push(']');
    Ok(output)
}
