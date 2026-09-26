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
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
)


def run_fast_paper_shadow_skip_source_publisher_cycle(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    *,
    decision_evidence_directory: str | Path,
) -> int:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(bootstrap) is not FastPaperShadowServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperShadowServiceExecutionBootstrap"
        )
    _require_bootstrap_manifest_binding(manifest, bootstrap)

    decision_root = Path(decision_evidence_directory).expanduser()
    if decision_root.is_symlink() or not decision_root.is_dir():
        raise ValueError(
            "SKIP source publisher decision evidence directory must be an existing regular non-symlink directory"
        )
    decision_root = decision_root.resolve(strict=True)

    decision_evidence = _oldest_unexecuted_decision(
        manifest,
        bootstrap,
        decision_root,
    )
    if decision_evidence is None:
        return 0

    if decision_evidence.decision.action != "SKIP":
        return 0

    source_path = bootstrap.source_directory / (
        f"{decision_evidence.evidence_fingerprint_sha256}.json"
    )
    if source_path.is_symlink():
        raise ValueError(
            "SKIP execution source record path must not be a symlink"
        )
    if source_path.exists():
        if not source_path.is_file():
            raise ValueError(
                "SKIP execution source record path must identify a regular file"
            )
        return 0

    source = FastPaperShadowExecutionInput(
        decision_evidence=decision_evidence,
        entry_authority=None,
        risk_context=None,
        market_regime=None,
        quote_usd_evidence=None,
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
            paper_checkpoint_payload_sha256=bootstrap.checkpoint.payload_sha256,
            shadow_runtime_state_fingerprint_sha256=(
                bootstrap.runtime_state.state_fingerprint_sha256
            ),
        )
        if restored != record:
            raise ValueError(
                "SKIP execution source write collision read-back mismatch"
            )
        return 0
    return 1


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
            "SKIP source publisher has ambiguous oldest decision source sequence"
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
            "SKIP source publisher ledger binding does not match runtime manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "SKIP source publisher policy does not match runtime manifest"
        )


def _require_decision_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "SKIP source decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "SKIP source decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "SKIP source decision champion fingerprint mismatch"
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
            "SKIP source decision conflicts with durable processed event identity"
        )
    if (
        state.last_processed_decision_evidence_fingerprint_sha256
        != evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "SKIP source decision conflicts with durable processed fingerprint"
        )
