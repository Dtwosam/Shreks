CREATE INDEX idx_token_lifecycle_events_pumpswap_pool_market
    ON token_lifecycle_events (pool_address, mint, quote_mint)
    WHERE event_type = 'pump_graduation'
      AND to_venue = 'pump_swap';
