from __future__ import annotations

from .models import (
    SafetyAssessment,
    SafetyDecision,
    SafetyFinding,
    SafetyInputs,
    SafetyPolicy,
    SafetyReasonCode,
    SafetySeverity,
)


def assess_safety(inputs: SafetyInputs, policy: SafetyPolicy) -> SafetyAssessment:
    findings: list[SafetyFinding] = []

    _append_hard_findings(findings, inputs, policy)
    _append_data_quality_findings(findings, inputs, policy)
    _append_soft_findings(findings, inputs, policy)

    if any(finding.severity is SafetySeverity.HARD for finding in findings):
        decision = SafetyDecision.REJECT
    elif any(
        finding.severity is SafetySeverity.DATA_QUALITY for finding in findings
    ):
        decision = SafetyDecision.INCOMPLETE
    else:
        decision = SafetyDecision.PASS

    return SafetyAssessment(
        decision=decision,
        policy_version=policy.version,
        as_of_unix_ms=inputs.as_of_unix_ms,
        findings=tuple(findings),
    )


def _append_hard_findings(
    findings: list[SafetyFinding],
    inputs: SafetyInputs,
    policy: SafetyPolicy,
) -> None:
    if inputs.global_risk_halt:
        findings.append(
            _finding(
                SafetyReasonCode.GLOBAL_RISK_HALT,
                SafetySeverity.HARD,
                "global risk halt is active",
                observed=True,
            )
        )

    if inputs.mint_authority_active is True:
        findings.append(
            _finding(
                SafetyReasonCode.MINT_AUTHORITY_ACTIVE,
                SafetySeverity.HARD,
                "mint authority is active",
                observed=True,
            )
        )

    if inputs.freeze_authority_active is True:
        findings.append(
            _finding(
                SafetyReasonCode.FREEZE_AUTHORITY_ACTIVE,
                SafetySeverity.HARD,
                "freeze authority is active",
                observed=True,
            )
        )

    if (
        inputs.liquidity_usd is not None
        and inputs.liquidity_usd < policy.min_liquidity_usd
    ):
        findings.append(
            _finding(
                SafetyReasonCode.LIQUIDITY_BELOW_MINIMUM,
                SafetySeverity.HARD,
                "liquidity is below the configured hard minimum",
                observed=inputs.liquidity_usd,
                threshold=policy.min_liquidity_usd,
            )
        )

    if (
        inputs.top_holder_concentration_pct is not None
        and inputs.top_holder_concentration_pct
        > policy.max_top_holder_concentration_pct
    ):
        findings.append(
            _finding(
                SafetyReasonCode.HOLDER_CONCENTRATION_ABOVE_MAXIMUM,
                SafetySeverity.HARD,
                "top-holder concentration exceeds the configured hard maximum",
                observed=inputs.top_holder_concentration_pct,
                threshold=policy.max_top_holder_concentration_pct,
            )
        )

    if inputs.exit_quote_available is False:
        findings.append(
            _finding(
                SafetyReasonCode.EXIT_QUOTE_UNAVAILABLE,
                SafetySeverity.HARD,
                "a reliable exit quote is explicitly unavailable",
                observed=False,
            )
        )

    if inputs.execution_trap_detected:
        findings.append(
            _finding(
                SafetyReasonCode.EXECUTION_TRAP_DETECTED,
                SafetySeverity.HARD,
                "an execution trap was explicitly detected",
                observed=True,
            )
        )


def _append_data_quality_findings(
    findings: list[SafetyFinding],
    inputs: SafetyInputs,
    policy: SafetyPolicy,
) -> None:
    if policy.require_known_authorities and inputs.mint_authority_active is None:
        findings.append(
            _finding(
                SafetyReasonCode.MINT_AUTHORITY_UNKNOWN,
                SafetySeverity.DATA_QUALITY,
                "mint authority state is unknown",
            )
        )

    if policy.require_known_authorities and inputs.freeze_authority_active is None:
        findings.append(
            _finding(
                SafetyReasonCode.FREEZE_AUTHORITY_UNKNOWN,
                SafetySeverity.DATA_QUALITY,
                "freeze authority state is unknown",
            )
        )

    if policy.require_liquidity and inputs.liquidity_usd is None:
        findings.append(
            _finding(
                SafetyReasonCode.LIQUIDITY_UNKNOWN,
                SafetySeverity.DATA_QUALITY,
                "liquidity is unknown",
            )
        )

    if (
        policy.require_holder_concentration
        and inputs.top_holder_concentration_pct is None
    ):
        findings.append(
            _finding(
                SafetyReasonCode.HOLDER_CONCENTRATION_UNKNOWN,
                SafetySeverity.DATA_QUALITY,
                "top-holder concentration is unknown",
            )
        )

    if policy.require_exit_quote and inputs.exit_quote_available is None:
        findings.append(
            _finding(
                SafetyReasonCode.EXIT_QUOTE_UNKNOWN,
                SafetySeverity.DATA_QUALITY,
                "exit-quote availability is unknown",
            )
        )

    observed_at = inputs.critical_data_observed_at_unix_ms
    contradiction_from_timestamp = False
    if observed_at is None:
        findings.append(
            _finding(
                SafetyReasonCode.CRITICAL_DATA_STALE,
                SafetySeverity.DATA_QUALITY,
                "critical-data observation timestamp is missing",
            )
        )
    elif observed_at > inputs.as_of_unix_ms:
        contradiction_from_timestamp = True
        findings.append(
            _finding(
                SafetyReasonCode.CRITICAL_DATA_CONTRADICTORY,
                SafetySeverity.DATA_QUALITY,
                "critical data is timestamped after the assessment time",
            )
        )
    elif inputs.as_of_unix_ms - observed_at > policy.max_critical_data_age_ms:
        findings.append(
            _finding(
                SafetyReasonCode.CRITICAL_DATA_STALE,
                SafetySeverity.DATA_QUALITY,
                "critical data is older than the configured freshness limit",
                observed=float(inputs.as_of_unix_ms - observed_at),
                threshold=float(policy.max_critical_data_age_ms),
            )
        )

    if inputs.critical_data_contradictory and not contradiction_from_timestamp:
        findings.append(
            _finding(
                SafetyReasonCode.CRITICAL_DATA_CONTRADICTORY,
                SafetySeverity.DATA_QUALITY,
                "critical data is explicitly contradictory",
                observed=True,
            )
        )


def _append_soft_findings(
    findings: list[SafetyFinding],
    inputs: SafetyInputs,
    policy: SafetyPolicy,
) -> None:
    if (
        inputs.liquidity_usd is not None
        and inputs.liquidity_usd >= policy.min_liquidity_usd
        and inputs.liquidity_usd < policy.soft_min_liquidity_usd
    ):
        findings.append(
            _finding(
                SafetyReasonCode.LIQUIDITY_WEAK,
                SafetySeverity.SOFT,
                "liquidity is above the hard minimum but below the preferred level",
                observed=inputs.liquidity_usd,
                threshold=policy.soft_min_liquidity_usd,
            )
        )

    if (
        inputs.top_holder_concentration_pct is not None
        and inputs.top_holder_concentration_pct
        > policy.soft_max_top_holder_concentration_pct
        and inputs.top_holder_concentration_pct
        <= policy.max_top_holder_concentration_pct
    ):
        findings.append(
            _finding(
                SafetyReasonCode.HOLDER_CONCENTRATION_ELEVATED,
                SafetySeverity.SOFT,
                "top-holder concentration is elevated but below the hard maximum",
                observed=inputs.top_holder_concentration_pct,
                threshold=policy.soft_max_top_holder_concentration_pct,
            )
        )

    if (
        inputs.creator_concentration_pct is not None
        and inputs.creator_concentration_pct
        > policy.soft_max_creator_concentration_pct
    ):
        findings.append(
            _finding(
                SafetyReasonCode.CREATOR_CONCENTRATION_ELEVATED,
                SafetySeverity.SOFT,
                "creator concentration exceeds the configured soft threshold",
                observed=inputs.creator_concentration_pct,
                threshold=policy.soft_max_creator_concentration_pct,
            )
        )

    if (
        inputs.exit_price_impact_pct is not None
        and inputs.exit_price_impact_pct > policy.soft_max_exit_price_impact_pct
    ):
        findings.append(
            _finding(
                SafetyReasonCode.EXIT_PRICE_IMPACT_ELEVATED,
                SafetySeverity.SOFT,
                "exit price impact exceeds the configured soft threshold",
                observed=inputs.exit_price_impact_pct,
                threshold=policy.soft_max_exit_price_impact_pct,
            )
        )


def _finding(
    code: SafetyReasonCode,
    severity: SafetySeverity,
    message: str,
    *,
    observed: float | bool | None = None,
    threshold: float | None = None,
) -> SafetyFinding:
    return SafetyFinding(
        code=code,
        severity=severity,
        message=message,
        observed_value=observed,
        threshold_value=threshold,
    )
