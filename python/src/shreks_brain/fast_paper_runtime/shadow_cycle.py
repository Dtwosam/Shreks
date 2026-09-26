from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.research.fast_training_features import (
    FastTrainingFeatureRecord,
    feature_logical_fingerprint_sha256,
)

from .codec import (
    build_fast_paper_runtime_state,
    read_fast_paper_runtime_state,
    verify_fast_paper_runtime_bindings,
    write_fast_paper_runtime_state,
)
from .models import (
    FastPaperRuntimeCursor,
    FastPaperRuntimeManifest,
    FastPaperRuntimeState,
)
from .shadow import (
    FastPaperShadowDecisionEvidence,
    FastPaperShadowQuoteEvidence,
    FastPaperShadowReductionQuote,
    evaluate_fast_paper_shadow_decision,
    read_fast_paper_shadow_decision_evidence,
    write_fast_paper_shadow_decision_evidence,
)


@dataclass(frozen=True, slots=True)
class FastPaperShadowCycleInput:
    record: FastTrainingFeatureRecord
    position: FastCampaignDecisionPosition
    evaluated_at_unix_ms: int
    max_exposure_fraction: float
    entry_quote: FastPaperShadowQuoteEvidence
    exit_quote: FastPaperShadowQuoteEvidence
    reduction_quotes: tuple[FastPaperShadowReductionQuote, ...] = ()
    force_sell: bool = False

    def __post_init__(self) -> None:
        if type(self.record) is not FastTrainingFeatureRecord:
            raise ValueError(
                "record must be exact FastTrainingFeatureRecord"
            )
        if type(self.position) is not FastCampaignDecisionPosition:
            raise ValueError(
                "position must be exact FastCampaignDecisionPosition"
            )
        if (
            isinstance(self.evaluated_at_unix_ms, bool)
            or not isinstance(self.evaluated_at_unix_ms, int)
            or self.evaluated_at_unix_ms < 0
        ):
            raise ValueError(
                "evaluated_at_unix_ms must be a non-negative integer"
            )
        if self.evaluated_at_unix_ms < self.record.decision_observed_at_unix_ms:
            raise ValueError(
                "shadow cycle evaluation cannot precede the decision"
            )
        if (
            isinstance(self.max_exposure_fraction, bool)
            or not isinstance(self.max_exposure_fraction, (int, float))
            or not math.isfinite(float(self.max_exposure_fraction))
            or not 0.0 <= float(self.max_exposure_fraction) <= 1.0
        ):
            raise ValueError(
                "max_exposure_fraction must be finite within [0,1]"
            )
        if type(self.entry_quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "entry_quote must be exact FastPaperShadowQuoteEvidence"
            )
        if type(self.exit_quote) is not FastPaperShadowQuoteEvidence:
            raise ValueError(
                "exit_quote must be exact FastPaperShadowQuoteEvidence"
            )
        if (
            not isinstance(self.reduction_quotes, tuple)
            or not all(
                type(value) is FastPaperShadowReductionQuote
                for value in self.reduction_quotes
            )
        ):
            raise ValueError(
                "reduction_quotes must contain exact FastPaperShadowReductionQuote values"
            )
        if type(self.force_sell) is not bool:
            raise ValueError("force_sell must be bool")


def run_fast_paper_shadow_batch(
    manifest: FastPaperRuntimeManifest,
    state: FastPaperRuntimeState,
    inputs: tuple[FastPaperShadowCycleInput, ...],
    *,
    evidence_directory: str | Path,
) -> FastPaperRuntimeState:
    if type(manifest) is not FastPaperRuntimeManifest:
        raise ValueError(
            "manifest must be exact FastPaperRuntimeManifest"
        )
    if type(state) is not FastPaperRuntimeState:
        raise ValueError(
            "state must be exact FastPaperRuntimeState"
        )
    if (
        not isinstance(inputs, tuple)
        or not inputs
        or not all(
            type(value) is FastPaperShadowCycleInput
            for value in inputs
        )
    ):
        raise ValueError(
            "inputs must be a non-empty tuple of exact FastPaperShadowCycleInput values"
        )

    verify_fast_paper_runtime_bindings(manifest)
    expected_state = build_fast_paper_runtime_state(
        manifest,
        cursor=state.cursor,
    )
    if state != expected_state:
        raise ValueError(
            "shadow batch state does not authenticate against manifest"
        )

    evidence_root = _prepare_evidence_directory(
        manifest,
        evidence_directory,
    )
    _require_checkpoint_matches_expected(
        manifest,
        state,
    )
    _validate_input_population(state, inputs)

    current = state
    for item in inputs:
        destination = evidence_root / _evidence_filename(item.record)
        if destination.exists() or destination.is_symlink():
            evidence = read_fast_paper_shadow_decision_evidence(
                destination
            )
            _require_replay_compatible(
                manifest,
                item,
                evidence,
            )
        else:
            evidence = evaluate_fast_paper_shadow_decision(
                manifest,
                item.record,
                item.position,
                evaluated_at_unix_ms=item.evaluated_at_unix_ms,
                max_exposure_fraction=item.max_exposure_fraction,
                entry_quote=item.entry_quote,
                exit_quote=item.exit_quote,
                reduction_quotes=item.reduction_quotes,
                force_sell=item.force_sell,
            )
            _require_replay_compatible(
                manifest,
                item,
                evidence,
            )
            write_fast_paper_shadow_decision_evidence(
                evidence,
                destination,
            )

        next_state = build_fast_paper_runtime_state(
            manifest,
            cursor=_cursor_for_record(item.record),
        )
        _require_checkpoint_matches_expected(
            manifest,
            current,
        )
        write_fast_paper_runtime_state(
            next_state,
            manifest.checkpoint_path,
        )
        current = next_state

    return current


def _validate_input_population(
    state: FastPaperRuntimeState,
    inputs: tuple[FastPaperShadowCycleInput, ...],
) -> None:
    previous_sequence = (
        0
        if state.cursor is None
        else state.cursor.decision_sequence
    )
    identities: set[tuple[str, int]] = set()
    for item in inputs:
        record = item.record
        if record.decision_sequence <= previous_sequence:
            raise ValueError(
                "shadow batch decision sequences must strictly advance"
            )
        identity = (
            record.decision_signature,
            record.decision_ordinal,
        )
        if identity in identities:
            raise ValueError(
                "shadow batch contains duplicate source identity"
            )
        identities.add(identity)
        previous_sequence = record.decision_sequence


def _prepare_evidence_directory(
    manifest: FastPaperRuntimeManifest,
    value: str | Path,
) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(
            "shadow evidence directory must be a string or Path"
        )
    if isinstance(value, str) and not value.strip():
        raise ValueError(
            "shadow evidence directory must be explicit and non-empty"
        )
    root = Path(value).expanduser()
    if root.is_symlink():
        raise ValueError(
            "shadow evidence directory must not be a symlink"
        )
    if root.exists() and not root.is_dir():
        raise ValueError(
            "shadow evidence directory must identify a directory"
        )

    resolved = root.resolve(strict=False)
    authoritative = Path(
        manifest.paper_evidence_path
    ).expanduser().resolve(strict=False)
    if resolved == authoritative:
        raise ValueError(
            "shadow evidence directory must differ from authoritative paper evidence path"
        )

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(
            "shadow evidence directory must remain a regular directory"
        )
    os.chmod(root, 0o700)
    _fsync_directory(root.parent)
    return root


def _require_checkpoint_matches_expected(
    manifest: FastPaperRuntimeManifest,
    expected: FastPaperRuntimeState,
) -> None:
    checkpoint = Path(manifest.checkpoint_path).expanduser()
    if checkpoint.is_symlink():
        raise ValueError(
            "shadow checkpoint must not be a symlink"
        )
    if not checkpoint.exists():
        if expected.cursor is not None:
            raise ValueError(
                "shadow checkpoint is absent for non-initial supplied state"
            )
        return
    if not checkpoint.is_file():
        raise ValueError(
            "shadow checkpoint must be a regular file"
        )
    durable = read_fast_paper_runtime_state(checkpoint)
    if durable != expected:
        raise ValueError(
            "shadow checkpoint does not match expected runtime state"
        )


def _require_replay_compatible(
    manifest: FastPaperRuntimeManifest,
    item: FastPaperShadowCycleInput,
    evidence: FastPaperShadowDecisionEvidence,
) -> None:
    record = item.record
    expected_source_event_id = (
        f"{record.decision_signature}:{record.decision_ordinal}"
    )
    expected_market_key = (
        f"{record.venue}:{record.mint}:{record.quote_mint}"
    )
    expected_feature_fingerprint = (
        feature_logical_fingerprint_sha256((record,))
    )

    if evidence.release_source_sha != manifest.release_source_sha:
        raise ValueError(
            "shadow replay release SHA mismatch"
        )
    if (
        evidence.manifest_fingerprint_sha256
        != manifest.manifest_fingerprint_sha256
    ):
        raise ValueError(
            "shadow replay manifest fingerprint mismatch"
        )
    if (
        evidence.champion_fingerprint_sha256
        != manifest.champion_fingerprint_sha256
    ):
        raise ValueError(
            "shadow replay champion fingerprint mismatch"
        )
    if evidence.action_policy_version != manifest.action_policy.version:
        raise ValueError(
            "shadow replay action-policy version mismatch"
        )
    if (
        evidence.feature_record_fingerprint_sha256
        != expected_feature_fingerprint
    ):
        raise ValueError(
            "shadow replay feature fingerprint mismatch"
        )
    if (
        evidence.source_event_id != expected_source_event_id
        or evidence.market_key != expected_market_key
        or evidence.source_sequence != record.decision_sequence
        or evidence.as_of_unix_ms
        != record.decision_observed_at_unix_ms
    ):
        raise ValueError(
            "shadow replay source identity mismatch"
        )
    if evidence.evaluated_at_unix_ms != item.evaluated_at_unix_ms:
        raise ValueError(
            "shadow replay evaluation timestamp mismatch"
        )
    if evidence.position != item.position:
        raise ValueError(
            "shadow replay position mismatch"
        )
    if evidence.entry_quote != item.entry_quote:
        raise ValueError(
            "shadow replay ENTRY quote mismatch"
        )
    if evidence.exit_quote != item.exit_quote:
        raise ValueError(
            "shadow replay EXIT quote mismatch"
        )
    if evidence.reduction_quotes != item.reduction_quotes:
        raise ValueError(
            "shadow replay reduction quote mismatch"
        )
    if (
        evidence.constraints.max_exposure_fraction
        != item.max_exposure_fraction
    ):
        raise ValueError(
            "shadow replay maximum exposure mismatch"
        )
    if evidence.constraints.force_sell != item.force_sell:
        raise ValueError(
            "shadow replay force-sell mismatch"
        )

    quotes = (
        item.entry_quote,
        item.exit_quote,
        *(value.quote for value in item.reduction_quotes),
    )
    if record.quote_mint != manifest.quote_mint:
        raise ValueError(
            "shadow replay feature quote mint does not match manifest"
        )
    if any(
        quote.provider != manifest.quote_provider
        for quote in quotes
    ):
        raise ValueError(
            "shadow replay quote provider does not match manifest"
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cursor_for_record(
    record: FastTrainingFeatureRecord,
) -> FastPaperRuntimeCursor:
    return FastPaperRuntimeCursor(
        decision_sequence=record.decision_sequence,
        decision_signature=record.decision_signature,
        decision_ordinal=record.decision_ordinal,
        decision_observed_at_unix_ms=(
            record.decision_observed_at_unix_ms
        ),
    )


def _evidence_filename(
    record: FastTrainingFeatureRecord,
) -> str:
    identity = {
        "decision_ordinal": record.decision_ordinal,
        "decision_signature": record.decision_signature,
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return (
        f"shadow-{record.decision_sequence:020d}-"
        f"{digest}.json"
    )
