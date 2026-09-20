from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from shreks_brain.paper import create_paper_ledger
from shreks_brain.paper_loop import create_paper_loop_state

from .observer_campaign.models import ObserverPaperQuoteAsset
from .observer_campaign.runtime_manifest import (
    OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION,
    OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
    ObserverPaperCampaignRuntimeManifest,
    ObserverPaperCampaignRuntimeManifestError,
    ObserverPaperQuoteUsdValuationMode,
    ObserverPaperQuoteUsdValuationPolicy,
    build_observer_paper_campaign_runtime_manifest_v2,
    decode_observer_paper_campaign_runtime_manifest,
    encode_observer_paper_campaign_runtime_manifest,
)


_MAX_U64 = 2**64 - 1


class G1CV2RuntimeManifestCandidateAuthoringError(ValueError):
    """Raised when an offline G1C v2 new-run candidate cannot be authored safely."""


def author_g1c_v2_runtime_manifest_candidate(
    *,
    source_runtime_manifest_path: str | Path,
    paper_run_id: str,
    start_at_unix_ms: int,
    quote_asset_mint: str,
    quote_asset_decimals: int,
    entry_input_amount: int,
) -> ObserverPaperCampaignRuntimeManifest:
    source_payload = _read_regular_file_stable(
        source_runtime_manifest_path,
        label="source runtime manifest",
    )
    try:
        source = decode_observer_paper_campaign_runtime_manifest(source_payload)
    except ObserverPaperCampaignRuntimeManifestError as error:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"source runtime manifest is not authenticated canonical content: {error}"
        ) from error

    if (
        source.schema_version
        != OBSERVER_PAPER_CAMPAIGN_RUNTIME_MANIFEST_SCHEMA_VERSION
    ):
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "source runtime manifest must be canonical v1 authority"
        )

    _require_non_empty_string("paper_run_id", paper_run_id)
    if paper_run_id == source.paper_run_id:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "paper_run_id must identify a different new run"
        )

    _require_non_negative_int("start_at_unix_ms", start_at_unix_ms)
    if start_at_unix_ms <= source.initial_state.last_cycle_at_unix_ms:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "new-run start_at_unix_ms must be later than source initial state"
        )

    _require_non_empty_string("quote_asset_mint", quote_asset_mint)
    if quote_asset_mint == source.policy_bundle.quote_asset.mint:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "target quote asset must differ from source for this transition"
        )
    _require_decimals("quote_asset_decimals", quote_asset_decimals)
    _require_positive_u64("entry_input_amount", entry_input_amount)

    _require_pristine_source_bootstrap(source)

    source_state = source.initial_state
    new_state = create_paper_loop_state(
        create_paper_ledger(
            source_state.ledger.starting_cash_usd,
            start_at_unix_ms,
        ),
        source_state.loop_policy,
        source_state.paper_fill_policy,
    )

    source_bundle = source.policy_bundle
    new_bundle = replace(
        source_bundle,
        quote_asset=ObserverPaperQuoteAsset(
            mint=quote_asset_mint,
            decimals=quote_asset_decimals,
            usd_per_token=1.0,
        ),
        entry_quote_identity=replace(
            source_bundle.entry_quote_identity,
            input_mint=quote_asset_mint,
            input_amount=entry_input_amount,
        ),
        regime_read_policy=replace(
            source_bundle.regime_read_policy,
            quote_asset_mint=quote_asset_mint,
            entry_input_amount=entry_input_amount,
        ),
        safety_probe_identity=replace(
            source_bundle.safety_probe_identity,
            output_mint=quote_asset_mint,
        ),
    )

    try:
        candidate = build_observer_paper_campaign_runtime_manifest_v2(
            paper_run_id=paper_run_id,
            candidate=source.candidate,
            initial_state=new_state,
            policy_bundle=new_bundle,
            risk_environment=source.risk_environment,
            selection_policy=source.selection_policy,
            recent_performance=source.recent_performance,
            global_risk_halt=source.global_risk_halt,
            quote_usd_valuation_policy=ObserverPaperQuoteUsdValuationPolicy(
                version=OBSERVER_PAPER_QUOTE_USD_VALUATION_POLICY_VERSION,
                mode=ObserverPaperQuoteUsdValuationMode.EXACT_MARKET_RATIO,
            ),
        )
        canonical = encode_observer_paper_campaign_runtime_manifest(candidate)
        decoded = decode_observer_paper_campaign_runtime_manifest(canonical)
    except (ObserverPaperCampaignRuntimeManifestError, TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"candidate runtime manifest invariants rejected transition: {error}"
        ) from error

    if decoded != candidate:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "candidate runtime manifest canonical round-trip changed content"
        )
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shreks-g1c-v2-runtime-manifest-candidate-author",
        description=(
            "Author one canonical, offline G1C runtime-manifest v2 candidate "
            "from authenticated v1 authority and explicit new-run quote inputs."
        ),
    )
    parser.add_argument("--source-runtime-manifest", required=True)
    parser.add_argument("--paper-run-id", required=True)
    parser.add_argument("--start-at-unix-ms", required=True, type=int)
    parser.add_argument("--quote-asset-mint", required=True)
    parser.add_argument("--quote-asset-decimals", required=True, type=int)
    parser.add_argument("--entry-input-amount", required=True, type=int)
    args = parser.parse_args(argv)

    try:
        manifest = author_g1c_v2_runtime_manifest_candidate(
            source_runtime_manifest_path=args.source_runtime_manifest,
            paper_run_id=args.paper_run_id,
            start_at_unix_ms=args.start_at_unix_ms,
            quote_asset_mint=args.quote_asset_mint,
            quote_asset_decimals=args.quote_asset_decimals,
            entry_input_amount=args.entry_input_amount,
        )
        payload = encode_observer_paper_campaign_runtime_manifest(manifest)
    except (G1CV2RuntimeManifestCandidateAuthoringError, TypeError, ValueError) as error:
        print(
            json.dumps(
                {"status": "FAILED", "error": str(error)},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(payload.decode("utf-8"))
    return 0


def _require_pristine_source_bootstrap(
    source: ObserverPaperCampaignRuntimeManifest,
) -> None:
    state = source.initial_state
    ledger = state.ledger
    if state.managed_positions or state.pending_entry is not None:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "source initial state must be a pristine bootstrap state"
        )
    if ledger.positions or ledger.entries or ledger.processed_intent_keys:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "source initial ledger must not carry trading history"
        )
    if (
        ledger.cash_balance_usd != ledger.starting_cash_usd
        or ledger.realized_pnl_usd != 0.0
        or ledger.unrealized_pnl_usd != 0.0
        or ledger.accumulated_costs_usd != 0.0
    ):
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            "source initial ledger accounting must be pristine"
        )


def _read_regular_file_stable(
    raw_path: str | Path,
    *,
    label: str,
) -> bytes:
    try:
        path = Path(raw_path).expanduser()
    except (TypeError, ValueError) as error:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{label} path is invalid"
        ) from error

    if path.is_symlink() or not path.is_file():
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{label} must be an existing regular non-symlink file"
        )
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{label} could not be read"
        ) from error

    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != before.st_size:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{label} changed while being read"
        )
    return payload


def _require_non_empty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{name} must be a non-empty string"
        )


def _require_non_negative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{name} must be a non-negative integer"
        )


def _require_decimals(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 255
    ):
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{name} must be an integer within [0, 255]"
        )


def _require_positive_u64(name: str, value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_U64
    ):
        raise G1CV2RuntimeManifestCandidateAuthoringError(
            f"{name} must be a positive u64 amount"
        )


if __name__ == "__main__":
    raise SystemExit(main())
