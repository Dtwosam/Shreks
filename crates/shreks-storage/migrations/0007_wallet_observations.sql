CREATE TABLE wallet_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_mint TEXT NOT NULL,
    provider TEXT NOT NULL,
    wallet TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN (
        'buy', 'sell', 'transfer', 'liquidity_event', 'creator_action', 'other'
    )),
    evidence TEXT NOT NULL CHECK (evidence IN ('direct', 'inferred')),
    signature TEXT NOT NULL,
    event_index INTEGER NOT NULL CHECK (event_index >= 0),
    slot TEXT NOT NULL,
    observed_at_unix_ms INTEGER NOT NULL CHECK (observed_at_unix_ms >= 0),
    occurred_at_unix_ms INTEGER CHECK (occurred_at_unix_ms IS NULL OR occurred_at_unix_ms >= 0),
    candidate_token_delta_raw TEXT,
    counter_asset_mint TEXT,
    counter_asset_delta_raw TEXT,
    venue TEXT,
    counterparty TEXT,
    UNIQUE (provider, signature, event_index, wallet, candidate_mint),
    CHECK (counter_asset_delta_raw IS NULL OR counter_asset_mint IS NOT NULL)
);

CREATE INDEX idx_wallet_observations_mint_time
    ON wallet_observations (
        candidate_mint,
        observed_at_unix_ms,
        provider,
        signature,
        event_index,
        wallet
    );

CREATE INDEX idx_wallet_observations_wallet_time
    ON wallet_observations (
        wallet,
        observed_at_unix_ms,
        provider,
        signature,
        event_index,
        candidate_mint
    );

CREATE INDEX idx_wallet_observations_provider_signature
    ON wallet_observations (provider, signature);
