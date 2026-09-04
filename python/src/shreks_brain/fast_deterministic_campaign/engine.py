from __future__ import annotations

from pathlib import Path

from shreks_brain.evaluation import TradingEvaluationPolicy
from shreks_brain.fast_campaign_paper import (
    FastDeterministicPaperSession,
    apply_fast_deterministic_paper_session_step,
    create_fast_deterministic_paper_session,
    fast_deterministic_paper_session_posture,
)
from shreks_brain.fast_deterministic_lifecycle import (
    FastDeterministicCandidateManifest,
)
from shreks_brain.fast_deterministic_offline import (
    evaluate_fast_deterministic_row_offline,
)
from shreks_brain.fast_paper import FastPaperPositionActionPolicy
from shreks_brain.paper import PaperFillPolicy, PaperLedger
from shreks_brain.risk import RiskPolicy

from .models import FastDeterministicCampaignRow
from .paper_evidence import (
    materialize_fast_deterministic_campaign_paper_evidence,
)


def run_fast_deterministic_chronological_campaign(
    *,
    binary_path: str | Path,
    manifest: FastDeterministicCandidateManifest,
    rows: tuple[FastDeterministicCampaignRow, ...],
    paper_run_id: str,
    assessment_version: str,
    starting_ledger: PaperLedger,
    fill_policy: PaperFillPolicy,
    risk_policy: RiskPolicy,
    position_policy: FastPaperPositionActionPolicy,
    evaluation_policy: TradingEvaluationPolicy,
) -> FastDeterministicPaperSession:
    binary = _preflight_campaign(
        binary_path=binary_path,
        manifest=manifest,
        rows=rows,
    )

    session = create_fast_deterministic_paper_session(
        manifest=manifest,
        paper_run_id=paper_run_id,
        assessment_version=assessment_version,
        starting_ledger=starting_ledger,
        fill_policy=fill_policy,
        risk_policy=risk_policy,
        position_policy=position_policy,
        evaluation_policy=evaluation_policy,
    )

    for row in rows:
        market_key = _market_key(row)
        posture = fast_deterministic_paper_session_posture(
            session,
            market_key,
        )
        strategy_evidence = (
            row.flat_evidence
            if posture.posture == "FLAT"
            else row.open_evidence
        )
        decision = evaluate_fast_deterministic_row_offline(
            binary_path=binary,
            record=row.record,
            manifest=manifest,
            posture=posture,
            evidence=strategy_evidence,
        )
        paper_evidence = materialize_fast_deterministic_campaign_paper_evidence(
            decision,
            row.paper_evidence,
        )
        session = apply_fast_deterministic_paper_session_step(
            session,
            decision,
            paper_evidence,
        )

    if session.latest_result is None:
        raise ValueError(
            "non-empty deterministic campaign must produce a final PAPER result"
        )
    return session


def _preflight_campaign(
    *,
    binary_path: str | Path,
    manifest: FastDeterministicCandidateManifest,
    rows: tuple[FastDeterministicCampaignRow, ...],
) -> Path:
    if type(manifest) is not FastDeterministicCandidateManifest:
        raise ValueError(
            "manifest must be exact FastDeterministicCandidateManifest"
        )
    if isinstance(binary_path, str) and not binary_path.strip():
        raise ValueError("binary_path must be explicit and non-empty")
    if not isinstance(binary_path, (str, Path)):
        raise ValueError("binary_path must be a string or Path")
    binary = Path(binary_path)
    if not binary.is_file():
        raise ValueError("binary_path must identify an existing file")

    if (
        not isinstance(rows, tuple)
        or not rows
        or not all(type(row) is FastDeterministicCampaignRow for row in rows)
    ):
        raise ValueError(
            "rows must be a non-empty tuple of exact FastDeterministicCampaignRow values"
        )

    expected_flat_kind = manifest.lifecycle_policy.entry_baseline_kind
    expected_open_kind = manifest.lifecycle_policy.manager_baseline_kind
    seen_source_ids: set[str] = set()
    previous_sequence: int | None = None
    latest_at_by_market: dict[str, int] = {}

    for row in rows:
        if row.flat_evidence.kind != expected_flat_kind:
            raise ValueError(
                "FLAT evidence family does not match manifest entry family"
            )
        if row.open_evidence.kind != expected_open_kind:
            raise ValueError(
                "OPEN evidence family does not match manifest manager family"
            )

        source_event_id = (
            f"{row.record.decision_signature}:{row.record.decision_ordinal}"
        )
        if row.paper_evidence.source_event_id != source_event_id:
            raise ValueError(
                "PAPER evidence source identity does not match FL8.1 row"
            )
        if source_event_id in seen_source_ids:
            raise ValueError(
                "deterministic campaign contains duplicate source identity"
            )
        seen_source_ids.add(source_event_id)

        sequence = row.record.decision_sequence
        if previous_sequence is not None and sequence <= previous_sequence:
            raise ValueError(
                "deterministic campaign decision sequence must strictly increase"
            )
        previous_sequence = sequence

        market_key = _market_key(row)
        decision_at = row.record.decision_observed_at_unix_ms
        previous_at = latest_at_by_market.get(market_key)
        if previous_at is not None and decision_at < previous_at:
            raise ValueError(
                "deterministic campaign per-market decision time cannot move backward"
            )
        latest_at_by_market[market_key] = decision_at

    return binary


def _market_key(row: FastDeterministicCampaignRow) -> str:
    record = row.record
    return f"{record.venue}:{record.mint}:{record.quote_mint}"
