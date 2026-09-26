from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from shreks_brain.fast_campaign import FastCampaignDecisionPosition
from shreks_brain.fast_paper_runtime import (
    FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_NAME,
    FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_VERSION,
    FastPaperShadowQuoteUsdEvidence,
    FastPaperShadowQuoteUsdSourceRecord,
    build_fast_paper_shadow_quote_usd_source_record,
    read_fast_paper_shadow_quote_usd_source_record,
    write_fast_paper_shadow_quote_usd_source_record,
)

from test_fast_paper_shadow_decision import _manifest, _record
from test_fast_paper_shadow_executor import _evidence_for, _runtime_fixture


def _fixture(monkeypatch, tmp_path: Path):
    manifest, _binding, _policy, _checkpoint, _runtime = _runtime_fixture(tmp_path)
    feature = _record()
    evidence = _evidence_for(
        monkeypatch,
        manifest,
        feature,
        action="HOLD",
        position=FastCampaignDecisionPosition(
            kind="OPEN",
            current_exposure_fraction=0.5,
        ),
        evaluated_at=20_020,
        entry_observed_at=20_010,
        exit_observed_at=20_015,
    )
    usd = FastPaperShadowQuoteUsdEvidence(
        quote_mint=feature.quote_mint,
        observed_at_unix_ms=20_018,
        quote_to_usd_rate=150.0,
        source_version="quote-usd-explicit-v1",
        source_fingerprint_sha256="d" * 64,
    )
    return manifest, evidence, usd


def test_quote_usd_source_binds_exact_decision_and_round_trips(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, evidence, usd = _fixture(monkeypatch, tmp_path)

    record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        usd,
    )
    assert type(record) is FastPaperShadowQuoteUsdSourceRecord
    assert record.schema_name == FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_NAME
    assert record.schema_version == FAST_PAPER_SHADOW_QUOTE_USD_SOURCE_SCHEMA_VERSION
    assert record.manifest_fingerprint_sha256 == manifest.manifest_fingerprint_sha256
    assert record.decision_evidence_fingerprint_sha256 == evidence.evidence_fingerprint_sha256
    assert record.source_event_id == evidence.source_event_id
    assert record.market_key == evidence.market_key
    assert record.evaluated_at_unix_ms == evidence.evaluated_at_unix_ms
    assert record.quote_mint == evidence.entry_quote.quote_mint
    assert record.quote_usd_evidence == usd
    assert len(record.record_fingerprint_sha256) == 64

    directory = tmp_path / "quote-usd-sources"
    directory.mkdir()
    path = write_fast_paper_shadow_quote_usd_source_record(record, directory)
    restored = read_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        directory,
    )
    assert restored == record
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8").endswith("\n")

    with pytest.raises(FileExistsError):
        write_fast_paper_shadow_quote_usd_source_record(record, directory)


def test_quote_usd_source_rejects_mint_and_future_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, evidence, usd = _fixture(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="mint|quote"):
        build_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            replace(usd, quote_mint="OtherQuote111"),
        )

    with pytest.raises(ValueError, match="future|evaluation|observation"):
        build_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            replace(usd, observed_at_unix_ms=evidence.evaluated_at_unix_ms + 1),
        )


def test_quote_usd_source_rejects_decision_manifest_drift(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _manifest, evidence, usd = _fixture(monkeypatch, tmp_path)
    other_root = tmp_path / "other-runtime"
    other_root.mkdir()
    other_manifest = _manifest(other_root)

    with pytest.raises(ValueError, match="manifest|fingerprint|decision"):
        build_fast_paper_shadow_quote_usd_source_record(
            other_manifest,
            evidence,
            usd,
        )


def test_quote_usd_source_rejects_tamper_unknown_fields_and_symlink(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest, evidence, usd = _fixture(monkeypatch, tmp_path)
    directory = tmp_path / "quote-usd-sources"
    directory.mkdir()
    record = build_fast_paper_shadow_quote_usd_source_record(
        manifest,
        evidence,
        usd,
    )
    path = write_fast_paper_shadow_quote_usd_source_record(record, directory)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["required_score_threshold"] = 99
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown|missing|canonical|fingerprint"):
        read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            directory,
        )

    path.unlink()
    write_fast_paper_shadow_quote_usd_source_record(record, directory)
    real = path.with_suffix(".real")
    path.rename(real)
    path.symlink_to(real.name)
    with pytest.raises(ValueError, match="symlink|regular"):
        read_fast_paper_shadow_quote_usd_source_record(
            manifest,
            evidence,
            directory,
        )


def test_quote_usd_source_has_no_derivation_execution_network_or_live_authority() -> None:
    import shreks_brain.fast_paper_runtime.shadow_quote_usd_source as source

    payload = Path(source.__file__).read_text(encoding="utf-8")
    for required in (
        "FastPaperShadowQuoteUsdEvidence",
        "FastPaperShadowDecisionEvidence",
    ):
        assert required in payload

    for forbidden in (
        "sqlite3",
        "ObserverMarketStore",
        "quote_asset_usd_evidence",
        "requests",
        "httpx",
        "aiohttp",
        "execute_fast_paper_shadow_decision(",
        "produce_fast_paper_shadow_execution_input_source_record",
        "write_fast_paper_shadow_execution_input_source_record",
        "shreks_brain.scoring",
        "score_candidate",
        "sign_transaction",
        "submit_transaction",
        "RuntimeMode.LIVE",
    ):
        assert forbidden not in payload
