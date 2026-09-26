from __future__ import annotations

from pathlib import Path

from .models import FastPaperRuntimeManifest
from .shadow import (
    FastPaperShadowDecisionEvidence,
    read_fast_paper_shadow_decision_evidence,
)
from .shadow_execution_input import FastPaperShadowExecutionInput
from .shadow_execution_producer import (
    produce_fast_paper_shadow_execution_input_source_record,
)
from .shadow_execution_source import (
    read_fast_paper_shadow_execution_input_source_record,
    write_fast_paper_shadow_execution_input_source_record,
)
from .shadow_quote_usd_source import (
    read_fast_paper_shadow_quote_usd_source_record,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
)


_OPEN_ACTIONS = frozenset({"HOLD", "REDUCE", "SELL"})


def run_fast_paper_shadow_open_source_publisher_cycle(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    *,
    decision_evidence_directory: str | Path,
    quote_usd_source_directory: str | Path,
) -> int:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(bootstrap) is not FastPaperShadowServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperShadowServiceExecutionBootstrap"
        )
    _require_bootstrap_manifest_binding(manifest, bootstrap)

    decision_root = _require_directory(
        decision_evidence_directory,
        label="OPEN source publisher decision evidence",
    )
    quote_usd_root = _require_directory(
        quote_usd_source_directory,
        label="OPEN source publisher quote/USD source",
    )

    decision_evidence = _oldest_unexecuted_decision(
        manifest,
        bootstrap,
        decision_root,
    )
    if decision_evidence is None:
        return 0

    action = decision_evidence.decision.action
    if action not in _OPEN_ACTIONS:
        return 0
    if decision_evidence.position.kind != "OPEN":
        raise ValueError(
            f"{action} OPEN source publisher requires OPEN learned posture"
        )

    execution_source_path = bootstrap.source_directory / (
        f"{decision_evidence.evidence_fingerprint_sha256}.json"
    )
    if execution_source_path.is_symlink():
        raise ValueError(
            "OPEN execution source record path must not be a symlink"
        )
    if execution_source_path.exists():
        if not execution_source_path.is_file():
            raise ValueError(
                "OPEN execution source record path must identify a regular file"
            )
        return 0

    quote_usd_path = quote_usd_root / (
        f"{decision_evidence.evidence_fingerprint_sha256}.json"
    )
    if quote_usd_path.is_symlink():
        raise ValueError(
            "OPEN quote/USD source record path must not be a symlink"
        )
    if not quote_usd_path.exists():
        return 0
    if not quote_usd_path.is_file():
        raise ValueError(
            "OPEN quote/USD source record path must identify a regular file"
        )

    quote_usd_record = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        decision_evidence,
        quote_usd_root,
    )
    source = FastPaperShadowExecutionInput(
        decision_evidence=decision_evidence,
        entry_authority=None,
        risk_context=None,
        market_regime=None,
        quote_usd_evidence=quote_usd_record.quote_usd_evidence,
    )
    record = produce_fast_paper_shadow_execution_input_source_record(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        bootstrap.checkpoint,
        bootstrap.runtime_state,
        source,
        source_observed_at_unix_ms=(
            decision_evidence.evaluated_at_unix_ms
        ),
        risk_day_started_at_unix_ms=None,
    )
    try:
        write_fast_paper_shadow_execution_input_source_record(
            record,
            bootstrap.source_directory,
        )
    except FileExistsError:
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
        if restored != record:
            raise ValueError(
                "OPEN execution source write collision read-back mismatch"
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
            "OPEN source publisher has ambiguous oldest decision source sequence"
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
            "OPEN source publisher ledger binding does not match runtime manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN source publisher policy does not match runtime manifest"
        )


def _require_decision_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "OPEN source decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN source decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN source decision champion fingerprint mismatch"
        )
    if evidence.action_policy_version != manifest.action_policy.version:
        raise ValueError(
            "OPEN source decision action policy version mismatch"
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
            "OPEN source decision conflicts with durable processed event identity"
        )
    if (
        state.last_processed_decision_evidence_fingerprint_sha256
        != evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "OPEN source decision conflicts with durable processed fingerprint"
        )
