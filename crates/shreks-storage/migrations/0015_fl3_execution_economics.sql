CREATE TABLE pump_trade_execution_economics (
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0 AND ordinal <= 4294967295),
    fee_recipient TEXT NOT NULL CHECK (length(trim(fee_recipient)) > 0),
    fee_basis_points TEXT NOT NULL CHECK (length(fee_basis_points) > 0),
    fee_raw TEXT NOT NULL CHECK (length(fee_raw) > 0),
    creator TEXT NOT NULL CHECK (length(trim(creator)) > 0),
    creator_fee_basis_points TEXT NOT NULL CHECK (length(creator_fee_basis_points) > 0),
    creator_fee_raw TEXT NOT NULL CHECK (length(creator_fee_raw) > 0),
    cashback_fee_basis_points TEXT NOT NULL CHECK (length(cashback_fee_basis_points) > 0),
    cashback_raw TEXT NOT NULL CHECK (length(cashback_raw) > 0),
    buyback_fee_basis_points TEXT NOT NULL CHECK (length(buyback_fee_basis_points) > 0),
    buyback_fee_raw TEXT NOT NULL CHECK (length(buyback_fee_raw) > 0),
    PRIMARY KEY (signature, ordinal),
    FOREIGN KEY (signature, ordinal)
        REFERENCES pump_trade_evidence(signature, ordinal)
        ON DELETE CASCADE
);

CREATE TABLE pump_swap_execution_economics (
    signature TEXT NOT NULL CHECK (length(trim(signature)) > 0),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 2147483648 AND ordinal <= 4294967295),
    lp_fee_basis_points TEXT NOT NULL CHECK (length(lp_fee_basis_points) > 0),
    lp_fee_raw TEXT NOT NULL CHECK (length(lp_fee_raw) > 0),
    protocol_fee_basis_points TEXT NOT NULL CHECK (length(protocol_fee_basis_points) > 0),
    protocol_fee_raw TEXT NOT NULL CHECK (length(protocol_fee_raw) > 0),
    quote_amount_with_or_without_lp_fee_raw TEXT NOT NULL
        CHECK (length(quote_amount_with_or_without_lp_fee_raw) > 0),
    coin_creator TEXT,
    coin_creator_fee_basis_points TEXT,
    coin_creator_fee_raw TEXT,
    cashback_fee_basis_points TEXT,
    cashback_raw TEXT,
    buyback_fee_basis_points TEXT,
    buyback_fee_raw TEXT,
    virtual_quote_reserves_raw TEXT,
    can_boost INTEGER CHECK (can_boost IS NULL OR can_boost IN (0, 1)),
    base_supply_raw TEXT,
    PRIMARY KEY (signature, ordinal),
    FOREIGN KEY (signature, ordinal)
        REFERENCES pump_swap_trade_evidence(signature, ordinal)
        ON DELETE CASCADE,
    CHECK (
        (
            coin_creator IS NULL
            AND coin_creator_fee_basis_points IS NULL
            AND coin_creator_fee_raw IS NULL
            AND cashback_fee_basis_points IS NULL
            AND cashback_raw IS NULL
            AND buyback_fee_basis_points IS NULL
            AND buyback_fee_raw IS NULL
            AND virtual_quote_reserves_raw IS NULL
            AND can_boost IS NULL
            AND base_supply_raw IS NULL
        )
        OR
        (
            coin_creator IS NOT NULL AND length(trim(coin_creator)) > 0
            AND coin_creator_fee_basis_points IS NOT NULL AND length(coin_creator_fee_basis_points) > 0
            AND coin_creator_fee_raw IS NOT NULL AND length(coin_creator_fee_raw) > 0
            AND cashback_fee_basis_points IS NOT NULL AND length(cashback_fee_basis_points) > 0
            AND cashback_raw IS NOT NULL AND length(cashback_raw) > 0
            AND buyback_fee_basis_points IS NOT NULL AND length(buyback_fee_basis_points) > 0
            AND buyback_fee_raw IS NOT NULL AND length(buyback_fee_raw) > 0
            AND virtual_quote_reserves_raw IS NOT NULL AND length(virtual_quote_reserves_raw) > 0
            AND can_boost IS NOT NULL
            AND base_supply_raw IS NOT NULL AND length(base_supply_raw) > 0
        )
    )
);
