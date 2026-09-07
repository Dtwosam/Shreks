use std::collections::BTreeMap;

use rusqlite::params;
use shreks_core::ProviderId;

use crate::{ShreksDb, StorageError};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedPumpSwapSamplingTarget {
    pub provider: ProviderId,
    pub mint: String,
    pub quote_mint: String,
    pub pool_address: String,
    pub detected_at_unix_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MigrationSamplingCandidate {
    pub candidate_id: i64,
    pub mint: String,
    pub discovered_at_unix_ms: i64,
}

impl ShreksDb {
    /// Return verified Pump.fun -> PumpSwap migrations whose lifecycle detection
    /// falls inside the requested inclusive interval.
    ///
    /// One mint may have duplicate identical lifecycle evidence, but contradictory
    /// quote/pool mappings fail closed instead of becoming an arbitrary sampler
    /// target.
    pub fn verified_pump_swap_sampling_targets(
        &self,
        from_detected_at_unix_ms: i64,
        through_detected_at_unix_ms: i64,
    ) -> Result<Vec<VerifiedPumpSwapSamplingTarget>, StorageError> {
        validate_window(from_detected_at_unix_ms, through_detected_at_unix_ms)?;

        let mut statement = self.connection.prepare(
            r#"SELECT
                   e.provider,
                   e.mint,
                   e.quote_mint,
                   e.pool_address,
                   e.detected_at_unix_ms
               FROM token_lifecycle_events AS e
               JOIN pump_migration_signals AS s
                 ON s.signature = e.signature
               WHERE s.status = 'verified'
                 AND e.event_type = 'pump_graduation'
                 AND e.from_venue = 'pump_fun_bonding_curve'
                 AND e.to_venue = 'pump_swap'
                 AND e.detected_at_unix_ms BETWEEN ?1 AND ?2
               ORDER BY
                   e.mint ASC,
                   e.detected_at_unix_ms ASC,
                   e.signature ASC,
                   e.pool_address ASC"#,
        )?;

        let raw = statement
            .query_map(
                params![from_detected_at_unix_ms, through_detected_at_unix_ms],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, i64>(4)?,
                    ))
                },
            )?
            .collect::<Result<Vec<_>, _>>()?;

        let mut by_mint = BTreeMap::<String, VerifiedPumpSwapSamplingTarget>::new();
        for (provider, mint, quote_mint, pool_address, detected_at_unix_ms) in raw {
            validate_nonempty(&mint, "migration sampling mint")?;
            validate_nonempty(&quote_mint, "migration sampling quote mint")?;
            validate_nonempty(&pool_address, "migration sampling pool address")?;
            if detected_at_unix_ms < 0 {
                return Err(StorageError::InvalidData(
                    "migration sampling detection timestamp must be nonnegative".to_owned(),
                ));
            }

            let next = VerifiedPumpSwapSamplingTarget {
                provider: parse_provider(&provider)?,
                mint: mint.clone(),
                quote_mint,
                pool_address,
                detected_at_unix_ms,
            };

            match by_mint.get_mut(&mint) {
                None => {
                    by_mint.insert(mint, next);
                }
                Some(existing) => {
                    if existing.quote_mint != next.quote_mint
                        || existing.pool_address != next.pool_address
                    {
                        return Err(StorageError::InvalidData(format!(
                            "verified PumpSwap migration mint '{}' has contradictory quote/pool targets",
                            existing.mint
                        )));
                    }
                    if (
                        next.detected_at_unix_ms,
                        next.provider.as_str(),
                    ) < (
                        existing.detected_at_unix_ms,
                        existing.provider.as_str(),
                    ) {
                        *existing = next;
                    }
                }
            }
        }

        Ok(by_mint.into_values().collect())
    }

    /// Resolve one existing candidate identity for migration-driven market
    /// sampling without inventing a duplicate mint identity.
    ///
    /// Selection is deterministic and outcome-neutral:
    /// - one candidate: reuse it;
    /// - multiple candidates with exactly one snapshot-owning identity: reuse it;
    /// - multiple candidates with zero or multiple snapshot owners: fail closed.
    pub fn migration_sampling_candidate_for_mint(
        &self,
        mint: &str,
    ) -> Result<Option<MigrationSamplingCandidate>, StorageError> {
        validate_nonempty(mint, "migration sampling candidate mint")?;

        let mut statement = self.connection.prepare(
            r#"SELECT
                   c.id,
                   c.mint,
                   c.discovered_at_unix_ms,
                   COUNT(s.id) AS snapshot_count,
                   c.discovery_source
               FROM token_candidates AS c
               LEFT JOIN market_snapshots AS s
                 ON s.candidate_id = c.id
               WHERE c.mint = ?1
               GROUP BY
                   c.id,
                   c.mint,
                   c.discovered_at_unix_ms,
                   c.discovery_source
               ORDER BY c.id ASC"#,
        )?;

        let rows = statement
            .query_map([mint], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, String>(4)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        if rows.is_empty() {
            return Ok(None);
        }

        let decode = |row: &(i64, String, i64, i64, String)| -> Result<MigrationSamplingCandidate, StorageError> {
            if row.0 <= 0 {
                return Err(StorageError::InvalidData(
                    "migration sampling candidate id must be positive".to_owned(),
                ));
            }
            validate_nonempty(&row.1, "migration sampling candidate mint")?;
            if row.2 < 0 {
                return Err(StorageError::InvalidData(
                    "migration sampling candidate discovery timestamp must be nonnegative".to_owned(),
                ));
            }
            if row.3 < 0 {
                return Err(StorageError::InvalidData(
                    "migration sampling snapshot count must be nonnegative".to_owned(),
                ));
            }
            parse_provider(&row.4)?;
            Ok(MigrationSamplingCandidate {
                candidate_id: row.0,
                mint: row.1.clone(),
                discovered_at_unix_ms: row.2,
            })
        };

        if rows.len() == 1 {
            return decode(&rows[0]).map(Some);
        }

        let owners = rows
            .iter()
            .filter(|row| row.3 > 0)
            .collect::<Vec<_>>();

        if owners.len() == 1 {
            return decode(owners[0]).map(Some);
        }

        if owners.is_empty() {
            let dexscreener = rows
                .iter()
                .filter(|row| row.4 == ProviderId::DexScreener.as_str())
                .collect::<Vec<_>>();
            if dexscreener.len() == 1 {
                return decode(dexscreener[0]).map(Some);
            }
        }

        let dexscreener_count = rows
            .iter()
            .filter(|row| row.4 == ProviderId::DexScreener.as_str())
            .count();
        Err(StorageError::InvalidData(format!(
            "migration sampling mint '{mint}' is ambiguous across {} candidate identities with {} snapshot owners and {} DexScreener candidates",
            rows.len(),
            owners.len(),
            dexscreener_count
        )))
    }
}

fn validate_window(from_unix_ms: i64, through_unix_ms: i64) -> Result<(), StorageError> {
    if from_unix_ms < 0 || through_unix_ms < 0 {
        return Err(StorageError::InvalidData(
            "migration sampling target window must be nonnegative".to_owned(),
        ));
    }
    if from_unix_ms > through_unix_ms {
        return Err(StorageError::InvalidData(
            "migration sampling target window is inverted".to_owned(),
        ));
    }
    Ok(())
}

fn validate_nonempty(value: &str, name: &str) -> Result<(), StorageError> {
    if value.trim().is_empty() {
        return Err(StorageError::InvalidData(format!("{name} must not be empty")));
    }
    Ok(())
}

fn parse_provider(value: &str) -> Result<ProviderId, StorageError> {
    match value {
        "dexscreener" => Ok(ProviderId::DexScreener),
        "helius" => Ok(ProviderId::Helius),
        "alchemy" => Ok(ProviderId::Alchemy),
        "chainstack" => Ok(ProviderId::Chainstack),
        "solana_public" => Ok(ProviderId::SolanaPublic),
        "jupiter" => Ok(ProviderId::Jupiter),
        "meteora" => Ok(ProviderId::Meteora),
        other => Err(StorageError::InvalidData(format!(
            "migration sampling target has unsupported provider '{other}'"
        ))),
    }
}
