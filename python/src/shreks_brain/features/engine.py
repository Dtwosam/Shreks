from __future__ import annotations

from shreks_brain.safety import SafetyReasonCode, SafetySeverity

from .models import FEATURE_SCHEMA_VERSION, FeatureInputs, FeatureVector


_MISSING_FEATURE_ORDER = (
    "token_age_seconds",
    "price_usd",
    "liquidity_usd",
    "liquidity_change_5m_pct",
    "exit_price_impact_pct",
    "volume_m5_usd",
    "volume_h1_usd",
    "volume_velocity_ratio",
    "tx_count_m5",
    "tx_count_h1",
    "buy_fraction_m5",
    "buy_fraction_h1",
    "buy_sell_ratio_m5",
    "buy_sell_ratio_h1",
    "buy_pressure_acceleration",
    "return_1m_pct",
    "return_5m_pct",
    "return_15m_pct",
    "momentum_acceleration_1m_vs_5m",
    "distance_from_local_high_pct",
    "range_position_pct",
)


def build_feature_vector(inputs: FeatureInputs) -> FeatureVector:
    current = inputs.current

    source_age_ms = inputs.as_of_unix_ms - current.observed_at_unix_ms
    token_age_seconds = (
        None
        if inputs.pair_created_at_unix_ms is None
        else (inputs.as_of_unix_ms - inputs.pair_created_at_unix_ms) / 1000
    )

    liquidity_change_5m_pct = _pct_change(
        current.liquidity_usd,
        None if inputs.five_minutes_ago is None else inputs.five_minutes_ago.liquidity_usd,
    )

    volume_velocity_ratio = _ratio_scaled(
        current.volume_m5_usd,
        current.volume_h1_usd,
        scale=12.0,
    )

    tx_count_m5 = _tx_count(current.buys_m5, current.sells_m5)
    tx_count_h1 = _tx_count(current.buys_h1, current.sells_h1)

    buy_fraction_m5 = _buy_fraction(current.buys_m5, current.sells_m5)
    buy_fraction_h1 = _buy_fraction(current.buys_h1, current.sells_h1)
    buy_sell_ratio_m5 = _buy_sell_ratio(current.buys_m5, current.sells_m5)
    buy_sell_ratio_h1 = _buy_sell_ratio(current.buys_h1, current.sells_h1)
    buy_pressure_acceleration = (
        None
        if buy_fraction_m5 is None or buy_fraction_h1 is None
        else buy_fraction_m5 - buy_fraction_h1
    )

    return_1m_pct = _pct_change(
        current.price_usd,
        None if inputs.one_minute_ago is None else inputs.one_minute_ago.price_usd,
    )
    return_5m_pct = _pct_change(
        current.price_usd,
        None if inputs.five_minutes_ago is None else inputs.five_minutes_ago.price_usd,
    )
    return_15m_pct = _pct_change(
        current.price_usd,
        None if inputs.fifteen_minutes_ago is None else inputs.fifteen_minutes_ago.price_usd,
    )
    momentum_acceleration_1m_vs_5m = (
        None
        if return_1m_pct is None or return_5m_pct is None
        else return_1m_pct - (return_5m_pct / 5.0)
    )

    distance_from_local_high_pct = _distance_from_high(
        current.price_usd,
        inputs.local_high_price_usd,
    )
    range_position_pct = _range_position(
        current.price_usd,
        inputs.local_high_price_usd,
        inputs.local_low_price_usd,
    )

    soft_findings = tuple(
        finding
        for finding in inputs.safety.findings
        if finding.severity is SafetySeverity.SOFT
    )
    reason_codes = {finding.code for finding in inputs.safety.findings}

    numeric_values = {
        "token_age_seconds": token_age_seconds,
        "price_usd": current.price_usd,
        "liquidity_usd": current.liquidity_usd,
        "liquidity_change_5m_pct": liquidity_change_5m_pct,
        "exit_price_impact_pct": inputs.exit_price_impact_pct,
        "volume_m5_usd": current.volume_m5_usd,
        "volume_h1_usd": current.volume_h1_usd,
        "volume_velocity_ratio": volume_velocity_ratio,
        "tx_count_m5": tx_count_m5,
        "tx_count_h1": tx_count_h1,
        "buy_fraction_m5": buy_fraction_m5,
        "buy_fraction_h1": buy_fraction_h1,
        "buy_sell_ratio_m5": buy_sell_ratio_m5,
        "buy_sell_ratio_h1": buy_sell_ratio_h1,
        "buy_pressure_acceleration": buy_pressure_acceleration,
        "return_1m_pct": return_1m_pct,
        "return_5m_pct": return_5m_pct,
        "return_15m_pct": return_15m_pct,
        "momentum_acceleration_1m_vs_5m": momentum_acceleration_1m_vs_5m,
        "distance_from_local_high_pct": distance_from_local_high_pct,
        "range_position_pct": range_position_pct,
    }
    missing_features = tuple(
        name for name in _MISSING_FEATURE_ORDER if numeric_values[name] is None
    )

    return FeatureVector(
        schema_version=FEATURE_SCHEMA_VERSION,
        as_of_unix_ms=inputs.as_of_unix_ms,
        source_observed_at_unix_ms=current.observed_at_unix_ms,
        source_age_ms=source_age_ms,
        safety_policy_version=inputs.safety.policy_version,
        safety_decision=inputs.safety.decision,
        token_age_seconds=token_age_seconds,
        price_usd=current.price_usd,
        liquidity_usd=current.liquidity_usd,
        liquidity_change_5m_pct=liquidity_change_5m_pct,
        exit_price_impact_pct=inputs.exit_price_impact_pct,
        volume_m5_usd=current.volume_m5_usd,
        volume_h1_usd=current.volume_h1_usd,
        volume_velocity_ratio=volume_velocity_ratio,
        tx_count_m5=tx_count_m5,
        tx_count_h1=tx_count_h1,
        buy_fraction_m5=buy_fraction_m5,
        buy_fraction_h1=buy_fraction_h1,
        buy_sell_ratio_m5=buy_sell_ratio_m5,
        buy_sell_ratio_h1=buy_sell_ratio_h1,
        buy_pressure_acceleration=buy_pressure_acceleration,
        return_1m_pct=return_1m_pct,
        return_5m_pct=return_5m_pct,
        return_15m_pct=return_15m_pct,
        momentum_acceleration_1m_vs_5m=momentum_acceleration_1m_vs_5m,
        distance_from_local_high_pct=distance_from_local_high_pct,
        range_position_pct=range_position_pct,
        safety_soft_finding_count=len(soft_findings),
        safety_liquidity_weak=SafetyReasonCode.LIQUIDITY_WEAK in reason_codes,
        safety_holder_concentration_elevated=(
            SafetyReasonCode.HOLDER_CONCENTRATION_ELEVATED in reason_codes
        ),
        safety_creator_concentration_elevated=(
            SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED in reason_codes
        ),
        safety_exit_price_impact_elevated=(
            SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED in reason_codes
        ),
        missing_features=missing_features,
    )


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return ((current / baseline) - 1.0) * 100.0


def _tx_count(buys: int | None, sells: int | None) -> int | None:
    if buys is None or sells is None:
        return None
    return buys + sells


def _buy_fraction(buys: int | None, sells: int | None) -> float | None:
    total = _tx_count(buys, sells)
    if total is None or total <= 0:
        return None
    return buys / total


def _buy_sell_ratio(buys: int | None, sells: int | None) -> float | None:
    if buys is None or sells is None or sells <= 0:
        return None
    return buys / sells


def _ratio_scaled(
    numerator: float | None,
    denominator: float | None,
    *,
    scale: float,
) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return (numerator * scale) / denominator


def _distance_from_high(
    price_usd: float | None,
    local_high_price_usd: float | None,
) -> float | None:
    if price_usd is None or local_high_price_usd is None or local_high_price_usd <= 0:
        return None
    return ((price_usd / local_high_price_usd) - 1.0) * 100.0


def _range_position(
    price_usd: float | None,
    local_high_price_usd: float | None,
    local_low_price_usd: float | None,
) -> float | None:
    if (
        price_usd is None
        or local_high_price_usd is None
        or local_low_price_usd is None
        or local_high_price_usd <= local_low_price_usd
    ):
        return None
    return (
        (price_usd - local_low_price_usd)
        / (local_high_price_usd - local_low_price_usd)
    ) * 100.0
