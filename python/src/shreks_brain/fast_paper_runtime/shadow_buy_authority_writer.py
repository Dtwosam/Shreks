from __future__ import annotations

from pathlib import Path

from shreks_brain.fast_deterministic_campaign import (
    FastDeterministicComparisonExecutionPolicy,
)
from shreks_brain.observer_campaign import ObserverRegimeReadPolicy
from shreks_brain.observer_market import ObserverMarketReadPolicy
from shreks_brain.observer_safety import ObserverSafetyProbeIdentity
from shreks_brain.regime import RegimePolicy
from shreks_brain.safety import SafetyPolicy

from .models import FastPaperRuntimeManifest
from .persisted_quotes import FastPaperShadowQuoteReadPolicy
from .shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .shadow_buy_authority_evidence_adapter import (
    produce_fast_paper_shadow_buy_authority_from_persisted_evidence,
)
from .shadow_buy_authority_source import (
    read_fast_paper_shadow_buy_authority_source_record,
    write_fast_paper_shadow_buy_authority_source_record,
)
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    _resolve_candidate_id,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
)


def run_fast_paper_shadow_buy_authority_writer_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    execution_bootstrap: FastPaperShadowServiceExecutionBootstrap,
    *,
    decision_evidence_directory: str | Path,
    buy_authority_source_directory: str | Path,
    quote_usd_source_directory: str | Path,
    market_read_policy: ObserverMarketReadPolicy,
    regime_read_policy: ObserverRegimeReadPolicy,
    regime_policy: RegimePolicy,
    safety_policy: SafetyPolicy,
    safety_probe_identity: ObserverSafetyProbeIdentity,
    execution_economics_policy: FastDeterministicComparisonExecutionPolicy,
    operator_risk_control_path: str | Path,
    entry_authority_binary_path: str | Path,
    day_started_at_unix_ms: int,
    data_healthy: bool | None,
    execution_healthy: bool | None,
    global_risk_halt: bool,
) -> int:
    if type(decision_bootstrap) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if (
        type(execution_bootstrap)
        is not FastPaperShadowServiceExecutionBootstrap
    ):
        raise ValueError(
            "execution_bootstrap must be exact "
            "FastPaperShadowServiceExecutionBootstrap"
        )

    manifest = decision_bootstrap.manifest
    _require_bootstrap_manifest_binding(
        manifest,
        execution_bootstrap,
    )
    decision_root = _require_directory(
        decision_evidence_directory,
        label="BUY authority writer decision evidence",
    )
    authority_root = _require_directory(
        buy_authority_source_directory,
        label="BUY authority writer source",
    )
    quote_usd_root = _require_directory(
        quote_usd_source_directory,
        label="BUY authority writer quote/USD source",
    )

    evidence = _oldest_unexecuted_decision(
        manifest,
        execution_bootstrap,
        decision_root,
    )
    if evidence is None:
        return 0
    if evidence.decision.action != "BUY":
        return 0
    if evidence.position.kind != "FLAT":
        raise ValueError(
            "BUY authority writer requires FLAT learned posture"
        )

    authority_path = authority_root / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    if authority_path.is_symlink():
        raise ValueError(
            "BUY authority source record path must not be a symlink"
        )
    if authority_path.exists():
        if not authority_path.is_file():
            raise ValueError(
                "BUY authority source record path must identify a regular file"
            )
        read_fast_paper_shadow_buy_authority_source_record(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.execution_policy,
            execution_bootstrap.checkpoint,
            execution_bootstrap.runtime_state,
            evidence,
            authority_root,
        )
        return 0

    quote_usd_path = quote_usd_root / (
        f"{evidence.evidence_fingerprint_sha256}.json"
    )
    if quote_usd_path.is_symlink():
        raise ValueError(
            "BUY authority quote/USD source record path must not be a symlink"
        )
    if not quote_usd_path.exists():
        return 0
    if not quote_usd_path.is_file():
        raise ValueError(
            "BUY authority quote/USD source record path must identify a regular file"
        )

    feature = evidence.feature_record
    policy = decision_bootstrap.policy
    candidate_id = _resolve_candidate_id(
        manifest.observer_database_path,
        mint=feature.mint,
        quote_mint=feature.quote_mint,
        provider=manifest.quote_provider,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        decision_observed_at_unix_ms=(
            feature.decision_observed_at_unix_ms
        ),
        evaluated_at_unix_ms=evidence.evaluated_at_unix_ms,
        max_quote_age_ms=policy.max_quote_age_ms,
    )
    quote_read_policy = FastPaperShadowQuoteReadPolicy(
        version=policy.route_evidence_version,
        candidate_id=candidate_id,
        probe_policy_version=policy.probe_policy_version,
        taker=policy.taker,
        slippage_bps=policy.slippage_bps,
        entry_input_amount_raw=policy.entry_input_amount_raw,
        exit_input_amount_raw=policy.exit_input_amount_raw,
        max_quote_age_ms=policy.max_quote_age_ms,
        reduction_reads=(),
    )

    record = (
        produce_fast_paper_shadow_buy_authority_from_persisted_evidence(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.execution_policy,
            execution_bootstrap.checkpoint,
            execution_bootstrap.runtime_state,
            evidence,
            feature,
            quote_read_policy,
            market_read_policy,
            regime_read_policy,
            regime_policy,
            safety_policy,
            safety_probe_identity,
            execution_economics_policy,
            quote_usd_source_directory=quote_usd_root,
            operator_risk_control_path=operator_risk_control_path,
            entry_authority_binary_path=entry_authority_binary_path,
            day_started_at_unix_ms=day_started_at_unix_ms,
            data_healthy=data_healthy,
            execution_healthy=execution_healthy,
            global_risk_halt=global_risk_halt,
        )
    )
    if record is None:
        return 0

    try:
        write_fast_paper_shadow_buy_authority_source_record(
            record,
            authority_root,
        )
    except FileExistsError:
        restored = read_fast_paper_shadow_buy_authority_source_record(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.execution_policy,
            execution_bootstrap.checkpoint,
            execution_bootstrap.runtime_state,
            evidence,
            authority_root,
        )
        if restored != record:
            raise ValueError(
                "BUY authority writer collision read-back mismatch"
            )
        return 0
    return 1


def _require_directory(
    value: str | Path,
    *,
    label: str,
) -> Path:
    root = Path(value).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return root.resolve(strict=True)


def _oldest_unexecuted_decision(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    directory: Path,
) -> FastPaperShadowDecisionEvidence | None:
    last_processed = (
        0
        if bootstrap.runtime_state.last_processed_source_sequence is None
        else bootstrap.runtime_state.last_processed_source_sequence
    )
    pending: list[tuple[int, str, FastPaperShadowDecisionEvidence]] = []
    for path in sorted(directory.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_manifest_binding(manifest, evidence)
        _require_processed_identity_compatible(bootstrap, evidence)
        if evidence.source_sequence > last_processed:
            pending.append(
                (
                    evidence.source_sequence,
                    path.name,
                    evidence,
                )
            )

    if not pending:
        return None
    pending.sort(key=lambda value: (value[0], value[1]))
    if len(pending) > 1 and pending[0][0] == pending[1][0]:
        raise ValueError(
            "BUY authority writer has ambiguous oldest decision source sequence"
        )
    return pending[0][2]


def _require_bootstrap_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
) -> None:
    if (
        bootstrap.binding.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer ledger binding does not match runtime manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer execution policy does not match runtime manifest"
        )
    if (
        bootstrap.runtime_state.binding_fingerprint_sha256
        != bootstrap.binding.binding_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer runtime state does not match ledger binding"
        )


def _require_decision_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "BUY authority writer decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer decision champion fingerprint mismatch"
        )
    if evidence.action_policy_version != manifest.action_policy.version:
        raise ValueError(
            "BUY authority writer decision action policy version mismatch"
        )


def _require_processed_identity_compatible(
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    state = bootstrap.runtime_state
    if state.last_processed_source_sequence != evidence.source_sequence:
        return
    if state.last_processed_source_event_id != evidence.source_event_id:
        raise ValueError(
            "BUY authority writer decision conflicts with durable processed event identity"
        )
    if (
        state.last_processed_decision_evidence_fingerprint_sha256
        != evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "BUY authority writer decision conflicts with durable processed fingerprint"
        )
