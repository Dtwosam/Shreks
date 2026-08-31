use rusqlite::params;
use shreks_core::{DiscoveredToken, ProviderId, VenueId};

use crate::{ShreksDb, StorageError};

const SYSTEM_SOL_MINT: &str = "11111111111111111111111111111111";
const WRAPPED_SOL_MINT: &str = "So11111111111111111111111111111111111111112";

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
        let limit = i64::try_from(limit).map_err(|_| {
            StorageError::InvalidData("fast-lane metadata hydration limit exceeds i64".to_owned())
        })?;

        let mut statement = self.connection.prepare(
            r#"WITH
               pump_rows AS (
                   SELECT
                       p.mint,
                       p.provider,
                       p.observed_at_unix_ms,
                       p.signature,
                       p.ordinal,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.mint
                           ORDER BY p.observed_at_unix_ms DESC,
                                    p.signature DESC,
                                    p.ordinal DESC
                       ) AS mint_rank
                   FROM pump_trade_evidence AS p
                   LEFT JOIN fast_events AS f
                     ON f.signature = p.signature AND f.ordinal = p.ordinal
                   WHERE f.sequence IS NULL
                     AND p.token_amount_raw <> '0'
                     AND (
                         (p.quote_mint IN (?1, ?2) AND p.sol_amount_raw <> '0')
                         OR
                         (p.quote_mint NOT IN (?1, ?2) AND p.quote_amount_raw <> '0')
                     )
                     AND NOT EXISTS (
                         SELECT 1
                         FROM pump_trade_evidence_conflicts AS conflict
                         WHERE conflict.signature = p.signature
                           AND conflict.ordinal = p.ordinal
                     )
               ),
               distinct_markets AS (
                   SELECT DISTINCT pool_address, mint, quote_mint
                   FROM token_lifecycle_events
                   WHERE event_type = 'pump_graduation'
                     AND to_venue = 'pump_swap'
               ),
               market_counts AS (
                   SELECT pool_address, COUNT(*) AS market_count
                   FROM distinct_markets
                   GROUP BY pool_address
               ),
               single_markets AS (
                   SELECT market.pool_address, market.mint
                   FROM distinct_markets AS market
                   JOIN market_counts AS counts
                     ON counts.pool_address = market.pool_address
                    AND counts.market_count = 1
               ),
               pumpswap_rows AS (
                   SELECT
                       market.mint,
                       p.provider,
                       p.observed_at_unix_ms,
                       p.signature,
                       p.ordinal,
                       ROW_NUMBER() OVER (
                           PARTITION BY market.mint
                           ORDER BY p.observed_at_unix_ms DESC,
                                    p.signature DESC,
                                    p.ordinal DESC
                       ) AS mint_rank
                   FROM pump_swap_trade_evidence AS p
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
               ),
               candidates AS (
                   SELECT mint, provider, observed_at_unix_ms,
                          'pump_fun_bonding_curve' AS venue
                   FROM pump_rows
                   WHERE mint_rank = 1

                   UNION ALL

                   SELECT mint, provider, observed_at_unix_ms,
                          'pump_swap' AS venue
                   FROM pumpswap_rows
                   WHERE mint_rank = 1
               ),
               missing AS (
                   SELECT
                       candidate.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY candidate.mint
                           ORDER BY candidate.observed_at_unix_ms DESC,
                                    candidate.venue ASC,
                                    candidate.provider ASC
                       ) AS mint_rank
                   FROM candidates AS candidate
                   WHERE NOT EXISTS (
                       SELECT 1
                       FROM token_candidates AS existing_candidate
                       JOIN token_mint_states AS state
                         ON state.candidate_id = existing_candidate.id
                       WHERE existing_candidate.mint = candidate.mint
                   )
               )
               SELECT mint, provider, observed_at_unix_ms, venue
               FROM missing
               WHERE mint_rank = 1
               ORDER BY observed_at_unix_ms DESC, mint ASC
               LIMIT ?3"#,
        )?;

        let rows = statement
            .query_map(params![SYSTEM_SOL_MINT, WRAPPED_SOL_MINT, limit], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                ))
            })?
            .collect::<Result<Vec<_>, _>>()?;

        rows.into_iter()
            .map(|(mint, provider, discovered_at_unix_ms, venue)| {
                Ok(DiscoveredToken {
                    mint,
                    pair_address: None,
                    dex_id: None,
                    venue: Some(parse_venue(&venue)?),
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

fn parse_venue(value: &str) -> Result<VenueId, StorageError> {
    match value {
        "pump_fun_bonding_curve" => Ok(VenueId::PumpFunBondingCurve),
        "pump_swap" => Ok(VenueId::PumpSwap),
        other => Err(StorageError::InvalidData(format!(
            "unknown fast-lane hydration venue '{other}'"
        ))),
    }
}
