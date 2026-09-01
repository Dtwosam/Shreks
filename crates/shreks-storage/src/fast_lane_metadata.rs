use std::collections::HashSet;

use rusqlite::params;
use shreks_core::{DiscoveredToken, ProviderId, TokenMintState, VenueId};

use crate::{unix_time_ms, ShreksDb, StorageError};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

/// Hard cap on raw evidence considered by one metadata-hydration selector call.
///
/// The production database can contain millions of historical raw events. A
/// metadata pass must therefore never rank or group the entire backlog just to
/// find a handful of current mints. The raw observed-at indexes let these
/// bounded frontiers read both current flow and historical debt without scanning
/// the full evidence tables.
const FAST_LANE_METADATA_RAW_SCAN_LIMIT: usize = 2_048;

impl ShreksDb {
    /// Return distinct fast-lane base mints whose verified mint state is missing.
    ///
    /// Most capacity stays newest-first so current order flow can become
    /// canonical promptly. For selector requests of at least four mints, one
    /// quarter of the capacity is reserved for the oldest positive Pump debt.
    /// This prevents a continuously advancing newest frontier from permanently
    /// starving historical mints while keeping every database read bounded.
    /// PumpSwap rows remain eligible in the fresh lane only when one verified
    /// graduation market identifies the pool's base mint; missing or
    /// contradictory lifecycle mapping is left unresolved rather than guessed.
    pub fn fast_lane_mints_missing_state(
        &self,
        limit: usize,
    ) -> Result<Vec<DiscoveredToken>, StorageError> {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let raw_scan_limit = i64::try_from(FAST_LANE_METADATA_RAW_SCAN_LIMIT).map_err(|_| {
            StorageError::InvalidData(
                "fast-lane metadata raw scan limit exceeds i64".to_owned(),
            )
        })?;

        let mut recent = self.recent_pump_rows(raw_scan_limit)?;
        recent.extend(self.recent_pumpswap_rows(raw_scan_limit)?);
        recent.sort_by(|left, right| {
            right
                .discovered_at_unix_ms
                .cmp(&left.discovered_at_unix_ms)
                .then_with(|| left.mint.cmp(&right.mint))
                .then_with(|| left.source.as_str().cmp(right.source.as_str()))
        });

        let debt_reserve = if limit >= 4 {
            (limit / 4).max(1)
        } else {
            0
        };
        let fresh_target = limit.saturating_sub(debt_reserve);

        let mut seen_mints = HashSet::new();
        let mut selected = Vec::with_capacity(limit);
        let mut recent = recent.into_iter();

        if fresh_target > 0 {
            for candidate in recent.by_ref() {
                if !seen_mints.insert(candidate.mint.clone()) {
                    continue;
                }
                selected.push(candidate);
                if selected.len() == fresh_target {
                    break;
                }
            }
        }

        for candidate in self.oldest_pump_rows(raw_scan_limit)? {
            if !seen_mints.insert(candidate.mint.clone()) {
                continue;
            }
            selected.push(candidate);
            if selected.len() == limit {
                return Ok(selected);
            }
        }

        for candidate in recent {
            if !seen_mints.insert(candidate.mint.clone()) {
                continue;
            }
            selected.push(candidate);
            if selected.len() == limit {
                break;
            }
        }
        Ok(selected)
    }

    /// Persist the candidate identity and its verified public-Solana mint state
    /// in one short SQLite transaction.
    ///
    /// Fast-lane raw evidence is already the durable restart-safe queue, so
    /// hydration should not acquire the writer twice around a provider call.
    /// The transaction either makes the verified metadata usable by the
    /// canonicalizer as one unit or leaves the raw evidence pending unchanged.
    pub fn persist_fast_lane_mint_state(
        &self,
        candidate: &DiscoveredToken,
        state: &TokenMintState,
    ) -> Result<(), StorageError> {
        if candidate.mint.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "fast-lane metadata candidate mint must not be empty".to_owned(),
            ));
        }
        if state.mint.trim().is_empty() || state.owner_program.trim().is_empty() {
            return Err(StorageError::InvalidData(
                "fast-lane mint state requires mint and owner program".to_owned(),
            ));
        }
        if state.mint != candidate.mint {
            return Err(StorageError::InvalidData(format!(
                "fast-lane mint-state identity mismatch: candidate={} state={}",
                candidate.mint, state.mint
            )));
        }
        if state.provider != ProviderId::SolanaPublic {
            return Err(StorageError::InvalidData(format!(
                "fast-lane mint-state provider must be solana_public, got {}",
                state.provider
            )));
        }

        let pair_address = candidate.pair_address.as_deref().unwrap_or("");
        let venue = candidate.venue.map(|value| value.as_str());
        let created_at = unix_time_ms()?;
        let transaction = self.connection.unchecked_transaction()?;

        transaction.execute(
            r#"INSERT INTO token_candidates (
                   mint, pair_address, discovery_source, discovered_at_unix_ms, created_at_unix_ms, venue
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)
               ON CONFLICT(mint, pair_address, discovery_source) DO UPDATE SET
                   venue = COALESCE(excluded.venue, token_candidates.venue),
                   discovered_at_unix_ms = MIN(token_candidates.discovered_at_unix_ms, excluded.discovered_at_unix_ms)"#,
            params![
                candidate.mint,
                pair_address,
                candidate.source.as_str(),
                candidate.discovered_at_unix_ms,
                created_at,
                venue,
            ],
        )?;

        let candidate_id: i64 = transaction.query_row(
            "SELECT id FROM token_candidates WHERE mint = ?1 AND pair_address = ?2 AND discovery_source = ?3",
            params![candidate.mint, pair_address, candidate.source.as_str()],
            |row| row.get(0),
        )?;

        transaction.execute(
            r#"INSERT OR IGNORE INTO token_mint_states (
                   candidate_id, provider, owner_program, supply, decimals, mint_authority,
                   freeze_authority, slot, observed_at_unix_ms
               ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)"#,
            params![
                candidate_id,
                state.provider.as_str(),
                state.owner_program,
                state.supply.to_string(),
                i64::from(state.decimals),
                state.mint_authority,
                state.freeze_authority,
                state.slot.to_string(),
                state.observed_at_unix_ms,
            ],
        )?;

        transaction.commit()?;
        Ok(())
    }

    /// Read only a fixed newest-first Pump raw frontier before applying any
    /// canonical, conflict, economics, or mint-state eligibility checks.
    fn recent_pump_rows(
        &self,
        raw_scan_limit: i64,
    ) -> Result<Vec<DiscoveredToken>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"WITH recent_pump_rows AS MATERIALIZED (
                   SELECT
                       p.mint,
                       p.quote_mint,
                       p.provider,
                       p.observed_at_unix_ms,
                       p.signature,
                       p.ordinal,
                       p.token_amount_raw,
                       p.sol_amount_raw,
                       p.quote_amount_raw
                   FROM pump_trade_evidence AS p
                   ORDER BY p.observed_at_unix_ms DESC,
                            p.signature DESC,
                            p.ordinal DESC
                   LIMIT ?1
               )
               SELECT
                   p.mint,
                   p.provider,
                   p.observed_at_unix_ms
               FROM recent_pump_rows AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
                 AND p.token_amount_raw <> '0'
                 AND (
                     (p.quote_mint IN (?2, ?3) AND p.sol_amount_raw <> '0')
                     OR
                     (p.quote_mint NOT IN (?2, ?3) AND p.quote_amount_raw <> '0')
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_trade_evidence_conflicts AS conflict
                     WHERE conflict.signature = p.signature
                       AND conflict.ordinal = p.ordinal
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM token_candidates AS existing_candidate
                     JOIN token_mint_states AS state
                       ON state.candidate_id = existing_candidate.id
                     WHERE existing_candidate.mint = p.mint
                 )
               ORDER BY p.observed_at_unix_ms DESC,
                        p.signature DESC,
                        p.ordinal DESC"#,
        )?;

        let rows = statement
            .query_map(
                params![raw_scan_limit, SYSTEM_SOL_MINT, WRAPPED_SOL_MINT],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, i64>(2)?,
                    ))
                },
            )?
            .collect::<Result<Vec<_>, _>>()?;

        rows.into_iter()
            .map(|(mint, provider, discovered_at_unix_ms)| {
                Ok(DiscoveredToken {
                    mint,
                    pair_address: None,
                    dex_id: None,
                    venue: Some(VenueId::PumpFunBondingCurve),
                    discovered_at_unix_ms,
                    source: parse_provider(&provider)?,
                })
            })
            .collect()
    }

    /// Read only a fixed oldest-first Pump raw frontier. The same eligibility
    /// rules as the fresh selector apply, but this lane exists solely to make
    /// guaranteed progress on durable metadata debt that has fallen behind the
    /// continuously advancing newest-first window.
    fn oldest_pump_rows(
        &self,
        raw_scan_limit: i64,
    ) -> Result<Vec<DiscoveredToken>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"WITH oldest_pump_rows AS MATERIALIZED (
                   SELECT
                       p.mint,
                       p.quote_mint,
                       p.provider,
                       p.observed_at_unix_ms,
                       p.signature,
                       p.ordinal,
                       p.token_amount_raw,
                       p.sol_amount_raw,
                       p.quote_amount_raw
                   FROM pump_trade_evidence AS p
                   ORDER BY p.observed_at_unix_ms ASC,
                            p.signature ASC,
                            p.ordinal ASC
                   LIMIT ?1
               )
               SELECT
                   p.mint,
                   p.provider,
                   p.observed_at_unix_ms
               FROM oldest_pump_rows AS p
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
                 AND p.token_amount_raw <> '0'
                 AND (
                     (p.quote_mint IN (?2, ?3) AND p.sol_amount_raw <> '0')
                     OR
                     (p.quote_mint NOT IN (?2, ?3) AND p.quote_amount_raw <> '0')
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_trade_evidence_conflicts AS conflict
                     WHERE conflict.signature = p.signature
                       AND conflict.ordinal = p.ordinal
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM token_candidates AS existing_candidate
                     JOIN token_mint_states AS state
                       ON state.candidate_id = existing_candidate.id
                     WHERE existing_candidate.mint = p.mint
                 )
               ORDER BY p.observed_at_unix_ms ASC,
                        p.signature ASC,
                        p.ordinal ASC"#,
        )?;

        let rows = statement
            .query_map(
                params![raw_scan_limit, SYSTEM_SOL_MINT, WRAPPED_SOL_MINT],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, i64>(2)?,
                    ))
                },
            )?
            .collect::<Result<Vec<_>, _>>()?;

        rows.into_iter()
            .map(|(mint, provider, discovered_at_unix_ms)| {
                Ok(DiscoveredToken {
                    mint,
                    pair_address: None,
                    dex_id: None,
                    venue: Some(VenueId::PumpFunBondingCurve),
                    discovered_at_unix_ms,
                    source: parse_provider(&provider)?,
                })
            })
            .collect()
    }

    /// Read only a fixed newest-first PumpSwap raw frontier, then resolve the
    /// bounded set of pools through durable lifecycle evidence. Ambiguous or
    /// missing pool mappings stay unresolved and are never guessed.
    fn recent_pumpswap_rows(
        &self,
        raw_scan_limit: i64,
    ) -> Result<Vec<DiscoveredToken>, StorageError> {
        let mut statement = self.connection.prepare(
            r#"WITH recent_pumpswap_rows AS MATERIALIZED (
                   SELECT
                       p.provider,
                       p.observed_at_unix_ms,
                       p.pool,
                       p.signature,
                       p.ordinal
                   FROM pump_swap_trade_evidence AS p
                   ORDER BY p.observed_at_unix_ms DESC,
                            p.signature DESC,
                            p.ordinal DESC
                   LIMIT ?1
               ),
               recent_pools AS MATERIALIZED (
                   SELECT DISTINCT pool
                   FROM recent_pumpswap_rows
               ),
               distinct_markets AS MATERIALIZED (
                   SELECT DISTINCT
                       lifecycle.pool_address,
                       lifecycle.mint,
                       lifecycle.quote_mint
                   FROM token_lifecycle_events AS lifecycle
                   JOIN recent_pools AS recent
                     ON recent.pool = lifecycle.pool_address
                   WHERE lifecycle.event_type = 'pump_graduation'
                     AND lifecycle.to_venue = 'pump_swap'
               ),
               market_counts AS MATERIALIZED (
                   SELECT pool_address, COUNT(*) AS market_count
                   FROM distinct_markets
                   GROUP BY pool_address
               ),
               single_markets AS MATERIALIZED (
                   SELECT market.pool_address, market.mint
                   FROM distinct_markets AS market
                   JOIN market_counts AS counts
                     ON counts.pool_address = market.pool_address
                    AND counts.market_count = 1
               )
               SELECT
                   market.mint,
                   p.provider,
                   p.observed_at_unix_ms
               FROM recent_pumpswap_rows AS p
               JOIN single_markets AS market
                 ON market.pool_address = p.pool
               LEFT JOIN fast_events AS f
                 ON f.signature = p.signature AND f.ordinal = p.ordinal
               WHERE f.sequence IS NULL
                 AND NOT EXISTS (
                     SELECT 1
                     FROM pump_swap_trade_evidence_conflicts AS conflict
                     WHERE conflict.signature = p.signature
                       AND conflict.ordinal = p.ordinal
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM token_candidates AS existing_candidate
                     JOIN token_mint_states AS state
                       ON state.candidate_id = existing_candidate.id
                     WHERE existing_candidate.mint = market.mint
                 )
               ORDER BY p.observed_at_unix_ms DESC,
                        p.signature DESC,
                        p.ordinal DESC"#,
        )?;

        let rows = statement
            .query_map(params![raw_scan_limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        rows.into_iter()
            .map(|(mint, provider, discovered_at_unix_ms)| {
                Ok(DiscoveredToken {
                    mint,
                    pair_address: None,
                    dex_id: None,
                    venue: Some(VenueId::PumpSwap),
                    discovered_at_unix_ms,
                    source: parse_provider(&provider)?,
                })
            })
            .collect()
    }
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
            "unknown fast-lane hydration provider '{other}'"
        ))),
    }
}
