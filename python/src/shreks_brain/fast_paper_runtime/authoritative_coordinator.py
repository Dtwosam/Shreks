from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.research.fast_training_features import FastTrainingFeatureRecord

from .authoritative_runner import (
    run_fast_paper_authoritative_pending_buy_retry,
)
from .authoritative_service_execution import (
    FastPaperAuthoritativeServiceExecutionBootstrap,
    FastPaperAuthoritativeServiceExecutionConfig,
    bootstrap_fast_paper_authoritative_service_execution,
    consume_fast_paper_authoritative_execution_source_record,
    fast_paper_authoritative_decision_position,
    run_fast_paper_authoritative_service_execution,
)
from .persisted_quotes import FastPaperShadowReductionRead
from .shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import FastPaperShadowExecutionInput
from .shadow_executor import FastPaperShadowPendingBuyRetryInput
from .shadow_service import (
    FastPaperShadowServiceBootstrap,
    FastPaperShadowServiceConfig,
    run_fast_paper_shadow_service_cycle,
)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeExecutionAuthority:
    source: FastPaperShadowExecutionInput
    source_observed_at_unix_ms: int
    risk_day_started_at_unix_ms: int | None

    def __post_init__(self) -> None:
        if type(self.source) is not FastPaperShadowExecutionInput:
            raise ValueError(
                "source must be exact FastPaperShadowExecutionInput"
            )
        _require_non_negative_int(
            "source_observed_at_unix_ms",
            self.source_observed_at_unix_ms,
        )
        if self.risk_day_started_at_unix_ms is not None:
            _require_non_negative_int(
                "risk_day_started_at_unix_ms",
                self.risk_day_started_at_unix_ms,
            )


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeCoordinatorResult:
    decision_bootstrap: FastPaperShadowServiceBootstrap
    execution_bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap
    decisions_produced: int
    executions_committed: int

    def __post_init__(self) -> None:
        if type(self.decision_bootstrap) is not FastPaperShadowServiceBootstrap:
            raise ValueError(
                "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
            )
        if (
            type(self.execution_bootstrap)
            is not FastPaperAuthoritativeServiceExecutionBootstrap
        ):
            raise ValueError(
                "execution_bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
            )
        for name in ("decisions_produced", "executions_committed"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value not in {0, 1}
            ):
                raise ValueError(f"{name} must be 0 or 1")
        if self.decisions_produced and self.executions_committed:
            raise ValueError(
                "authoritative coordinator cannot produce and execute a decision together"
            )


def run_fast_paper_authoritative_coordinated_cycle(
    decision_bootstrap: FastPaperShadowServiceBootstrap,
    decision_config: FastPaperShadowServiceConfig,
    execution_config: FastPaperAuthoritativeServiceExecutionConfig,
    *,
    clock_unix_ms: Callable[[], int] | None = None,
    reduction_read_resolver: (
        Callable[
            [FastTrainingFeatureRecord, FastCampaignDecisionPosition],
            tuple[FastPaperShadowReductionRead, ...],
        ]
        | None
    ) = None,
    exit_input_amount_resolver: (
        Callable[
            [FastTrainingFeatureRecord, FastCampaignDecisionPosition],
            int,
        ]
        | None
    ) = None,
    execution_authority_resolver: (
        Callable[
            [
                FastPaperShadowDecisionEvidence,
                FastPaperAuthoritativeServiceExecutionBootstrap,
            ],
            FastPaperAuthoritativeExecutionAuthority | None,
        ]
        | None
    ) = None,
    pending_buy_retry_resolver: (
        Callable[
            [
                FastPaperAuthoritativeServiceExecutionBootstrap,
                FastPaperShadowDecisionEvidence,
            ],
            FastPaperShadowPendingBuyRetryInput | None,
        ]
        | None
    ) = None,
    committed_at_unix_ms: int,
) -> FastPaperAuthoritativeCoordinatorResult:
    if type(decision_bootstrap) is not FastPaperShadowServiceBootstrap:
        raise ValueError(
            "decision_bootstrap must be exact FastPaperShadowServiceBootstrap"
        )
    if type(decision_config) is not FastPaperShadowServiceConfig:
        raise ValueError(
            "decision_config must be exact FastPaperShadowServiceConfig"
        )
    if (
        type(execution_config)
        is not FastPaperAuthoritativeServiceExecutionConfig
    ):
        raise ValueError(
            "execution_config must be exact FastPaperAuthoritativeServiceExecutionConfig"
        )
    _require_non_negative_int(
        "committed_at_unix_ms",
        committed_at_unix_ms,
    )

    manifest = decision_bootstrap.manifest
    execution_bootstrap = (
        bootstrap_fast_paper_authoritative_service_execution(
            manifest,
            execution_config,
        )
    )
    decision_sequence = _decision_sequence(decision_bootstrap)
    execution_sequence = _execution_sequence_for_cycle(
        manifest,
        execution_bootstrap,
        decision_sequence,
        decision_config.evidence_directory,
    )
    _require_cursor_relationship(
        decision_sequence,
        execution_sequence,
    )

    if decision_sequence == execution_sequence + 1:
        evidence = _oldest_unexecuted_decision(
            manifest,
            execution_bootstrap,
            decision_config.evidence_directory,
            last_processed_sequence=execution_sequence,
        )
        if evidence is None:
            return FastPaperAuthoritativeCoordinatorResult(
                decision_bootstrap=decision_bootstrap,
                execution_bootstrap=execution_bootstrap,
                decisions_produced=0,
                executions_committed=0,
            )

        source_path = execution_bootstrap.source_directory / (
            f"{evidence.evidence_fingerprint_sha256}.json"
        )
        previous_checkpoint_sequence = execution_bootstrap.checkpoint.sequence
        if source_path.is_symlink():
            raise ValueError(
                "authoritative execution source path must not be a symlink"
            )
        if source_path.exists():
            if not source_path.is_file():
                raise ValueError(
                    "authoritative execution source path must identify a regular file"
                )
            result = (
                consume_fast_paper_authoritative_execution_source_record(
                    manifest,
                    execution_bootstrap,
                    evidence,
                    committed_at_unix_ms=committed_at_unix_ms,
                )
            )
        else:
            authority = _resolve_execution_authority(
                evidence,
                execution_bootstrap,
                execution_authority_resolver,
            )
            if authority is None:
                return FastPaperAuthoritativeCoordinatorResult(
                    decision_bootstrap=decision_bootstrap,
                    execution_bootstrap=execution_bootstrap,
                    decisions_produced=0,
                    executions_committed=0,
                )
            if authority.source.decision_evidence != evidence:
                raise ValueError(
                    "authoritative execution authority decision evidence mismatch"
                )
            result = run_fast_paper_authoritative_service_execution(
                manifest,
                execution_bootstrap,
                authority.source,
                source_observed_at_unix_ms=(
                    authority.source_observed_at_unix_ms
                ),
                risk_day_started_at_unix_ms=(
                    authority.risk_day_started_at_unix_ms
                ),
                committed_at_unix_ms=committed_at_unix_ms,
            )

        if not result.committed or result.replayed:
            raise ValueError(
                "authoritative coordinated execution must commit exactly once"
            )
        refreshed = (
            bootstrap_fast_paper_authoritative_service_execution(
                manifest,
                execution_config,
            )
        )
        if (
            refreshed.checkpoint.sequence
            != previous_checkpoint_sequence + 1
        ):
            raise ValueError(
                "authoritative execution checkpoint did not advance exactly once"
            )
        if _execution_sequence(refreshed) != decision_sequence:
            raise ValueError(
                "authoritative execution cursor did not catch up to decision cursor"
            )
        return FastPaperAuthoritativeCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=refreshed,
            decisions_produced=0,
            executions_committed=1,
        )

    state = execution_bootstrap.runtime_state
    if execution_bootstrap.checkpoint.state.pending_buy is not None:
        evidence = _processed_decision_evidence(
            manifest,
            execution_bootstrap,
            decision_config.evidence_directory,
        )
        if pending_buy_retry_resolver is None:
            raise ValueError(
                "authoritative coordinator pending BUY requires explicit retry authority"
            )
        retry = pending_buy_retry_resolver(
            execution_bootstrap,
            evidence,
        )
        if retry is None:
            return FastPaperAuthoritativeCoordinatorResult(
                decision_bootstrap=decision_bootstrap,
                execution_bootstrap=execution_bootstrap,
                decisions_produced=0,
                executions_committed=0,
            )

        previous_checkpoint_sequence = execution_bootstrap.checkpoint.sequence
        result = run_fast_paper_authoritative_pending_buy_retry(
            manifest,
            execution_bootstrap.binding,
            execution_bootstrap.execution_policy,
            retry,
            evidence,
            committed_at_unix_ms=committed_at_unix_ms,
        )
        if not result.committed or result.replayed:
            raise ValueError(
                "authoritative pending BUY retry must commit exactly once"
            )
        refreshed = (
            bootstrap_fast_paper_authoritative_service_execution(
                manifest,
                execution_config,
            )
        )
        if (
            refreshed.checkpoint.sequence
            != previous_checkpoint_sequence + 1
        ):
            raise ValueError(
                "authoritative pending BUY retry checkpoint did not advance exactly once"
            )
        if _execution_sequence(refreshed) != execution_sequence:
            raise ValueError(
                "authoritative pending BUY retry changed learned execution cursor"
            )
        return FastPaperAuthoritativeCoordinatorResult(
            decision_bootstrap=decision_bootstrap,
            execution_bootstrap=refreshed,
            decisions_produced=0,
            executions_committed=1,
        )

    if state.market_positions and reduction_read_resolver is None:
        raise ValueError(
            "authoritative coordinator OPEN posture requires explicit reduction quote authority"
        )

    bounded_config = replace(
        decision_config,
        maximum_decisions=1,
    )

    def position_resolver(
        record: FastTrainingFeatureRecord,
    ) -> FastCampaignDecisionPosition:
        market_key = (
            f"{record.venue}:{record.mint}:{record.quote_mint}"
        )
        return fast_paper_authoritative_decision_position(
            state,
            market_key,
        )

    cycle_kwargs = {
        "clock_unix_ms": clock_unix_ms,
        "position_resolver": position_resolver,
    }
    if reduction_read_resolver is not None:
        cycle_kwargs["reduction_read_resolver"] = (
            reduction_read_resolver
        )
    if exit_input_amount_resolver is not None:
        cycle_kwargs["exit_input_amount_resolver"] = (
            exit_input_amount_resolver
        )

    updated, produced = run_fast_paper_shadow_service_cycle(
        decision_bootstrap,
        bounded_config,
        **cycle_kwargs,
    )
    if type(produced) is not int or produced not in {0, 1}:
        raise ValueError(
            "bounded authoritative decision cycle must report zero or one produced decision"
        )

    updated_sequence = _decision_sequence(updated)
    if produced == 0:
        if updated_sequence != decision_sequence:
            raise ValueError(
                "authoritative decision cursor advanced without a produced decision"
            )
    elif updated_sequence != decision_sequence + 1:
        raise ValueError(
            "authoritative decision cursor did not advance exactly once"
        )

    return FastPaperAuthoritativeCoordinatorResult(
        decision_bootstrap=updated,
        execution_bootstrap=execution_bootstrap,
        decisions_produced=produced,
        executions_committed=0,
    )


def _resolve_execution_authority(
    evidence: FastPaperShadowDecisionEvidence,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    resolver,
) -> FastPaperAuthoritativeExecutionAuthority | None:
    if evidence.decision.action == "SKIP":
        return FastPaperAuthoritativeExecutionAuthority(
            source=FastPaperShadowExecutionInput(
                decision_evidence=evidence,
                entry_authority=None,
                risk_context=None,
                market_regime=None,
                quote_usd_evidence=None,
            ),
            source_observed_at_unix_ms=(
                evidence.evaluated_at_unix_ms
            ),
            risk_day_started_at_unix_ms=None,
        )
    if resolver is None:
        raise ValueError(
            f"authoritative {evidence.decision.action} execution requires explicit source authority"
        )
    authority = resolver(evidence, bootstrap)
    if authority is not None and (
        type(authority)
        is not FastPaperAuthoritativeExecutionAuthority
    ):
        raise ValueError(
            "execution authority resolver must return exact FastPaperAuthoritativeExecutionAuthority or None"
        )
    return authority


def _oldest_unexecuted_decision(
    manifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    directory: Path,
    *,
    last_processed_sequence: int,
) -> FastPaperShadowDecisionEvidence | None:
    root = _require_directory(
        directory,
        "authoritative decision evidence",
    )
    last_processed = last_processed_sequence
    pending: list[
        tuple[int, str, FastPaperShadowDecisionEvidence]
    ] = []
    for path in sorted(root.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_manifest_binding(manifest, evidence)
        _require_processed_identity_compatible(
            bootstrap,
            evidence,
        )
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
            "authoritative coordinator has ambiguous oldest decision source sequence"
        )
    evidence = pending[0][2]
    if evidence.source_sequence != last_processed + 1:
        raise ValueError(
            "authoritative coordinator pending decision sequence is not contiguous"
        )
    return evidence


def _processed_decision_evidence(
    manifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    directory: Path,
) -> FastPaperShadowDecisionEvidence:
    state = bootstrap.runtime_state
    sequence = state.last_processed_source_sequence
    event_id = state.last_processed_source_event_id
    fingerprint = (
        state.last_processed_decision_evidence_fingerprint_sha256
    )
    if sequence is None or event_id is None or fingerprint is None:
        raise ValueError(
            "authoritative pending BUY requires durable learned decision identity"
        )
    root = _require_directory(
        directory,
        "authoritative decision evidence",
    )
    matches: list[FastPaperShadowDecisionEvidence] = []
    for path in sorted(root.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_manifest_binding(manifest, evidence)
        if evidence.evidence_fingerprint_sha256 == fingerprint:
            matches.append(evidence)
    if len(matches) != 1:
        raise ValueError(
            "authoritative pending BUY requires exactly one matching original decision evidence record"
        )
    evidence = matches[0]
    if (
        evidence.source_sequence != sequence
        or evidence.source_event_id != event_id
    ):
        raise ValueError(
            "authoritative pending BUY original decision identity mismatch"
        )
    return evidence


def _decision_sequence(
    bootstrap: FastPaperShadowServiceBootstrap,
) -> int:
    cursor = bootstrap.state.cursor
    if cursor is None:
        return 0
    value = cursor.decision_sequence
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            "authoritative decision cursor sequence must be positive"
        )
    return value



def _execution_sequence_for_cycle(
    manifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_sequence: int,
    directory: Path,
) -> int:
    value = bootstrap.runtime_state.last_processed_source_sequence
    if value is not None:
        return _execution_sequence(bootstrap)

    if bootstrap.checkpoint.sequence != 0:
        raise ValueError(
            "authoritative non-initial checkpoint is missing learned execution identity"
        )
    root = _require_directory(
        directory,
        "authoritative decision evidence",
    )
    pending: list[FastPaperShadowDecisionEvidence] = []
    for path in sorted(root.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_manifest_binding(manifest, evidence)
        pending.append(evidence)

    if not pending:
        return decision_sequence
    if len(pending) != 1:
        raise ValueError(
            "pristine authoritative runtime may retain at most one unexecuted decision"
        )
    evidence = pending[0]
    if (
        decision_sequence <= 0
        or evidence.source_sequence != decision_sequence
    ):
        raise ValueError(
            "pristine authoritative pending decision does not match decision cursor"
        )
    return decision_sequence - 1


def _execution_sequence(
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
) -> int:
    value = bootstrap.runtime_state.last_processed_source_sequence
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            "authoritative execution cursor sequence must be positive"
        )
    return value


def _require_cursor_relationship(
    decision_sequence: int,
    execution_sequence: int,
) -> None:
    if execution_sequence > decision_sequence:
        raise ValueError(
            "authoritative execution cursor cannot be ahead of decision cursor"
        )
    if decision_sequence - execution_sequence > 1:
        raise ValueError(
            "authoritative decision/execution cursor gap exceeds one"
        )


def _require_decision_manifest_binding(
    manifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "authoritative decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative decision champion fingerprint mismatch"
        )
    if evidence.action_policy_version != manifest.action_policy.version:
        raise ValueError(
            "authoritative decision action policy version mismatch"
        )


def _require_processed_identity_compatible(
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    state = bootstrap.runtime_state
    if state.last_processed_source_sequence != evidence.source_sequence:
        return
    if state.last_processed_source_event_id != evidence.source_event_id:
        raise ValueError(
            "authoritative decision conflicts with durable processed event identity"
        )
    if (
        state.last_processed_decision_evidence_fingerprint_sha256
        != evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative decision conflicts with durable processed fingerprint"
        )


def _require_directory(value: Path, label: str) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"{label} directory must be Path")
    if value.is_symlink() or not value.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return value.resolve(strict=True)


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
