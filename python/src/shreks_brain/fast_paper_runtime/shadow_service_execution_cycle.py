from __future__ import annotations

from pathlib import Path

from .models import FastPaperRuntimeManifest
from .shadow import read_fast_paper_shadow_decision_evidence
from .shadow_service_execution import (
    consume_fast_paper_shadow_service_execution_source_record,
)
from .shadow_service_execution_bootstrap import (
    FastPaperShadowServiceExecutionBootstrap,
)


def run_fast_paper_shadow_service_execution_cycle(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    *,
    decision_evidence_directory: str | Path,
    committed_at_unix_ms: int,
) -> int:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError("manifest must be exact FastPaperRuntimeManifest")
    if type(bootstrap) is not FastPaperShadowServiceExecutionBootstrap:
        raise ValueError(
            "bootstrap must be exact FastPaperShadowServiceExecutionBootstrap"
        )
    if (
        isinstance(committed_at_unix_ms, bool)
        or not isinstance(committed_at_unix_ms, int)
        or committed_at_unix_ms < 0
    ):
        raise ValueError(
            "committed_at_unix_ms must be a non-negative integer"
        )
    _require_bootstrap_manifest_binding(manifest, bootstrap)

    decision_root = Path(decision_evidence_directory).expanduser()
    if decision_root.is_symlink() or not decision_root.is_dir():
        raise ValueError(
            "decision evidence directory must be an existing regular non-symlink directory"
        )
    decision_root = decision_root.resolve(strict=True)

    last_processed = (
        0
        if bootstrap.runtime_state.last_processed_source_sequence is None
        else bootstrap.runtime_state.last_processed_source_sequence
    )
    pending = []
    for path in sorted(decision_root.glob("shadow-*.json")):
        evidence = read_fast_paper_shadow_decision_evidence(path)
        _require_decision_manifest_binding(manifest, evidence)
        _require_processed_identity_compatible(
            bootstrap,
            evidence,
        )
        if evidence.source_sequence > last_processed:
            pending.append((evidence.source_sequence, path.name, evidence))

    if not pending:
        return 0

    pending.sort(key=lambda value: (value[0], value[1]))
    if len(pending) > 1 and pending[0][0] == pending[1][0]:
        raise ValueError(
            "execution cycle has ambiguous oldest decision source sequence"
        )
    decision_evidence = pending[0][2]
    source_path = bootstrap.source_directory / (
        f"{decision_evidence.evidence_fingerprint_sha256}.json"
    )
    if source_path.is_symlink():
        raise ValueError(
            "execution source record path must not be a symlink"
        )
    if not source_path.exists():
        return 0
    if not source_path.is_file():
        raise ValueError(
            "execution source record path must identify a regular file"
        )

    consume_fast_paper_shadow_service_execution_source_record(
        manifest,
        bootstrap.binding,
        bootstrap.execution_policy,
        decision_evidence=decision_evidence,
        source_directory=bootstrap.source_directory,
        committed_at_unix_ms=committed_at_unix_ms,
    )
    return 1


def _require_bootstrap_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
) -> None:
    if (
        bootstrap.binding.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "execution bootstrap ledger binding does not match runtime manifest"
        )
    if (
        bootstrap.execution_policy.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "execution bootstrap policy does not match runtime manifest"
        )


def _require_decision_manifest_binding(
    manifest: FastPaperRuntimeManifest,
    evidence,
) -> None:
    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "execution decision release source does not match runtime manifest"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "execution decision manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "execution decision champion fingerprint mismatch"
        )


def _require_processed_identity_compatible(
    bootstrap: FastPaperShadowServiceExecutionBootstrap,
    evidence,
) -> None:
    state = bootstrap.runtime_state
    if state.last_processed_source_sequence != evidence.source_sequence:
        return
    if state.last_processed_source_event_id != evidence.source_event_id:
        raise ValueError(
            "execution decision conflicts with durable processed event identity"
        )
    if (
        state.last_processed_decision_evidence_fingerprint_sha256
        != evidence.evidence_fingerprint_sha256
    ):
        raise ValueError(
            "execution decision conflicts with durable processed fingerprint"
        )
