from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.paper import derive_paper_risk_accounting_facts
from shreks_brain.paper_validation import FastPaperCheckpointRecord

from .authoritative_handoff import (
    FastPaperAuthoritativeBinding,
    load_fast_paper_authoritative_binding,
    load_latest_fast_paper_authoritative_checkpoint,
)
from .authoritative_runner import (
    FastPaperAuthoritativeRunnerResult,
    run_fast_paper_authoritative_execution,
)
from .authoritative_runtime_state import (
    FastPaperAuthoritativeRuntimeState,
    load_latest_fast_paper_authoritative_runtime_state,
)
from .models import FastPaperRuntimeManifest
from .shadow import FastPaperShadowDecisionEvidence
from .shadow_execution_input import (
    FastPaperShadowExecutionInput,
    FastPaperShadowExecutionPolicy,
    read_fast_paper_shadow_execution_policy,
)
from .shadow_execution_source import (
    FastPaperShadowExecutionInputSourceRecord,
    build_fast_paper_shadow_execution_input_source_record,
    read_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_execution_input_source_record,
)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeServiceExecutionConfig:
    execution_policy_path: Path
    source_directory: Path
    database_path: Path
    run_id: str

    def __post_init__(self) -> None:
        for name in (
            "execution_policy_path",
            "source_directory",
            "database_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise ValueError(f"{name} must be Path")
            if not value.is_absolute():
                raise ValueError(f"{name} must be absolute")
        _require_text("run_id", self.run_id)


@dataclass(frozen=True, slots=True)
class FastPaperAuthoritativeServiceExecutionBootstrap:
    binding: FastPaperAuthoritativeBinding
    execution_policy: FastPaperShadowExecutionPolicy
    checkpoint: FastPaperCheckpointRecord
    runtime_state: FastPaperAuthoritativeRuntimeState
    source_directory: Path

    def __post_init__(self) -> None:
        if type(self.binding) is not FastPaperAuthoritativeBinding:
            raise ValueError(
                "binding must be exact FastPaperAuthoritativeBinding"
            )
        if type(self.execution_policy) is not FastPaperShadowExecutionPolicy:
            raise ValueError(
                "execution_policy must be exact FastPaperShadowExecutionPolicy"
            )
        if type(self.checkpoint) is not FastPaperCheckpointRecord:
            raise ValueError(
                "checkpoint must be exact FastPaperCheckpointRecord"
            )
        if (
            type(self.runtime_state)
            is not FastPaperAuthoritativeRuntimeState
        ):
            raise ValueError(
                "runtime_state must be exact FastPaperAuthoritativeRuntimeState"
            )
        if not isinstance(self.source_directory, Path):
            raise ValueError("source_directory must be Path")
        if (
            self.runtime_state.paper_checkpoint_sequence
            != self.checkpoint.sequence
            or self.runtime_state.paper_checkpoint_payload_sha256
            != self.checkpoint.payload_sha256
        ):
            raise ValueError(
                "authoritative execution bootstrap checkpoint/runtime pair is torn"
            )
        if (
            self.runtime_state.execution_policy_fingerprint_sha256
            != self.execution_policy.policy_fingerprint_sha256
            or self.binding.execution_policy_fingerprint_sha256
            != self.execution_policy.policy_fingerprint_sha256
        ):
            raise ValueError(
                "authoritative execution bootstrap policy fingerprint mismatch"
            )


def load_fast_paper_authoritative_service_execution_config(
    environment: dict[str, str] | None = None,
) -> FastPaperAuthoritativeServiceExecutionConfig:
    env = dict(os.environ if environment is None else environment)

    def required_path(name: str) -> Path:
        value = env.get(name)
        if value is None or not value.strip():
            raise ValueError(
                f"missing required authoritative execution setting {name}"
            )
        return Path(value).expanduser().resolve(strict=False)

    run_id_name = "SHREKS_FAST_PAPER_AUTHORITATIVE_RUN_ID"
    run_id = env.get(run_id_name)
    if run_id is None or not run_id.strip():
        raise ValueError(
            f"missing required authoritative execution setting {run_id_name}"
        )

    return FastPaperAuthoritativeServiceExecutionConfig(
        execution_policy_path=required_path(
            "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_POLICY_PATH"
        ),
        source_directory=required_path(
            "SHREKS_FAST_PAPER_AUTHORITATIVE_EXECUTION_SOURCE_DIRECTORY"
        ),
        database_path=required_path(
            "SHREKS_FAST_PAPER_AUTHORITATIVE_DATABASE_PATH"
        ),
        run_id=run_id,
    )


def bootstrap_fast_paper_authoritative_service_execution(
    manifest: FastPaperRuntimeManifest,
    config: FastPaperAuthoritativeServiceExecutionConfig,
) -> FastPaperAuthoritativeServiceExecutionBootstrap:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(config) is not FastPaperAuthoritativeServiceExecutionConfig:
        raise ValueError(
            "config must be exact FastPaperAuthoritativeServiceExecutionConfig"
        )

    source_directory = _require_directory(
        config.source_directory,
        "authoritative execution source",
    )
    policy_path = config.execution_policy_path
    if policy_path.is_symlink() or not policy_path.is_file():
        raise ValueError(
            "authoritative execution policy must be an existing regular non-symlink file"
        )
    policy_path = policy_path.resolve(strict=True)
    if _is_within(policy_path, source_directory):
        raise ValueError(
            "authoritative execution policy must stay outside execution source directory"
        )

    database = config.database_path
    if database.is_symlink() or not database.is_file():
        raise ValueError(
            "authoritative database must be an existing regular non-symlink file"
        )
    database = database.resolve(strict=True)

    execution_policy = read_fast_paper_shadow_execution_policy(
        manifest,
        policy_path,
    )
    binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=config.run_id,
        database_path=database,
    )
    checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        binding,
    )
    runtime_state = load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
    )
    return FastPaperAuthoritativeServiceExecutionBootstrap(
        binding=binding,
        execution_policy=execution_policy,
        checkpoint=checkpoint,
        runtime_state=runtime_state,
        source_directory=source_directory,
    )


def fast_paper_authoritative_decision_position(
    state: FastPaperAuthoritativeRuntimeState,
    market_key: str,
) -> FastCampaignDecisionPosition:
    if type(state) is not FastPaperAuthoritativeRuntimeState:
        raise ValueError(
            "state must be exact FastPaperAuthoritativeRuntimeState"
        )
    _require_text("market_key", market_key)
    position = next(
        (
            value
            for value in state.market_positions
            if value.market_key == market_key
        ),
        None,
    )
    if position is None:
        return FastCampaignDecisionPosition(kind="FLAT")
    return FastCampaignDecisionPosition(
        kind="OPEN",
        current_exposure_fraction=(
            position.current_exposure_fraction
        ),
    )


def produce_fast_paper_authoritative_execution_input_source_record(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    paper_checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
    source: FastPaperShadowExecutionInput,
    *,
    source_observed_at_unix_ms: int,
    risk_day_started_at_unix_ms: int | None,
) -> FastPaperShadowExecutionInputSourceRecord:
    _require_exact_pair(
        manifest,
        binding,
        execution_policy,
        paper_checkpoint,
        runtime_state,
    )
    if type(source) is not FastPaperShadowExecutionInput:
        raise ValueError(
            "source must be exact FastPaperShadowExecutionInput"
        )
    _require_non_negative_int(
        "source_observed_at_unix_ms",
        source_observed_at_unix_ms,
    )

    evidence = source.decision_evidence
    current_position = fast_paper_authoritative_decision_position(
        runtime_state,
        evidence.market_key,
    )
    if evidence.position != current_position:
        raise ValueError(
            "authoritative execution source decision posture does not match durable position state"
        )
    if evidence.as_of_unix_ms < paper_checkpoint.state.as_of_unix_ms:
        raise ValueError(
            "authoritative execution source decision predates durable PAPER state"
        )
    if source_observed_at_unix_ms > evidence.evaluated_at_unix_ms:
        raise ValueError(
            "authoritative execution source observation cannot be later than evaluation"
        )

    if evidence.decision.action == "BUY":
        if risk_day_started_at_unix_ms is None:
            raise ValueError(
                "BUY authoritative execution source requires a risk day start"
            )
        _require_non_negative_int(
            "risk_day_started_at_unix_ms",
            risk_day_started_at_unix_ms,
        )
        if risk_day_started_at_unix_ms > evidence.evaluated_at_unix_ms:
            raise ValueError(
                "BUY risk day start cannot be later than evaluation"
            )
        if paper_checkpoint.state.pending_buy is not None:
            raise ValueError(
                "BUY authoritative execution source requires no unresolved pending BUY"
            )
        risk = source.risk_context
        _require_buy_risk_context_matches_checkpoint(
            paper_checkpoint,
            risk,
            day_started_at_unix_ms=risk_day_started_at_unix_ms,
        )
    elif risk_day_started_at_unix_ms is not None:
        raise ValueError(
            "non-BUY authoritative execution source cannot carry a risk day start"
        )

    # Reuse the sealed execution-source envelope. The legacy-named
    # shadow_runtime_state_fingerprint field carries the exact authoritative
    # runtime-state fingerprint in this production PAPER path.
    return build_fast_paper_shadow_execution_input_source_record(
        manifest,
        execution_policy,
        source,
        paper_checkpoint_sequence=paper_checkpoint.sequence,
        paper_checkpoint_payload_sha256=paper_checkpoint.payload_sha256,
        shadow_runtime_state_fingerprint_sha256=(
            runtime_state.state_fingerprint_sha256
        ),
        source_observed_at_unix_ms=source_observed_at_unix_ms,
    )


def run_fast_paper_authoritative_service_execution(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    source: FastPaperShadowExecutionInput,
    *,
    source_observed_at_unix_ms: int,
    risk_day_started_at_unix_ms: int | None,
    committed_at_unix_ms: int,
) -> FastPaperAuthoritativeRunnerResult:
    if type(bootstrap) is not FastPaperAuthoritativeServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    record = produce_fast_paper_authoritative_execution_input_source_record(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        bootstrap.checkpoint,
        bootstrap.runtime_state,
        source,
        source_observed_at_unix_ms=source_observed_at_unix_ms,
        risk_day_started_at_unix_ms=risk_day_started_at_unix_ms,
    )
    try:
        write_fast_paper_shadow_execution_input_source_record(
            record,
            bootstrap.source_directory,
        )
    except FileExistsError:
        pass

    restored = read_fast_paper_shadow_execution_input_source_record(
        manifest,
        bootstrap.execution_policy,
        source.decision_evidence,
        bootstrap.source_directory,
        paper_checkpoint_sequence=bootstrap.checkpoint.sequence,
        paper_checkpoint_payload_sha256=(
            bootstrap.checkpoint.payload_sha256
        ),
        shadow_runtime_state_fingerprint_sha256=(
            bootstrap.runtime_state.state_fingerprint_sha256
        ),
    )
    if restored != record:
        raise ValueError(
            "authoritative execution source read-back mismatch"
        )
    return run_fast_paper_authoritative_execution(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        restored.execution_input,
        committed_at_unix_ms=committed_at_unix_ms,
    )


def consume_fast_paper_authoritative_execution_source_record(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperAuthoritativeServiceExecutionBootstrap,
    decision_evidence: FastPaperShadowDecisionEvidence,
    *,
    committed_at_unix_ms: int,
) -> FastPaperAuthoritativeRunnerResult:
    if type(bootstrap) is not FastPaperAuthoritativeServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperAuthoritativeServiceExecutionBootstrap"
        )
    if type(decision_evidence) is not FastPaperShadowDecisionEvidence:
        raise ValueError(
            "decision_evidence must be exact FastPaperShadowDecisionEvidence"
        )
    restored = read_fast_paper_shadow_execution_input_source_record(
        manifest,
        bootstrap.execution_policy,
        decision_evidence,
        bootstrap.source_directory,
        paper_checkpoint_sequence=bootstrap.checkpoint.sequence,
        paper_checkpoint_payload_sha256=(
            bootstrap.checkpoint.payload_sha256
        ),
        shadow_runtime_state_fingerprint_sha256=(
            bootstrap.runtime_state.state_fingerprint_sha256
        ),
    )
    return run_fast_paper_authoritative_execution(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        restored.execution_input,
        committed_at_unix_ms=committed_at_unix_ms,
    )


def _require_exact_pair(
    manifest: FastPaperRuntimeManifest,
    binding: FastPaperAuthoritativeBinding,
    execution_policy: FastPaperShadowExecutionPolicy,
    checkpoint: FastPaperCheckpointRecord,
    runtime_state: FastPaperAuthoritativeRuntimeState,
) -> None:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(binding) is not FastPaperAuthoritativeBinding:
        raise ValueError(
            "binding must be exact FastPaperAuthoritativeBinding"
        )
    if type(execution_policy) is not FastPaperShadowExecutionPolicy:
        raise ValueError(
            "execution_policy must be exact FastPaperShadowExecutionPolicy"
        )
    if type(checkpoint) is not FastPaperCheckpointRecord:
        raise ValueError(
            "checkpoint must be exact FastPaperCheckpointRecord"
        )
    if (
        type(runtime_state)
        is not FastPaperAuthoritativeRuntimeState
    ):
        raise ValueError(
            "runtime_state must be exact FastPaperAuthoritativeRuntimeState"
        )

    latest_binding = load_fast_paper_authoritative_binding(
        manifest,
        fast_run_id=binding.fast_run_id,
        database_path=binding.database_path,
    )
    latest_checkpoint = load_latest_fast_paper_authoritative_checkpoint(
        manifest,
        binding,
    )
    latest_runtime = load_latest_fast_paper_authoritative_runtime_state(
        manifest,
        binding,
    )
    if latest_binding != binding:
        raise ValueError(
            "authoritative execution source binding changed"
        )
    if latest_checkpoint != checkpoint:
        raise ValueError(
            "authoritative execution source requires exact latest checkpoint"
        )
    if latest_runtime != runtime_state:
        raise ValueError(
            "authoritative execution source requires exact latest runtime state"
        )
    if (
        runtime_state.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
        or binding.execution_policy_fingerprint_sha256
        != execution_policy.policy_fingerprint_sha256
    ):
        raise ValueError(
            "authoritative execution source policy fingerprint drift"
        )
    if (
        runtime_state.paper_checkpoint_sequence != checkpoint.sequence
        or runtime_state.paper_checkpoint_payload_sha256
        != checkpoint.payload_sha256
    ):
        raise ValueError(
            "authoritative execution source checkpoint/runtime pair is torn"
        )


def _require_buy_risk_context_matches_checkpoint(
    paper_checkpoint: FastPaperCheckpointRecord,
    risk: object,
    *,
    day_started_at_unix_ms: int,
) -> None:
    from shreks_brain.risk import RiskContext

    if type(risk) is not RiskContext:
        raise ValueError(
            "BUY authoritative execution source requires exact RiskContext"
        )
    ledger = paper_checkpoint.state.ledger
    if risk.trading_capital_usd != ledger.starting_cash_usd:
        raise ValueError(
            "BUY risk trading capital must equal authoritative ledger starting cash"
        )
    if risk.active_intent_keys:
        raise ValueError(
            "BUY authoritative execution source cannot claim external active intents"
        )
    accounting = derive_paper_risk_accounting_facts(
        ledger,
        day_started_at_unix_ms=day_started_at_unix_ms,
    )
    expected = (
        accounting.open_position_count,
        accounting.aggregate_open_risk_usd,
        accounting.daily_realized_pnl_usd,
        accounting.rolling_drawdown_pct,
        accounting.consecutive_losses,
        accounting.last_loss_at_unix_ms,
    )
    actual = (
        risk.open_position_count,
        risk.aggregate_open_risk_usd,
        risk.daily_realized_pnl_usd,
        risk.rolling_drawdown_pct,
        risk.consecutive_losses,
        risk.last_loss_at_unix_ms,
    )
    if actual != expected:
        raise ValueError(
            "BUY risk accounting does not match authoritative ledger"
        )


def _require_directory(value: Path, label: str) -> Path:
    if not isinstance(value, Path):
        raise ValueError(f"{label} directory must be Path")
    if value.is_symlink() or not value.is_dir():
        raise ValueError(
            f"{label} directory must be an existing regular non-symlink directory"
        )
    return value.resolve(strict=True)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{name} must be a non-negative integer"
        )
