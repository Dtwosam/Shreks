use std::collections::HashSet;

use rusqlite::params;
use shreks_core::{DiscoveredToken, ProviderId, VenueId};

use crate::{ShreksDb, StorageError};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

/// Hard cap on raw evidence considered by one metadata-hydration selector call.
///
/// The production database can contain millions of historical raw events. A
/// metadata pass must therefore never rank or group the entire backlog just to
/// find a handful of current mints. The raw observed-at indexes let these
/// frontiers read the newest evidence first while historical debt remains
/// durable for later cycles.
const FAST_LANE_METADATA_RAW_SCAN_LIMIT: usize = 2_048;

impl ShreksDb {
    /// Return the freshest distinct fast-lane base mints whose verified mint
    /// state is still missing.
    ///
    /// The durable raw evidence is the restart-safe queue. New/current order
    /// flow is deliberately prioritized over historical debt so metadata
    /// hydration can keep the canonical lane current while old evidence remains
    /// preserved for later catch-up. PumpSwap rows are eligible only when one
    /// verified graduation market identifies the pool's base mint; missing or
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

        let mut candidates = self.recent_pump_rows(raw_scan_limit)?;
        candidates.extend(self.recent_pumpswap_rows(raw_scan_limit)?);
        candidates.sort_by(|left, right| {
            right
                .discovered_at_unix_ms
                .cmp(&left.discovered_at_unix_ms)
                .then_with(|| left.mint.cmp(&right.mint))
                .then_with(|| left.source.as_str().cmp(right.source.as_str()))
        });

        let mut seen_mints = HashSet::new();
        let mut selected = Vec::with_capacity(limit.min(candidates.len()));
        for candidate in candidates {
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
